"""Carnet de progression : copie durable (climb_log) des blocs réussis, indépendante des suppressions."""

def sync_climb_log(conn, user_id, block_id):
    """
    Tient à jour le carnet de progression d'une personne pour UN bloc. Le carnet est une copie
    indépendante des blocs : quand un bloc, un mur ou une salle est supprimé(e), la réussite reste
    dans le carnet, avec le nom et la cotation au moment où elle a été conservée.
    La ligne n'est retirée que si la personne décoche elle-même sa réussite.
    """
    a = conn.execute("SELECT done, flash, done_at, created_at FROM ascent WHERE user_id = ? AND block_id = ?",
                     (user_id, block_id)).fetchone()
    if not a or not (a["done"] or a["flash"]):
        conn.execute("DELETE FROM climb_log WHERE user_id = ? AND block_id = ?", (user_id, block_id))
        return
    b = conn.execute("""SELECT b.name, b.grade, w.id AS wall_id, w.name AS wall_name FROM block b
                        JOIN wall w ON w.id = b.wall_id WHERE b.id = ?""", (block_id,)).fetchone()
    if not b:
        return
    conn.execute("""
        INSERT INTO climb_log(user_id, block_id, wall_id, block_name, wall_name, grade, flash, done_at)
        VALUES(?, ?, ?, ?, ?, ?, ?, COALESCE(?, ?, CURRENT_TIMESTAMP))
        ON CONFLICT(user_id, block_id) DO UPDATE SET flash = excluded.flash, done_at = excluded.done_at,
            block_name = excluded.block_name, wall_name = excluded.wall_name, grade = excluded.grade, wall_id = excluded.wall_id
    """, (user_id, block_id, b["wall_id"], b["name"], b["wall_name"], b["grade"] or "", 1 if a["flash"] else 0,
          a["done_at"], a["created_at"]))
