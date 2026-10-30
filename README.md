# CruxWall

Application web de **bouldering** : on prend en photo un mur d'escalade, on entoure les prises de mains et de pieds pour créer un **bloc**, puis on retrouve ses blocs, ses réussites et ses favoris dans son compte, avec toutes leurs caractéristiques (cotation, couleur, description, lien vidéo, cotation communautaire…).

Application **Flask + SQLite**, interface en français, sans framework JavaScript (JS « vanilla »). Hébergée sur PythonAnywhere (plan gratuit).

## Sommaire

1. [Installation et lancement](#installation-et-lancement)
2. [Fonctionnalités](#fonctionnalités)
3. [Structure du projet](#structure-du-projet)
4. [Architecture](#architecture)
5. [Configuration (.env)](#configuration-env)
6. [Sauvegarde et maintenance](#sauvegarde-et-maintenance)
7. [Déploiement](#déploiement)
8. [Tests](#tests)
9. [Documentation](#documentation)

## Installation et lancement

Prérequis : **Python 3.10+** (3.13 utilisé pour les tests).

```bash
python -m venv venv
source venv/bin/activate          # Windows : venv\Scripts\activate
pip install -r requirements.txt   # ou requirements-pythonanywhere.txt (sans détection IA locale)
```

Copier `.env.example` en **`.env`** à la racine (jamais versionné) et remplir au minimum :

```
FLASK_SECRET_KEY=une-longue-chaine-aleatoire-d-au-moins-32-caracteres
CRUXWALL_ENV=development
```

Puis :

```bash
python run.py
```

Le site est disponible sur <http://127.0.0.1:5000> (et sur le réseau Wi-Fi local, l'adresse est affichée au démarrage). La base `cruxwall.db` est créée au premier démarrage. Pour obtenir un compte administrateur : créer un compte sur le site, puis

```bash
python scripts/make_admin.py MonPseudo
```

> `CRUXWALL_ENV=development` est réservé à ton PC : il désactive le HTTPS forcé et le cookie « secure ». **Ne jamais le mettre sur le serveur.**

## Fonctionnalités

| Domaine | Contenu |
|---|---|
| **Salles et murs** | Salles (publiques ou privées avec code), murs avec photo recompressée, murs privés avec code d'accès de 10 caractères, recherche dans une salle avec propositions. |
| **Blocs** | Éditeur sur la photo : prises de départ, intermédiaires, de fin et **pieds uniquement** ; cotation 3a → 9c, couleur, description, lien (http/https) ; détection automatique des prises (Roboflow, puis modèle local). |
| **Communauté** | Cotation communautaire (mode des votes, ouvreur inclus), ascensions « fait » / « flash ». |
| **Mon compte** | Favoris (murs, salles, blocs), liste « à faire », **carnet de progression** persistant avec statistiques, export JSON de ses données, suppression du compte. |
| **Modération** | Signalements, page d'administration, journal des actions d'admin, notifications. |
| **Sécurité** | CSRF, CSP avec nonce, HSTS, limitation des tentatives en base, murs privés invisibles (404), photos servies avec contrôle d'accès. |
| **Exploitation** | Sauvegarde et nettoyage automatiques une fois par jour, murs inactifs supprimés après 180 jours (avertissement à 173). |

Détail complet : [docs/FONCTIONNALITES.md](docs/FONCTIONNALITES.md) · limites : [docs/LIMITES.md](docs/LIMITES.md).

## Structure du projet

```
cruxwall/
├── run.py                      # point d'entrée (python run.py) et objet WSGI `app`
├── requirements.txt            # dépendances complètes (PC) : + ultralytics
├── requirements-pythonanywhere.txt  # dépendances du serveur (sans ultralytics)
├── requirements-dev.txt        # + pytest et pytest-cov
├── pytest.ini
├── README.md
├── .env.example                # modèle de réglages (à copier en .env)
├── .env                        # réglages secrets (jamais versionné)
├── cruxwall.db                 # base SQLite (créée au démarrage, jamais versionnée)
├── uploads/                    # photos des murs (jamais versionné, servi par /media)
├── backups/                    # sauvegardes automatiques (jamais versionné)
├── docs/                       # documentation détaillée
├── scripts/                    # outils en ligne de commande
│   ├── make_admin.py  check_env.py  check_updates.py  setup_db.py
│   └── backup_db.py  cleanup_inactive_walls.py  daily_maintenance.py
├── src/
│   ├── __init__.py             # fabrique d'application : create_app()
│   ├── config.py  constants.py # réglages, limites, quotas, cotations
│   ├── db.py  schema.py        # connexion SQLite, tables et migrations
│   ├── auth.py  security.py    # session, CSRF, en-têtes, journaux
│   ├── errors.py  templating.py
│   ├── routes/                 # couche HTTP (un blueprint par domaine)
│   │   ├── public.py  auth.py  profile.py  legal.py  media.py  search.py
│   │   ├── gyms.py  walls.py  blocks.py  ascents.py  favorites.py
│   │   └── reports.py  admin.py  detection.py
│   ├── services/               # logique métier
│   │   ├── access.py  ratelimit.py  quotas.py  antibot.py  validation.py
│   │   ├── images.py  holds.py  search.py  activity.py  climb_log.py
│   │   ├── deletion.py  admin_log.py  detection.py  legal.py
│   │   └── backup.py  cleanup.py  maintenance.py
│   ├── templates/              # base.html, auth/, pages/, partials/
│   └── static/                 # css/ (par thème), js/{core,features,pages}/, fonts/
└── tests/
    ├── conftest.py  helpers.py #   fixtures (base temporaire, clients connectés) et fabriques
    ├── unit/                   #   fonctions pures, schéma, configuration, scripts, JavaScript
    ├── services/               #   logique métier sur une base SQLite temporaire
    └── routes/                 #   pages et API via le client de test Flask
```

## Architecture

- **Trois couches** : *routes* (HTTP) → *services* (règles métier) → *SQLite*. `get_db()` ouvre une connexion par appel, l'appelant la ferme et fait lui-même le `commit`.
- **Fabrique d'application** : `create_app(config=None)` assemble configuration, base, sécurité, gestion d'erreurs, maintenance, templates et blueprints. Les tests lui passent une configuration temporaire.
- **Un blueprint par domaine**, nommé comme son module (`walls.wall`, `media.media`…).
- **Front** : pages rendues côté serveur (Jinja2) ; JS sans compilation, scripts chargés dans `base.html`.

Voir [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Configuration (.env)

| Variable | Rôle | Défaut |
|---|---|---|
| `FLASK_SECRET_KEY` | Clé de signature des sessions (**obligatoire**, 16 caractères minimum) | — |
| `CRUXWALL_ENV` | `development` sur le PC ; **absent** sur le serveur | production |
| `TRUST_PROXY` | `1` sur le serveur : lit la vraie IP du visiteur (limitations d'essais) | non |
| `FORCE_HTTPS` | `0` pour désactiver la redirection HTTP → HTTPS (production) | actif |
| `AUTO_MAINTENANCE` | `0` désactive la sauvegarde/nettoyage automatiques | actif |
| `ROBOFLOW_API_KEY`, `ROBOFLOW_PROJECT`, `ROBOFLOW_VERSION` | Détection en ligne des prises | clé absente → modèle local |
| `DETECT_DAILY_LIMIT` | Analyses de détection par 24 h pour tout le site | 100 |
| `MAX_UPLOADS_MB` | Plafond total des photos sur le disque | 350 |
| `BACKUP_DIR` | Dossier des sauvegardes | `backups/` |
| `SQLITE_WAL` | `1` : mode WAL (seulement si l'hébergeur le supporte) | non |
| `CRUXWALL_DATABASE` | Chemin du fichier SQLite | `cruxwall.db` à la racine |
| `LEGAL_PUBLISHER_NAME`, `LEGAL_PUBLISHER_ADDRESS`, `LEGAL_CONTACT_EMAIL`, `LEGAL_HOST` | Pages légales | hébergeur : PythonAnywhere |

`python scripts/check_env.py` vérifie le `.env` du serveur sans jamais afficher de secret.

## Sauvegarde et maintenance

Sur le plan gratuit de PythonAnywhere il n'y a pas de tâche planifiée : **la première visite de la journée** déclenche, après l'envoi de la réponse, 1) la sauvegarde (base conservée 14 jours, photos le dimanche, 2 archives conservées, ignorées au-delà de 100 Mo) puis 2) le nettoyage des murs inactifs. Un fichier-repère `backups/.maintenance-AAAA-MM-JJ` évite tout doublon entre processus. Les sauvegardes restent **sur le serveur** : télécharge-les régulièrement ailleurs (onglet *Files*).

À la main : `python scripts/daily_maintenance.py` (ou `backup_db.py` / `cleanup_inactive_walls.py` séparément).

## Déploiement

Résumé : `git pull` sur PythonAnywhere, fichier WSGI `from run import app as application`, **Reload**. Guide pas à pas, y compris la migration depuis l'ancienne structure « à plat » : [docs/DEPLOIEMENT.md](docs/DEPLOIEMENT.md).

## Tests

```bash
pip install -r requirements-dev.txt
pytest                                   # toute la suite (~700 tests, une minute)
pytest tests/unit                        # fonctions pures (très rapide)
pytest -k recherche                      # tests dont le nom contient « recherche »
pytest --cov=src --cov-report=term-missing   # couverture
```

Chaque test travaille sur une base SQLite temporaire neuve : `tests/conftest.py` redirige base, photos et sauvegardes vers un dossier temporaire, **ta vraie base n'est jamais touchée**. La suite couvre ≈ 96 % du code (la détection IA réelle et le réseau sont simulés).

| Dossier | Contenu |
|---|---|
| `tests/unit/` | constantes, validation, prises, schéma et migrations d'une ancienne base, configuration, filtre de journaux, scripts en ligne de commande, syntaxe de tous les fichiers JS et cotation communautaire (exécutée avec Node si présent) |
| `tests/services/` | limitation des tentatives, droits d'accès, quotas, anti-robots, photos (formats, bombes, EXIF), activité, journal admin, recherche, suppression de compte, détection (simulée), sauvegarde, nettoyage, maintenance quotidienne |
| `tests/routes/` | accueil, authentification, profil, sécurité, médias, légal, recherche, salles, murs, blocs, ascensions, favoris/carnet, signalements, administration, détection, pages d'erreur |

## Documentation

| Fichier | Contenu |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | couches, cycle d'une requête, modules, front |
| [docs/FONCTIONNALITES.md](docs/FONCTIONNALITES.md) | toutes les fonctionnalités, règles métier |
| [docs/MODELE_DONNEES.md](docs/MODELE_DONNEES.md) | tables, colonnes, relations, suppressions |
| [docs/API.md](docs/API.md) | toutes les routes (pages et JSON) |
| [docs/SECURITE.md](docs/SECURITE.md) | mesures de sécurité et protection de la vie privée |
| [docs/LIMITES.md](docs/LIMITES.md) | tous les plafonds et délais |
| [docs/DEPLOIEMENT.md](docs/DEPLOIEMENT.md) | PythonAnywhere, mises à jour, migration |
| [docs/GUIDE_UTILISATEUR.md](docs/GUIDE_UTILISATEUR.md) | mode d'emploi pour les grimpeurs |
