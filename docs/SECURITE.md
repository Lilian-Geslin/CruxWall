# Sécurité et vie privée

## Sessions et comptes

- Mots de passe stockés **hachés** (Werkzeug), 8 à 128 caractères. À la connexion, un calcul de hachage est toujours fait (même sans compte) et le message d'erreur est identique : impossible de deviner quels emails existent.
- Cookie de session `HttpOnly`, `SameSite=Lax`, `Secure` en production, durée **30 jours**. Clé `FLASK_SECRET_KEY` obligatoire (l'application refuse de démarrer sans elle).
- À **chaque requête**, le compte est relu en base : compte supprimé → déconnecté ; rôle changé → appliqué tout de suite ; `session_version` différente (mot de passe changé ailleurs) → déconnecté. Changer son mot de passe déconnecte donc les autres appareils.
- Redirections après connexion : adresses internes uniquement (`safe_next_url`, `safe_referrer`).

## Protection contre les attaques web

| Mesure | Détail |
|---|---|
| **CSRF** | jeton de session obligatoire sur tout `POST/PUT/PATCH/DELETE` (champ `csrf_token` ou en-tête `X-CSRF-Token`) |
| **CSP** | `default-src 'self'` ; scripts : `'self'` + **nonce** par requête (aucun script en ligne non signé) ; styles `'self' 'unsafe-inline'` ; images `'self' data: blob:` ; `connect-src 'self'` ; `object-src 'none'` ; `frame-ancestors 'none'` ; `form-action 'self'` |
| **En-têtes** | `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy` (géolocalisation, micro, paiement désactivés), **HSTS** 180 jours en production |
| **HTTPS** | redirection 301 si `X-Forwarded-Proto: http` (production, `FORCE_HTTPS` ≠ 0) |
| **XSS** | Jinja2 échappe tout ; les textes de confirmation passent par `data-confirm` (jamais injectés dans du JavaScript) ; liens utilisateur limités à http/https |
| **Injection SQL** | requêtes paramétrées ; motifs `LIKE` échappés (`%` et `_` saisis sont des caractères ordinaires) |
| **Redirection ouverte** | `next`/`Referer` acceptés seulement s'ils sont internes |
| **Clickjacking** | `X-Frame-Options: DENY` et `frame-ancestors 'none'` |

## Limitation des abus (table `auth_attempt`)

Compteurs **en base** (PythonAnywhere lance plusieurs processus ; la mémoire ne suffirait pas). Avec `TRUST_PROXY=1` l'adresse IP est lue dans `X-Real-IP` puis `X-Forwarded-For` (dernière adresse, celle ajoutée par le proxy de confiance) ; sans ce réglage les en-têtes sont ignorés.

| Action | Limite |
|---|---|
| Connexion | 5 échecs / 15 min par couple (email + IP) ; 50 par IP ; 100 par email |
| Inscription | 50 par heure et par IP + piège à robots + jeton daté |
| Code d'accès (mur / salle) | 10 échecs / 15 min par compte ; 40 / heure par IP |
| Réglages du compte | 5 mots de passe actuels faux / 15 min ; 3 changements de pseudo / 24 h |
| Suppression du compte | 5 mots de passe faux / 15 min |
| Export de données | 5 / heure |
| Signalements | 5 / heure par compte ; 20 / heure par IP |
| Détection des prises | 10 / heure par compte ; 100 / 24 h au total (`DETECT_DAILY_LIMIT`) |
| Créations | quotas par compte, voir [LIMITES.md](LIMITES.md) |

Dépasser une limite donne `429` (message « Trop de tentatives. Réessayez dans quelques minutes. »). Un succès remet à zéro le compteur concerné.

## Contenus privés

- Un mur privé (ou dans une salle privée) est **invisible** sans accès : absent des listes, de la recherche, des propositions, de l'API, des favoris et du carnet (non cliquable), et sa photo répond 404. Le refus est **identique à un contenu inexistant** (404) : on ne révèle pas qu'il existe.
- `forbid_or_hide` : une action réservée au créateur donne **403** si le contenu est visible, **404** sinon.
- Codes d'accès de **10 caractères** tirés avec `secrets` dans un alphabet de 32 signes (≈ 10¹⁵ possibilités), comparés en temps constant (`compare_digest`), tolérants à la casse, aux espaces et aux tirets.
- Les photos ne sont jamais dans `static/` : elles passent par `/media/<nom>.jpg` (nom de 32 caractères hexadécimaux validé par expression régulière) avec contrôle d'accès ; cache `private` pour un mur privé, `public` sinon.

## Photos

Vrai format vérifié (PNG, JPEG, WEBP), taille de requête ≤ 15 Mo, ≤ 40 mégapixels (protection contre les « bombes de décompression »), rotation EXIF appliquée, réduction à 1600 px, **ré-encodage JPEG** : tout contenu caché et toutes les métadonnées (GPS compris) sont supprimés. Plafond global de stockage (350 Mo par défaut).

## Journaux et secrets

- `RedactSecretsFilter` remplace par `***` les valeurs de `api_key=`, `token=`, `secret=`, `password=` dans tous les messages de journal.
- Les erreurs 500 n'affichent aucun détail ; l'échec de la détection n'expose pas le message technique de Roboflow.
- Le `.env` contient les secrets : **jamais versionné** (`.gitignore`), droits `600` conseillés ; `python scripts/check_env.py` le vérifie sans afficher les valeurs.
- Le débogueur interactif de Werkzeug est désactivé même en développement (`use_debugger=False`).

## Vie privée

- Données conservées : pseudo, email, mot de passe haché, date d'acceptation des conditions, contenus créés, réussites, favoris, carnet, notifications. Aucun traceur, aucune police ni script externes (la CSP n'autorise que le site lui-même ; Roboflow n'est appelé que **depuis le serveur**).
- Droit d'accès : export JSON (`/profil/export`). Droit à l'effacement : suppression du compte (`/profil/delete`), qui efface les données personnelles ; les sauvegardes de sécurité disparaissent d'elles-mêmes sous 14 jours.
- Signalement des photos montrant une personne reconnaissable ou des informations personnelles ; modération par les administrateurs, avec journal des actions.
- Pages légales (`/cgu`, `/confidentialite`, `/mentions-legales`) renseignées par le `.env`.

## Dépendances

Versions **épinglées** (voir `requirements-pythonanywhere.txt`). `python scripts/check_updates.py` (environ une fois par mois) liste les mises à jour disponibles et, si `pip-audit` est installé, les failles connues ; il ne modifie rien.

## Vérifié par les tests

`tests/routes/test_security.py` (CSRF, CSP, en-têtes, HTTPS, honeypot, `session_version`…), `test_auth.py`, `test_media.py`, `test_walls.py` / `test_blocks.py` (murs privés invisibles), `tests/services/test_services.py` (droits, limites, photos, bombes), `tests/unit/test_schema_config.py` (filtre de journaux).
