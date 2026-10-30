"""Recherche : échappement des motifs LIKE, recherche dans une salle (murs, blocs, cotation, ouvreur)."""

from ..services.access import can_view_wall


def gym_search(conn, visible_walls, q, limit):
    """Cherche dans une salle parmi les murs VISIBLES : noms de murs, et blocs
    (nom, début de cotation — « 6a » trouve aussi 6a+ —, nom de l'ouvreur)."""
    ql = q.lower()
    pattern = like_pattern(q)
    grade_pattern = like_pattern(ql)[1:]          # « 6a% » : début de cotation
    walls = [w for w in visible_walls if ql in (w["name"] or "").lower()]
    blocks = []
    ids = [w["id"] for w in visible_walls]
    if ids:
        marks = ",".join("?" * len(ids))
        blocks = conn.execute(f"""
            SELECT b.id, b.name, b.grade, b.color, w.id AS wall_id, w.name AS wall_name,
                   u.name AS creator_name
            FROM block b
            JOIN wall w ON b.wall_id = w.id
            LEFT JOIN user u ON b.created_by = u.id
            WHERE w.id IN ({marks})
              AND (b.name LIKE ? ESCAPE '\\' OR u.name LIKE ? ESCAPE '\\' OR LOWER(b.grade) LIKE ? ESCAPE '\\')
            ORDER BY b.grade, b.name
            LIMIT ?
        """, (*ids, pattern, pattern, grade_pattern, limit)).fetchall()
    return walls, blocks

def gym_visible_walls(conn, gym):
    rows = conn.execute("""
        SELECT w.*, COUNT(DISTINCT b.id) as block_count
        FROM wall w LEFT JOIN block b ON b.wall_id = w.id
        WHERE w.gym_id = ? GROUP BY w.id ORDER BY w.created_at DESC
    """, (gym["id"],)).fetchall()
    return [w for w in rows if can_view_wall(conn, w, gym)]

def like_pattern(text):
    """Texte cherché -> motif LIKE où % et _ saisis par la personne sont des caractères ordinaires."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
