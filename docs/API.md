# Routes (pages et API JSON)

Toutes les routes qui **modifient** quelque chose sont en `POST` et exigent le **jeton CSRF** : champ de formulaire `csrf_token`, ou en-tête `X-CSRF-Token` (le JavaScript le lit dans `<meta name="csrf-token">` via `window.csrfToken()`). Sans jeton : `400`. Les routes marquées 🔒 exigent d'être connecté (sinon redirection vers `/login` ; pour une API `POST` sans jeton valide, `400`), 🛡 d'être administrateur (`403` sinon).

Les erreurs des routes `/api/…` sont en JSON `{"error": "message"}` ; celles des pages sont des pages HTML (voir [Codes d'erreur](#codes-derreur)).

## Pages publiques

| Méthode | Route | Rôle |
|---|---|---|
| GET | `/` | accueil : 12 derniers murs visibles et liste des salles |
| GET | `/health` | `ok` (200) ou `erreur` (503), `Cache-Control: no-store` |
| GET | `/cgu`, `/confidentialite`, `/mentions-legales` | pages légales |
| GET | `/media/<fichier>.jpg` | photo d'un mur (404 si interdit ou inexistant) |

## Compte

| Méthode | Route | Rôle |
|---|---|---|
| GET, POST | `/register` | inscription (champs : `name`, `email`, `password`, `accept_terms`, `form_ts`, piège `company_url`) |
| GET, POST | `/login` | connexion (`email`, `password`) |
| POST 🔒 | `/logout` | déconnexion |
| GET 🔒 | `/profil` | profil et notifications |
| GET, POST 🔒 | `/profil/settings` | `action` (`pseudo`, `email` ou `password`) + `current_password` + `new_pseudo` / `new_email` / `new_password` et `confirm_password` |
| GET 🔒 | `/profil/export` | export JSON (`Content-Disposition: attachment`) |
| GET, POST 🔒 | `/profil/delete` | suppression du compte (`password`, `confirm`, `delete_public`) |

## Salles

| Méthode | Route | Rôle |
|---|---|---|
| GET | `/gyms` | liste |
| GET | `/gym/<id>` | page (`?q=` : recherche, 2 caractères minimum, 100 maximum) |
| GET | `/gym/<id>/suggest?q=` | propositions : `{"walls": [{id, name}], "blocks": [{id, name, grade, wall, creator}]}` (25 murs et 50 blocs maximum ; listes vides sous 2 caractères ; 404 si la salle est privée et verrouillée) |
| POST 🔒 | `/gym/new` | création (`name`, `location`, `is_private`) |
| POST 🔒 | `/api/gym/quick_create` | création rapide → `{"success": true, "id", "name", "location", "access_code"}` ; erreurs `400` (nom vide, trop long, doublon) ou `429` (quota) |
| GET, POST 🔒 | `/gym/<id>/edit` | modification (créateur ou admin ; `regenerate_code`) |
| POST 🔒 | `/gym/<id>/unlock` | code d'accès (`code`) |
| POST 🔒 | `/gym/<id>/delete` | suppression avec tous ses murs (créateur ou admin) |
| POST 🔒 | `/gym/<id>/favorite` | ajoute / retire des favoris |

## Murs

| Méthode | Route | Rôle |
|---|---|---|
| GET | `/walls` | tous les murs visibles |
| GET | `/wall/<id>` | page du mur (ou formulaire de code si privé) |
| GET, POST 🔒 | `/wall/new` | création, `multipart/form-data` : `name`, `gym_id`, `is_private`, `image` (`?gym_id=` présélectionne la salle) |
| GET, POST 🔒 | `/wall/<id>/edit` | `name`, `gym_id`, `is_private`, `regenerate_code` |
| POST 🔒 | `/wall/<id>/unlock` | `code` ; `429` si trop d'essais |
| POST 🔒 | `/wall/<id>/delete` | suppression (créateur ou admin) |
| POST 🔒 | `/wall/<id>/favorite` | favori |
| POST 🔒 | `/api/wall/<id>/detect_holds` | détection des prises (`?force=1` : nouvelle analyse) |

`POST /api/wall/<id>/detect_holds` → `{"success": true, "holds": [{x, y, w, h}], "source": "roboflow" | "local", "cached": true?}` ; `429 {"error": "detection_limited"}` ; `500 {"error": "detection_unavailable"}` ; `404` (mur invisible ou photo manquante).

## Blocs

| Méthode | Route | Rôle |
|---|---|---|
| GET | `/block/<id>` | page du bloc |
| GET 🔒 | `/wall/<id>/block/new` | page de l'éditeur |
| POST 🔒 | `/api/block/save` | création (JSON ci-dessous) |
| GET, POST 🔒 | `/block/<id>/edit` | `name`, `grade`, `color`, `description`, `link` |
| POST 🔒 | `/block/<id>/delete` | suppression (créateur ou admin) → redirection vers le mur |
| POST 🔒 | `/block/<id>/favorite`, `/block/<id>/todo` | favori / « à faire » |
| GET | `/api/block/<id>/holds` | liste des prises |
| GET | `/api/block/<id>/full` | `{block, holds, notes, ascents, my_note, my_ascent, logged_in}` |

`POST /api/block/save` :

```json
{
  "wall_id": 1, "name": "Mon bloc", "grade": "6b", "color": "#3b82f6",
  "description": "Départ assis", "link": "https://exemple.fr/video",
  "holds": [{"x": 0.1, "y": 0.2, "type": "start", "w": 0.05, "h": 0.04}, {"x": 0.5, "y": 0.5, "type": "top"}]
}
```

`type` ∈ `start`, `mid`, `top`, `foot` ; `x`, `y` ∈ [0, 1] ; `w`, `h` facultatifs ∈ ]0, 1]. Succès : `{"success": true, "block_id": 12}`. Erreurs `400` avec message : « Nom et mur requis. », « Le nom est limité à 100 caractères. », « Cotation invalide. », « Couleur invalide. », « La description est limitée à 500 caractères. », message de lien, « Un bloc doit avoir au moins 2 prises. », « Un bloc ne peut pas avoir plus de 100 prises. », « Position de prise invalide. », « Type de prise invalide. », « Taille de prise invalide. », « Un bloc nommé "…" existe déjà sur ce mur. » ; `429` quota ; `404` mur introuvable ou inaccessible.

## Cotations et ascensions

| Méthode | Route | Corps / réponse |
|---|---|---|
| POST 🔒 | `/api/block/<id>/note` | `{"note": "6b"}` → `{"success": true, "message", "notes": [{note, user_name}]}` ; `400` si vide ou cotation inconnue |
| GET | `/api/block/<id>/notes` | `{"notes": [...], "my_note": "6b" \| null}` |
| POST 🔒 | `/api/block/<id>/ascent` | `{"done": bool, "flash": bool}` → `{"success": true, "ascents": [{user_name, done, flash}], "my_ascent": {done, flash}}` |
| GET | `/api/block/<id>/ascents` | `{"ascents": [...], "my_ascent": {...}}` |

Les quatre routes répondent `404` si le mur du bloc est invisible pour la personne.

## Mon espace

| Méthode | Route | Rôle |
|---|---|---|
| GET 🔒 | `/favoris` | murs, salles et blocs favoris |
| GET 🔒 | `/a-faire` | blocs « à faire » |
| GET 🔒 | `/carnet` | carnet de progression et statistiques |

Les routes de favori redirigent vers la page d'origine (en-tête `Referer`, même site seulement) ; au-delà de la limite : page « Limite atteinte » (`400`).

## Recherche

`GET /search?q=` → tableau JSON (12 éléments maximum) :
`{"type": "wall", "id", "name", "gym_name"}` ou `{"type": "gym", "id", "name", "is_private", "can_view"}` ; `[]` sous 2 caractères.

## Signalements

`POST 🔒 /report` : `target_type` (`wall` | `block`), `target_id`, `reason` (`person`, `inappropriate`, `rights`, `personal`, `other`), `details`. Réponse : page « Merci » (`200`), « Déjà signalé » (`200`), `400` (motif invalide, précision manquante pour « Autre », précisions trop longues), `429`, `404`.

## Administration 🛡

| Méthode | Route | Rôle |
|---|---|---|
| GET | `/admin` | page (`?q=` filtre les comptes) |
| POST | `/admin/report/<id>/dismiss` | ignorer (ou classer « déjà supprimé ») |
| POST | `/admin/report/<id>/remove` | supprimer le contenu signalé et prévenir son créateur |
| POST | `/admin/user/<id>/role` | `role` = `admin` ou `user` (`400` sur soi-même ou rôle invalide, `404` si inconnu) |
| POST | `/admin/user/<id>/delete` | supprimer le compte et ses contenus publics (`400` sur soi-même) |

## Codes d'erreur

| Code | Page | Quand |
|---|---|---|
| 400 | Requête invalide / Session expirée | jeton CSRF absent ou faux, corps invalide |
| 403 | Accès refusé | action réservée au créateur ou à l'admin sur un contenu **visible** |
| 404 | Page introuvable | inexistant **ou invisible** (mur privé, photo) : même réponse, on ne révèle rien |
| 405 | Action non autorisée | mauvaise méthode (ex. `GET` sur une route de suppression) |
| 409 | Conflit | contrainte d'unicité violée (deux créations simultanées) |
| 413 | Fichier trop volumineux | requête > 15 Mo |
| 429 | Trop de demandes | limitation d'essais, quotas |
| 500 | Erreur du serveur | message générique, détail uniquement dans le journal du serveur |

Aucune erreur n'affiche de détail technique ; les messages des routes `/api/…` sont en JSON.
