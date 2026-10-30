# Limites et délais

Toutes les valeurs sont dans `src/constants.py` (sauf mention contraire). Les administrateurs sont exemptés des quotas de création.

## Textes

| Élément | Limite |
|---|---|
| Nom de salle, de mur, de bloc | 100 caractères |
| Ville d'une salle | 60 caractères |
| Description d'un bloc | 500 caractères |
| Lien d'un bloc | 300 caractères |
| Précisions d'un signalement | 500 caractères (« Autre » : 5 caractères minimum) |
| Pseudo | 3 à 30 caractères (`A-Za-z0-9_-`) |
| Mot de passe | 8 à 128 caractères |
| Texte cherché | 2 caractères minimum, 100 maximum |

## Contenus

| Élément | Limite |
|---|---|
| Murs par compte | 250 au total, 50 par 24 h |
| Salles par compte | 100 au total, 25 par 24 h |
| Blocs par compte | 500 au total, 100 par 24 h |
| Prises par bloc | 2 minimum, 100 maximum |
| Favoris | 200 murs, 200 salles, 200 blocs |
| Blocs « à faire » | 500 |
| Propositions de recherche de salle | 25 murs et 50 blocs |
| Résultats de la page d'une salle recherchée | 100 blocs |
| Recherche globale (barre du haut) | 12 résultats |
| Page d'accueil | 12 murs |

## Photos

| Élément | Limite |
|---|---|
| Taille de la requête | 15 Mo |
| Définition | 40 mégapixels maximum |
| Après traitement | 1600 px maximum, JPEG qualité 80 |
| Stockage total sur le serveur | 350 Mo (`MAX_UPLOADS_MB`) |

## Tentatives (voir aussi [SECURITE.md](SECURITE.md))

| Action | Limite |
|---|---|
| Connexion | 5 échecs / 15 min (email + IP), 50 par IP, 100 par email |
| Inscription | 50 / heure par IP |
| Code d'accès | 10 / 15 min par compte, 40 / heure par IP |
| Signalements | 5 / heure par compte, 20 / heure par IP |
| Détection des prises | 10 / heure par compte, 100 / 24 h pour le site (`DETECT_DAILY_LIMIT`) |
| Changement de pseudo | 3 / 24 h |
| Mot de passe actuel faux (réglages) | 5 / 15 min |
| Export de ses données | 5 / heure |

## Délais

| Élément | Valeur |
|---|---|
| Session | 30 jours |
| Formulaire d'inscription | rempli en plus de 2 s et moins de 6 h |
| Mise à jour de l'activité d'un mur | au plus une fois par heure |
| Avertissement avant suppression d'un mur inactif | 173 jours sans activité |
| Suppression d'un mur inactif | 180 jours (et seulement après l'avertissement) |
| Sauvegardes de la base | 14 jours conservés |
| Archives des photos | le dimanche, 2 conservées, ignorées au-delà de 100 Mo |
| Journal d'administration | 1 an |
| Compteurs d'essais | purgés après 24 h |
| Cache d'une photo | 1 h (mur privé) ou 24 h (mur public) |
| HSTS | 180 jours |
