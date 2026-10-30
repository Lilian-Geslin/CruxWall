"""API de détection des prises d'une photo de mur."""

from flask import Blueprint
import json
import os

from flask import current_app
from flask import jsonify
from flask import request
from flask import session

from ..auth import login_required
from ..db import get_db
from ..services.access import require_wall_access
from ..services.detection import DETECT_DAILY_LIMIT, DETECT_USER_MAX, DETECT_USER_WINDOW, detect_with_local_model, detect_with_roboflow, save_detection
from ..services.ratelimit import rl_count, rl_hit


bp = Blueprint("detection", __name__)

@bp.route("/api/wall/<int:wall_id>/detect_holds", methods=["POST"])
@login_required
def detect_holds(wall_id):
    """
    Détecte les prises sur la photo du mur : Roboflow (en ligne) en priorité,
    repli automatique sur le modèle local si Roboflow échoue pour une raison
    quelconque. Les coordonnées renvoyées sont en pourcentage (0-1) de l'image.

    Le résultat est conservé en base : la photo d'un mur ne change pas, donc
    la deuxième personne (ou le deuxième bloc) qui ouvre ce mur ne consomme
    plus aucun crédit Roboflow. ?force=1 (bouton "Refaire la détection")
    relance une vraie analyse. Les vraies analyses sont limitées par compte
    et pour l'ensemble du site, pour qu'on ne puisse pas vider tes crédits.
    """
    force = request.args.get("force") == "1"
    conn = get_db()
    wall = require_wall_access(conn, wall_id)

    if not force and wall["detected_holds"]:
        try:
            cached = json.loads(wall["detected_holds"])
        except ValueError:
            cached = None
        if cached:
            conn.close()
            return jsonify({"success": True, "holds": cached,
                            "source": wall["detected_source"] or "local", "cached": True})

    user_bucket = f"detect:user:{session['user_id']}"
    if (rl_count(conn, user_bucket, DETECT_USER_WINDOW) >= DETECT_USER_MAX
            or rl_count(conn, "detect:global", 24 * 3600) >= DETECT_DAILY_LIMIT):
        conn.close()
        return jsonify({"error": "detection_limited"}), 429
    rl_hit(conn, user_bucket)
    rl_hit(conn, "detect:global")
    conn.commit()
    conn.close()

    img_path = os.path.join(current_app.config["UPLOAD_FOLDER"], wall["image_filename"])
    if not os.path.exists(img_path):
        return jsonify({"error": "Image introuvable"}), 404

    errors = []

    try:
        holds = detect_with_roboflow(img_path)
        if holds:
            save_detection(wall_id, holds, "roboflow")
        return jsonify({"success": True, "holds": holds, "source": "roboflow"})
    except Exception as e:
        errors.append(f"Roboflow (en ligne) : {e}")

    try:
        holds = detect_with_local_model(img_path)
        if holds:
            save_detection(wall_id, holds, "local")
        return jsonify({"success": True, "holds": holds, "source": "local"})
    except Exception as e:
        errors.append(f"modèle local : {e}")

    # Le détail technique (crédits épuisés, modèle absent, etc.) est utile
    # pour nous mais pas pour la personne qui utilise l'appli : on le
    # garde dans les logs serveur (onglet "Error log" sur PythonAnywhere)
    # et on renvoie un message générique côté client. Un échec n'est jamais
    # mis en cache : le prochain essai refera une vraie analyse.
    current_app.logger.warning("Détection IA indisponible : " + " / ".join(errors))
    return jsonify({"error": "detection_unavailable"}), 500
