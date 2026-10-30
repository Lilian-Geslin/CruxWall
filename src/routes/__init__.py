"""Routes de l'application, regroupées par thème dans des blueprints.

Un blueprint = un groupe de routes Flask défini dans son propre fichier (variable `bp`). Les routes lisent la requête,
vérifient les droits, appellent les services (src/services) et répondent (page HTML, JSON ou redirection).
"""
from . import (admin, ascents, auth, blocks, detection, favorites, gyms, legal, media, profile, public, reports,
               search, walls)


def register_blueprints(app):
    """Branche tous les blueprints sur l'application (appelé par `create_app`)."""
    for module in (public, auth, walls, gyms, blocks, ascents, favorites, profile, search, media, legal, reports,
                   admin, detection):
        app.register_blueprint(module.bp)
