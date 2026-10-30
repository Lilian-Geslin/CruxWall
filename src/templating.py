"""Branchements pour les templates : version des fichiers statiques, variables communes, filtre image_url."""

import os

from flask import current_app
from flask import g
from flask import session

from .constants import REPORT_REASONS
from .db import get_db
from .security import get_csrf_token
from .services.antibot import make_form_token
from .services.legal import legal_info


def add_static_version(endpoint, values):
    """Ajoute ?v=<date du fichier> aux fichiers statiques : après une mise à jour, les navigateurs
    (téléphones surtout) rechargent le nouveau CSS/JS au lieu de garder l'ancien en cache."""
    if endpoint == "static" and "filename" in values and "v" not in values:
        try:
            values["v"] = int(os.path.getmtime(os.path.join(current_app.static_folder, values["filename"])))
        except (OSError, ValueError):
            pass

def inject_notification_count():
    """Rend le jeton CSRF et le nombre de notifications non lues disponibles dans tous les templates."""
    ctx = {
        "csrf_token": get_csrf_token,
        "csp_nonce": g.get("csp_nonce", ""),
        "new_form_token": make_form_token,
        "legal": legal_info(),
        "report_reasons": REPORT_REASONS,
    }
    if "user_id" not in session:
        return ctx
    conn = get_db()
    if session.get("user_role") == "admin":
        ctx["open_reports"] = conn.execute("SELECT COUNT(*) AS n FROM report WHERE status = 'open'").fetchone()["n"]
    count = conn.execute(
        "SELECT COUNT(*) as n FROM notification WHERE user_id = ? AND read_at IS NULL",
        (session["user_id"],)
    ).fetchone()["n"]
    conn.close()
    ctx["unread_notifications"] = count
    return ctx

def image_url(filename):
    return f"/media/{filename}"


def init_app(app):
    """Branche les fonctions ci-dessus sur l'application (appelé par create_app)."""
    app.url_defaults(add_static_version)
    app.context_processor(inject_notification_count)
    app.add_template_global(image_url)
