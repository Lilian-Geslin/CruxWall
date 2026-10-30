"""Création et mise à jour du schéma de la base (tables, index, migrations).

`init_db` est idempotent : appelée à chaque démarrage de l'application, elle crée ce qui manque et ajoute les
colonnes des versions récentes (CREATE TABLE IF NOT EXISTS + ALTER TABLE), sans jamais effacer de données.
La description de chaque table se trouve dans docs/MODELE_DONNEES.md.
"""
import os
import sqlite3

from .config import BASE_DIR


def init_db(database=None):
    """Crée / met à jour toutes les tables de `database` (par défaut : la base du projet)."""
    conn = sqlite3.connect(database or os.path.join(BASE_DIR, "cruxwall.db"))

    conn.execute("""
    CREATE TABLE IF NOT EXISTS user (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT DEFAULT 'user'
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS gym (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        location TEXT,
        created_by INTEGER,
        is_private INTEGER DEFAULT 0,
        access_code TEXT,
        FOREIGN KEY (created_by) REFERENCES user(id)
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS wall (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        gym_id INTEGER,
        name TEXT NOT NULL,
        image_filename TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        created_by INTEGER,
        ai_disabled INTEGER DEFAULT 0,
        is_private INTEGER DEFAULT 0,
        access_code TEXT,
        FOREIGN KEY (gym_id) REFERENCES gym(id),
        FOREIGN KEY (created_by) REFERENCES user(id)
    )
    """)

    # Migration : les bases créées avant ces fonctionnalités n'ont pas
    # encore ces colonnes (CREATE TABLE IF NOT EXISTS ne modifie pas une
    # table déjà existante). On les ajoute si besoin, sans rien perdre.
    existing_cols = [row[1] for row in conn.execute("PRAGMA table_info(wall)").fetchall()]
    if "ai_disabled" not in existing_cols:
        conn.execute("ALTER TABLE wall ADD COLUMN ai_disabled INTEGER DEFAULT 0")
    if "last_activity_at" not in existing_cols:
        # Pas de valeur par défaut non constante possible avec ADD COLUMN en
        # SQLite : on ajoute la colonne vide, puis on l'initialise à partir
        # de created_at pour les murs déjà existants.
        conn.execute("ALTER TABLE wall ADD COLUMN last_activity_at TIMESTAMP")
        conn.execute("UPDATE wall SET last_activity_at = created_at WHERE last_activity_at IS NULL")
    if "warning_sent_at" not in existing_cols:
        conn.execute("ALTER TABLE wall ADD COLUMN warning_sent_at TIMESTAMP")
    if "is_private" not in existing_cols:
        conn.execute("ALTER TABLE wall ADD COLUMN is_private INTEGER DEFAULT 0")
    if "access_code" not in existing_cols:
        conn.execute("ALTER TABLE wall ADD COLUMN access_code TEXT")

    gym_cols = [row[1] for row in conn.execute("PRAGMA table_info(gym)").fetchall()]
    if "created_by" not in gym_cols:
        conn.execute("ALTER TABLE gym ADD COLUMN created_by INTEGER")
    if "is_private" not in gym_cols:
        conn.execute("ALTER TABLE gym ADD COLUMN is_private INTEGER DEFAULT 0")
    if "access_code" not in gym_cols:
        conn.execute("ALTER TABLE gym ADD COLUMN access_code TEXT")

    # Qui a débloqué quel mur/salle privé(e) en entrant le bon code — accès
    # définitif une fois débloqué, pas besoin de retaper le code à chaque fois.
    conn.execute("""
    CREATE TABLE IF NOT EXISTS wall_access (
        wall_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (wall_id, user_id),
        FOREIGN KEY (wall_id) REFERENCES wall(id),
        FOREIGN KEY (user_id) REFERENCES user(id)
    )
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS gym_access (
        gym_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (gym_id, user_id),
        FOREIGN KEY (gym_id) REFERENCES gym(id),
        FOREIGN KEY (user_id) REFERENCES user(id)
    )
    """)

    # Notifications affichées à l'utilisateur (ex : avertissement avant
    # suppression d'un mur inactif). Pas d'envoi d'e-mail : c'est un système
    # de messages internes à l'appli, visibles une fois connecté.
    conn.execute("""
    CREATE TABLE IF NOT EXISTS notification (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        wall_id INTEGER,
        message TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        read_at TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES user(id),
        FOREIGN KEY (wall_id) REFERENCES wall(id)
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS block (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        wall_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        grade TEXT,
        color TEXT,
        description TEXT,
        created_by INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (wall_id) REFERENCES wall(id),
        FOREIGN KEY (created_by) REFERENCES user(id)
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS hold (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        block_id INTEGER NOT NULL,
        x REAL NOT NULL,
        y REAL NOT NULL,
        hold_type TEXT DEFAULT 'mid',
        w REAL,
        h REAL,
        FOREIGN KEY (block_id) REFERENCES block(id)
    )
    """)

    # Migration : lien externe optionnel (vidéo, etc.) sur un bloc.
    block_cols = [row[1] for row in conn.execute("PRAGMA table_info(block)").fetchall()]
    if "link" not in block_cols:
        conn.execute("ALTER TABLE block ADD COLUMN link TEXT")

    # Migration : les prises créées avant l'ajout du redimensionnement n'ont
    # pas encore ces colonnes.
    hold_cols = [row[1] for row in conn.execute("PRAGMA table_info(hold)").fetchall()]
    if "w" not in hold_cols:
        conn.execute("ALTER TABLE hold ADD COLUMN w REAL")
    if "h" not in hold_cols:
        conn.execute("ALTER TABLE hold ADD COLUMN h REAL")

    # Note de difficulte percue (cotation grimpe) par utilisateur par bloc
    conn.execute("""
    CREATE TABLE IF NOT EXISTS block_note (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        block_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        note TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(block_id, user_id),
        FOREIGN KEY (block_id) REFERENCES block(id),
        FOREIGN KEY (user_id) REFERENCES user(id)
    )
    """)

    # Ascension : done = reussi, flash = premier essai
    conn.execute("""
    CREATE TABLE IF NOT EXISTS ascent (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        block_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        done INTEGER DEFAULT 0,
        flash INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(block_id, user_id),
        FOREIGN KEY (block_id) REFERENCES block(id),
        FOREIGN KEY (user_id) REFERENCES user(id)
    )
    """)

    # Tentatives de connexion / inscription / saisie de code d'accès, pour
    # limiter le nombre d'essais (voir rl_count / rl_hit dans services/ratelimit.py).
    conn.execute("""
    CREATE TABLE IF NOT EXISTS auth_attempt (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bucket TEXT NOT NULL,
        ts INTEGER NOT NULL
    )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_attempt ON auth_attempt(bucket, ts)")

    # Cache du résultat de la détection IA des prises (une seule analyse par
    # mur au lieu d'une à chaque ouverture de l'éditeur).
    wall_cols2 = [row[1] for row in conn.execute("PRAGMA table_info(wall)").fetchall()]
    if "detected_holds" not in wall_cols2:
        conn.execute("ALTER TABLE wall ADD COLUMN detected_holds TEXT")
    if "detected_source" not in wall_cols2:
        conn.execute("ALTER TABLE wall ADD COLUMN detected_source TEXT")
    if "detected_at" not in wall_cols2:
        conn.execute("ALTER TABLE wall ADD COLUMN detected_at TIMESTAMP")

    # Acceptation des conditions d'utilisation (preuve de consentement, RGPD)
    user_cols = [row[1] for row in conn.execute("PRAGMA table_info(user)").fetchall()]
    if "terms_accepted_at" not in user_cols:
        conn.execute("ALTER TABLE user ADD COLUMN terms_accepted_at TIMESTAMP")
    # Change à chaque changement de mot de passe : déconnecte les autres appareils
    if "session_version" not in user_cols:
        conn.execute("ALTER TABLE user ADD COLUMN session_version INTEGER NOT NULL DEFAULT 0")

    # Date de réussite d'un bloc (carnet de progression)
    ascent_cols = [row[1] for row in conn.execute("PRAGMA table_info(ascent)").fetchall()]
    if "done_at" not in ascent_cols:
        conn.execute("ALTER TABLE ascent ADD COLUMN done_at TIMESTAMP")
        conn.execute("UPDATE ascent SET done_at = created_at WHERE done = 1 AND done_at IS NULL")

    # Carnet de progression : une ligne par bloc réussi, COPIE indépendante des blocs (pas de clé étrangère
    # vers block/wall) pour que les totaux ne bougent pas quand un bloc, un mur ou une salle est supprimé(e).
    # Remplie une seule fois, à la création de la table, à partir des réussites déjà enregistrées.
    log_exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='climb_log'").fetchone()
    conn.execute("""
    CREATE TABLE IF NOT EXISTS climb_log (
        user_id INTEGER NOT NULL,
        block_id INTEGER NOT NULL,
        wall_id INTEGER,
        block_name TEXT,
        wall_name TEXT,
        grade TEXT,
        flash INTEGER NOT NULL DEFAULT 0,
        done_at TIMESTAMP,
        PRIMARY KEY (user_id, block_id),
        FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE
    )
    """)
    if not log_exists:
        conn.execute("""
            INSERT OR IGNORE INTO climb_log(user_id, block_id, wall_id, block_name, wall_name, grade, flash, done_at)
            SELECT a.user_id, a.block_id, w.id, b.name, w.name, COALESCE(b.grade, ''), a.flash, COALESCE(a.done_at, a.created_at)
            FROM ascent a JOIN block b ON b.id = a.block_id JOIN wall w ON w.id = b.wall_id
            WHERE a.done = 1 OR a.flash = 1
        """)

    # Favoris (murs, salles) et liste de blocs « à faire ». Suppression en cascade :
    # si le mur / la salle / le bloc / le compte disparaît, la ligne disparaît avec.
    conn.execute("""
    CREATE TABLE IF NOT EXISTS wall_favorite (
        user_id INTEGER NOT NULL,
        wall_id INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, wall_id),
        FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE,
        FOREIGN KEY (wall_id) REFERENCES wall(id) ON DELETE CASCADE
    )
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS gym_favorite (
        user_id INTEGER NOT NULL,
        gym_id INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, gym_id),
        FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE,
        FOREIGN KEY (gym_id) REFERENCES gym(id) ON DELETE CASCADE
    )
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS block_favorite (
        user_id INTEGER NOT NULL,
        block_id INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, block_id),
        FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE,
        FOREIGN KEY (block_id) REFERENCES block(id) ON DELETE CASCADE
    )
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS block_todo (
        user_id INTEGER NOT NULL,
        block_id INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, block_id),
        FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE,
        FOREIGN KEY (block_id) REFERENCES block(id) ON DELETE CASCADE
    )
    """)

    # Journal des actions d'administration. Pas de clé étrangère : l'historique
    # doit survivre à la suppression du compte administrateur ou du contenu concerné.
    conn.execute("""
    CREATE TABLE IF NOT EXISTS admin_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id INTEGER,
        admin_name TEXT NOT NULL,
        action TEXT NOT NULL,
        target TEXT,
        details TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_admin_log_date ON admin_log(created_at)")

    # Signalements de murs/blocs par les utilisateurs, traités depuis la page /admin.
    # Pas de clé étrangère sur le contenu signalé ni sur handled_by : l'historique
    # doit survivre à la suppression du contenu ou du compte administrateur.
    conn.execute("""
    CREATE TABLE IF NOT EXISTS report (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reporter_id INTEGER,
        target_type TEXT NOT NULL,
        target_id INTEGER NOT NULL,
        target_name TEXT,
        wall_id INTEGER,
        reason TEXT NOT NULL,
        details TEXT,
        status TEXT NOT NULL DEFAULT 'open',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        handled_by INTEGER,
        handled_at TIMESTAMP,
        FOREIGN KEY (reporter_id) REFERENCES user(id)
    )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_report_status ON report(status, created_at)")

    # Contraintes d'unicité garanties par la base elle-même (les vérifications du
    # code ne suffisent pas si deux personnes valident au même instant).
    # Si des doublons existent déjà, l'index n'est pas créé : un message le signale.
    for name, sql in [
        ("pseudo", "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_name_ci ON user(LOWER(name))"),
        ("email", "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_email_ci ON user(LOWER(email))"),
        ("nom de salle", "CREATE UNIQUE INDEX IF NOT EXISTS uq_gym_name_ci ON gym(LOWER(name))"),
        ("nom de bloc par mur", "CREATE UNIQUE INDEX IF NOT EXISTS uq_block_wall_name_ci ON block(wall_id, LOWER(name))"),
    ]:
        try:
            conn.execute(sql)
        except sqlite3.IntegrityError:
            print(f"ATTENTION : des doublons existent déjà ({name}) : contrainte d'unicité non créée. "
                  "Renommez ou supprimez les doublons puis redémarrez l'application.")

    # Mode WAL (lectures et écriture simultanées sans blocage) : OPTIONNEL, à activer
    # avec SQLITE_WAL=1 dans le .env seulement si l'hébergeur le supporte.
    if os.environ.get("SQLITE_WAL") == "1":
        conn.execute("PRAGMA journal_mode=WAL")

    conn.commit()
    conn.close()
