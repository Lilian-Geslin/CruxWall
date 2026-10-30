"""Blocs : page d'un bloc, création (éditeur), modification, suppression, données des prises."""

from flask import Blueprint
from flask import abort
from flask import jsonify
from flask import redirect
from flask import render_template
from flask import request
from flask import session

from ..auth import login_required
from ..constants import ALLOWED_COLORS, DEFAULT_BLOCK_COLOR, DESCRIPTION_MAX, GRADES, NAME_MAX
from ..db import get_db
from ..services.access import can_view_wall, forbid_or_hide, require_block_access, require_wall_access
from ..services.activity import touch_wall_activity
from ..services.admin_log import log_if_admin_on_foreign
from ..services.deletion import _delete_block_rows
from ..services.holds import parse_holds
from ..services.quotas import quota_error, quota_register
from ..services.validation import clean_link, clean_text, to_int


bp = Blueprint("blocks", __name__)

@bp.route("/block/<int:block_id>")
def block_detail(block_id):
    conn = get_db()
    block = conn.execute("""
        SELECT b.*, w.name as wall_name, w.image_filename, w.id as wall_id,
               u.name as creator_name
        FROM block b
        JOIN wall w ON b.wall_id = w.id
        LEFT JOIN user u ON b.created_by = u.id
        WHERE b.id = ?
    """, (block_id,)).fetchone()
    if not block:
        abort(404)

    parent_wall = conn.execute("SELECT * FROM wall WHERE id = ?", (block["wall_id"],)).fetchone()
    if not can_view_wall(conn, parent_wall):
        conn.close()
        return render_template("pages/unlock.html",
            kind="mur", name=parent_wall["name"],
            action=f"/wall/{parent_wall['id']}/unlock"
        )

    touch_wall_activity(conn, block["wall_id"])
    conn.commit()

    holds = [dict(h) for h in conn.execute(
        "SELECT * FROM hold WHERE block_id = ? ORDER BY id", (block_id,)).fetchall()
    ]
    is_fav = bool("user_id" in session and conn.execute(
        "SELECT 1 FROM block_favorite WHERE user_id = ? AND block_id = ?", (session["user_id"], block_id)).fetchone())
    in_todo = bool("user_id" in session and conn.execute(
        "SELECT 1 FROM block_todo WHERE user_id = ? AND block_id = ?", (session["user_id"], block_id)).fetchone())
    conn.close()
    return render_template("pages/block.html", block=block, holds=holds, grades=GRADES, in_todo=in_todo, is_fav=is_fav)

@bp.route("/wall/<int:wall_id>/block/new", methods=["GET", "POST"])
@login_required
def new_block(wall_id):
    conn = get_db()
    wall = require_wall_access(conn, wall_id)
    conn.close()
    return render_template("pages/new_block.html", wall=wall, grades=GRADES)

@bp.route("/api/block/save", methods=["POST"])
@login_required
def save_block():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Requête invalide."}), 400
    wall_id = to_int(data.get("wall_id"))
    name = clean_text(data.get("name"))
    grade = data.get("grade") or ""
    color = data.get("color") or DEFAULT_BLOCK_COLOR
    description = clean_text(data.get("description"), multiline=True)
    link, link_error = clean_link(data.get("link"))

    if not name or not wall_id:
        return jsonify({"error": "Nom et mur requis."}), 400
    if len(name) > NAME_MAX:
        return jsonify({"error": f"Le nom est limité à {NAME_MAX} caractères."}), 400
    if grade and grade not in GRADES:
        return jsonify({"error": "Cotation invalide."}), 400
    if color not in ALLOWED_COLORS:
        return jsonify({"error": "Couleur invalide."}), 400
    if len(description) > DESCRIPTION_MAX:
        return jsonify({"error": f"La description est limitée à {DESCRIPTION_MAX} caractères."}), 400
    if link_error:
        return jsonify({"error": link_error}), 400
    holds, hold_error = parse_holds(data.get("holds"))
    if hold_error:
        return jsonify({"error": hold_error}), 400

    conn = get_db()
    require_wall_access(conn, wall_id)
    existing = conn.execute(
        "SELECT id FROM block WHERE wall_id = ? AND LOWER(name) = LOWER(?)",
        (wall_id, name)
    ).fetchone()
    if existing:
        conn.close()
        return jsonify({"error": f"Un bloc nommé \"{name}\" existe déjà sur ce mur."}), 400

    quota_message = quota_error(conn, "block")
    if quota_message:
        conn.close()
        return jsonify({"error": quota_message}), 429

    cursor = conn.execute(
        "INSERT INTO block(wall_id, name, grade, color, description, link, created_by) VALUES(?, ?, ?, ?, ?, ?, ?)",
        (wall_id, name, grade, color, description, link, session["user_id"])
    )
    block_id = cursor.lastrowid
    for x, y, hold_type, w, h in holds:
        conn.execute(
            "INSERT INTO hold(block_id, x, y, hold_type, w, h) VALUES(?, ?, ?, ?, ?, ?)",
            (block_id, x, y, hold_type, w, h)
        )
    quota_register(conn, "block")
    touch_wall_activity(conn, wall_id)
    conn.commit()
    conn.close()
    return jsonify({"success": True, "block_id": block_id})

@bp.route("/block/<int:block_id>/edit", methods=["GET", "POST"])
@login_required
def edit_block(block_id):
    """Modifier le nom, la cotation, la couleur et la description d'un bloc (créateur ou admin)."""
    conn = get_db()
    block = conn.execute("SELECT * FROM block WHERE id = ?", (block_id,)).fetchone()
    if not block:
        conn.close()
        abort(404)
    if block["created_by"] != session["user_id"] and session.get("user_role") != "admin":
        forbid_or_hide(conn, conn.execute("SELECT * FROM wall WHERE id = ?", (block["wall_id"],)).fetchone())
    error = None
    if request.method == "POST":
        name = clean_text(request.form.get("name"))
        grade = request.form.get("grade", "")
        color = request.form.get("color") or (block["color"] if block["color"] in ALLOWED_COLORS else DEFAULT_BLOCK_COLOR)
        description = clean_text(request.form.get("description"), multiline=True)
        link, link_error = clean_link(request.form.get("link"))
        if not name:
            error = "Le nom du bloc est requis."
        elif len(name) > NAME_MAX:
            error = f"Le nom est limité à {NAME_MAX} caractères."
        elif grade and grade not in GRADES:
            error = "Cotation invalide."
        elif color not in ALLOWED_COLORS:
            error = "Couleur invalide."
        elif len(description) > DESCRIPTION_MAX:
            error = f"La description est limitée à {DESCRIPTION_MAX} caractères."
        elif link_error:
            error = link_error
        else:
            existing = conn.execute(
                "SELECT id FROM block WHERE wall_id = ? AND LOWER(name) = LOWER(?) AND id != ?",
                (block["wall_id"], name, block_id)
            ).fetchone()
            if existing:
                error = f'Un autre bloc nommé "{name}" existe déjà sur ce mur.'
            else:
                conn.execute(
                    "UPDATE block SET name = ?, grade = ?, color = ?, description = ?, link = ? WHERE id = ?",
                    (name, grade, color, description, link, block_id)
                )
                conn.execute("UPDATE climb_log SET block_name = ?, grade = ? WHERE block_id = ?", (name, grade or "", block_id))
                touch_wall_activity(conn, block["wall_id"])
                conn.commit()
                conn.close()
                return redirect(f"/block/{block_id}")
    conn.close()
    return render_template("pages/edit_block.html", block=block, grades=GRADES, error=error)

@bp.route("/block/<int:block_id>/delete", methods=["POST"])
@login_required
def delete_block(block_id):
    conn = get_db()
    block = conn.execute("SELECT * FROM block WHERE id = ?", (block_id,)).fetchone()
    if not block or (block["created_by"] != session["user_id"] and session.get("user_role") != "admin"):
        forbid_or_hide(conn, conn.execute("SELECT * FROM wall WHERE id = ?", (block["wall_id"],)).fetchone() if block else None)
    log_if_admin_on_foreign(conn, block["created_by"], "Bloc supprimé par un admin", f"« {block['name']} » (#{block['id']})")
    wall_id = block["wall_id"]
    _delete_block_rows(conn, block_id)
    conn.commit()
    conn.close()
    return redirect(f"/wall/{wall_id}")

@bp.route("/api/block/<int:block_id>/holds")
def api_block_holds(block_id):
    conn = get_db()
    require_block_access(conn, block_id)
    holds = conn.execute("SELECT * FROM hold WHERE block_id = ?", (block_id,)).fetchall()
    conn.close()
    return jsonify([dict(h) for h in holds])

@bp.route("/api/block/<int:block_id>/full")
def api_block_full(block_id):
    """Retourne toutes les infos d'un bloc pour l'affichage dans le panneau du mur."""
    conn = get_db()
    block = conn.execute("""
        SELECT b.*, u.name as creator_name
        FROM block b LEFT JOIN user u ON b.created_by = u.id
        WHERE b.id = ?
    """, (block_id,)).fetchone()
    if not block:
        conn.close()
        return jsonify({"error": "Bloc introuvable"}), 404
    require_wall_access(conn, block["wall_id"])

    touch_wall_activity(conn, block["wall_id"])
    conn.commit()

    holds = [dict(h) for h in conn.execute(
        "SELECT * FROM hold WHERE block_id = ? ORDER BY id", (block_id,)).fetchall()
    ]
    notes = [dict(n) for n in conn.execute("""
        SELECT n.note, u.name as user_name
        FROM block_note n JOIN user u ON n.user_id = u.id
        WHERE n.block_id = ? ORDER BY n.created_at DESC
    """, (block_id,)).fetchall()]
    ascents = [dict(a) for a in conn.execute("""
        SELECT u.name as user_name, a.done, a.flash
        FROM ascent a JOIN user u ON a.user_id = u.id
        WHERE a.block_id = ? AND (a.done = 1 OR a.flash = 1)
        ORDER BY a.flash DESC, a.created_at ASC
    """, (block_id,)).fetchall()]

    my_note = None
    my_ascent = {"done": 0, "flash": 0}
    if "user_id" in session:
        r = conn.execute(
            "SELECT note FROM block_note WHERE block_id = ? AND user_id = ?",
            (block_id, session["user_id"])
        ).fetchone()
        if r:
            my_note = r["note"]
        a = conn.execute(
            "SELECT done, flash FROM ascent WHERE block_id = ? AND user_id = ?",
            (block_id, session["user_id"])
        ).fetchone()
        if a:
            my_ascent = dict(a)

    conn.close()
    return jsonify({
        "block": dict(block),
        "holds": holds,
        "notes": notes,
        "ascents": ascents,
        "my_note": my_note,
        "my_ascent": my_ascent,
        "logged_in": "user_id" in session
    })
