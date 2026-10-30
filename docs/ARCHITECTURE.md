# Architecture

## Vue d'ensemble

```
navigateur ──HTTP──▶ Flask (create_app)
                       │  before_request : HTTPS, CSRF, relecture du compte
                       ▼
                    routes/ (blueprints)   lit la requête, vérifie les droits, appelle un service, répond
                       │
                       ▼
                    services/              règles métier, requêtes SQL, fichiers
                       │
                       ▼
              SQLite (cruxwall.db)   +   uploads/ (photos JPEG)   +   backups/
                       ▲
                       │  after_request : en-têtes de sécurité, maintenance quotidienne
```

- Une **route** ne contient que de la coordination (lecture du formulaire, droits, réponse). Les règles réutilisables vivent dans `services/`.
- Un **service** ne connaît Flask que pour `session`/`request`/`current_app` quand c'est inévitable (droits, quotas) ; les tests le simulent avec un contexte de requête.
- La base est **SQLite**, une connexion par appel de `get_db()`. L'appelant fait `conn.commit()` et `conn.close()`.

## La fabrique d'application (`src/__init__.py`)

`create_app(config=None)` :

1. crée `Flask`, charge `Config` puis impose `SECRET_KEY` (lue dans `FLASK_SECRET_KEY`, refus de démarrer si absente ou < 16 caractères) ;
2. applique le dictionnaire `config` en dernier (c'est ce que font les tests : base, photos et sauvegardes temporaires) ;
3. crée le dossier des photos, déplace les anciennes photos de `src/static/uploads/` vers `uploads/`, puis `init_db` crée / met à jour les tables ;
4. branche : `templating`, `security`, `maintenance`, gestionnaires d'erreurs, blueprints.

`run.py` appelle `create_app()` et expose `app` : c'est l'objet que lit le serveur WSGI de PythonAnywhere (`from run import app as application`).

## Cycle d'une requête

1. **Avant** (`security.security_checks`) : redirection HTTPS si `X-Forwarded-Proto: http` (hors développement) ; pour toute requête qui modifie (POST/PUT/PATCH/DELETE), contrôle du jeton CSRF ; relecture du compte en base (compte supprimé → déconnexion, mot de passe changé ailleurs → déconnexion, changement de rôle appliqué tout de suite).
2. **Route** : décorateurs `login_required` / `admin_required`, validation (`services/validation.py`), droits (`services/access.py`), quotas, écriture.
3. **Réponse** : template Jinja2 ou JSON.
4. **Après** : en-têtes de sécurité (CSP avec nonce, HSTS en production…) puis, une fois par jour, planification de la maintenance (exécutée à la fermeture de la réponse).

## Modules

### Racine de `src/`

| Fichier | Rôle |
|---|---|
| `config.py` | chemins, mode (`IS_DEV`), `FORCE_HTTPS`, `AUTO_MAINTENANCE`, limites photo, clé secrète |
| `constants.py` | cotations, limites, quotas, délais, couleurs, motifs de signalement |
| `db.py` | `connect(path)` (clés étrangères activées, timeout 10 s), `get_db()` |
| `schema.py` | `init_db` : création idempotente des tables, migrations (`ALTER TABLE`), index uniques |
| `auth.py` | `login_required`, `admin_required`, `start_session`, hachage factice (anti-énumération de comptes) |
| `security.py` | CSRF, contrôles avant requête, en-têtes, filtre de masquage des secrets dans les journaux |
| `errors.py` | pages d'erreur HTML / JSON (`/api/…`), `notice_page` |
| `templating.py` | version des fichiers statiques (`?v=`), variables communes aux templates, `image_url` |

### `routes/` (un blueprint par domaine)

| Module | Contenu |
|---|---|
| `public` | accueil, `/health` |
| `auth` | connexion, inscription, déconnexion |
| `profile` | profil et notifications, réglages du compte, export JSON, suppression du compte |
| `gyms` | liste, page (recherche et propositions), création (normale et rapide), modification, déblocage, suppression |
| `walls` | liste, page, création avec photo, modification, déblocage, suppression |
| `blocks` | page, éditeur, enregistrement, modification, suppression, données des prises |
| `ascents` | cotations proposées et ascensions (fait / flash) |
| `favorites` | favoris, « à faire », carnet de progression |
| `search` | recherche globale (barre du haut) |
| `media` | service des photos avec contrôle d'accès |
| `reports` | signalements |
| `admin` | page d'administration, rôles, comptes, signalements |
| `detection` | détection des prises sur la photo |
| `legal` | CGU, confidentialité, mentions légales |

### `services/`

| Module | Rôle |
|---|---|
| `validation` | nettoyage de texte, entiers/flottants, liens, redirections sûres |
| `access` | qui voit quoi (salle, mur, bloc), codes d'accès, 404 pour l'invisible |
| `ratelimit` | compteurs d'essais en base (`auth_attempt`), IP du visiteur |
| `quotas` | plafonds de création par compte, taille totale des photos |
| `antibot` | jeton daté signé du formulaire d'inscription |
| `images` | vérification et recompression des photos, migration des anciennes |
| `holds` | validation de la liste des prises envoyée par l'éditeur |
| `search` | recherche dans une salle (murs, blocs, cotation, ouvreur), motifs `LIKE` échappés |
| `activity` | date de dernière activité d'un mur |
| `climb_log` | carnet de progression (copie durable) |
| `deletion` | suppression en cascade d'un bloc, d'un mur, d'un compte |
| `admin_log` | journal des actions d'administration |
| `detection` | Roboflow (en ligne) puis YOLO local |
| `backup` / `cleanup` / `maintenance` | sauvegarde, nettoyage des murs inactifs, déclenchement quotidien |
| `legal` | informations légales lues dans le `.env` |

## Front

- **Templates** : `base.html` (en-tête, menu, recherche, scripts communs) ; `auth/` (connexion, inscription) ; `pages/` (une page = un fichier) ; `partials/` (onglets « Mon espace », formulaire de signalement).
- **JavaScript** (`static/js/`) : `core/csrf.js` (jeton CSRF, confirmations `data-confirm`), `features/` (menu mobile, recherche globale, recherche de salle avec propositions, flèche retour intelligente), `pages/` (éditeur de blocs, page d'un mur, page d'un bloc avec cotation communautaire). Pas de compilation.
- **CSS** (`static/css/`) : un fichier par thème (base, header, menu, boutons, accueil, salles, murs, blocs, éditeur, favoris, profil, admin, responsive…), chargés dans l'ordre de `base.html` (l'ordre compte en CSS).
- **Polices** : fichiers locaux dans `static/fonts/` (aucune requête vers un site externe : la CSP n'autorise que `'self'`).

## Photos

Les photos ne sont **jamais** dans `static/` : elles sont dans `uploads/` et servies par `/media/<nom>.jpg` (nom = 32 caractères hexadécimaux + `.jpg`), uniquement à qui peut voir le mur correspondant (sinon 404). À l'envoi, la photo est vérifiée (vrai format PNG/JPEG/WEBP, nombre de pixels), tournée selon l'EXIF, réduite à 1600 px maximum et réencodée en JPEG qualité 80 : les métadonnées (dont le GPS) disparaissent.

## Maintenance automatique

`services/maintenance.py` : après chaque requête, si la journée n'a pas encore été traitée par ce processus, tente de créer le fichier-repère `backups/.maintenance-AAAA-MM-JJ` en exclusivité ; **un seul processus par jour** réussit et lance alors, à la fermeture de la réponse, la sauvegarde puis le nettoyage. Sont ignorés : fichiers statiques, `/media/…`, `/health`. Une étape qui échoue n'empêche pas l'autre. Voir [DEPLOIEMENT.md](DEPLOIEMENT.md).
