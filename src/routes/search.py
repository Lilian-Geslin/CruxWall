"""Recherche globale (murs et salles) de la barre du haut."""

from flask import Blueprint
from flask import jsonify
from flask import request

from ..constants import SEARCH_MAX
from ..db import get_db
from ..services.access import can_view_gym, can_view_wall
from ..services.search import like_pattern


bp = Blueprint("search", __name__)

@bp.route("/search")
def search():
    q = (request.args.get("q") or "").strip()[:SEARCH_MAX]
    if len(q) < 2:
        return jsonify([])
    pattern = like_pattern(q)
    conn = get_db()

    wall_rows = conn.execute("""
        SELECT w.*, g.name as gym_name, g.is_private as gym_is_private,
               g.created_by as gym_created_by
        FROM wall w LEFT JOIN gym g ON w.gym_id = g.id
        WHERE w.name LIKE ? ESCAPE '\\' OR g.name LIKE ? ESCAPE '\\'
        LIMIT 20
    """, (pattern, pattern)).fetchall()

    results = []
    for w in wall_rows:
        gym = None
        if w["gym_id"]:
            gym = {"id": w["gym_id"], "is_private": w["gym_is_private"], "created_by": w["gym_created_by"]}
        if can_view_wall(conn, w, gym):
            results.append({"type": "wall", "id": w["id"], "name": w["name"], "gym_name": w["gym_name"]})

    # Les salles sont cherchées séparément et toujours listées (même privées,
    # même sans mur dessus) — seul leur contenu reste caché, comme sur /gyms.
    gym_rows = conn.execute("SELECT * FROM gym WHERE name LIKE ? ESCAPE '\\' LIMIT 10", (pattern,)).fetchall()
    for g in gym_rows:
        results.append({
            "type": "gym", "id": g["id"], "name": g["name"],
            "is_private": bool(g["is_private"]), "can_view": can_view_gym(conn, g)
        })

    conn.close()
    return jsonify(results[:12])
