"""Nettoyage et validation des saisies : textes, liens, entiers, adresses de redirection sûres."""

from urllib.parse import urlparse
import math
import re

from flask import request

from ..constants import LINK_MAX


_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

def clean_text(value, multiline=False):
    """Texte propre : chaîne, sans caractères de contrôle, espaces de bord retirés."""
    if not isinstance(value, str):
        return ""
    value = _CONTROL_CHARS.sub("", value)
    if not multiline:
        value = value.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    return value.strip()

def clean_link(value):
    """Lien externe optionnel. Retourne (lien, erreur). Seuls http/https sont acceptés."""
    value = clean_text(value)
    if not value:
        return "", None
    if len(value) > LINK_MAX:
        return "", f"Le lien est limité à {LINK_MAX} caractères."
    if " " in value:
        return "", "Le lien ne doit pas contenir d'espace."
    if "://" not in value:
        value = "https://" + value
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or "." not in parsed.netloc or "@" in parsed.netloc:
        return "", "Lien invalide : il doit commencer par http:// ou https://."
    return value, None

def normalize_email(value):
    return (value or "").strip().lower() if isinstance(value, str) else ""

def to_int(value):
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

def to_float(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None

def safe_next_url(target, default="/"):
    """
    N'accepte qu'un chemin interne du site ("/wall/3"). Refuse les adresses
    externes ("https://autre-site.com", "//autre-site.com", "/\\autre-site.com"),
    sinon le paramètre ?redirect= permettrait de renvoyer les gens ailleurs
    juste après leur connexion (redirection ouverte, utilisée pour l'hameçonnage).
    """
    if not isinstance(target, str):
        return default
    target = target.strip()
    if not target.startswith("/") or target.startswith("//") or "\\" in target:
        return default
    if any(ord(c) < 32 for c in target):
        return default
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc:
        return default
    return target

def safe_referrer(default="/"):
    """Page d'où l'on vient, uniquement si elle est sur ce même site."""
    ref = request.referrer
    if ref:
        parsed = urlparse(ref)
        if parsed.netloc == request.host:
            path = parsed.path + (("?" + parsed.query) if parsed.query else "")
            return safe_next_url(path, default)
    return default
