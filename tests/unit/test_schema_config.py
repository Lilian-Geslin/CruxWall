"""Schéma de la base (idempotence, migrations, unicité, clés étrangères), configuration et filtre des journaux."""
import logging
import sqlite3

import pytest

from src import config, create_app
from src.db import connect
from src.schema import init_db
from src.security import RedactSecretsFilter

TABLES = {"user", "gym", "wall", "block", "hold", "ascent", "block_note", "notification", "auth_attempt", "wall_access", "gym_access",
          "climb_log", "wall_favorite", "gym_favorite", "block_favorite", "block_todo", "report", "admin_log"}


def tables(conn):
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}


class TestSchema:
    def test_toutes_les_tables(self, conn):
        assert TABLES <= tables(conn)

    def test_idempotent_et_sans_perte(self, conn, db_path, uid):
        init_db(db_path); init_db(db_path)
        assert conn.execute("SELECT name FROM user").fetchone()[0] == "Lilian"

    def test_migration_d_une_ancienne_base(self, tmp_path):
        old = str(tmp_path / "old.db")
        c = sqlite3.connect(old)
        c.executescript("""
            CREATE TABLE user(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, password TEXT NOT NULL, role TEXT DEFAULT 'user');
            CREATE TABLE gym(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, location TEXT);
            CREATE TABLE wall(id INTEGER PRIMARY KEY AUTOINCREMENT, gym_id INTEGER, name TEXT NOT NULL, image_filename TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, created_by INTEGER);
            CREATE TABLE block(id INTEGER PRIMARY KEY AUTOINCREMENT, wall_id INTEGER NOT NULL, name TEXT NOT NULL, grade TEXT, color TEXT, description TEXT, created_by INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE hold(id INTEGER PRIMARY KEY AUTOINCREMENT, block_id INTEGER NOT NULL, x REAL, y REAL, hold_type TEXT);
            CREATE TABLE ascent(id INTEGER PRIMARY KEY AUTOINCREMENT, block_id INTEGER, user_id INTEGER, done INTEGER DEFAULT 0, flash INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
            INSERT INTO user(name, email, password) VALUES('Vieux', 'v@x.fr', 'h');
            INSERT INTO gym(name) VALUES('G'); INSERT INTO wall(gym_id, name, image_filename, created_by) VALUES(1, 'M', 'a.jpg', 1);
            INSERT INTO block(wall_id, name, grade, created_by) VALUES(1, 'B', '6a', 1);
            INSERT INTO ascent(block_id, user_id, done, flash) VALUES(1, 1, 1, 1);
        """)
        c.commit(); c.close()
        init_db(old)
        c = connect(old)
        cols = lambda t: {r[1] for r in c.execute(f"PRAGMA table_info({t})")}
        assert {"is_private", "access_code", "last_activity_at", "warning_sent_at", "detected_holds", "detected_source"} <= cols("wall")
        assert {"is_private", "access_code", "created_by"} <= cols("gym") and "link" in cols("block") and {"w", "h"} <= cols("hold")
        assert {"session_version", "terms_accepted_at"} <= cols("user") and "done_at" in cols("ascent")
        assert TABLES <= tables(c)
        assert c.execute("SELECT name FROM user").fetchone()[0] == "Vieux"
        log = c.execute("SELECT block_name, wall_name, grade, flash FROM climb_log").fetchone()      # carnet reconstruit depuis les ascensions
        assert tuple(log) == ("B", "M", "6a", 1)

    def test_unicite_insensible_a_la_casse(self, conn):
        conn.execute("INSERT INTO user(name, email, password) VALUES('Alice', 'a@x.fr', 'h')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO user(name, email, password) VALUES('ALICE', 'b@x.fr', 'h')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO user(name, email, password) VALUES('Bob', 'A@X.FR', 'h')")
        conn.execute("INSERT INTO gym(name) VALUES('Salle')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO gym(name) VALUES('SALLE')")
        conn.execute("INSERT INTO wall(gym_id, name, image_filename) VALUES(1, 'M', 'a.jpg')")
        conn.execute("INSERT INTO block(wall_id, name) VALUES(1, 'Bloc')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO block(wall_id, name) VALUES(1, 'BLOC')")

    def test_cles_etrangeres_actives(self, conn):
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO hold(block_id, x, y, hold_type) VALUES(999, 0.1, 0.1, 'mid')")

    def test_suppression_en_cascade_du_compte(self, conn, uid):
        """Carnet et favoris suivent le compte ; les autres données sont retirées explicitement par delete_user_account."""
        conn.execute("INSERT INTO gym(name) VALUES('G')")
        conn.execute("INSERT INTO wall(gym_id, name, image_filename) VALUES(1, 'M', 'a.jpg')")
        conn.execute("INSERT INTO wall_favorite(user_id, wall_id) VALUES(?, 1)", (uid,))
        conn.execute("INSERT INTO climb_log(user_id, block_id, block_name, wall_name, grade, flash, done_at) VALUES(?, 5, 'b', 'm', '6a', 0, '2026-01-01')", (uid,))
        conn.commit()
        conn.execute("DELETE FROM user WHERE id = ?", (uid,))
        assert conn.execute("SELECT COUNT(*) FROM wall_favorite").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM climb_log").fetchone()[0] == 0

    def test_roles_et_valeurs_par_defaut(self, conn, uid):
        assert conn.execute("SELECT role, session_version FROM user").fetchone()[:] == ("user", 0)

    def test_le_mode_wal_est_optionnel(self, db_path, tmp_path, monkeypatch):
        monkeypatch.setenv("SQLITE_WAL", "1")
        p = str(tmp_path / "wal.db")
        init_db(p)
        assert sqlite3.connect(p).execute("PRAGMA journal_mode").fetchone()[0] in ("wal", "delete")


class TestConfig:
    def test_cle_obligatoire(self, monkeypatch):
        monkeypatch.delenv("FLASK_SECRET_KEY", raising=False)
        with pytest.raises(RuntimeError, match="FLASK_SECRET_KEY"):
            config.load_secret_key()
        monkeypatch.setenv("FLASK_SECRET_KEY", "courte")
        with pytest.raises(RuntimeError):
            config.load_secret_key()
        monkeypatch.setenv("FLASK_SECRET_KEY", "x" * 16)
        assert config.load_secret_key() == "x" * 16

    def test_l_appli_refuse_de_demarrer_sans_cle(self, monkeypatch, tmp_path):
        monkeypatch.delenv("FLASK_SECRET_KEY", raising=False)
        with pytest.raises(RuntimeError):
            create_app({"DATABASE": str(tmp_path / "d.db"), "UPLOAD_FOLDER": str(tmp_path / "u"), "LEGACY_UPLOAD_FOLDER": str(tmp_path / "l")})

    def test_valeurs_officielles(self):
        assert config.MAX_UPLOAD_BYTES == 15 * 1024 * 1024 and config.MAX_IMAGE_PIXELS == 40_000_000
        assert config.MAX_IMAGE_DIMENSION == 1600 and config.JPEG_QUALITY == 80 and config.ALLOWED_EXTENSIONS == {"png", "jpg", "jpeg", "webp"}
        assert config.Config.PERMANENT_SESSION_LIFETIME.days == 30 and config.Config.SESSION_COOKIE_HTTPONLY and config.Config.SESSION_COOKIE_SAMESITE == "Lax"

    def test_application(self, app):
        assert app.config["MAX_CONTENT_LENGTH"] == config.MAX_UPLOAD_BYTES
        assert set(app.blueprints) >= {"public", "auth", "walls", "gyms", "blocks", "ascents", "favorites", "profile", "search", "media",
                                       "legal", "reports", "admin", "detection"}

    def test_les_photos_sont_hors_du_dossier_static(self, app):
        assert "static" not in app.config["UPLOAD_FOLDER"].replace("\\", "/").split("/")[-2:]

    def test_deux_applications_independantes(self, tmp_path):
        a = create_app({"DATABASE": str(tmp_path / "a.db"), "UPLOAD_FOLDER": str(tmp_path / "ua"), "LEGACY_UPLOAD_FOLDER": str(tmp_path / "la")})
        b = create_app({"DATABASE": str(tmp_path / "b.db"), "UPLOAD_FOLDER": str(tmp_path / "ub"), "LEGACY_UPLOAD_FOLDER": str(tmp_path / "lb")})
        assert a.config["DATABASE"] != b.config["DATABASE"]

    def test_anciennes_photos_deplacees_au_demarrage(self, tmp_path):
        legacy = tmp_path / "legacy"; legacy.mkdir(); (legacy / "a.jpg").write_bytes(b"x")
        create_app({"DATABASE": str(tmp_path / "d.db"), "UPLOAD_FOLDER": str(tmp_path / "u"), "LEGACY_UPLOAD_FOLDER": str(legacy)})
        assert (tmp_path / "u" / "a.jpg").exists() and not (legacy / "a.jpg").exists()


class TestFiltreDesJournaux:
    def passe(self, message, *args):
        rec = logging.LogRecord("t", logging.INFO, "f", 1, message, args, None)
        RedactSecretsFilter().filter(rec)
        return rec.getMessage()

    @pytest.mark.parametrize("brut,attendu", [
        ("GET /x?api_key=ABC123&z=1", "GET /x?api_key=***&z=1"),
        ("token=abcdef", "token=***"), ("password=hunter2 fin", "password=*** fin"), ("SECRET=zzz", "SECRET=***"),
        ("rien de secret ici", "rien de secret ici"),
    ])
    def test_masquage(self, brut, attendu):
        assert self.passe(brut) == attendu

    def test_arguments_formates(self):
        assert self.passe("url=%s", "https://x/?api_key=KEY") == "url=https://x/?api_key=***"

    def test_message_non_formatable_ne_plante_pas(self):
        assert RedactSecretsFilter().filter(logging.LogRecord("t", logging.INFO, "f", 1, "%d", ("x",), None)) is True
