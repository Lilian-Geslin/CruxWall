"""Nettoyage automatique des murs inactifs.

Lancé chaque jour par la maintenance automatique (services/maintenance.py) ou à la main avec
`python scripts/cleanup_inactive_walls.py`.

Règle :
- Un mur sans aucune activité (consultation OU ajout de contenu) depuis presque 6 mois reçoit un
  avertissement (notification interne à l'appli) à la personne qui l'a créé, une semaine avant suppression.
- Si l'inactivité continue jusqu'à 6 mois complets, le mur est supprimé définitivement : le mur lui-même,
  ses blocs, leurs prises, notes et ascensions, ainsi que la photo du mur sur le disque.
- Si le mur redevient actif entre-temps (quelqu'un le consulte ou y ajoute quelque chose), l'avertissement
  est automatiquement annulé (voir touch_wall_activity dans services/activity.py) et le compte à rebours
  repart de zéro.
"""
import os
import sqlite3
from datetime import datetime, timedelta

from ..config import Config

INACTIVITY_LIMIT = timedelta(days=180)  # ~6 mois
WARNING_BEFORE = timedelta(days=7)      # avertir 1 semaine avant la suppression


def run(database=None, upload_folder=None):
    """Avertit puis supprime les murs inactifs. Retourne (avertissements, suppressions)."""
    database = database or Config.DATABASE
    upload_folder = upload_folder or Config.UPLOAD_FOLDER
    conn = sqlite3.connect(database, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    now = datetime.utcnow()
    warn_threshold = now - (INACTIVITY_LIMIT - WARNING_BEFORE)
    delete_threshold = now - INACTIVITY_LIMIT

    walls = conn.execute("SELECT * FROM wall").fetchall()
    warned, deleted = 0, 0

    for w in walls:
        if not w["last_activity_at"]:
            continue
        last_activity = datetime.fromisoformat(w["last_activity_at"])

        if last_activity <= delete_threshold and w["warning_sent_at"]:
            # Averti il y a au moins une semaine, toujours inactif : suppression.
            _delete_wall(conn, w, upload_folder)
            deleted += 1
        elif last_activity <= warn_threshold and not w["warning_sent_at"]:
            # Approche des 6 mois sans avertissement encore envoyé.
            _warn_creator(conn, w)
            warned += 1

    conn.commit()
    conn.close()
    print(f"Nettoyage terminé : {warned} avertissement(s) envoyé(s), {deleted} mur(s) supprimé(s).")
    return warned, deleted


def _warn_creator(conn, w):
    if not w["created_by"]:
        return
    message = (
        f"Le mur « {w['name']} » n'a pas été utilisé depuis presque 6 mois. "
        f"Sans nouvelle activité, il sera supprimé définitivement (avec ses "
        f"blocs, prises, notes, ascensions et sa photo) dans environ une semaine."
    )
    conn.execute(
        "INSERT INTO notification(user_id, wall_id, message) VALUES(?, ?, ?)",
        (w["created_by"], w["id"], message)
    )
    conn.execute(
        "UPDATE wall SET warning_sent_at = CURRENT_TIMESTAMP WHERE id = ?",
        (w["id"],)
    )


def _delete_wall(conn, w, upload_folder):
    block_ids = [r["id"] for r in conn.execute(
        "SELECT id FROM block WHERE wall_id = ?", (w["id"],)).fetchall()]
    for bid in block_ids:
        conn.execute("DELETE FROM hold WHERE block_id = ?", (bid,))
        conn.execute("DELETE FROM block_note WHERE block_id = ?", (bid,))
        conn.execute("DELETE FROM ascent WHERE block_id = ?", (bid,))
    conn.execute("DELETE FROM block WHERE wall_id = ?", (w["id"],))
    conn.execute("DELETE FROM wall_access WHERE wall_id = ?", (w["id"],))
    # L'avertissement envoyé plus tôt pointe vers ce mur : on le retire (sinon
    # il resterait un lien mort, et la clé étrangère refuserait la suppression)
    conn.execute("DELETE FROM notification WHERE wall_id = ?", (w["id"],))

    if w["created_by"]:
        conn.execute(
            "INSERT INTO notification(user_id, wall_id, message) VALUES(?, NULL, ?)",
            (w["created_by"],
             f"Le mur « {w['name']} » a été supprimé automatiquement après 6 mois d'inactivité.")
        )

    conn.execute("DELETE FROM wall WHERE id = ?", (w["id"],))
    try:
        # Les signalements en attente sur ce mur (ou ses blocs) n'ont plus d'objet
        conn.execute(
            "UPDATE report SET status = 'gone', handled_at = CURRENT_TIMESTAMP WHERE status = 'open' "
            "AND ((target_type = 'wall' AND target_id = ?) OR wall_id = ?)", (w["id"], w["id"]))
    except sqlite3.OperationalError:
        pass  # base ancienne sans table report

    img_path = os.path.join(upload_folder, w["image_filename"])
    if os.path.exists(img_path):
        os.remove(img_path)

