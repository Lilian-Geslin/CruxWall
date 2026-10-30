"""Lance à la main le nettoyage des murs inactifs (avertissement à 173 jours, suppression à 180 jours).

    python scripts/cleanup_inactive_walls.py

Le nettoyage est normalement automatique (src/services/maintenance.py). Règles détaillées : src/services/cleanup.py.
"""
import os
import sys

# Les scripts vivent dans scripts/ : on ajoute la racine du projet pour pouvoir importer `src`.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from src.services import cleanup

if __name__ == "__main__":
    cleanup.run()
