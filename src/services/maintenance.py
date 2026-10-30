"""Maintenance automatique quotidienne : sauvegarde puis nettoyage, lancés par la première visite de la journée.

Le plan gratuit de PythonAnywhere n'a pas de tâche planifiée : la première requête du jour déclenche la
maintenance APRÈS l'envoi de la réponse au visiteur, qui n'attend donc rien. Un fichier-repère par jour
(`backups/.maintenance-AAAA-MM-JJ`, créé en exclusivité) empêche tout doublon entre processus.
La sauvegarde passe avant le nettoyage : si celui-ci supprime un mur, la copie du jour le contient encore.
"""
import os
from datetime import datetime

from flask import current_app, request

from ..config import AUTO_MAINTENANCE
from . import backup, cleanup

_maintenance_state = {"day": None}   # jour déjà traité par CE processus (évite de retester le fichier-repère)

# Pages qui ne déclenchent jamais la maintenance (fichiers statiques, photos, contrôle de santé)
SKIPPED_ENDPOINTS = (None, "static", "media.media", "public.health")


def run_daily_maintenance(app):
    """Exécute la sauvegarde puis le nettoyage ; un échec d'une étape n'empêche pas l'autre."""
    with app.app_context():
        cfg = app.config
        steps = (
            ("sauvegarde", lambda: backup.run(database=cfg["DATABASE"], upload_folder=cfg["UPLOAD_FOLDER"], backup_dir=cfg["BACKUP_DIR"])),
            ("nettoyage", lambda: cleanup.run(database=cfg["DATABASE"], upload_folder=cfg["UPLOAD_FOLDER"])),
        )
        for name, step in steps:
            try:
                step()
            except Exception:
                app.logger.exception("Maintenance automatique : échec de l'étape « %s »", name)


def _safe_maintenance(app):
    try:
        run_daily_maintenance(app)
    except Exception:
        app.logger.exception("Maintenance automatique : erreur inattendue")


def _claim_maintenance_slot(folder, today):
    """Vrai pour UN seul processus par jour : celui qui réussit à créer le fichier-repère du jour."""
    try:
        os.makedirs(folder, mode=0o700, exist_ok=True)
        fd = os.open(os.path.join(folder, f".maintenance-{today}"), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
    except FileExistsError:
        return False
    except OSError:
        return False
    for old in os.listdir(folder):   # repères de plus de 3 jours
        if old.startswith(".maintenance-") and old < f".maintenance-{today}":
            try:
                if (datetime.now() - datetime.fromtimestamp(os.path.getmtime(os.path.join(folder, old)))).days >= 3:
                    os.remove(os.path.join(folder, old))
            except OSError:
                pass
    return True


def schedule_daily_maintenance(resp):
    """Après-requête : planifie la maintenance du jour (une seule fois par jour, tous processus confondus)."""
    if not AUTO_MAINTENANCE or request.endpoint in SKIPPED_ENDPOINTS:
        return resp
    today = datetime.now().strftime("%Y-%m-%d")
    if _maintenance_state["day"] == today:
        return resp
    _maintenance_state["day"] = today
    try:
        app = current_app._get_current_object()
        if _claim_maintenance_slot(app.config["BACKUP_DIR"], today):
            resp.call_on_close(lambda: _safe_maintenance(app))
    except Exception:
        current_app.logger.exception("Maintenance automatique : planification impossible")
    return resp


def init_app(app):
    """Branche la planification sur l'application (appelé par create_app)."""
    app.after_request(schedule_daily_maintenance)
