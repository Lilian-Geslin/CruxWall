"""Activité d'un mur : date de dernière consultation, qui retarde le nettoyage des murs abandonnés."""

from flask import request
from flask import session

from ..constants import ACTIVITY_THROTTLE_MINUTES, BOT_UA_RE


def touch_wall_activity(conn, wall_id):
    """
    Marque un mur comme actif (consulté ou modifié à l'instant). Annule au
    passage tout avertissement de suppression en attente : un mur qui
    redevient actif n'a plus de raison d'être supprimé.

    Cette date ne sert qu'au nettoyage des murs abandonnés (délai de 6 mois) :
    inutile de l'écrire à chaque affichage. On ne la met à jour qu'au plus
    une fois par heure, sauf pour annuler un avertissement (immédiat). Cela
    ne retarde en rien l'affichage du contenu : blocs, ascensions et
    cotations sont lus directement en base à chaque requête.
    Les visites de robots (moteurs de recherche, outils de supervision...) ne
    comptent pas, pour qu'ils ne gardent pas artificiellement des murs en vie.
    """
    if "user_id" not in session:
        return   # un visiteur anonyme ne fait aucune écriture en base (ni ne garde un mur en vie)
    if request.method == "GET" and BOT_UA_RE.search(request.headers.get("User-Agent", "")):
        return
    conn.execute(
        "UPDATE wall SET last_activity_at = CURRENT_TIMESTAMP, warning_sent_at = NULL "
        "WHERE id = ? AND (warning_sent_at IS NOT NULL OR last_activity_at IS NULL "
        "OR last_activity_at < datetime('now', ?))",
        (wall_id, f"-{ACTIVITY_THROTTLE_MINUTES} minutes")
    )
