"""Informations légales (éditeur, hébergeur, contact) lues dans le fichier .env."""

import os


def legal_info():
    """Informations légales affichées dans les mentions et la politique de confidentialité (voir .env)."""
    return {
        "publisher": os.environ.get("LEGAL_PUBLISHER_NAME", "").strip(),
        "publisher_address": os.environ.get("LEGAL_PUBLISHER_ADDRESS", "").strip(),
        "email": os.environ.get("LEGAL_CONTACT_EMAIL", "").strip(),
        "host": os.environ.get("LEGAL_HOST", "PythonAnywhere (https://www.pythonanywhere.com)").strip(),
        "updated": "11 octobre 2026",
    }
