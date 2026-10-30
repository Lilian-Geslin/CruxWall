"""Profil : page du profil, réglages du compte, suppression du compte, export JSON des données."""

from flask import Blueprint
from datetime import datetime
from datetime import timezone
import json

from flask import Response
from flask import abort
from flask import redirect
from flask import render_template
from flask import request
from flask import session
from werkzeug.security import check_password_hash
from werkzeug.security import generate_password_hash

from ..auth import login_required
from ..constants import ACCOUNT_FAIL_MAX, ACCOUNT_FAIL_WINDOW, EMAIL_RE, PASSWORD_MAX, PASSWORD_MIN, PSEUDO_CHANGE_MAX, PSEUDO_RE, SETTINGS_OK_MESSAGES, TOO_MANY_MSG
from ..db import get_db
from ..errors import notice_page
from ..services.deletion import account_deletion_plan, delete_user_account
from ..services.ratelimit import rl_count, rl_hit, rl_reset
from ..services.validation import normalize_email


bp = Blueprint("profile", __name__)

@bp.route("/profil")
@login_required
def profil():
    conn = get_db()
    user = conn.execute("SELECT * FROM user WHERE id = ?", (session["user_id"],)).fetchone()

    notifications = conn.execute("""
        SELECT * FROM notification
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT 20
    """, (session["user_id"],)).fetchall()
    conn.execute(
        "UPDATE notification SET read_at = CURRENT_TIMESTAMP WHERE user_id = ? AND read_at IS NULL",
        (session["user_id"],)
    )
    conn.commit()

    created_blocks = conn.execute("""
        SELECT b.*, w.name as wall_name, w.id as wall_id
        FROM block b JOIN wall w ON b.wall_id = w.id
        WHERE b.created_by = ?
        ORDER BY b.created_at DESC
    """, (session["user_id"],)).fetchall()

    created_walls = conn.execute("""
        SELECT w.*, g.name as gym_name,
               COUNT(DISTINCT b.id) as block_count
        FROM wall w
        LEFT JOIN gym g ON w.gym_id = g.id
        LEFT JOIN block b ON b.wall_id = w.id
        WHERE w.created_by = ?
        GROUP BY w.id
        ORDER BY w.created_at DESC
    """, (session["user_id"],)).fetchall()

    ascents = conn.execute("""
        SELECT a.done, a.flash, a.created_at,
               b.id as block_id, b.name as block_name, b.grade, b.color,
               w.id as wall_id, w.name as wall_name
        FROM ascent a
        JOIN block b ON a.block_id = b.id
        JOIN wall w ON b.wall_id = w.id
        WHERE a.user_id = ? AND (a.done = 1 OR a.flash = 1)
        ORDER BY w.name, a.flash DESC, a.created_at DESC
    """, (session["user_id"],)).fetchall()

    ascents_by_wall = {}
    for a in ascents:
        wname = a["wall_name"]
        if wname not in ascents_by_wall:
            ascents_by_wall[wname] = {"wall_id": a["wall_id"], "blocks": []}
        ascents_by_wall[wname]["blocks"].append(dict(a))

    climbed_total, climbed_flash = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(flash), 0) FROM climb_log WHERE user_id = ?", (session["user_id"],)).fetchone()
    conn.close()
    return render_template("pages/profil.html",
        user=user,
        climbed_total=climbed_total,
        climbed_flash=climbed_flash,
        created_blocks=created_blocks,
        created_walls=created_walls,
        ascents_by_wall=ascents_by_wall,
        notifications=notifications
    )

@bp.route("/profil/delete", methods=["GET", "POST"])
@login_required
def delete_account():
    conn = get_db()
    user = conn.execute("SELECT * FROM user WHERE id = ?", (session["user_id"],)).fetchone()
    if not user:
        conn.close()
        session.clear()
        return redirect("/")
    plan = account_deletion_plan(conn, user["id"])
    error = None

    if request.method == "POST":
        bucket = f"delete:user:{user['id']}"
        password = request.form.get("password", "")
        if rl_count(conn, bucket, 15 * 60) >= 5:
            error = TOO_MANY_MSG
        elif not request.form.get("confirm"):
            error = "Cochez la case pour confirmer que vous avez compris."
        elif len(password) > PASSWORD_MAX or not check_password_hash(user["password"], password):
            rl_hit(conn, bucket)
            conn.commit()
            error = "Mot de passe incorrect."
        elif (user["role"] == "admin"
              and conn.execute("SELECT COUNT(*) FROM user WHERE role = 'admin' AND id != ?", (user["id"],)).fetchone()[0] == 0):
            error = "Vous êtes le dernier administrateur : nommez d'abord un autre administrateur (page Admin) avant de supprimer votre compte."
        else:
            summary = delete_user_account(conn, user["id"], delete_public=bool(request.form.get("delete_public")))
            conn.commit()
            conn.close()
            session.clear()
            lines = ["Votre compte et vos données ont été supprimés."]
            if summary["walls_kept"] or summary["gyms_kept"]:
                lines.append(f"Restent en ligne, sans votre nom : {summary['walls_kept']} mur(s) et {summary['gyms_kept']} salle(s) publics.")
            lines.append("Les sauvegardes de sécurité du site disparaissent d'elles-mêmes sous 14 jours au plus.")
            return notice_page("Compte supprimé", lines)

    conn.close()
    return render_template("pages/delete_account.html", error=error, **plan), (429 if error == TOO_MANY_MSG else 200)

@bp.route("/profil/settings", methods=["GET", "POST"])
@login_required
def account_settings():
    conn = get_db()
    user = conn.execute("SELECT * FROM user WHERE id = ?", (session["user_id"],)).fetchone()
    if not user:
        conn.close()
        session.clear()
        return redirect("/")
    error = error_form = None

    if request.method == "POST":
        action = request.form.get("action", "")
        if action not in ("pseudo", "email", "password"):
            conn.close()
            abort(400)
        error_form = action
        bucket = f"account:user:{user['id']}"
        current = request.form.get("current_password", "")
        if rl_count(conn, bucket, ACCOUNT_FAIL_WINDOW) >= ACCOUNT_FAIL_MAX:
            error = TOO_MANY_MSG
        elif len(current) > PASSWORD_MAX or not check_password_hash(user["password"], current):
            rl_hit(conn, bucket)
            conn.commit()
            error = "Mot de passe actuel incorrect."
        elif action == "pseudo":
            new = (request.form.get("new_pseudo") or "").strip()
            if not PSEUDO_RE.match(new):
                error = "Pseudo invalide : 3 à 30 caractères, uniquement lettres (sans accents), chiffres, tiret (-) et underscore (_)."
            elif new == user["name"]:
                error = "C'est déjà votre pseudo."
            elif conn.execute("SELECT 1 FROM user WHERE LOWER(name) = LOWER(?) AND id != ?", (new, user["id"])).fetchone():
                error = "Ce pseudo est déjà pris, choisissez-en un autre."
            elif rl_count(conn, f"pseudo:user:{user['id']}", 24 * 3600) >= PSEUDO_CHANGE_MAX:
                error = f"Vous avez déjà changé de pseudo {PSEUDO_CHANGE_MAX} fois aujourd'hui. Réessayez demain."
            else:
                conn.execute("UPDATE user SET name = ? WHERE id = ?", (new, user["id"]))
                rl_hit(conn, f"pseudo:user:{user['id']}")
                conn.commit()
                session["user_name"] = new
        elif action == "email":
            new = normalize_email(request.form.get("new_email"))
            if len(new) > 254 or not EMAIL_RE.match(new):
                error = "Adresse email invalide."
            elif new == (user["email"] or "").lower():
                error = "C'est déjà votre adresse email."
            elif conn.execute("SELECT 1 FROM user WHERE LOWER(email) = ? AND id != ?", (new, user["id"])).fetchone():
                error = "Cette adresse est déjà utilisée par un autre compte."
            else:
                conn.execute("UPDATE user SET email = ? WHERE id = ?", (new, user["id"]))
                conn.commit()
        else:  # password
            new = request.form.get("new_password") or ""
            if not (PASSWORD_MIN <= len(new) <= PASSWORD_MAX):
                error = f"Le nouveau mot de passe doit contenir entre {PASSWORD_MIN} et {PASSWORD_MAX} caractères."
            elif new != (request.form.get("confirm_password") or ""):
                error = "La confirmation ne correspond pas au nouveau mot de passe."
            elif new == current:
                error = "Le nouveau mot de passe doit être différent de l'ancien."
            else:
                version = (user["session_version"] or 0) + 1
                conn.execute("UPDATE user SET password = ?, session_version = ? WHERE id = ?",
                             (generate_password_hash(new), version, user["id"]))
                rl_reset(conn, bucket)
                conn.commit()
                session["sv"] = version   # cette session reste ouverte, les autres sont déconnectées
        if not error:
            conn.close()
            return redirect(f"/profil/settings?ok={action}")

    conn.close()
    ok = SETTINGS_OK_MESSAGES.get(request.args.get("ok", ""))
    return render_template("pages/account_settings.html", user=user, error=error, error_form=error_form, ok=ok,
                           values=request.form), (429 if error == TOO_MANY_MSG else 200)

@bp.route("/profil/export")
@login_required
def export_data():
    """Télécharge, en JSON lisible, toutes les données conservées sur la personne connectée."""
    uid = session["user_id"]
    conn = get_db()
    bucket = f"export:user:{uid}"
    if rl_count(conn, bucket, 3600) >= 5:
        conn.close()
        return notice_page("Trop de demandes", ["Vous pouvez télécharger vos données 5 fois par heure. Réessayez plus tard."],
                       "/profil", "← Retour au profil", 429)
    rl_hit(conn, bucket)
    conn.commit()

    def rows(sql):
        return [dict(r) for r in conn.execute(sql, (uid,)).fetchall()]

    blocks = rows("""SELECT b.id, b.name, b.grade, b.color, b.description, b.link, b.created_at, w.name AS wall_name
                     FROM block b JOIN wall w ON b.wall_id = w.id WHERE b.created_by = ?""")
    for b in blocks:
        b["holds"] = [dict(h) for h in conn.execute(
            "SELECT x, y, hold_type, w, h FROM hold WHERE block_id = ? ORDER BY id", (b["id"],)).fetchall()]
    data = {
        "exporte_le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "compte": rows("SELECT name AS pseudo, email, role AS role, terms_accepted_at AS conditions_acceptees_le FROM user WHERE id = ?")[0],
        "murs_crees": rows("""SELECT id, name, is_private, access_code, created_at, last_activity_at, image_filename
                              FROM wall WHERE created_by = ?"""),
        "salles_creees": rows("SELECT id, name, location, is_private, access_code FROM gym WHERE created_by = ?"),
        "blocs_crees": blocks,
        "ascensions": rows("""SELECT a.done AS reussi, a.flash, a.created_at, a.done_at AS reussi_le, b.name AS bloc, w.name AS mur
                              FROM ascent a JOIN block b ON a.block_id = b.id JOIN wall w ON b.wall_id = w.id
                              WHERE a.user_id = ?"""),
        "cotations_proposees": rows("""SELECT n.note AS cotation, n.created_at, b.name AS bloc, w.name AS mur
                                       FROM block_note n JOIN block b ON n.block_id = b.id JOIN wall w ON b.wall_id = w.id
                                       WHERE n.user_id = ?"""),
        "notifications": rows("SELECT message, created_at, read_at FROM notification WHERE user_id = ?"),
        "signalements_envoyes": rows("""SELECT target_type AS type, target_name AS nom, reason AS motif, details AS precisions,
                                        status AS statut, created_at FROM report WHERE reporter_id = ?"""),
        "carnet_de_progression": rows("""SELECT block_name AS bloc, wall_name AS mur, grade AS cotation, flash, done_at AS reussi_le
                                         FROM climb_log WHERE user_id = ? ORDER BY done_at"""),
        "blocs_favoris": rows("""SELECT b.name AS bloc, w.name AS mur, f.created_at FROM block_favorite f
                                 JOIN block b ON f.block_id = b.id JOIN wall w ON b.wall_id = w.id WHERE f.user_id = ?"""),
        "murs_favoris": rows("""SELECT w.name, f.created_at FROM wall_favorite f JOIN wall w ON f.wall_id = w.id WHERE f.user_id = ?"""),
        "salles_favorites": rows("""SELECT g.name, f.created_at FROM gym_favorite f JOIN gym g ON f.gym_id = g.id WHERE f.user_id = ?"""),
        "blocs_a_faire": rows("""SELECT b.name AS bloc, w.name AS mur, t.created_at FROM block_todo t
                                 JOIN block b ON t.block_id = b.id JOIN wall w ON b.wall_id = w.id WHERE t.user_id = ?"""),
        "murs_prives_debloques": rows("""SELECT w.name FROM wall_access a JOIN wall w ON a.wall_id = w.id WHERE a.user_id = ?"""),
        "salles_privees_debloquees": rows("""SELECT g.name FROM gym_access a JOIN gym g ON a.gym_id = g.id WHERE a.user_id = ?"""),
    }
    conn.close()
    resp = Response(json.dumps(data, ensure_ascii=False, indent=2), mimetype="application/json")
    resp.headers["Content-Disposition"] = 'attachment; filename="cruxwall-mes-donnees.json"'
    resp.headers["Cache-Control"] = "no-store"
    return resp
