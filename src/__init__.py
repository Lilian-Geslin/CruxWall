"""CruxWall : application web de bouldering (Flask + SQLite).

Ce fichier contient la « fabrique d'application » `create_app` : c'est elle qui assemble toutes les pièces du projet
(configuration, base de données, sécurité, gestion des erreurs, routes, templates). Elle est appelée par `run.py` en
développement, par le fichier WSGI de PythonAnywhere en production et par les tests (qui lui passent leur propre
configuration, par exemple une base temporaire).
"""
import os

from flask import Flask

from . import security, templating
from .services import maintenance
from .config import Config
from .errors import register_error_handlers
from .routes import register_blueprints
from .schema import init_db
from .services.images import migrate_legacy_uploads


def create_app(config=None):
    """Crée et configure l'application.

    `config` : dictionnaire facultatif qui écrase les réglages par défaut
    (ex. {'DATABASE': ..., 'UPLOAD_FOLDER': ..., 'TESTING': True}).
    """
    # ─── Configuration ───
    app = Flask(__name__)
    app.config.from_object(Config)
    app.config["SECRET_KEY"] = Config.secret_key()
    # Appliqué en dernier pour que les tests puissent tout surcharger (base, photos, clé secrète…).
    if config:
        app.config.update(config)

    # ─── Dossiers et base de données ───
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    migrate_legacy_uploads(app.config["LEGACY_UPLOAD_FOLDER"], app.config["UPLOAD_FOLDER"])
    # Crée / met à jour les tables au démarrage (idempotent : sans danger à chaque lancement).
    init_db(app.config["DATABASE"])

    # ─── Branchements (sécurité, templates, maintenance, erreurs, routes) ───
    security.init_app(app)
    templating.init_app(app)
    maintenance.init_app(app)
    register_error_handlers(app)
    register_blueprints(app)
    return app
