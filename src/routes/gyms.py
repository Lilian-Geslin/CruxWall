"""Salles : liste, page d'une salle (avec recherche et propositions), création, modification, déblocage, suppression."""

from flask import Blueprint
from flask import abort
from flask import jsonify
from flask import redirect
from flask import render_template
from flask import request
from flask import session

from ..auth import login_required
from ..constants import LOCATION_MAX, NAME_MAX, SEARCH_MAX, SUGGEST_BLOCKS_MAX, SUGGEST_WALLS_MAX, TOO_MANY_MSG
from ..db import get_db
from ..services.access import can_view_gym, can_view_wall, codes_match, generate_access_code, normalize_access_code
from ..services.deletion import _delete_wall_cascade
from ..services.quotas import quota_error, quota_register
from ..services.ratelimit import rl_reset, unlock_rate_limited, unlock_register_failure
from ..services.search import gym_search, gym_visible_walls
from ..services.validation import clean_text, safe_referrer


bp = Blueprint("gyms", __name__)

@bp.route("/gym/new", methods=["POST"])
@login_required
def new_gym():
    name = clean_text(request.form.get("name"))
    location = clean_text(request.form.get("location"))
    is_private = 1 if request.form.get("is_private") else 0
    if not name or len(name) > NAME_MAX or len(location) > LOCATION_MAX:
        return redirect(safe_referrer("/gyms"))

    conn = get_db()
    problem = None
    if conn.execute("SELECT id FROM gym WHERE LOWER(name) = LOWER(?)", (name,)).fetchone():
        problem = "Une salle porte déjà ce nom."
    else:
        problem = quota_error(conn, "gym")
    if problem:
        conn.close()
        return render_template("pages/error.html", title="Salle non créée", message=problem), 400

    access_code = generate_access_code() if is_private else None
    conn.execute(
        "INSERT INTO gym(name, location, created_by, is_private, access_code) VALUES(?, ?, ?, ?, ?)",
        (name, location, session["user_id"], is_private, access_code)
    )
    quota_register(conn, "gym")
    conn.commit()
    conn.close()
    return redirect(safe_referrer("/gyms"))

@bp.route("/api/gym/quick_create", methods=["POST"])
@login_required
def quick_create_gym():
    """
    Crée une salle sans quitter la page (utilisé depuis le formulaire de
    création de mur, pour ne pas perdre le nom/la photo déjà saisis si on a
    oublié de créer une salle avant).
    """
    name = clean_text(request.form.get("name"))
    location = clean_text(request.form.get("location"))
    is_private = 1 if request.form.get("is_private") else 0
    if not name:
        return jsonify({"error": "Le nom de la salle est requis."}), 400
    if len(name) > NAME_MAX or len(location) > LOCATION_MAX:
        return jsonify({"error": f"Nom et ville sont limités à {NAME_MAX} caractères."}), 400

    conn = get_db()
    existing = conn.execute("SELECT id FROM gym WHERE LOWER(name) = LOWER(?)", (name,)).fetchone()
    if existing:
        conn.close()
        return jsonify({"error": "Une salle porte déjà ce nom."}), 400
    quota_message = quota_error(conn, "gym")
    if quota_message:
        conn.close()
        return jsonify({"error": quota_message}), 429

    access_code = generate_access_code() if is_private else None
    cursor = conn.execute(
        "INSERT INTO gym(name, location, created_by, is_private, access_code) VALUES(?, ?, ?, ?, ?)",
        (name, location, session["user_id"], is_private, access_code)
    )
    quota_register(conn, "gym")
    conn.commit()
    gym_id = cursor.lastrowid
    conn.close()
    return jsonify({
        "success": True, "id": gym_id, "name": name,
        "location": location, "access_code": access_code
    })

@bp.route("/gyms")
def gyms_list():
    """Toutes les salles. Une salle privée apparaît dans la liste, mais son contenu reste caché."""
    conn = get_db()
    gyms = conn.execute("""
        SELECT g.*, COUNT(w.id) as wall_count
        FROM gym g LEFT JOIN wall w ON w.gym_id = g.id
        GROUP BY g.id
        ORDER BY g.name COLLATE NOCASE
    """).fetchall()
    gyms = [dict(g, can_view=can_view_gym(conn, g)) for g in gyms]
    conn.close()
    return render_template("pages/gyms.html", gyms=gyms)

@bp.route("/gym/<int:gym_id>/suggest")
def gym_suggest(gym_id):
    """Propositions de la barre de recherche d'une salle (JSON, mêmes droits que la page)."""
    q = clean_text(request.args.get("q"))[:SEARCH_MAX]
    conn = get_db()
    gym = conn.execute("SELECT * FROM gym WHERE id = ?", (gym_id,)).fetchone()
    if not gym or not can_view_gym(conn, gym):
        conn.close()
        abort(404)
    if len(q) < 2:
        conn.close()
        return jsonify({"walls": [], "blocks": []})
    walls, blocks = gym_search(conn, gym_visible_walls(conn, gym), q, SUGGEST_BLOCKS_MAX)
    conn.close()
    return jsonify({
        "walls": [{"id": w["id"], "name": w["name"]} for w in walls[:SUGGEST_WALLS_MAX]],
        "blocks": [{"id": b["id"], "name": b["name"], "grade": b["grade"] or "",
                    "wall": b["wall_name"], "creator": b["creator_name"] or ""} for b in blocks],
    })

@bp.route("/gym/<int:gym_id>")
def gym_detail(gym_id):
    conn = get_db()
    gym = conn.execute("""
        SELECT g.*, u.name as creator_name
        FROM gym g LEFT JOIN user u ON g.created_by = u.id
        WHERE g.id = ?
    """, (gym_id,)).fetchone()
    if not gym:
        conn.close()
        abort(404)

    if not can_view_gym(conn, gym):
        conn.close()
        # La salle est visible, mais pas ses murs : on propose le code.
        return render_template("pages/unlock.html",
            kind="salle", name=gym["name"],
            action=f"/gym/{gym_id}/unlock"
        )

    walls = conn.execute("""
        SELECT w.*, COUNT(DISTINCT b.id) as block_count
        FROM wall w LEFT JOIN block b ON b.wall_id = w.id
        WHERE w.gym_id = ?
        GROUP BY w.id
        ORDER BY w.created_at DESC
    """, (gym_id,)).fetchall()
    # Un mur privé (dans une salle publique) reste caché sans accès
    walls = [w for w in walls if can_view_wall(conn, w, gym)]
    is_fav = bool("user_id" in session and conn.execute(
        "SELECT 1 FROM gym_favorite WHERE user_id = ? AND gym_id = ?", (session["user_id"], gym_id)).fetchone())

    # Recherche dans la salle : noms de murs, et blocs (nom, cotation exacte,
    # nom de l'ouvreur). Seuls les murs que la personne a le droit de voir
    # sont parcourus.
    q = clean_text(request.args.get("q"))[:SEARCH_MAX]
    search_blocks = None
    if len(q) >= 2:
        walls, search_blocks = gym_search(conn, walls, q, 100)
    conn.close()
    return render_template("pages/gym.html", gym=gym, walls=walls, is_fav=is_fav,
                           q=q, search_blocks=search_blocks)

@bp.route("/gym/<int:gym_id>/edit", methods=["GET", "POST"])
@login_required
def edit_gym(gym_id):
    """Modifier le nom, la ville et la confidentialité d'une salle (créateur ou admin)."""
    conn = get_db()
    gym = conn.execute("SELECT * FROM gym WHERE id = ?", (gym_id,)).fetchone()
    if not gym:
        conn.close()
        abort(404)
    if gym["created_by"] != session["user_id"] and session.get("user_role") != "admin":
        conn.close()
        abort(403)
    error = None
    if request.method == "POST":
        name = clean_text(request.form.get("name"))
        location = clean_text(request.form.get("location"))
        is_private = 1 if request.form.get("is_private") else 0
        regenerate = bool(request.form.get("regenerate_code"))
        if not name:
            error = "Le nom de la salle est requis."
        elif len(name) > NAME_MAX or len(location) > LOCATION_MAX:
            error = f"Nom et ville sont limités à {NAME_MAX} caractères."
        elif conn.execute("SELECT id FROM gym WHERE LOWER(name) = LOWER(?) AND id != ?", (name, gym_id)).fetchone():
            error = "Une salle porte déjà ce nom."
        else:
            access_code = gym["access_code"]
            if is_private and (not access_code or regenerate):
                access_code = generate_access_code()
            if not is_private:
                access_code = None
            conn.execute(
                "UPDATE gym SET name = ?, location = ?, is_private = ?, access_code = ? WHERE id = ?",
                (name, location, is_private, access_code, gym_id)
            )
            conn.commit()
            conn.close()
            return redirect(f"/gym/{gym_id}")
    conn.close()
    return render_template("pages/edit_gym.html", gym=gym, error=error)

@bp.route("/gym/<int:gym_id>/delete", methods=["POST"])
@login_required
def delete_gym(gym_id):
    """
    Supprime une salle ET tous ses murs (avec leurs blocs, prises, notes,
    ascensions et photos). Action irréversible — la page affiche un message
    de confirmation explicite avant d'envoyer cette requête.
    """
    conn = get_db()
    gym = conn.execute("SELECT * FROM gym WHERE id = ?", (gym_id,)).fetchone()
    if not gym:
        conn.close()
        return redirect("/gyms")
    if gym["created_by"] != session["user_id"] and session.get("user_role") != "admin":
        conn.close()
        abort(403)
    walls = conn.execute("SELECT * FROM wall WHERE gym_id = ?", (gym_id,)).fetchall()
    for w in walls:
        _delete_wall_cascade(conn, w)
    conn.execute("DELETE FROM gym_access WHERE gym_id = ?", (gym_id,))
    conn.execute("DELETE FROM gym WHERE id = ?", (gym_id,))
    conn.commit()
    conn.close()
    return redirect("/gyms")

@bp.route("/gym/<int:gym_id>/unlock", methods=["POST"])
@login_required
def unlock_gym(gym_id):
    """Débloque une salle privée en entrant son code (nombre d'essais limité)."""
    code = normalize_access_code(request.form.get("code"))
    conn = get_db()
    gym = conn.execute("SELECT * FROM gym WHERE id = ?", (gym_id,)).fetchone()
    if not gym:
        conn.close()
        abort(404)
    if unlock_rate_limited(conn):
        conn.close()
        return render_template("pages/unlock.html", kind="salle", name=gym["name"],
                               action=f"/gym/{gym_id}/unlock", error=TOO_MANY_MSG), 429
    if codes_match(gym["access_code"], code):
        conn.execute(
            "INSERT OR IGNORE INTO gym_access(gym_id, user_id) VALUES(?, ?)",
            (gym_id, session["user_id"])
        )
        rl_reset(conn, f"unlock:user:{session['user_id']}")
        conn.commit()
        conn.close()
        return redirect(f"/gym/{gym_id}")
    unlock_register_failure(conn)
    conn.commit()
    conn.close()
    return render_template("pages/unlock.html",
        kind="salle", name=gym["name"],
        action=f"/gym/{gym_id}/unlock",
        error="Code incorrect."
    )
