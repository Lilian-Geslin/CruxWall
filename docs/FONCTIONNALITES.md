# Fonctionnalités

Cette page décrit ce que fait CruxWall et les règles qui s'appliquent. Les plafonds chiffrés sont réunis dans [LIMITES.md](LIMITES.md), les routes dans [API.md](API.md).

## Comptes

- **Inscription** (`/register`) : pseudo (3–30 caractères : lettres, chiffres, `_` et `-`), email, mot de passe (8 à 128 caractères), case d'acceptation des conditions obligatoire. Le pseudo et l'email sont uniques sans tenir compte de la casse. Un champ caché piège les robots (`company_url`) et un jeton daté signé exige que le formulaire ait été rempli en plus de 2 secondes (et moins de 6 heures). Après inscription la personne est connectée.
- **Connexion** (`/login`) : email + mot de passe. Même message d'erreur que le compte existe ou non (« Email ou mot de passe incorrect. ») et même durée de calcul. La session dure **30 jours**. Après connexion on revient à la page demandée (redirection interne uniquement).
- **Déconnexion** (`POST /logout`).
- **Réglages** (`/profil/settings`) : changer de pseudo (3 fois par 24 h maximum), d'email, de mot de passe. Chaque changement demande le mot de passe actuel (5 erreurs par 15 min maximum). Changer le mot de passe **déconnecte tous les autres appareils**.
- **Profil** (`/profil`) : informations du compte, notifications (marquées lues à l'ouverture).
- **Export** (`/profil/export`) : fichier JSON `cruxwall-mes-donnees.json` avec toutes les données conservées sur la personne (compte, murs et salles créés, blocs avec prises, ascensions, cotations proposées, notifications, signalements envoyés, carnet, favoris, « à faire », accès débloqués) ; 5 téléchargements par heure.
- **Suppression du compte** (`/profil/delete`) : mot de passe + case de confirmation ; choix de conserver ou supprimer ses murs et salles publics (voir [MODELE_DONNEES.md](MODELE_DONNEES.md#suppression-dun-compte-servicesdeletionpy)). Le dernier administrateur ne peut pas supprimer son compte.

## Salles

- Liste `/gyms` (ordre alphabétique sans casse). Une salle **privée** figure dans la liste mais son contenu (ses murs) reste caché sans code.
- Création : nom (≤ 100 caractères, **unique sans casse**), ville facultative (≤ 60), case « privée » (un code de 10 caractères est généré). Une **création rapide** (`/api/gym/quick_create`) permet de créer une salle depuis le formulaire de mur sans perdre le nom et la photo déjà saisis.
- Modification et suppression par le **créateur ou un admin**. Supprimer une salle supprime ses murs, avec leurs blocs et leurs photos.
- **Recherche dans la salle** : barre au-dessus du bouton « Nouveau mur ». Dès 2 caractères, un tableau déroulant propose **jusqu'à 25 murs et 50 blocs**, défilable au doigt ou à la souris. On cherche dans les noms de murs, les noms de blocs, les noms d'ouvreurs et le **début** d'une cotation (« 6a » trouve aussi 6a+). Valider la recherche affiche la page de la salle filtrée (jusqu'à 100 blocs). Seuls les murs que la personne a le droit de voir sont parcourus.
- Une salle peut être mise en **favori**.

## Murs

- **Création** : nom (≤ 100), salle (obligatoire), photo JPG/PNG/WEBP, case « privé ». La photo est vérifiée (vrai format), tournée selon l'EXIF, réduite à 1600 px et recompressée en JPEG (qualité 80) : les métadonnées, dont le GPS, disparaissent. Si le site a atteint son plafond de stockage de photos, la création est refusée sans laisser de fichier orphelin.
- **Mur privé** : un code de 10 caractères (alphabet sans `0`, `1`, `I`, `O`) est généré ; le créateur le voit et le partage. Pour un autre compte le mur est **invisible** (listes, recherche, API, photo) ; l'URL directe affiche seulement le formulaire de code. Le code est comparé sans tenir compte de la casse, des espaces et des tirets. Si la **salle** est privée, c'est elle qui décide : l'accès à la salle ouvre ses murs.
- **Modification** (créateur ou admin) : nom, salle, confidentialité, régénération du code. Renommer un mur met aussi à jour le carnet des personnes qui l'ont grimpé.
- **Suppression** : le mur, ses blocs, prises, cotations, ascensions, accès, favoris, notifications et sa photo (le carnet est conservé).
- **Page d'un mur** : photo, blocs triables et filtrables par tranche de difficulté, clic → page du bloc, bouton « Nouveau bloc », signalement, favori.
- **Inactivité** : un mur consulté ou modifié par une personne **connectée** est « actif » (écriture limitée à une fois par heure ; les robots et les visiteurs anonymes ne comptent pas). Sans activité pendant 173 jours le créateur reçoit une notification ; à 180 jours (et seulement après l'avertissement) le mur est supprimé.

## Blocs et éditeur

- **Éditeur** (`/wall/<id>/block/new`) sur la photo du mur : quatre types de prises — **départ** (vert), **intermédiaire** (bleu), **fin** (rouge), **pied uniquement** (jaune, « prise pied uniquement »). Un bloc a de **2 à 100 prises**. Les positions et tailles sont enregistrées en proportion de la photo (0 à 1).
- **Détection automatique** des prises : Roboflow (en ligne) en priorité, repli sur le modèle local YOLO (`best.pt`, s'il est installé), sinon placement manuel. Le résultat est **mis en cache dans le mur** : la deuxième personne qui ouvre le mur ne consomme plus aucun crédit. « Refaire la détection » force une nouvelle analyse (10 par heure et par compte, 100 par 24 h pour tout le site). Les échecs ne sont jamais mis en cache et le détail technique n'est jamais affiché.
- **Caractéristiques** : nom (≤ 100, unique par mur sans casse), cotation facultative (3a, 3a+, … 9c), couleur parmi 7, description (≤ 500), **lien** facultatif (≤ 300 ; http/https ; sans schéma on ajoute `https://` ; refusés : autres schémas comme `javascript:` ou `mailto:`, et les adresses contenant `@` avant le domaine). Le lien est affiché **cliquable sous le commentaire**, avec `rel="noopener"`.
- **Modification** (créateur ou admin) : tout sauf les prises. **Suppression** : prises, cotations, ascensions, favoris du bloc.
- Un bloc d'un mur inaccessible renvoie 404 (page et API).

## Cotation communautaire

Chaque compte peut proposer **une cotation** par bloc (modifiable). La cotation communautaire est le **mode** des votes, l'**ouvreur comptant pour un vote** (sa cotation d'ouverture) :

- égalité entre deux cotations **voisines** : affichage « 6a/+ » (pour 6a et 6a+) ou « 6a+/6b » ;
- égalité entre cotations **éloignées** : on garde celle qui est la plus proche de la cotation de l'ouvreur (sans ouvreur : de la moyenne des votes, la plus basse en cas d'égalité) ;
- aucun vote : « Aucune cotation pour l'instant. »

Le calcul est fait dans le navigateur par `communityGrade` (`static/js/pages/block-view.js`) et testé avec Node (`tests/unit/test_js.py`).

## Ascensions

Sur la page d'un bloc : **Fait** et **Flash** (le flash implique « fait »). Décocher retire la réussite. La date de première réussite (`done_at`) est conservée. Réussir un bloc le retire automatiquement de la liste « à faire ». Les ascensions de tous les comptes sont listées sur la page du bloc (flashs en premier).

## Mon espace : favoris, « à faire », carnet

Onglets `/favoris`, `/a-faire`, `/carnet` (partiel `_mytabs.html`).

- **Favoris** : murs (200 max), salles (200 max), blocs (200 max). Un mur devenu privé disparaît de la liste des personnes qui n'y ont plus accès.
- **À faire** : 500 blocs maximum ; liste personnelle.
- **Carnet de progression** : total, nombre et pourcentage de flashs, murs différents, bloc le plus dur et flash le plus dur, répartition par cotation, courbe des 12 derniers mois, journal par mois (150 dernières entrées). Il est alimenté par `climb_log` : **supprimer un bloc, un mur ou une salle ne change aucun chiffre**. Les entrées dont le bloc existe encore et reste visible sont cliquables.

## Recherche

- **Barre du haut** (`/search`, JSON) : dès 2 caractères, jusqu'à 12 résultats — murs (20 cherchés, filtrés par droits) puis salles. Les salles privées sont listées mais marquées.
- **Barre d'une salle** : voir plus haut.

## Signalements et modération

- Tout compte connecté peut **signaler un mur ou un bloc** qu'il peut voir : motif (personne reconnaissable, contenu inapproprié ou illégal, droits, informations personnelles, autre — « Autre » exige une précision de 5 caractères ou plus), précisions ≤ 500. Un signalement en attente par compte et par contenu ; 5 par heure et par compte, 20 par heure et par IP. Les administrateurs reçoivent une notification.
- **Page Admin** (`/admin`) : file des signalements (ignorer / supprimer le contenu, ce qui clôt tous les signalements en attente sur ce contenu et prévient son créateur), 30 derniers signalements traités, comptes (recherche par pseudo/email, 100 maximum, nombre de murs et de blocs), statistiques, nommer ou retirer un administrateur, supprimer un compte, journal des 60 dernières actions.
- **Journal** (`admin_log`) : toute action d'un admin sur le contenu d'autrui est tracée (suppression de mur, de bloc, de compte, droits, signalements) ; les actions faites depuis la console (`make_admin.py`) aussi. Conservé un an.
- Un admin a accès à tous les murs et salles, n'est soumis à aucun quota, et peut modifier / supprimer les contenus des autres.

## Notifications

Messages internes (pas d'email) : avertissement de suppression d'un mur inactif, suppression automatique, contenu supprimé suite à un signalement, nouveau signalement (admins). Pastille de non-lues dans le menu, pastille « Admin » pour les signalements ouverts.

## Pages légales

`/cgu`, `/confidentialite`, `/mentions-legales` : l'éditeur, l'adresse, l'email de contact et l'hébergeur viennent du `.env` (`LEGAL_*`) ; un rappel jaune s'affiche tant que l'éditeur ou le contact n'est pas renseigné.

## Confort

- **Flèche retour du mur** (`data-back`, `features/back-link.js`) : revient à la page d'où l'on vient (même site, page précédente de l'historique) ; sinon elle suit son lien de secours (la salle du mur, ou l'accueil). La flèche « ← Toutes les salles » de la page d'une salle est un **lien direct vers `/gyms`**, sans passer par l'historique.
- **Menu mobile** (bouton ☰), recherche en direct, confirmations avant les actions destructrices (`data-confirm`).
- **`/health`** : « ok » si le site et la base répondent (503 sinon), pour une surveillance externe.

## Exploitation

Sauvegarde quotidienne, nettoyage des murs inactifs, scripts en ligne de commande : voir [DEPLOIEMENT.md](DEPLOIEMENT.md).
