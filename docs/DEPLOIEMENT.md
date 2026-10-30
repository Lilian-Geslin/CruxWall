# Déploiement (PythonAnywhere) et exploitation

Exemple de configuration : compte PythonAnywhere `VOTRE_USER`, dossier `~/cruxwall/app`, virtualenv `cruxwall-env`, site `VOTRE_USER.pythonanywhere.com` (remplace `VOTRE_USER` par ton nom de compte partout dans ce guide). Flux de travail : modifier sur le PC → `git push` → sur PythonAnywhere `git pull` → **Reload**.

## Fichiers à ne jamais perdre ni versionner

| Fichier / dossier | Contenu | Où |
|---|---|---|
| `.env` | secrets et réglages (une copie sur le PC, **une autre sur le serveur**, différentes) | racine du projet |
| `cruxwall.db` | toute la base de données | racine du projet |
| `uploads/` | photos des murs | racine du projet |
| `backups/` | sauvegardes automatiques | racine du projet |
| `best.pt` | modèle local de détection (facultatif) | racine du projet |

Ils sont dans `.gitignore` : `git pull` ne les touche pas. **Ne jamais lancer `python scripts/setup_db.py --reset` sur le serveur** (efface toute la base).

## `.env` du serveur

```
FLASK_SECRET_KEY=<chaine aléatoire d'au moins 32 caractères>
TRUST_PROXY=1
LEGAL_PUBLISHER_NAME=...
LEGAL_CONTACT_EMAIL=...
# facultatif : ROBOFLOW_API_KEY=..., MAX_UPLOADS_MB=350, DETECT_DAILY_LIMIT=100, LEGAL_PUBLISHER_ADDRESS=...
```

**Pas** de `CRUXWALL_ENV=development` sur le serveur. Génération d'une clé : `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Contrôle : `python scripts/check_env.py` (affiche OK / ATTENTION / ERREUR sans montrer les valeurs).

## Fichier WSGI

Onglet **Web** → lien du fichier WSGI (`/var/www/VOTRE_USER_pythonanywhere_com_wsgi.py`) : tout le contenu doit se résumer à

```python
import sys
sys.path.insert(0, '/home/VOTRE_USER/cruxwall/app')
from run import app as application
```

(l'ancienne ligne `from app import app` ne fonctionne plus : `app.py` n'existe plus.) Onglet Web : *Source code* et *Working directory* = `/home/VOTRE_USER/cruxwall/app`, *Virtualenv* = `/home/VOTRE_USER/.virtualenvs/cruxwall-env` (ou le chemin actuel).

## Mise à jour courante

1. Sur le PC : `pytest`, puis `git add -A`, `git commit`, `git push`.
2. Sur PythonAnywhere (console Bash) :
   ```bash
   cd ~/cruxwall/app
   git pull
   workon cruxwall-env        # ou : source ~/.virtualenvs/cruxwall-env/bin/activate
   pip install -r requirements-pythonanywhere.txt   # seulement si les dépendances ont changé
   python scripts/check_env.py
   ```
3. Onglet **Web** → **Reload**. Les tables manquantes ou colonnes nouvelles sont créées automatiquement au redémarrage.

## Migration depuis l'ancienne structure « à plat »

L'ancienne version avait `app.py`, `setup_db.py`, `templates/`, `static/` et les scripts à la racine. La nouvelle range tout dans `src/`, `scripts/`, `tests/`, `docs/`. **La base, les photos et le `.env` restent exactement au même endroit** et ne sont pas modifiés.

1. **Sauvegarde de précaution** (console PythonAnywhere) :
   ```bash
   cd ~/cruxwall/app
   mkdir -p ~/securite && cp cruxwall.db ~/securite/cruxwall-avant-migration.db && cp .env ~/securite/env-avant-migration && tar cf ~/securite/uploads-avant-migration.tar uploads
   ```
2. **Sur le PC** : dans ton dossier du projet, supprime les anciens fichiers (`app.py`, `setup_db.py`, `backup_db.py`, `cleanup_inactive_walls.py`, `daily_maintenance.py`, `make_admin.py`, `check_env.py`, `check_updates.py`, anciens dossiers `templates/` et `static/`, ancien `README.md`) **sans toucher** à `.env`, `cruxwall.db`, `uploads/`, `backups/`, `best.pt`, `.git/`. Copie à la place le contenu du zip (`src/`, `scripts/`, `tests/`, `docs/`, `run.py`, `README.md`, `requirements*.txt`, `pytest.ini`, `.gitignore`).
3. **Teste en local** : `pip install -r requirements-dev.txt`, `pytest`, puis `python run.py` et ouvre <http://127.0.0.1:5000>.
4. **Envoie** : `git add -A` · `git commit -m "Réorganisation : src/, tests/, docs/"` · `git push`. Git enregistre la suppression des anciens fichiers.
5. **Sur PythonAnywhere** : `cd ~/cruxwall/app && git pull`. Vérifie : `ls` doit montrer `run.py`, `src/`, `scripts/`, `.env`, `cruxwall.db`, `uploads/`. Si un ancien dossier `static/` subsiste, regarde qu'il ne contient plus de photos (`ls static/uploads`) : les éventuelles photos restantes se déplacent avec `mv static/uploads/* uploads/`, puis tu peux supprimer `static/` et `templates/` (`rm -r static templates`).
6. **Corrige le fichier WSGI** (voir plus haut) puis `python scripts/check_env.py`.
7. **Reload** (onglet Web) et vérifie : accueil, connexion, une photo de mur, le menu mobile, la recherche dans une salle, la flèche retour d'un mur, `/health` (affiche `ok`).
8. **En cas de problème** : onglet Web → *Error log*. Retour en arrière : `git revert` du commit de migration, ancien WSGI (`from app import app as application`), Reload ; la base n'a pas été modifiée dans sa structure (la même mise à jour automatique s'applique avant et après).

Les anciennes commandes changent de chemin : `python scripts/make_admin.py MonPseudo`, `python scripts/backup_db.py`, `python scripts/cleanup_inactive_walls.py`, `python scripts/daily_maintenance.py`, `python scripts/check_env.py`, `python scripts/check_updates.py`, `python scripts/setup_db.py`.

## Sauvegarde, nettoyage et maintenance quotidienne

Sur le plan gratuit il n'existe pas de tâche planifiée : **la première visite de la journée** lance, après avoir répondu au visiteur, la sauvegarde puis le nettoyage (même ordre qu'à la main : si le nettoyage supprime un mur, la copie du jour le contient encore). Un fichier `backups/.maintenance-AAAA-MM-JJ`, créé en exclusivité, garantit qu'un seul processus s'en charge. `AUTO_MAINTENANCE=0` la désactive. Plan payant : tâche planifiée `…/bin/python /home/VOTRE_USER/cruxwall/app/scripts/daily_maintenance.py`.

- **Sauvegarde** (`services/backup.py`) : copie cohérente de la base (API de sauvegarde SQLite), vérifiée par `PRAGMA integrity_check`, fichier `backups/cruxwall-AAAA-MM-JJ.db` (droits `600`), **14 jours conservés** ; archive `uploads-AAAA-MM-JJ.tar` le dimanche (2 conservées, ignorée au-delà de 100 Mo).
- **Nettoyage** (`services/cleanup.py`) : mur sans activité depuis **173 jours** → notification d'avertissement au créateur ; à **180 jours** et seulement s'il a été averti → suppression (blocs, prises, notes, ascensions, photo ; le carnet des grimpeurs est conservé).
- **Restaurer** : arrêter le site (Web → *Disable*), copier `backups/cruxwall-AAAA-MM-JJ.db` en `cruxwall.db`, réactiver et *Reload*.
- Les sauvegardes sont **sur le serveur** : télécharge-les de temps en temps (onglet *Files*).

## Surveillance

`/health` répond `ok` (200) quand le site et la base fonctionnent, `erreur` (503) sinon : à brancher sur un service de supervision (les robots ne comptent pas comme activité des murs). Les erreurs serveur sont dans *Error log* de PythonAnywhere.

## Comptes administrateurs

`python scripts/make_admin.py MonPseudo` (ajoute `--remove` pour retirer le rôle). Ensuite la page `/admin` permet de nommer d'autres administrateurs ; l'action est inscrite au journal.

## Détection IA

- **Roboflow** : `ROBOFLOW_API_KEY` (et éventuellement `ROBOFLOW_PROJECT`, `ROBOFLOW_VERSION`) dans le `.env`. Depuis le plan gratuit de PythonAnywhere, seules les sorties vers une liste de sites autorisés fonctionnent : si Roboflow n'est pas joignable, la détection répond « indisponible » et on place les prises à la main.
- **Modèle local** : `best.pt` à la racine et `pip install ultralytics` (hors plan gratuit : trop volumineux). `requirements-pythonanywhere.txt` ne l'inclut volontairement pas.

## Mises à jour des dépendances

`python scripts/check_updates.py` environ une fois par mois. Pour mettre à jour un paquet : changer sa version dans `requirements-pythonanywhere.txt` **et** `requirements.txt`, `pip install -r …`, `pytest`, puis pousser.
