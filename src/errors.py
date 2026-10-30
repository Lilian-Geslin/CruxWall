"""Pages d'erreur et gestionnaires d'exceptions (HTML pour les pages, JSON pour /api/)."""

import sqlite3

from flask import current_app
from flask import jsonify
from flask import render_template
from flask import request

from .config import MAX_UPLOAD_BYTES
from .constants import TOO_MANY_MSG


def too_large(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Fichier trop volumineux."}), 413
    return render_template("pages/error.html", title="Fichier trop volumineux",
        message=f"La photo dépasse {MAX_UPLOAD_BYTES // (1024 * 1024)} Mo. Réduisez-la puis réessayez."
    ), 413

def _error_page(code, title, message):
    if request.path.startswith("/api/"):
        return jsonify({"error": message}), code
    try:
        return render_template("pages/error.html", title=title, message=message), code
    except Exception:
        # Dernier filet : si même la page d'erreur plante (base inaccessible...)
        return f"{title} — {message}", code

def err_400(e):
    return _error_page(400, "Requête invalide", "La requête n'a pas pu être comprise. Rechargez la page puis réessayez.")

def err_403(e):
    return _error_page(403, "Accès refusé", "Vous n'avez pas le droit d'accéder à cette page.")

def err_404(e):
    return _error_page(404, "Page introuvable", "Cette page n'existe pas ou a été supprimée.")

def err_405(e):
    return _error_page(405, "Action non autorisée", "Cette action n'est pas autorisée sur cette page.")

def err_500(e):
    # Le détail technique est déjà dans le journal du serveur : on n'affiche rien de plus
    return _error_page(500, "Erreur du serveur", "Un problème est survenu de notre côté. Réessayez dans un instant.")

def err_integrity(e):
    # Contrainte d'unicité ou clé étrangère violée (deux personnes qui créent
    # le même pseudo/nom en même temps, élément supprimé entre-temps...)
    current_app.logger.warning("Contrainte de base de données : %s", e)
    return _error_page(409, "Conflit",
                       "Cette opération entre en conflit avec des données existantes (nom déjà pris, "
                       "élément supprimé entre-temps...). Rechargez la page puis réessayez.")

def err_429(e):
    return _error_page(429, "Trop de demandes", TOO_MANY_MSG)

def notice_page(title, lines, back_url="/", back_label=None, code=200):
    return render_template("pages/notice.html", title=title, lines=lines,
                           back_url=back_url, back_label=back_label), code


def register_error_handlers(app):
    """Branche les fonctions ci-dessus sur l'application (appelé par create_app)."""
    app.errorhandler(413)(too_large)
    app.errorhandler(400)(err_400)
    app.errorhandler(403)(err_403)
    app.errorhandler(404)(err_404)
    app.errorhandler(405)(err_405)
    app.errorhandler(500)(err_500)
    app.errorhandler(sqlite3.IntegrityError)(err_integrity)
    app.errorhandler(429)(err_429)
