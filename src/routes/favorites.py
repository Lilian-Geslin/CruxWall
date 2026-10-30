"""Favoris (murs, salles, blocs), liste « à faire » et carnet de progression."""

from flask import Blueprint
from datetime import datetime
from datetime import timezone

from flask import abort
from flask import redirect
from flask import render_template
from flask import session

from ..auth import login_required
from ..constants import GRADES, MAX_FAVORITES, MAX_TODO
from ..db import get_db
from ..errors import notice_page
from ..services.access import can_view_wall, require_block_access, require_wall_access
from ..services.validation import safe_referrer


bp = Blueprint("favorites", __name__)

def _toggle(conn, table, id_column, item_id, limit, label):
    """Ajoute ou retire une ligne (favori / à faire). Retourne (ajouté ?, message d'erreur éventuel)."""
    uid = session["user_id"]
    if conn.execute(f"SELECT 1 FROM {table} WHERE user_id = ? AND {id_column} = ?", (uid, item_id)).fetchone():
        conn.execute(f"DELETE FROM {table} WHERE user_id = ? AND {id_column} = ?", (uid, item_id))
        return False, None
    if conn.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id = ?", (uid,)).fetchone()[0] >= limit:
        return False, f"Limite atteinte : {limit} {label} au maximum."
    conn.execute(f"INSERT INTO {table}(user_id, {id_column}) VALUES(?, ?)", (uid, item_id))
    return True, None

@bp.route("/wall/<int:wall_id>/favorite", methods=["POST"])
@login_required
def toggle_wall_favorite(wall_id):
    conn = get_db()
    require_wall_access(conn, wall_id)
    _, err = _toggle(conn, "wall_favorite", "wall_id", wall_id, MAX_FAVORITES, "murs favoris")
    conn.commit()
    conn.close()
    if err:
        return notice_page("Limite atteinte", [err], f"/wall/{wall_id}", "← Retour au mur", 400)
    return redirect(safe_referrer(f"/wall/{wall_id}"))

@bp.route("/gym/<int:gym_id>/favorite", methods=["POST"])
@login_required
def toggle_gym_favorite(gym_id):
    conn = get_db()
    if not conn.execute("SELECT 1 FROM gym WHERE id = ?", (gym_id,)).fetchone():
        conn.close()
        abort(404)
    _, err = _toggle(conn, "gym_favorite", "gym_id", gym_id, MAX_FAVORITES, "salles favorites")
    conn.commit()
    conn.close()
    if err:
        return notice_page("Limite atteinte", [err], f"/gym/{gym_id}", "← Retour à la salle", 400)
    return redirect(safe_referrer(f"/gym/{gym_id}"))

@bp.route("/block/<int:block_id>/favorite", methods=["POST"])
@login_required
def toggle_block_favorite(block_id):
    conn = get_db()
    require_block_access(conn, block_id)
    _, err = _toggle(conn, "block_favorite", "block_id", block_id, MAX_FAVORITES, "blocs favoris")
    conn.commit()
    conn.close()
    if err:
        return notice_page("Limite atteinte", [err], f"/block/{block_id}", "← Retour au bloc", 400)
    return redirect(safe_referrer(f"/block/{block_id}"))

@bp.route("/block/<int:block_id>/todo", methods=["POST"])
@login_required
def toggle_block_todo(block_id):
    conn = get_db()
    require_block_access(conn, block_id)
    _, err = _toggle(conn, "block_todo", "block_id", block_id, MAX_TODO, "blocs dans la liste « à faire »")
    conn.commit()
    conn.close()
    if err:
        return notice_page("Limite atteinte", [err], f"/block/{block_id}", "← Retour au bloc", 400)
    return redirect(safe_referrer(f"/block/{block_id}"))

@bp.route("/favoris")
@login_required
def favorites_page():
    conn = get_db()
    uid = session["user_id"]
    walls = conn.execute("""
        SELECT w.*, g.name AS gym_name, COUNT(DISTINCT b.id) AS block_count
        FROM wall_favorite f JOIN wall w ON w.id = f.wall_id
        LEFT JOIN gym g ON g.id = w.gym_id LEFT JOIN block b ON b.wall_id = w.id
        WHERE f.user_id = ? GROUP BY w.id ORDER BY f.created_at DESC
    """, (uid,)).fetchall()
    walls = [w for w in walls if can_view_wall(conn, w)]   # un mur devenu privé n'apparaît plus
    gyms = conn.execute("""
        SELECT g.*, (SELECT COUNT(*) FROM wall w WHERE w.gym_id = g.id) AS wall_count
        FROM gym_favorite f JOIN gym g ON g.id = f.gym_id
        WHERE f.user_id = ? ORDER BY f.created_at DESC
    """, (uid,)).fetchall()
    block_rows = conn.execute("""
        SELECT b.id, b.name, b.grade, b.color, w.id AS wall_id, w.name AS wall_name, w.gym_id, w.is_private,
               w.created_by AS wall_owner
        FROM block_favorite f JOIN block b ON b.id = f.block_id JOIN wall w ON w.id = b.wall_id
        WHERE f.user_id = ? ORDER BY f.created_at DESC
    """, (uid,)).fetchall()
    blocks = [r for r in block_rows if can_view_wall(conn, {"id": r["wall_id"], "gym_id": r["gym_id"], "is_private": r["is_private"],
                                                            "created_by": r["wall_owner"]})]
    conn.close()
    return render_template("pages/favorites.html", walls=walls, gyms=gyms, blocks=blocks, active_tab="favoris")

@bp.route("/a-faire")
@login_required
def todo_page():
    conn = get_db()
    rows = conn.execute("""
        SELECT b.id, b.name, b.grade, b.color, w.id AS wall_id, w.name AS wall_name, w.gym_id, w.is_private,
               w.created_by AS wall_owner, t.created_at AS added_at
        FROM block_todo t JOIN block b ON b.id = t.block_id JOIN wall w ON w.id = b.wall_id
        WHERE t.user_id = ? ORDER BY t.created_at DESC
    """, (session["user_id"],)).fetchall()
    blocks = [r for r in rows if can_view_wall(conn, {"id": r["wall_id"], "gym_id": r["gym_id"], "is_private": r["is_private"],
                                                       "created_by": r["wall_owner"]})]
    conn.close()
    return render_template("pages/todo.html", todo=blocks, active_tab="afaire")

@bp.route("/carnet")
@login_required
def logbook_page():
    conn = get_db()
    # Le carnet vient de climb_log (copie propre à chaque personne) : supprimer un bloc, un mur ou une salle
    # ne change AUCUN chiffre. Les noms/cotations affichés sont ceux du bloc s'il existe encore, sinon la copie.
    rows = conn.execute("""
        SELECT l.block_id, l.flash, l.done_at AS day, l.wall_id,
               COALESCE(b.name, l.block_name) AS name, CASE WHEN b.id IS NOT NULL THEN b.grade ELSE l.grade END AS grade,
               COALESCE(w.name, l.wall_name) AS wall_name, b.color AS color, (b.id IS NOT NULL) AS exists_now,
               w.gym_id, w.is_private, w.created_by AS wall_owner
        FROM climb_log l LEFT JOIN block b ON b.id = l.block_id LEFT JOIN wall w ON w.id = b.wall_id
        WHERE l.user_id = ? ORDER BY l.done_at DESC, l.rowid DESC
    """, (session["user_id"],)).fetchall()
    entries = []
    for r in rows:
        e = dict(r)
        e["linkable"] = bool(r["exists_now"]) and can_view_wall(
            conn, {"id": r["wall_id"], "gym_id": r["gym_id"], "is_private": r["is_private"], "created_by": r["wall_owner"]})
        entries.append(e)
    conn.close()

    def rank(grade):
        return GRADES.index(grade) if grade in GRADES else -1

    total = len(entries)
    flashes = sum(1 for e in entries if e["flash"])
    graded = [e for e in entries if e["grade"] in GRADES]
    hardest = max(graded, key=lambda e: rank(e["grade"]), default=None)
    hardest_flash = max((e for e in graded if e["flash"]), key=lambda e: rank(e["grade"]), default=None)

    by_grade_counts = {}
    for e in entries:
        key = e["grade"] if e["grade"] in GRADES else "?"
        by_grade_counts[key] = by_grade_counts.get(key, 0) + 1
    ordered = sorted(by_grade_counts.items(), key=lambda kv: (kv[0] == "?", rank(kv[0])))
    top = max(by_grade_counts.values(), default=1)
    by_grade = [{"grade": g if g != "?" else "Sans cotation", "count": n, "pct": max(4, round(100 * n / top))} for g, n in ordered]

    # 12 derniers mois (y compris ceux à zéro)
    today = datetime.now(timezone.utc)
    months = []
    y, m = today.year, today.month
    for _ in range(12):
        months.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    months.reverse()
    month_counts = {k: 0 for k in months}
    for e in entries:
        k = (e["day"] or "")[:7]
        if k in month_counts:
            month_counts[k] += 1
    mtop = max(month_counts.values(), default=0) or 1
    by_month = [{"label": f"{k[5:]}/{k[2:4]}", "count": n, "pct": round(100 * n / mtop)} for k, n in month_counts.items()]

    journal = {}
    for e in entries[:150]:
        journal.setdefault((e["day"] or "")[:7] or "?", []).append(e)
    return render_template("pages/logbook.html", total=total, flashes=flashes,
                           flash_pct=round(100 * flashes / total) if total else 0,
                           walls_count=len({e["wall_id"] for e in entries}), hardest=hardest, hardest_flash=hardest_flash,
                           by_grade=by_grade, by_month=by_month, journal=journal, active_tab="carnet")
