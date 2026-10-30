"""Sauvegarde manuelle de la base (et des photos avec --uploads).

    python scripts/backup_db.py            # base
    python scripts/backup_db.py --uploads  # base + photos

La sauvegarde automatique du quotidien est faite par src/services/maintenance.py ; ce script sert à en faire une
à la demande (avant une mise à jour, par exemple). Détails dans src/services/backup.py.
"""
import os
import sys

# Les scripts vivent dans scripts/ : on ajoute la racine du projet pour pouvoir importer `src`.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from src.services import backup

if __name__ == "__main__":
    backup.run(force_uploads="--uploads" in sys.argv)
