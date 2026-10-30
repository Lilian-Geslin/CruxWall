"""Configuration de l'application : chemins, mode de fonctionnement, clé de session, réglages du serveur.

Lu une seule fois au démarrage par `create_app` (src/__init__.py). Les variables d'environnement viennent du
fichier `.env` placé à la racine du projet (jamais versionné). Les tests surchargent ces valeurs en passant leur
propre dictionnaire à `create_app` (base temporaire, dossier de photos temporaire…).
"""
import os
from datetime import timedelta

from dotenv import load_dotenv

# Racine du projet (le dossier qui contient run.py et src/) : on remonte de deux niveaux depuis ce fichier.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

load_dotenv(os.path.join(BASE_DIR, ".env"))  # charge les variables du fichier .env s'il existe

# Mode de fonctionnement. Par défaut : "production" (le plus sûr). Pour travailler en local, mettre
# CRUXWALL_ENV=development dans le .env de ton PC (jamais sur PythonAnywhere !).
IS_DEV = os.environ.get("CRUXWALL_ENV", "production").strip().lower() == "development"

# Redirection automatique http -> https en production (désactivable avec FORCE_HTTPS=0).
FORCE_HTTPS = (not IS_DEV) and os.environ.get("FORCE_HTTPS", "1") != "0"

# Sauvegarde + nettoyage lancés par la première visite de la journée (AUTO_MAINTENANCE=0 pour désactiver).
AUTO_MAINTENANCE = os.environ.get("AUTO_MAINTENANCE", "1") != "0"

MAX_UPLOAD_BYTES = 15 * 1024 * 1024   # taille maximale d'une requête (photo comprise)
MAX_IMAGE_PIXELS = 40_000_000         # ~ 40 mégapixels : au-delà, refus (bombe de décompression)
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
MAX_IMAGE_DIMENSION = 1600            # px : au-delà, inutile pour l'affichage et coûteux en stockage
JPEG_QUALITY = 80

SECRET_KEY_MIN_LENGTH = 16


def load_secret_key():
    """Clé qui signe le cookie de session (variable FLASK_SECRET_KEY du .env).

    Elle est obligatoire : sans elle, une clé aléatoire serait générée à chaque démarrage (tout le monde
    déconnecté) et, pire, elle pourrait différer d'un processus à l'autre sur l'hébergeur.
    """
    key = os.environ.get("FLASK_SECRET_KEY", "")
    if len(key) < SECRET_KEY_MIN_LENGTH:
        raise RuntimeError(
            "FLASK_SECRET_KEY absente ou trop courte (16 caractères minimum) : "
            "ajoute-la dans le fichier .env (voir README)."
        )
    return key


class Config:
    """Réglages chargés par `app.config.from_object(Config)` dans create_app."""
    # Base SQLite, photos (hors du dossier static : servies par /media avec contrôle d'accès), sauvegardes.
    DATABASE = os.environ.get("CRUXWALL_DATABASE", os.path.join(BASE_DIR, "cruxwall.db"))
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
    LEGACY_UPLOAD_FOLDER = os.path.join(BASE_DIR, "src", "static", "uploads")  # anciennes photos, déplacées au démarrage
    BACKUP_DIR = os.environ.get("BACKUP_DIR") or os.path.join(BASE_DIR, "backups")
    MODEL_PATH = os.path.join(BASE_DIR, "best.pt")  # modèle local YOLOv8 (facultatif)

    MAX_CONTENT_LENGTH = MAX_UPLOAD_BYTES
    SESSION_COOKIE_HTTPONLY = True        # le JavaScript ne peut pas lire le cookie de session
    SESSION_COOKIE_SAMESITE = "Lax"       # le cookie n'est pas envoyé par les requêtes d'autres sites
    SESSION_COOKIE_SECURE = not IS_DEV    # uniquement en HTTPS en production
    PERMANENT_SESSION_LIFETIME = timedelta(days=30)

    @staticmethod
    def secret_key():
        """Clé secrète de session (voir load_secret_key) : lue au moment de créer l'application, pas à l'import."""
        return load_secret_key()
