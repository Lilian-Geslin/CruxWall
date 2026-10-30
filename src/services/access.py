"""Droits d'accès aux salles, murs et blocs (publics ou privés avec code).

Un mur auquel on n'a pas accès répond 404, comme un mur inexistant : on ne révèle pas qu'il existe."""

import re
import secrets

from flask import abort
from flask import session

from ..constants import ACCESS_CODE_ALPHABET, ACCESS_CODE_LENGTH


def normalize_access_code(value):
    return re.sub(r"[\s-]", "", value or "").upper()[:32]

def codes_match(stored, given):
    if not stored or not given:
        return False
    return secrets.compare_digest(stored.encode("utf-8"), given.encode("utf-8"))

def generate_access_code():
    """Code à partager pour débloquer un mur/salle privé(e)."""
    return "".join(secrets.choice(ACCESS_CODE_ALPHABET) for _ in range(ACCESS_CODE_LENGTH))

def can_view_gym(conn, gym):
    """
    Une salle privée reste visible dans les listes (on sait qu'elle existe)
    mais son contenu (ses murs) est caché à qui n'a pas le code — sauf son
    créateur et les admins.
    """
    if not gym or not gym["is_private"]:
        return True
    if "user_id" not in session:
        return False
    if session.get("user_role") == "admin" or gym["created_by"] == session["user_id"]:
        return True
    row = conn.execute(
        "SELECT 1 FROM gym_access WHERE gym_id = ? AND user_id = ?",
        (gym["id"], session["user_id"])
    ).fetchone()
    return row is not None

def can_view_wall(conn, wall, gym=None):
    """
    Un mur est invisible à qui n'a pas accès si : le mur lui-même est privé,
    OU si la salle qui le contient est privée (dans ce cas, la salle prime :
    peu importe le statut propre du mur, cf. discussion produit).
    """
    if session.get("user_role") == "admin" or (wall["created_by"] and wall["created_by"] == session.get("user_id")):
        return True

    if gym is None and wall["gym_id"]:
        gym = conn.execute("SELECT * FROM gym WHERE id = ?", (wall["gym_id"],)).fetchone()

    if gym and gym["is_private"]:
        return can_view_gym(conn, gym)

    if not wall["is_private"]:
        return True

    if "user_id" not in session:
        return False
    row = conn.execute(
        "SELECT 1 FROM wall_access WHERE wall_id = ? AND user_id = ?",
        (wall["id"], session["user_id"])
    ).fetchone()
    return row is not None

def require_wall_access(conn, wall_id):
    """Interrompt la requête (404) si le mur n'existe pas ou si l'utilisateur n'y a pas accès."""
    wall = conn.execute("SELECT * FROM wall WHERE id = ?", (wall_id,)).fetchone()
    if not wall:
        conn.close()
        abort(404)
    if not can_view_wall(conn, wall):
        conn.close()
        abort(404)   # même réponse qu'un mur inexistant : on ne révèle pas qu'il existe
    return wall

def forbid_or_hide(conn, wall):
    """Refus d'une action réservée au créateur : 403 si le mur est visible, 404 sinon (on ne révèle rien)."""
    visible = wall is not None and can_view_wall(conn, wall)
    conn.close()
    abort(403 if visible else 404)

def require_block_access(conn, block_id):
    """Comme require_wall_access, mais à partir de l'id d'un bloc."""
    row = conn.execute("SELECT wall_id FROM block WHERE id = ?", (block_id,)).fetchone()
    if not row:
        conn.close()
        abort(404)
    return require_wall_access(conn, row["wall_id"])
