"""Validation de la liste des prises envoyée par l'éditeur de bloc."""

from ..constants import HOLD_TYPES, MAX_HOLDS_PER_BLOCK
from ..services.validation import to_float


def parse_holds(raw):
    """Valide la liste des prises envoyée par l'éditeur. Retourne (liste, erreur)."""
    if not isinstance(raw, list):
        return None, "Prises invalides."
    if len(raw) < 2:
        return None, "Un bloc doit avoir au moins 2 prises."
    if len(raw) > MAX_HOLDS_PER_BLOCK:
        return None, f"Un bloc ne peut pas avoir plus de {MAX_HOLDS_PER_BLOCK} prises."
    out = []
    for h in raw:
        if not isinstance(h, dict):
            return None, "Prises invalides."
        x, y = to_float(h.get("x")), to_float(h.get("y"))
        if x is None or y is None or not (0 <= x <= 1 and 0 <= y <= 1):
            return None, "Position de prise invalide."
        hold_type = h.get("type", "mid")
        if hold_type not in HOLD_TYPES:
            return None, "Type de prise invalide."
        sizes = []
        for key in ("w", "h"):
            v = h.get(key)
            if v is None:
                sizes.append(None)
                continue
            v = to_float(v)
            if v is None or not (0 < v <= 1):
                return None, "Taille de prise invalide."
            sizes.append(v)
        out.append((x, y, hold_type, sizes[0], sizes[1]))
    return out, None
