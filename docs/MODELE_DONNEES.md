# Modèle de données

Base SQLite `cruxwall.db`, créée et mise à jour par `src/schema.py` (`init_db`, idempotente : `CREATE TABLE IF NOT EXISTS` + `ALTER TABLE` pour les colonnes récentes, sans jamais effacer de données). Les clés étrangères sont activées à chaque connexion (`PRAGMA foreign_keys = ON`).

## Schéma relationnel

```
user ─┬─< gym ─┬─< wall ──< block ──< hold
      │        │      │        ├──< ascent  >── user
      │        │      │        ├──< block_note >── user
      │        │      │        ├──< block_favorite / block_todo >── user
      │        │      ├──< wall_access >── user     (code débloqué)
      │        │      └──< wall_favorite >── user
      │        ├──< gym_access >── user
      │        └──< gym_favorite >── user
      ├──< climb_log            (carnet de progression, copie durable)
      ├──< notification
      ├──< report (reporter)
      └──< admin_log (admin)    auth_attempt : compteurs anti-abus
```

## Tables

### `user`
| Colonne | Type | Remarque |
|---|---|---|
| `id` | INTEGER PK | |
| `name` | TEXT | pseudo, 3–30 caractères `A-Za-z0-9_-`, **unique sans tenir compte de la casse** |
| `email` | TEXT | **unique sans tenir compte de la casse** |
| `password` | TEXT | hachage Werkzeug (jamais le mot de passe) |
| `role` | TEXT | `user` (défaut) ou `admin` |
| `terms_accepted_at` | TIMESTAMP | date d'acceptation des conditions à l'inscription |
| `session_version` | INTEGER | augmente quand le mot de passe change : déconnecte les autres appareils |

### `gym` (salle)
`id`, `name` (unique sans casse), `location`, `created_by` → `user`, `is_private` (0/1), `access_code` (10 caractères si privée, sinon NULL).

### `wall` (mur)
`id`, `gym_id` → `gym`, `name`, `image_filename` (`<32 hex>.jpg`), `created_at`, `created_by` → `user`, `is_private`, `access_code`, `last_activity_at`, `warning_sent_at` (avertissement de suppression envoyé), `detected_holds` (JSON des prises détectées, mis en cache), `detected_source` (`roboflow` ou `local`), `detected_at`, `ai_disabled` (réservé, non utilisé par l'interface actuelle).

### `block` (bloc)
`id`, `wall_id` → `wall`, `name` (**unique par mur, sans casse**), `grade` (cotation d'ouverture, `3a`…`9c`, peut être vide), `color` (une des 7 couleurs autorisées), `description` (≤ 500), `link` (http/https, ≤ 300), `created_by`, `created_at`.

### `hold` (prise d'un bloc)
`id`, `block_id`, `x`, `y` (position en proportion de la photo, entre 0 et 1), `hold_type` (`start`, `mid`, `top`, `foot`), `w`, `h` (taille en proportion, facultatives).

### `ascent` (réussite)
`id`, `block_id`, `user_id`, `done`, `flash` (le flash implique « fait »), `created_at`, `done_at` (date de la première réussite, conservée si on repasse de « fait » à « flash »). Une ligne par couple compte/bloc.

### `block_note` (cotation proposée)
`id`, `block_id`, `user_id`, `note` (une cotation de la liste), `created_at`. Un vote par compte et par bloc (mise à jour si le compte revote).

### `climb_log` (carnet de progression)
Clé primaire `(user_id, block_id)`. `wall_id`, `block_name`, `wall_name`, `grade`, `flash`, `done_at`. **Copie durable** des réussites : elle n'a pas de clé étrangère vers `block`/`wall`, donc supprimer un bloc, un mur ou une salle ne change **aucun chiffre** du carnet. Seule la personne qui décoche sa réussite retire la ligne ; elle est supprimée en cascade avec le compte. Le nom du bloc/mur et la cotation y sont mis à jour quand le bloc ou le mur est modifié.

### Favoris et « à faire »
`wall_favorite(user_id, wall_id)`, `gym_favorite(user_id, gym_id)`, `block_favorite(user_id, block_id)`, `block_todo(user_id, block_id)` — clé primaire composite, `created_at`, **suppression en cascade** avec le compte et avec l'élément.

### Accès aux contenus privés
`wall_access(wall_id, user_id, granted_at)` et `gym_access(gym_id, user_id, granted_at)` : qui a débloqué quel mur / quelle salle avec le code.

### `notification`
`id`, `user_id`, `wall_id` (peut être NULL), `message`, `created_at`, `read_at` (NULL = non lue). Les notifications sont marquées lues à l'ouverture du profil.

### `report` (signalement)
`id`, `reporter_id`, `target_type` (`wall` ou `block`), `target_id`, `target_name`, `wall_id`, `reason` (`person`, `inappropriate`, `rights`, `personal`, `other`), `details` (≤ 500), `status` (`open`, `dismissed`, `removed`, `gone`), `created_at`, `handled_by`, `handled_at`.

### `admin_log`
`id`, `admin_id`, `admin_name`, `action` (≤ 100), `target` (≤ 200), `details` (≤ 500), `created_at`. Les lignes de plus de 365 jours sont purgées à chaque écriture.

### `auth_attempt`
`id`, `bucket` (ex. `login:ip:1.2.3.4`, `quota:wall:7`, `unlock:user:7`), `ts` (secondes Unix). Sert à **toutes** les limitations (connexion, inscription, déblocage, signalements, détection, quotas journaliers, changements de pseudo…). Stockée en base et non en mémoire : PythonAnywhere lance plusieurs processus. Les lignes de plus de 24 h sont purgées à chaque enregistrement.

## Index

| Index | Rôle |
|---|---|
| `uq_user_name_ci` | pseudo unique sans casse |
| `uq_user_email_ci` | email unique sans casse |
| `uq_gym_name_ci` | nom de salle unique sans casse |
| `uq_block_wall_name_ci` | nom de bloc unique par mur, sans casse |
| `idx_auth_attempt(bucket, ts)` | comptage rapide des essais |
| `idx_admin_log_date(created_at)` | purge et affichage |
| `idx_report_status(status, created_at)` | file des signalements |

## Suppressions

| Quand | Ce qui est supprimé |
|---|---|
| Un **bloc** | prises, ascensions, cotations, favoris et « à faire » de ce bloc (`climb_log` conservé) |
| Un **mur** | ses blocs (comme ci-dessus), les accès débloqués, les favoris du mur, la **photo**, les notifications liées ; les signalements en attente passent à `gone` |
| Une **salle** | tous ses murs (comme ci-dessus), les accès débloqués, les favoris de la salle |
| Un **compte** | voir ci-dessous |
| Un mur **inactif 180 jours** | comme un mur, plus une notification au créateur |

### Suppression d'un compte (`services/deletion.py`)
- Murs créés : les **privés** (ou situés dans une salle privée) sont toujours supprimés ; les **publics** seulement si la personne coche « supprimer aussi mes contenus publics », sinon ils restent **sans créateur** (`created_by = NULL`).
- Salles créées : même règle, mais une salle qui contient encore des murs d'autres personnes n'est jamais supprimée (elle reste sans créateur).
- Blocs créés (sur n'importe quel mur), ascensions, cotations, carnet, notifications, accès débloqués, signalements envoyés, compteurs anti-abus du compte : supprimés. Le dernier administrateur ne peut pas supprimer son compte.

## Migration

`init_db` ajoute les colonnes manquantes des anciennes bases (`ai_disabled`, `last_activity_at`, `warning_sent_at`, `is_private`, `access_code`, `created_by` des salles, `link`, `w`/`h` des prises, `detected_*`, `terms_accepted_at`, `session_version`, `done_at`), crée les tables récentes et reconstruit le carnet (`climb_log`) à partir des ascensions lorsque la table est créée pour la première fois. Cela se fait **automatiquement à chaque démarrage** ; `python scripts/setup_db.py` fait la même chose à la demande.
