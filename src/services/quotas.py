"""Quotas de création par compte (murs, salles, blocs) et plafond d'espace disque des photos."""

import os

from flask import current_app
from flask import session

from ..constants import QUOTAS
from ..services.ratelimit import rl_count, rl_hit


def quota_error(conn, kind):
    """Message d'erreur si le compte a atteint un quota (total ou journalier), sinon None. Les admins sont exemptés."""
    if session.get("user_role") == "admin":
        return None
    q = QUOTAS[kind]
    n = conn.execute(
        f"SELECT COUNT(*) AS n FROM {q['table']} WHERE created_by = ?", (session["user_id"],)
    ).fetchone()["n"]
    if n >= q["total"]:
        return f"Limite atteinte : {q['total']} {q['label']} maximum par compte. Supprimez-en pour en créer de nouveaux."
    if rl_count(conn, f"quota:{kind}:{session['user_id']}", 24 * 3600) >= q["daily"]:
        return f"Limite journalière atteinte ({q['daily']} {q['label']} par 24 h). Réessayez demain."
    return None

def quota_register(conn, kind):
    rl_hit(conn, f"quota:{kind}:{session['user_id']}")

def uploads_size_bytes():
    total = 0
    try:
        with os.scandir(current_app.config["UPLOAD_FOLDER"]) as it:
            for entry in it:
                if entry.is_file():
                    total += entry.stat().st_size
    except OSError:
        pass
    return total
