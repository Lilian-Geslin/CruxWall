"""Murs : liste, page d'un mur, création, modification, déblocage par code, suppression."""

from flask import Blueprint
import os
import uuid

from flask import abort
from flask import current_app
from flask import redirect
from flask import render_template
from flask import request
from flask import session

from ..auth import login_required
from ..constants import GRADES, MAX_UPLOADS_MB, NAME_MAX, TOO_MANY_MSG
from ..db import get_db
from ..services.access import can_view_gym, can_view_wall, codes_match, forbid_or_hide, generate_access_code, normalize_access_code
from ..services.activity import touch_wall_activity
from ..services.admin_log import log_if_admin_on_foreign
from ..services.deletion import _delete_wall_cascade
from ..services.images import ImageRejected, allowed_file, save_optimized_image
from ..services.quotas import quota_error, quota_register, uploads_size_bytes
from ..services.ratelimit import rl_reset, unlock_rate_limited, unlock_register_failure
from ..services.validation import clean_text, to_int


bp = Blueprint("walls", __name__)

@bp.route("/wall/<int:wall_id>")
def wall(wall_id):
    conn = get_db()
    wall = conn.execute("""
        SELECT w.*, g.name as gym_name, u.name as creator_name
        FROM wall w
        LEFT JOIN gym g ON w.gym_id = g.id
        LEFT JOIN user u ON w.created_by = u.id
        WHERE w.id = ?
    """, (wall_id,)).fetchone()
    if not wall:
        abort(404)

    if not can_view_wall(conn, wall):
        conn.close()
        return render_template("pages/unlock.html",
            kind="mur", name=wall["name"],
            action=f"/wall/{wall_id}/unlock"
        )

    touch_wall_activity(conn, wall_id)
    conn.commit()

    blocks = conn.execute("""
        SELECT b.*, u.name as creator_name
        FROM block b
        LEFT JOIN user u ON b.created_by = u.id
        WHERE b.wall_id = ?
        ORDER BY b.created_at DESC
    """, (wall_id,)).fetchall()
    is_fav = bool("user_id" in session and conn.execute(
        "SELECT 1 FROM wall_favorite WHERE user_id = ? AND wall_id = ?", (session["user_id"], wall_id)).fetchone())
    conn.close()
    return render_template("pages/wall.html", wall=wall, blocks=blocks, grades=GRADES, is_fav=is_fav)

@bp.route("/wall/new", methods=["GET", "POST"])
@login_required
def new_wall():
    conn = get_db()
    gyms = conn.execute("SELECT * FROM gym ORDER BY name").fetchall()
    conn.close()
    error = None
    preselected_gym = request.args.get("gym_id", "")
    if request.method == "POST":
        name = clean_text(request.form.get("name"))
        gym_id = to_int(request.form.get("gym_id"))
        is_private = 1 if request.form.get("is_private") else 0
        file = request.files.get("image")
        preselected_gym = gym_id or ""

        conn = get_db()
        gym = conn.execute("SELECT * FROM gym WHERE id = ?", (gym_id,)).fetchone() if gym_id else None
        if not name:
            error = "Le nom du mur est requis."
        elif len(name) > NAME_MAX:
            error = f"Le nom du mur est limité à {NAME_MAX} caractères."
        elif not gym_id:
            error = "Une salle est requise pour créer un mur."
        elif not gym:
            error = "Cette salle n'existe pas."
        elif not can_view_gym(conn, gym):
            error = "Cette salle est privée : entrez d'abord son code d'accès."
        elif not file or not allowed_file(file.filename):
            error = "Veuillez uploader une image (jpg, png, webp)."
        elif (quota_message := quota_error(conn, "wall")):
            error = quota_message
        elif uploads_size_bytes() > MAX_UPLOADS_MB * 1024 * 1024:
            error = "Le site a atteint sa capacité de stockage de photos : impossible d'ajouter un mur pour le moment."
        else:
            # On enregistre toujours en .jpg recompressé, quel que soit le
            # format d'origine : c'est ce qui économise le plus de place.
            filename = f"{uuid.uuid4().hex}.jpg"
            dest_path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
            try:
                save_optimized_image(file, dest_path)
            except ImageRejected as e:
                error = str(e)
            except Exception:
                error = "Image invalide ou illisible."
            else:
                access_code = generate_access_code() if is_private else None
                cursor = conn.execute(
                    "INSERT INTO wall(name, gym_id, image_filename, created_by, last_activity_at, is_private, access_code) "
                    "VALUES(?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)",
                    (name, gym_id, filename, session["user_id"], is_private, access_code)
                )
                quota_register(conn, "wall")
                conn.commit()
                wall_id = cursor.lastrowid
                conn.close()
                return redirect(f"/wall/{wall_id}")
        conn.close()
    return render_template("pages/new_wall.html", gyms=gyms, error=error, preselected_gym=preselected_gym)

@bp.route("/wall/<int:wall_id>/edit", methods=["GET", "POST"])
@login_required
def edit_wall(wall_id):
    """Modifier le nom d'un mur, la salle à laquelle il appartient, et sa confidentialité."""
    conn = get_db()
    wall = conn.execute("SELECT * FROM wall WHERE id = ?", (wall_id,)).fetchone()
    if not wall:
        conn.close()
        abort(404)
    if wall["created_by"] != session["user_id"] and session.get("user_role") != "admin":
        forbid_or_hide(conn, wall)
    gyms = conn.execute("SELECT * FROM gym ORDER BY name").fetchall()
    error = None
    if request.method == "POST":
        name = clean_text(request.form.get("name"))
        gym_id = to_int(request.form.get("gym_id"))
        is_private = 1 if request.form.get("is_private") else 0
        regenerate = bool(request.form.get("regenerate_code"))
        gym = conn.execute("SELECT * FROM gym WHERE id = ?", (gym_id,)).fetchone() if gym_id else None
        if not name:
            error = "Le nom du mur est requis."
        elif len(name) > NAME_MAX:
            error = f"Le nom du mur est limité à {NAME_MAX} caractères."
        elif not gym_id:
            error = "Une salle est requise."
        elif not gym:
            error = "Cette salle n'existe pas."
        elif not can_view_gym(conn, gym):
            error = "Cette salle est privée : entrez d'abord son code d'accès."
        else:
            access_code = wall["access_code"]
            if is_private and (not access_code or regenerate):
                access_code = generate_access_code()
            if not is_private:
                access_code = None
            conn.execute(
                "UPDATE wall SET name = ?, gym_id = ?, is_private = ?, access_code = ? WHERE id = ?",
                (name, gym_id, is_private, access_code, wall_id)
            )
            conn.execute("UPDATE climb_log SET wall_name = ? WHERE wall_id = ?", (name, wall_id))
            touch_wall_activity(conn, wall_id)
            conn.commit()
            conn.close()
            return redirect(f"/wall/{wall_id}")
    conn.close()
    return render_template("pages/edit_wall.html", wall=wall, gyms=gyms, error=error)

@bp.route("/wall/<int:wall_id>/unlock", methods=["POST"])
@login_required
def unlock_wall(wall_id):
    """Débloque un mur privé en entrant son code (nombre d'essais limité)."""
    code = normalize_access_code(request.form.get("code"))
    conn = get_db()
    wall = conn.execute("SELECT * FROM wall WHERE id = ?", (wall_id,)).fetchone()
    if not wall:
        conn.close()
        abort(404)
    if unlock_rate_limited(conn):
        conn.close()
        return render_template("pages/unlock.html", kind="mur", name=wall["name"],
                               action=f"/wall/{wall_id}/unlock", error=TOO_MANY_MSG), 429
    if codes_match(wall["access_code"], code):
        conn.execute(
            "INSERT OR IGNORE INTO wall_access(wall_id, user_id) VALUES(?, ?)",
            (wall_id, session["user_id"])
        )
        rl_reset(conn, f"unlock:user:{session['user_id']}")
        conn.commit()
        conn.close()
        return redirect(f"/wall/{wall_id}")
    unlock_register_failure(conn)
    conn.commit()
    conn.close()
    return render_template("pages/unlock.html",
        kind="mur", name=wall["name"],
        action=f"/wall/{wall_id}/unlock",
        error="Code incorrect."
    )

@bp.route("/wall/<int:wall_id>/delete", methods=["POST"])
@login_required
def delete_wall(wall_id):
    conn = get_db()
    wall = conn.execute("SELECT * FROM wall WHERE id = ?", (wall_id,)).fetchone()
    if not wall or (wall["created_by"] != session["user_id"] and session.get("user_role") != "admin"):
        forbid_or_hide(conn, wall)
    log_if_admin_on_foreign(conn, wall["created_by"], "Mur supprimé par un admin", f"« {wall['name']} » (#{wall['id']})")
    _delete_wall_cascade(conn, wall)
    conn.commit()
    conn.close()
    return redirect("/")

@bp.route("/walls")
def walls_list():
    """Tous les murs visibles par la personne qui consulte (les murs privés sans accès sont exclus)."""
    conn = get_db()
    rows = conn.execute("""
        SELECT w.*, g.name as gym_name, g.is_private as gym_is_private, g.created_by as gym_created_by,
               COUNT(DISTINCT b.id) as block_count
        FROM wall w
        LEFT JOIN gym g ON w.gym_id = g.id
        LEFT JOIN block b ON b.wall_id = w.id
        GROUP BY w.id
        ORDER BY w.created_at DESC
    """).fetchall()
    visible_walls = []
    for w in rows:
        gym = None
        if w["gym_id"]:
            gym = {"id": w["gym_id"], "is_private": w["gym_is_private"], "created_by": w["gym_created_by"]}
        if can_view_wall(conn, w, gym):
            visible_walls.append(w)
    conn.close()
    return render_template("pages/walls.html", walls=visible_walls)
