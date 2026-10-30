"""Signalement de contenus (murs, salles, blocs) par les utilisateurs."""

from flask import Blueprint
from flask import abort
from flask import request
from flask import session

from ..auth import login_required
from ..constants import REPORT_DETAILS_MAX, REPORT_IP_MAX, REPORT_REASONS, REPORT_USER_MAX, REPORT_WINDOW
from ..db import get_db
from ..errors import notice_page
from ..services.access import require_wall_access
from ..services.ratelimit import client_ip, rl_count, rl_hit
from ..services.validation import clean_text, safe_referrer, to_int


bp = Blueprint("reports", __name__)

@bp.route("/report", methods=["POST"])
@login_required
def report_content():
    target_type = request.form.get("target_type", "")
    target_id = to_int(request.form.get("target_id"))
    reason = request.form.get("reason", "")
    details = clean_text(request.form.get("details"), multiline=True)

    if target_type not in ("wall", "block") or not target_id or reason not in REPORT_REASONS:
        return notice_page("Signalement invalide", ["Le signalement n'a pas pu être enregistré : motif manquant ou invalide."],
                       safe_referrer("/"), "← Retour", 400)
    if len(details) > REPORT_DETAILS_MAX:
        return notice_page("Signalement invalide", [f"Les précisions sont limitées à {REPORT_DETAILS_MAX} caractères."],
                       safe_referrer("/"), "← Retour", 400)
    if reason == "other" and len(details) < 5:
        return notice_page("Signalement invalide", ["Merci de préciser votre signalement (motif « Autre »)."],
                       safe_referrer("/"), "← Retour", 400)

    conn = get_db()
    user_bucket = f"report:user:{session['user_id']}"
    ip_bucket = f"report:ip:{client_ip()}"
    if (rl_count(conn, user_bucket, REPORT_WINDOW) >= REPORT_USER_MAX
            or rl_count(conn, ip_bucket, REPORT_WINDOW) >= REPORT_IP_MAX):
        conn.close()
        return notice_page("Trop de signalements",
                       [f"Vous avez atteint la limite de {REPORT_USER_MAX} signalements par heure. Réessayez un peu plus tard."],
                       safe_referrer("/"), "← Retour", 429)

    if target_type == "wall":
        wall = require_wall_access(conn, target_id)       # 404 / 403 si introuvable ou inaccessible
        target_name, wall_id, back = wall["name"], wall["id"], f"/wall/{wall['id']}"
    else:
        block = conn.execute("SELECT * FROM block WHERE id = ?", (target_id,)).fetchone()
        if not block:
            conn.close()
            abort(404)
        require_wall_access(conn, block["wall_id"])
        target_name, wall_id, back = block["name"], block["wall_id"], f"/block/{block['id']}"

    already = conn.execute(
        "SELECT 1 FROM report WHERE reporter_id = ? AND target_type = ? AND target_id = ? AND status = 'open'",
        (session["user_id"], target_type, target_id)
    ).fetchone()
    if already:
        conn.close()
        return notice_page("Déjà signalé", ["Vous avez déjà signalé ce contenu : il est en attente d'examen."], back, "← Retour")

    conn.execute(
        "INSERT INTO report(reporter_id, target_type, target_id, target_name, wall_id, reason, details) "
        "VALUES(?, ?, ?, ?, ?, ?, ?)",
        (session["user_id"], target_type, target_id, target_name, wall_id, reason, details)
    )
    rl_hit(conn, user_bucket)
    rl_hit(conn, ip_bucket)
    # Prévient chaque administrateur dans l'appli (pas d'email) : notification + pastille sur « Admin »
    label = "mur" if target_type == "wall" else "bloc"
    conn.execute(
        "INSERT INTO notification(user_id, wall_id, message) SELECT id, NULL, ? FROM user WHERE role = 'admin'",
        (f"Nouveau signalement ({REPORT_REASONS[reason]}) : {label} « {target_name} ». À examiner dans la page Admin.",)
    )
    conn.commit()
    conn.close()
    return notice_page("Merci", ["Votre signalement a été transmis. Il sera examiné rapidement."], back, "← Retour")
