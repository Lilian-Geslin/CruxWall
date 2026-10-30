"""Scripts d'exploitation (scripts/) lancés comme sur le serveur : dans un processus à part, sur une base temporaire."""
import os
import shutil
import sqlite3
import subprocess
import sys

import pytest

from src.schema import init_db
from tests.helpers import insert_user
from src.db import connect

RACINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def lancer(script, *args, env=None, cwd=RACINE):
    e = {**os.environ, **(env or {})}
    return subprocess.run([sys.executable, os.path.join(RACINE, "scripts", script), *args], capture_output=True, text=True, env=e, cwd=cwd, timeout=60)


@pytest.fixture
def base(tmp_path):
    p = str(tmp_path / "s.db")
    init_db(p)
    c = connect(p)
    insert_user(c, "Lilian", "l@x.fr")
    c.close()
    return p


class TestMakeAdmin:
    def test_promotion_et_retrait(self, base):
        r = lancer("make_admin.py", "lilian", env={"CRUXWALL_DATABASE": base})
        assert r.returncode == 0 and "admin" in r.stdout
        c = sqlite3.connect(base)
        assert c.execute("SELECT role FROM user").fetchone()[0] == "admin"
        assert "Droits administrateur accordés" in c.execute("SELECT action FROM admin_log").fetchone()[0]
        lancer("make_admin.py", "Lilian", "--remove", env={"CRUXWALL_DATABASE": base})
        assert c.execute("SELECT role FROM user").fetchone()[0] == "user"

    def test_compte_inconnu(self, base):
        r = lancer("make_admin.py", "Fantome", env={"CRUXWALL_DATABASE": base})
        assert r.returncode == 1 and "Aucun compte" in r.stdout

    def test_sans_argument(self, base):
        assert lancer("make_admin.py", env={"CRUXWALL_DATABASE": base}).returncode == 1


class TestSauvegardeEtNettoyage:
    def test_backup_db(self, base, tmp_path):
        r = lancer("backup_db.py", env={"CRUXWALL_DATABASE": base, "BACKUP_DIR": str(tmp_path / "bk")})
        assert r.returncode == 0, r.stderr
        assert [f for f in os.listdir(tmp_path / "bk") if f.startswith("cruxwall-") and f.endswith(".db")]

    def test_cleanup(self, base):
        r = lancer("cleanup_inactive_walls.py", env={"CRUXWALL_DATABASE": base})
        assert r.returncode == 0, r.stderr and "0 avertissement" in r.stdout

    def test_daily_maintenance(self, base, tmp_path):
        r = lancer("daily_maintenance.py", env={"CRUXWALL_DATABASE": base, "BACKUP_DIR": str(tmp_path / "bk")})
        assert r.returncode == 0, r.stderr
        assert os.listdir(tmp_path / "bk")


class TestSetupDb:
    def test_creation_de_la_base(self, tmp_path):
        p = str(tmp_path / "neuve.db")
        r = lancer("setup_db.py", env={"CRUXWALL_DATABASE": p})
        assert r.returncode == 0, r.stderr
        assert "user" in {x[0] for x in sqlite3.connect(p).execute("SELECT name FROM sqlite_master WHERE type='table'")}

    def test_reset_demande_une_confirmation(self, base):
        r = subprocess.run([sys.executable, os.path.join(RACINE, "scripts", "setup_db.py"), "--reset"], input="non\n", capture_output=True,
                           text=True, env={**os.environ, "CRUXWALL_DATABASE": base}, cwd=RACINE, timeout=60)
        assert sqlite3.connect(base).execute("SELECT COUNT(*) FROM user").fetchone()[0] == 1      # rien n'est effacé sans confirmation


class TestCheckEnv:
    @pytest.fixture
    def projet(self, tmp_path):
        """Copie du script dans un faux projet : il lit le .env situé à côté de scripts/."""
        (tmp_path / "scripts").mkdir()
        shutil.copy(os.path.join(RACINE, "scripts", "check_env.py"), tmp_path / "scripts" / "check_env.py")
        return tmp_path

    def verifier(self, projet, contenu):
        (projet / ".env").write_text(contenu)
        os.chmod(projet / ".env", 0o600)
        return subprocess.run([sys.executable, str(projet / "scripts" / "check_env.py")], capture_output=True, text=True, timeout=60)

    def test_sans_env(self, projet):
        r = subprocess.run([sys.executable, str(projet / "scripts" / "check_env.py")], capture_output=True, text=True, timeout=60)
        assert r.returncode == 1 and "aucun fichier .env" in r.stdout

    def test_configuration_correcte(self, projet):
        r = self.verifier(projet, "FLASK_SECRET_KEY=" + "aZ9" * 20 + "\nTRUST_PROXY=1\nLEGAL_PUBLISHER_NAME=J\nLEGAL_CONTACT_EMAIL=a@b.fr\n")
        assert r.returncode == 0 and "ERREUR" not in r.stdout

    def test_erreurs_detectees_sans_afficher_les_secrets(self, projet):
        r = self.verifier(projet, "FLASK_SECRET_KEY=Zq7Xk2\nCRUXWALL_ENV=development\n")
        assert r.returncode != 0 and "ERREUR" in r.stdout and "Zq7Xk2" not in r.stdout and "TRUST_PROXY" in r.stdout

    def test_ligne_mal_formee(self, projet):
        r = self.verifier(projet, "FLASK_SECRET_KEY=" + "aZ9" * 20 + "\nTRUST_PROXY=1\nPAS_DE_EGAL\n")
        assert "ligne 3" in r.stdout
