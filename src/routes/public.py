"""Pages publiques : accueil et point de contrôle /health."""

from flask import Blueprint
from flask import Response
from flask import render_template

from ..db import get_db
from ..services.access import can_view_wall


bp = Blueprint("public", __name__)

@bp.route("/")
def home():
    conn = get_db()
    walls = conn.execute("""
        SELECT w.*, g.name as gym_name, g.is_private as gym_is_private,
               g.id as gym_id_check, g.created_by as gym_created_by,
               COUNT(DISTINCT b.id) as block_count
        FROM wall w
        LEFT JOIN gym g ON w.gym_id = g.id
        LEFT JOIN block b ON b.wall_id = w.id
        GROUP BY w.id
        ORDER BY w.created_at DESC
        LIMIT 30
    """).fetchall()

    visible_walls = []
    for w in walls:
        gym = None
        if w["gym_id"]:
            gym = {"id": w["gym_id"], "is_private": w["gym_is_private"], "created_by": w["gym_created_by"]}
        if can_view_wall(conn, w, gym):
            visible_walls.append(w)
        if len(visible_walls) >= 12:
            break

    gyms = conn.execute("SELECT * FROM gym ORDER BY name").fetchall()
    conn.close()
    return render_template("pages/index.html", walls=visible_walls, gyms=gyms)

@bp.route("/health")
def health():
    """Réponse « ok » si le site et sa base répondent (pour un service de surveillance)."""
    try:
        conn = get_db()
        conn.execute("SELECT 1").fetchone()
        conn.close()
    except Exception:
        return Response("erreur", status=503, mimetype="text/plain")
    resp = Response("ok", mimetype="text/plain")
    resp.headers["Cache-Control"] = "no-store"
    return resp
