"""Tâche quotidienne à la main (ou planifiée sur un plan payant de PythonAnywhere) : 1) sauvegarde, 2) nettoyage.

La sauvegarde passe en premier : si le nettoyage supprime un mur, la copie du jour le contient encore.
Sur le plan gratuit, rien à programmer : la première visite de la journée déclenche déjà ces deux étapes.

Commande à programmer (onglet Tasks) :
  /home/VOTRE_USER/.virtualenvs/cruxwall-env/bin/python /home/VOTRE_USER/cruxwall/app/scripts/daily_maintenance.py
"""
import traceback
import os
import sys

# Les scripts vivent dans scripts/ : on ajoute la racine du projet pour pouvoir importer `src`.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from src.services import backup, cleanup

failed = False
for name, step in (("sauvegarde", backup.run), ("nettoyage", cleanup.run)):
    try:
        step()
    except Exception:
        failed = True
        print(f"ERREUR pendant l'étape « {name} » :")
        traceback.print_exc()

sys.exit(1 if failed else 0)
