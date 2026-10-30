"""Service des photos avec contrôle d'accès (jamais directement depuis static/)."""

from flask import Blueprint
from flask import abort
from flask import current_app
from flask import send_from_directory

from ..constants import MEDIA_NAME_RE
from ..db import get_db
from ..services.access import can_view_wall
from ..services.deletion import _wall_is_private


bp = Blueprint("media", __name__)

@bp.route("/media/<filename>")
def media(filename):
    """
    Sert la photo d'un mur, uniquement à qui a le droit de voir ce mur. Pour tout refus
    (photo inexistante ou interdite) la réponse est la même 404 : on ne révèle pas
    qu'un mur privé existe.
    """
    if not MEDIA_NAME_RE.match(filename):
        abort(404)
    conn = get_db()
    wall = conn.execute("SELECT * FROM wall WHERE image_filename = ?", (filename,)).fetchone()
    if not wall or not can_view_wall(conn, wall):
        conn.close()
        abort(404)
    private = _wall_is_private(conn, wall)
    conn.close()
    resp = send_from_directory(current_app.config["UPLOAD_FOLDER"], filename, mimetype="image/jpeg")
    # Les noms de fichiers sont uniques (jamais réutilisés) : le navigateur peut garder l'image.
    resp.headers["Cache-Control"] = "private, max-age=3600" if private else "public, max-age=86400"
    return resp
