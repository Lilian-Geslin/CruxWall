"""Sauvegarde automatique de la base (et, une fois par semaine, des photos).

Lancée chaque jour par la maintenance automatique (services/maintenance.py) ou à la main avec
`python scripts/backup_db.py`.

- Base : copie cohérente (API de sauvegarde de SQLite, sûre même pendant que le site tourne), vérifiée,
  conservée 14 jours.
- Photos : archive le dimanche, conservée 2 semaines, ignorée si le dossier dépasse 100 Mo (pour ne pas
  saturer le quota de l'hébergeur).
- Dossier : backups/ à la racine du projet (ou BACKUP_DIR dans le .env), exclu de Git. Les sauvegardes
  restent SUR LE SERVEUR : télécharge-les régulièrement ailleurs (onglet Files de PythonAnywhere),
  sinon elles ne protègent pas contre la perte du compte.
"""
import os
import sqlite3
import tarfile
from datetime import datetime

from ..config import Config

KEEP_DB = 14
KEEP_UPLOADS = 2
MAX_UPLOADS_ARCHIVE_MB = 100


def _prune(backup_dir, prefix, suffix, keep):
    files = sorted(f for f in os.listdir(backup_dir) if f.startswith(prefix) and f.endswith(suffix))
    for old in files[:-keep]:
        os.remove(os.path.join(backup_dir, old))


def backup_database(database, backup_dir):
    os.makedirs(backup_dir, mode=0o700, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d")
    dest = os.path.join(backup_dir, f"cruxwall-{stamp}.db")
    tmp = dest + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)

    src = sqlite3.connect(database, timeout=30)
    dst = sqlite3.connect(tmp)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()

    check = sqlite3.connect(tmp)
    try:
        result = check.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        check.close()
    if result != "ok":
        os.remove(tmp)
        raise RuntimeError(f"Sauvegarde corrompue ({result}) : abandonnée.")

    os.chmod(tmp, 0o600)
    os.replace(tmp, dest)
    _prune(backup_dir, "cruxwall-", ".db", KEEP_DB)
    print(f"Base sauvegardée : {dest}")


def backup_uploads(upload_folder, backup_dir, force=False):
    if not force and datetime.now().weekday() != 6:  # dimanche seulement
        return
    if not os.path.isdir(upload_folder):
        return
    size = sum(os.path.getsize(os.path.join(upload_folder, f))
               for f in os.listdir(upload_folder) if os.path.isfile(os.path.join(upload_folder, f)))
    if size > MAX_UPLOADS_ARCHIVE_MB * 1024 * 1024:
        print(f"Photos non archivées : {size // (1024 * 1024)} Mo (> {MAX_UPLOADS_ARCHIVE_MB} Mo).")
        return
    os.makedirs(backup_dir, mode=0o700, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d")
    dest = os.path.join(backup_dir, f"uploads-{stamp}.tar")
    tmp = dest + ".tmp"
    with tarfile.open(tmp, "w") as tar:  # les JPEG sont déjà compressés : pas de gzip
        tar.add(upload_folder, arcname="uploads")
    os.chmod(tmp, 0o600)
    os.replace(tmp, dest)
    _prune(backup_dir, "uploads-", ".tar", KEEP_UPLOADS)
    print(f"Photos archivées : {dest}")


def run(force_uploads=False, database=None, upload_folder=None, backup_dir=None):
    """Sauvegarde la base, puis (le dimanche, ou si `force_uploads`) les photos. Chemins par défaut : ceux de Config."""
    database = database or Config.DATABASE
    upload_folder = upload_folder or Config.UPLOAD_FOLDER
    backup_dir = backup_dir or Config.BACKUP_DIR
    backup_database(database, backup_dir)
    backup_uploads(upload_folder, backup_dir, force=force_uploads)
