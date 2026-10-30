"""Administration : signalements, rôles, suppression de comptes, journal."""

from flask import Blueprint
from flask import abort
from flask import redirect
from flask import render_template
from flask import request
from flask import session

from ..auth import admin_required
from ..constants import REPORT_STATUS_LABELS
from ..db import get_db
from ..services.admin_log import admin_log
from ..services.deletion import _delete_block_rows, _delete_wall_cascade, delete_user_account
from ..services.search import like_pattern
from ..services.validation import clean_text


bp = Blueprint("admin", __name__)

@bp.route("/admin")
@admin_required
def admin_page():
    q = clean_text(request.args.get("q"))[:60]
    conn = get_db()
    open_reports = []
    for r in conn.execute(
            "SELECT r.*, u.name AS reporter_name FROM report r LEFT JOIN user u ON r.reporter_id = u.id "
            "WHERE r.status = 'open' ORDER BY r.created_at ASC, r.id ASC").fetchall():
        d = dict(r)
        table = "wall" if d["target_type"] == "wall" else "block"
        d["target_exists"] = conn.execute(f"SELECT 1 FROM {table} WHERE id = ?", (d["target_id"],)).fetchone() is not None
        d["target_url"] = f"/{table}/{d['target_id']}"
        open_reports.append(d)
    handled = [dict(r) for r in conn.execute(
        "SELECT * FROM report WHERE status != 'open' ORDER BY COALESCE(handled_at, created_at) DESC, id DESC LIMIT 30").fetchall()]
    like = like_pattern(q)
    users = conn.execute("""
        SELECT u.id, u.name, u.email, u.role,
               (SELECT COUNT(*) FROM wall w WHERE w.created_by = u.id) AS wall_count,
               (SELECT COUNT(*) FROM block b WHERE b.created_by = u.id) AS block_count
        FROM user u
        WHERE (? = '' OR u.name LIKE ? ESCAPE '\\' OR u.email LIKE ? ESCAPE '\\')
        ORDER BY u.name COLLATE NOCASE
        LIMIT 100
    """, (q, like, like)).fetchall()
    stats = {
        "users": conn.execute("SELECT COUNT(*) FROM user").fetchone()[0],
        "gyms": conn.execute("SELECT COUNT(*) FROM gym").fetchone()[0],
        "walls": conn.execute("SELECT COUNT(*) FROM wall").fetchone()[0],
        "blocks": conn.execute("SELECT COUNT(*) FROM block").fetchone()[0],
    }
    log_rows = conn.execute("SELECT * FROM admin_log ORDER BY id DESC LIMIT 60").fetchall()
    conn.close()
    return render_template("pages/admin.html", open_reports=open_reports, handled_reports=handled,
                           users=users, stats=stats, q=q, status_labels=REPORT_STATUS_LABELS,
                           admin_logs=log_rows)

@bp.route("/admin/report/<int:report_id>/dismiss", methods=["POST"])
@admin_required
def admin_report_dismiss(report_id):
    conn = get_db()
    r = conn.execute("SELECT * FROM report WHERE id = ? AND status = 'open'", (report_id,)).fetchone()
    if r:
        table = "wall" if r["target_type"] == "wall" else "block"
        exists = conn.execute(f"SELECT 1 FROM {table} WHERE id = ?", (r["target_id"],)).fetchone()
        conn.execute(
            "UPDATE report SET status = ?, handled_by = ?, handled_at = CURRENT_TIMESTAMP WHERE id = ?",
            ("dismissed" if exists else "gone", session["user_id"], report_id))
        admin_log(conn, "Signalement classé" if not exists else "Signalement ignoré",
                  f"{'mur' if r['target_type'] == 'wall' else 'bloc'} « {r['target_name']} » (#{r['target_id']})",
                  f"motif : {r['reason']}")
        conn.commit()
    conn.close()
    return redirect("/admin")

@bp.route("/admin/report/<int:report_id>/remove", methods=["POST"])
@admin_required
def admin_report_remove(report_id):
    conn = get_db()
    r = conn.execute("SELECT * FROM report WHERE id = ? AND status = 'open'", (report_id,)).fetchone()
    if not r:
        conn.close()
        return redirect("/admin")
    # Tous les signalements en attente sur ce même contenu sont clos d'un coup
    conn.execute(
        "UPDATE report SET status = 'removed', handled_by = ?, handled_at = CURRENT_TIMESTAMP "
        "WHERE status = 'open' AND target_type = ? AND target_id = ?",
        (session["user_id"], r["target_type"], r["target_id"]))
    admin_log(conn, "Contenu supprimé suite à un signalement",
              f"{'mur' if r['target_type'] == 'wall' else 'bloc'} « {r['target_name']} » (#{r['target_id']})",
              f"motif : {r['reason']}")
    if r["target_type"] == "wall":
        wall = conn.execute("SELECT * FROM wall WHERE id = ?", (r["target_id"],)).fetchone()
        if wall:
            owner, name = wall["created_by"], wall["name"]
            _delete_wall_cascade(conn, wall)
            if owner:
                conn.execute("INSERT INTO notification(user_id, wall_id, message) VALUES(?, NULL, ?)",
                             (owner, f"Votre mur « {name} » a été supprimé suite à un signalement (non-respect des conditions d'utilisation)."))
    else:
        block = conn.execute("SELECT * FROM block WHERE id = ?", (r["target_id"],)).fetchone()
        if block:
            owner, name = block["created_by"], block["name"]
            _delete_block_rows(conn, block["id"])
            if owner:
                conn.execute("INSERT INTO notification(user_id, wall_id, message) VALUES(?, NULL, ?)",
                             (owner, f"Votre bloc « {name} » a été supprimé suite à un signalement (non-respect des conditions d'utilisation)."))
    conn.commit()
    conn.close()
    return redirect("/admin")

@bp.route("/admin/user/<int:user_id>/role", methods=["POST"])
@admin_required
def admin_user_role(user_id):
    role = request.form.get("role")
    if role not in ("admin", "user") or user_id == session["user_id"]:
        abort(400)
    conn = get_db()
    target = conn.execute("SELECT name FROM user WHERE id = ?", (user_id,)).fetchone()
    if not target:
        conn.close()
        abort(404)
    conn.execute("UPDATE user SET role = ? WHERE id = ?", (role, user_id))
    admin_log(conn, "Droits administrateur accordés" if role == "admin" else "Droits administrateur retirés",
              f"{target['name']} (#{user_id})")
    conn.commit()
    conn.close()
    return redirect("/admin")

@bp.route("/admin/user/<int:user_id>/delete", methods=["POST"])
@admin_required
def admin_user_delete(user_id):
    if user_id == session["user_id"]:
        abort(400)
    conn = get_db()
    target = conn.execute("SELECT name FROM user WHERE id = ?", (user_id,)).fetchone()
    if target:
        delete_user_account(conn, user_id, delete_public=True)
        admin_log(conn, "Compte supprimé par un admin", f"{target['name']} (#{user_id})")
        conn.commit()
    conn.close()
    return redirect("/admin")
