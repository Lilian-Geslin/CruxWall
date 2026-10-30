"""Suppressions en cascade : blocs, murs, salles, comptes (et leurs photos)."""

import os

from flask import current_app


def _delete_block_rows(conn, block_id):
    """Supprime un bloc, ses prises, cotations et ascensions (sans commit)."""
    conn.execute("DELETE FROM hold WHERE block_id = ?", (block_id,))
    conn.execute("DELETE FROM block_note WHERE block_id = ?", (block_id,))
    conn.execute("DELETE FROM ascent WHERE block_id = ?", (block_id,))
    conn.execute("DELETE FROM block WHERE id = ?", (block_id,))
    conn.execute(
        "UPDATE report SET status = 'gone', handled_at = CURRENT_TIMESTAMP "
        "WHERE status = 'open' AND target_type = 'block' AND target_id = ?", (block_id,))

def _delete_wall_cascade(conn, wall):
    """
    Supprime un mur et absolument tout ce qui lui est rattaché : ses blocs,
    leurs prises, notes et ascensions, les accès débloqués, les anciennes
    notifications le concernant, ainsi que sa photo sur le disque.
    Ne fait pas conn.commit() ni conn.close() — à l'appelant de le faire,
    pour pouvoir enchaîner plusieurs murs dans la même transaction.
    """
    block_ids = [r["id"] for r in conn.execute("SELECT id FROM block WHERE wall_id = ?", (wall["id"],)).fetchall()]
    for bid in block_ids:
        conn.execute("DELETE FROM hold WHERE block_id = ?", (bid,))
        conn.execute("DELETE FROM block_note WHERE block_id = ?", (bid,))
        conn.execute("DELETE FROM ascent WHERE block_id = ?", (bid,))
    conn.execute("DELETE FROM block WHERE wall_id = ?", (wall["id"],))
    conn.execute("DELETE FROM wall_access WHERE wall_id = ?", (wall["id"],))
    conn.execute("DELETE FROM notification WHERE wall_id = ?", (wall["id"],))
    conn.execute("DELETE FROM wall WHERE id = ?", (wall["id"],))
    # Les signalements en attente sur ce mur (ou ses blocs) n'ont plus d'objet
    conn.execute(
        "UPDATE report SET status = 'gone', handled_at = CURRENT_TIMESTAMP WHERE status = 'open' "
        "AND ((target_type = 'wall' AND target_id = ?) OR wall_id = ?)", (wall["id"], wall["id"]))
    img_path = os.path.join(current_app.config["UPLOAD_FOLDER"], wall["image_filename"])
    if os.path.exists(img_path):
        os.remove(img_path)

def _wall_is_private(conn, wall):
    """Un mur est considéré comme privé s'il l'est lui-même ou s'il est dans une salle privée."""
    if wall["is_private"]:
        return True
    if wall["gym_id"]:
        gym = conn.execute("SELECT is_private FROM gym WHERE id = ?", (wall["gym_id"],)).fetchone()
        return bool(gym and gym["is_private"])
    return False

def account_deletion_plan(conn, user_id):
    walls = conn.execute("SELECT * FROM wall WHERE created_by = ? ORDER BY name", (user_id,)).fetchall()
    gyms = conn.execute("SELECT * FROM gym WHERE created_by = ? ORDER BY name", (user_id,)).fetchall()
    return {
        "private_walls": [w for w in walls if _wall_is_private(conn, w)],
        "public_walls": [w for w in walls if not _wall_is_private(conn, w)],
        "private_gyms": [g for g in gyms if g["is_private"]],
        "public_gyms": [g for g in gyms if not g["is_private"]],
    }

def delete_user_account(conn, user_id, delete_public):
    """
    Supprime un compte et TOUTES ses données (sans commit : à l'appelant de valider).

    - Murs créés : les privés (ou situés dans une salle privée) sont toujours supprimés ;
      les publics seulement si delete_public est vrai, sinon ils restent, sans créateur.
    - Salles créées : même règle, mais une salle qui contient encore des murs créés par
      d'autres personnes n'est jamais supprimée (elle reste, sans créateur).
    - Blocs créés (sur n'importe quel mur), ascensions, cotations, notifications,
      accès débloqués, signalements envoyés : supprimés.
    Retourne un résumé (nombre d'éléments supprimés / conservés).
    """
    summary = {"walls_deleted": 0, "walls_kept": 0, "gyms_deleted": 0, "gyms_kept": 0}

    for w in conn.execute("SELECT * FROM wall WHERE created_by = ?", (user_id,)).fetchall():
        if _wall_is_private(conn, w) or delete_public:
            _delete_wall_cascade(conn, w)
            summary["walls_deleted"] += 1
        else:
            conn.execute("UPDATE wall SET created_by = NULL WHERE id = ?", (w["id"],))
            summary["walls_kept"] += 1

    for gy in conn.execute("SELECT * FROM gym WHERE created_by = ?", (user_id,)).fetchall():
        remaining = conn.execute("SELECT COUNT(*) FROM wall WHERE gym_id = ?", (gy["id"],)).fetchone()[0]
        if (gy["is_private"] or delete_public) and remaining == 0:
            conn.execute("DELETE FROM gym_access WHERE gym_id = ?", (gy["id"],))
            conn.execute("DELETE FROM gym WHERE id = ?", (gy["id"],))
            summary["gyms_deleted"] += 1
        else:
            conn.execute("UPDATE gym SET created_by = NULL WHERE id = ?", (gy["id"],))
            summary["gyms_kept"] += 1

    for b in conn.execute("SELECT id FROM block WHERE created_by = ?", (user_id,)).fetchall():
        _delete_block_rows(conn, b["id"])

    conn.execute("DELETE FROM ascent WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM climb_log WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM block_note WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM notification WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM wall_access WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM gym_access WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM report WHERE reporter_id = ?", (user_id,))
    # Compteurs anti-abus rattachés à ce compte
    conn.execute("DELETE FROM auth_attempt WHERE bucket LIKE ? OR bucket LIKE ?",
                 (f"%:user:{user_id}", f"quota:%:{user_id}"))
    conn.execute("DELETE FROM user WHERE id = ?", (user_id,))
    return summary
