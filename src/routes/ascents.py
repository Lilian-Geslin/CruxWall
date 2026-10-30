"""API des cotations communautaires et des ascensions (fait / flash) d'un bloc."""

from flask import Blueprint
from flask import jsonify
from flask import request
from flask import session

from ..auth import login_required
from ..constants import GRADES
from ..db import get_db
from ..services.access import require_block_access, require_wall_access
from ..services.activity import touch_wall_activity
from ..services.climb_log import sync_climb_log
from ..services.validation import clean_text


bp = Blueprint("ascents", __name__)

@bp.route("/api/block/<int:block_id>/note", methods=["POST"])
@login_required
def set_block_note(block_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Requête invalide."}), 400
    note = clean_text(data.get("note"))
    if not note:
        return jsonify({"error": "Note vide."}), 400
    if note not in GRADES:
        return jsonify({"error": "Cotation invalide."}), 400
    conn = get_db()
    block_row = conn.execute("SELECT wall_id FROM block WHERE id = ?", (block_id,)).fetchone()
    if not block_row:
        conn.close()
        return jsonify({"error": "Bloc introuvable"}), 404
    require_wall_access(conn, block_row["wall_id"])
    existing = conn.execute(
        "SELECT id FROM block_note WHERE block_id = ? AND user_id = ?",
        (block_id, session["user_id"])
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE block_note SET note = ? WHERE block_id = ? AND user_id = ?",
            (note, block_id, session["user_id"])
        )
        msg = "Cotation mise à jour."
    else:
        conn.execute(
            "INSERT INTO block_note(block_id, user_id, note) VALUES(?, ?, ?)",
            (block_id, session["user_id"], note)
        )
        msg = "Cotation enregistrée."
    touch_wall_activity(conn, block_row["wall_id"])
    conn.commit()
    notes = conn.execute("""
        SELECT n.note, u.name as user_name
        FROM block_note n JOIN user u ON n.user_id = u.id
        WHERE n.block_id = ?
        ORDER BY n.created_at DESC
    """, (block_id,)).fetchall()
    conn.close()
    return jsonify({"success": True, "message": msg, "notes": [dict(n) for n in notes]})

@bp.route("/api/block/<int:block_id>/notes")
def get_block_notes(block_id):
    conn = get_db()
    require_block_access(conn, block_id)
    notes = conn.execute("""
        SELECT n.note, u.name as user_name
        FROM block_note n JOIN user u ON n.user_id = u.id
        WHERE n.block_id = ?
        ORDER BY n.created_at DESC
    """, (block_id,)).fetchall()
    my_note = None
    if "user_id" in session:
        r = conn.execute(
            "SELECT note FROM block_note WHERE block_id = ? AND user_id = ?",
            (block_id, session["user_id"])
        ).fetchone()
        if r:
            my_note = r["note"]
    conn.close()
    return jsonify({"notes": [dict(n) for n in notes], "my_note": my_note})

@bp.route("/api/block/<int:block_id>/ascent", methods=["POST"])
@login_required
def set_ascent(block_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Requête invalide."}), 400
    done = 1 if data.get("done") else 0
    flash = 1 if data.get("flash") else 0
    # Flash implique done
    if flash:
        done = 1
    conn = get_db()
    block_row = conn.execute("SELECT wall_id FROM block WHERE id = ?", (block_id,)).fetchone()
    if not block_row:
        conn.close()
        return jsonify({"error": "Bloc introuvable"}), 404
    require_wall_access(conn, block_row["wall_id"])
    existing = conn.execute(
        "SELECT id FROM ascent WHERE block_id = ? AND user_id = ?",
        (block_id, session["user_id"])
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE ascent SET done = ?, flash = ?, "
            "done_at = CASE WHEN ? = 1 AND (done = 0 OR done_at IS NULL) THEN CURRENT_TIMESTAMP ELSE done_at END "
            "WHERE block_id = ? AND user_id = ?",
            (done, flash, done, block_id, session["user_id"])
        )
    else:
        conn.execute(
            "INSERT INTO ascent(block_id, user_id, done, flash, done_at) "
            "VALUES(?, ?, ?, ?, CASE WHEN ? = 1 THEN CURRENT_TIMESTAMP ELSE NULL END)",
            (block_id, session["user_id"], done, flash, done)
        )
    sync_climb_log(conn, session["user_id"], block_id)
    if done:   # bloc réussi : il sort tout seul de la liste « à faire »
        conn.execute("DELETE FROM block_todo WHERE user_id = ? AND block_id = ?", (session["user_id"], block_id))
    touch_wall_activity(conn, block_row["wall_id"])
    conn.commit()
    ascents = conn.execute("""
        SELECT u.name as user_name, a.done, a.flash
        FROM ascent a JOIN user u ON a.user_id = u.id
        WHERE a.block_id = ? AND (a.done = 1 OR a.flash = 1)
        ORDER BY a.flash DESC, a.created_at ASC
    """, (block_id,)).fetchall()
    my_ascent = conn.execute(
        "SELECT done, flash FROM ascent WHERE block_id = ? AND user_id = ?",
        (block_id, session["user_id"])
    ).fetchone()
    conn.close()
    return jsonify({
        "success": True,
        "ascents": [dict(a) for a in ascents],
        "my_ascent": dict(my_ascent) if my_ascent else {"done": 0, "flash": 0}
    })

@bp.route("/api/block/<int:block_id>/ascents")
def get_ascents(block_id):
    conn = get_db()
    require_block_access(conn, block_id)
    ascents = conn.execute("""
        SELECT u.name as user_name, a.done, a.flash
        FROM ascent a JOIN user u ON a.user_id = u.id
        WHERE a.block_id = ? AND (a.done = 1 OR a.flash = 1)
        ORDER BY a.flash DESC, a.created_at ASC
    """, (block_id,)).fetchall()
    my_ascent = {"done": 0, "flash": 0}
    if "user_id" in session:
        r = conn.execute(
            "SELECT done, flash FROM ascent WHERE block_id = ? AND user_id = ?",
            (block_id, session["user_id"])
        ).fetchone()
        if r:
            my_ascent = dict(r)
    conn.close()
    return jsonify({"ascents": [dict(a) for a in ascents], "my_ascent": my_ascent})
