"""Constantes et réglages de référence : cotations, limites, quotas, délais, couleurs.

Tout ce qu'on peut vouloir ajuster sans toucher à la logique est regroupé ici (voir docs/FONCTIONNALITES.md,
section « Limites »)."""

import os
import re

GRADES = [
    "3a", "3a+", "3b", "3b+", "3c", "3c+",
    "4a", "4a+", "4b", "4b+", "4c", "4c+",
    "5a", "5a+", "5b", "5b+", "5c", "5c+",
    "6a", "6a+", "6b", "6b+", "6c", "6c+",
    "7a", "7a+", "7b", "7b+", "7c", "7c+",
    "8a", "8a+", "8b", "8b+", "8c", "8c+",
    "9a", "9a+", "9b", "9b+", "9c"
]
PSEUDO_RE = re.compile(r"^[A-Za-z0-9_-]{3,30}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PASSWORD_MIN, PASSWORD_MAX = 8, 128
NAME_MAX = 100
LOCATION_MAX = 60
DESCRIPTION_MAX = 500
MAX_HOLDS_PER_BLOCK = 100
DEFAULT_BLOCK_COLOR = "#3b82f6"
ALLOWED_COLORS = {"#eab308", "#22c55e", "#3b82f6", "#8b5cf6", "#ef4444", "#ffffff", "#111827"}
HOLD_TYPES = {"start", "mid", "top", "foot"}
LINK_MAX = 300
SEARCH_MAX = 100
SUGGEST_WALLS_MAX, SUGGEST_BLOCKS_MAX = 25, 50   # propositions de la recherche de salle

# Connexion : le blocage compte les échecs par couple (email + adresse IP), et non par email seul.
# Une personne qui tape de mauvais mots de passe depuis SON adresse ne peut donc pas empêcher le
# vrai propriétaire du compte (depuis une autre adresse) de se connecter. Garde-fous en plus :
# 50 échecs par adresse IP, et 100 par email (attaque répartie sur de nombreuses adresses).
LOGIN_PAIR_MAX, LOGIN_IP_MAX, LOGIN_EMAIL_MAX, LOGIN_WINDOW = 5, 50, 100, 15 * 60
REGISTER_IP_MAX, REGISTER_WINDOW = 50, 60 * 60   # large : une classe peut partager la même IP
UNLOCK_USER_MAX, UNLOCK_USER_WINDOW = 10, 15 * 60
UNLOCK_IP_MAX, UNLOCK_IP_WINDOW = 40, 60 * 60
TOO_MANY_MSG = "Trop de tentatives. Réessayez dans quelques minutes."

# total = nombre maximum par compte ; daily = nombre maximum de créations par 24 h
QUOTAS = {
    "wall":  {"table": "wall",  "total": 250, "daily": 50,  "label": "murs"},
    "gym":   {"table": "gym",   "total": 100, "daily": 25,  "label": "salles"},
    "block": {"table": "block", "total": 500, "daily": 100, "label": "blocs"},
}

try:
    MAX_UPLOADS_MB = int(os.environ.get("MAX_UPLOADS_MB", "350"))  # plafond total des photos sur le disque
except ValueError:
    MAX_UPLOADS_MB = 350

# Formulaire d'inscription : piège à robots (champ caché que seul un robot remplit)
# + jeton daté (un humain met plus de 2 secondes à remplir le formulaire).
REGISTER_MIN_SECONDS = 2
REGISTER_MAX_SECONDS = 6 * 3600
ACTIVITY_THROTTLE_MINUTES = 60
BOT_UA_RE = re.compile(r"bot|crawl|spider|slurp|facebookexternalhit|preview|monitor|curl|wget|python-requests", re.I)
ACCESS_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sans 0, 1, I ni O, faciles à confondre
ACCESS_CODE_LENGTH = 10  # 32^10 ≈ 10^15 possibilités (l'ancien code à 6 caractères hexadécimaux : 16 millions)
MEDIA_NAME_RE = re.compile(r"^[0-9a-f]{32}\.jpg$")
REPORT_REASONS = {
    "person": "Personne reconnaissable sur la photo",
    "inappropriate": "Contenu inapproprié ou illégal",
    "rights": "Photo ou contenu dont je détiens les droits",
    "personal": "Informations personnelles visibles",
    "other": "Autre",
}
REPORT_STATUS_LABELS = {
    "open": "En attente",
    "dismissed": "Ignoré",
    "removed": "Contenu supprimé",
    "gone": "Contenu déjà supprimé",
}
REPORT_USER_MAX, REPORT_WINDOW = 5, 3600   # 5 signalements par heure et par compte
REPORT_IP_MAX = 20                          # et 20 par heure et par adresse IP
REPORT_DETAILS_MAX = 500
ACCOUNT_FAIL_MAX, ACCOUNT_FAIL_WINDOW = 5, 15 * 60   # 5 mots de passe actuels faux / 15 min
PSEUDO_CHANGE_MAX = 3                                 # 3 changements de pseudo par 24 h
SETTINGS_OK_MESSAGES = {
    "pseudo": "Pseudo modifié.",
    "email": "Adresse email modifiée.",
    "password": "Mot de passe modifié. Vos autres appareils ont été déconnectés.",
}
MAX_FAVORITES, MAX_TODO = 200, 500
