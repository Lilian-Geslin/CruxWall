"""Journal des actions d'administration (table admin_log)."""

from flask import session


def admin_log(conn, action, target="", details=""):
    """Note une action d'administration (sans commit : fait partie de la même transaction que l'action)."""
    conn.execute(
        "INSERT INTO admin_log(admin_id, admin_name, action, target, details) VALUES(?, ?, ?, ?, ?)",
        (session.get("user_id"), session.get("user_name") or "?", action[:100], (target or "")[:200], (details or "")[:500]))
    conn.execute("DELETE FROM admin_log WHERE created_at < datetime('now', '-365 days')")

def log_if_admin_on_foreign(conn, owner_id, action, target):
    """Journalise une action faite par un admin sur le contenu de quelqu'un d'autre."""
    if session.get("user_role") == "admin" and owner_id != session.get("user_id"):
        admin_log(conn, action, target)
