"""Sauvegarde, nettoyage des murs inactifs et maintenance quotidienne automatique."""
import os
import sqlite3
import stat
import sys
import tarfile
from datetime import datetime, timedelta

import pytest

from src.services import backup, cleanup, maintenance
from tests.helpers import insert_user


def droits(chemin):
    """Droits du fichier (ex. 0o600). Windows ne gère pas ces droits : on ne les vérifie que sous Linux/macOS."""
    return None if sys.platform.startswith("win") else stat.S_IMODE(os.stat(chemin).st_mode)


@pytest.fixture
def dossiers(tmp_path):
    up = tmp_path / "uploads"; up.mkdir()
    return str(tmp_path / "backups"), str(up)


class TestSauvegarde:
    def test_copie_verifiee_et_permissions(self, conn, uid, db_path, dossiers):
        bdir, up = dossiers
        backup.backup_database(db_path, bdir)
        dest = os.path.join(bdir, f"cruxwall-{datetime.now():%Y-%m-%d}.db")
        assert os.path.exists(dest) and droits(dest) in (0o600, None)
        assert droits(bdir) in (0o700, None)
        copy = sqlite3.connect(dest)
        assert copy.execute("SELECT name FROM user").fetchone()[0] == "Lilian"
        copy.close()
        assert not os.path.exists(dest + ".tmp")

    def test_rotation_14_jours(self, conn, db_path, dossiers):
        bdir, _ = dossiers
        os.makedirs(bdir)
        for i in range(20):
            open(os.path.join(bdir, f"cruxwall-2020-01-{i + 1:02d}.db"), "w").close()
        backup.backup_database(db_path, bdir)
        files = sorted(f for f in os.listdir(bdir) if f.endswith(".db"))
        assert len(files) == backup.KEEP_DB and files[-1].startswith(f"cruxwall-{datetime.now():%Y}")
        assert "cruxwall-2020-01-01.db" not in files

    def test_photos_seulement_le_dimanche(self, db_path, dossiers, monkeypatch):
        bdir, up = dossiers
        open(os.path.join(up, "a.jpg"), "wb").write(b"x")

        class Lundi(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2026, 10, 26)       # lundi
        monkeypatch.setattr(backup, "datetime", Lundi)
        backup.backup_uploads(up, bdir)
        assert not os.path.exists(bdir) or not [f for f in os.listdir(bdir) if f.endswith(".tar")]

    def test_photos_forcees_et_contenu(self, dossiers):
        bdir, up = dossiers
        open(os.path.join(up, "a.jpg"), "wb").write(b"abc")
        backup.backup_uploads(up, bdir, force=True)
        tars = [f for f in os.listdir(bdir) if f.endswith(".tar")]
        assert len(tars) == 1
        with tarfile.open(os.path.join(bdir, tars[0])) as t:
            assert "uploads/a.jpg" in t.getnames()
        assert droits(os.path.join(bdir, tars[0])) in (0o600, None)

    def test_photos_ignorees_si_trop_lourdes(self, dossiers, monkeypatch):
        bdir, up = dossiers
        open(os.path.join(up, "a.jpg"), "wb").write(b"x" * 2048)
        monkeypatch.setattr(backup, "MAX_UPLOADS_ARCHIVE_MB", 0)
        backup.backup_uploads(up, bdir, force=True)
        assert not os.path.exists(bdir) or not os.listdir(bdir)

    def test_rotation_des_archives_de_photos(self, dossiers):
        bdir, up = dossiers
        os.makedirs(bdir)
        for d in ("2020-01-05", "2020-01-12", "2020-01-19"):
            open(os.path.join(bdir, f"uploads-{d}.tar"), "w").close()
        backup.backup_uploads(up, bdir, force=True)
        assert len([f for f in os.listdir(bdir) if f.startswith("uploads-")]) == backup.KEEP_UPLOADS

    def test_dossier_de_photos_absent(self, tmp_path):
        backup.backup_uploads(str(tmp_path / "rien"), str(tmp_path / "b"), force=True)

    def test_run_complet(self, conn, db_path, dossiers):
        bdir, up = dossiers
        backup.run(force_uploads=True, database=db_path, upload_folder=up, backup_dir=bdir)
        assert len(os.listdir(bdir)) == 2


class TestNettoyage:
    @pytest.fixture
    def mur(self, conn, uid, dossiers):
        _, up = dossiers
        conn.execute("INSERT INTO gym(name, created_by) VALUES('G', ?)", (uid,))
        conn.execute("INSERT INTO wall(name, gym_id, image_filename, created_by) VALUES('M', 1, 'photo.jpg', ?)", (uid,))
        conn.execute("INSERT INTO block(wall_id, name, created_by) VALUES(1, 'B', ?)", (uid,))
        conn.commit()
        open(os.path.join(up, "photo.jpg"), "wb").write(b"x")
        return up

    def vieillir(self, conn, jours):
        conn.execute("UPDATE wall SET last_activity_at = ?", ((datetime.utcnow() - timedelta(days=jours)).isoformat(sep=" "),))
        conn.commit()

    def lancer(self, db_path, up):
        return cleanup.run(database=db_path, upload_folder=up)

    def test_mur_recent_intact(self, conn, mur, db_path):
        self.vieillir(conn, 10)
        assert self.lancer(db_path, mur) == (0, 0)

    def test_avertissement_a_173_jours(self, conn, mur, db_path, uid):
        self.vieillir(conn, 174)
        assert self.lancer(db_path, mur) == (1, 0)
        n = conn.execute("SELECT * FROM notification").fetchall()
        assert len(n) == 1 and n[0]["user_id"] == uid and "supprimé définitivement" in n[0]["message"]
        assert conn.execute("SELECT warning_sent_at FROM wall").fetchone()[0] is not None
        assert self.lancer(db_path, mur) == (0, 0)      # pas de second avertissement

    def test_pas_de_suppression_sans_avertissement_prealable(self, conn, mur, db_path):
        self.vieillir(conn, 400)
        assert self.lancer(db_path, mur) == (1, 0)
        assert conn.execute("SELECT 1 FROM wall").fetchone()

    def test_suppression_apres_avertissement_a_180_jours(self, conn, mur, db_path, uid):
        self.vieillir(conn, 174)
        self.lancer(db_path, mur)
        self.vieillir(conn, 181)
        assert self.lancer(db_path, mur) == (0, 1)
        for t in ("wall", "block"):
            assert conn.execute(f"SELECT 1 FROM {t}").fetchone() is None
        assert not os.path.exists(os.path.join(mur, "photo.jpg"))
        msgs = [r["message"] for r in conn.execute("SELECT message FROM notification")]
        assert any("supprimé automatiquement" in m for m in msgs) and not any("presque 6 mois" in m for m in msgs)

    def test_signalements_en_attente_clos(self, conn, mur, db_path, uid):
        conn.execute("INSERT INTO report(reporter_id, target_type, target_id, target_name, wall_id, reason) VALUES(?, 'wall', 1, 'M', 1, 'person')", (uid,))
        conn.commit()
        self.vieillir(conn, 174); self.lancer(db_path, mur); self.vieillir(conn, 181); self.lancer(db_path, mur)
        assert conn.execute("SELECT status FROM report").fetchone()[0] == "gone"

    def test_le_carnet_survit(self, conn, mur, db_path, uid):
        conn.execute("INSERT INTO ascent(block_id, user_id, done) VALUES(1, ?, 1)", (uid,))
        conn.execute("INSERT INTO climb_log(user_id, block_id, wall_id, block_name, wall_name, grade, flash, done_at) VALUES(?,1,1,'B','M','6a',0,'2026-01-01')", (uid,))
        conn.commit()
        self.vieillir(conn, 174); self.lancer(db_path, mur); self.vieillir(conn, 181); self.lancer(db_path, mur)
        assert conn.execute("SELECT 1 FROM climb_log").fetchone()

    def test_mur_sans_date_ignore(self, conn, mur, db_path):
        conn.execute("UPDATE wall SET last_activity_at = NULL"); conn.commit()
        assert self.lancer(db_path, mur) == (0, 0)


class TestMaintenanceQuotidienne:
    def test_un_seul_processus_par_jour(self, tmp_path):
        d = str(tmp_path / "b")
        assert maintenance._claim_maintenance_slot(d, "2026-10-29") is True
        assert maintenance._claim_maintenance_slot(d, "2026-10-29") is False
        assert maintenance._claim_maintenance_slot(d, "2026-10-30") is True

    def test_vieux_reperes_supprimes(self, tmp_path):
        d = tmp_path / "b"; d.mkdir()
        vieux = d / ".maintenance-2026-10-01"; vieux.write_text("")
        os.utime(vieux, (0, 0))
        maintenance._claim_maintenance_slot(str(d), "2026-10-29")
        assert not vieux.exists()

    def test_declenchee_apres_la_reponse_et_une_seule_fois(self, app, anon, monkeypatch):
        monkeypatch.setattr("src.services.maintenance.AUTO_MAINTENANCE", True)
        monkeypatch.setitem(maintenance._maintenance_state, "day", None)
        anon.get("/").close()        # la maintenance part à la fermeture de la réponse
        sauvegardes = [f for f in os.listdir(app.config["BACKUP_DIR"]) if f.startswith("cruxwall-")]
        assert len(sauvegardes) == 1
        assert [f for f in os.listdir(app.config["BACKUP_DIR"]) if f.startswith(".maintenance-")]
        os.remove(os.path.join(app.config["BACKUP_DIR"], sauvegardes[0]))
        anon.get("/gyms").close()       # même jour : rien de plus
        assert not [f for f in os.listdir(app.config["BACKUP_DIR"]) if f.startswith("cruxwall-")]

    def test_desactivee(self, app, anon, monkeypatch):
        monkeypatch.setattr("src.services.maintenance.AUTO_MAINTENANCE", False)
        monkeypatch.setitem(maintenance._maintenance_state, "day", None)
        anon.get("/")
        assert not os.path.exists(app.config["BACKUP_DIR"])

    @pytest.mark.parametrize("path", ["/health", "/static/css/base.css"])
    def test_pages_ignorees(self, app, anon, monkeypatch, path):
        monkeypatch.setattr("src.services.maintenance.AUTO_MAINTENANCE", True)
        monkeypatch.setitem(maintenance._maintenance_state, "day", None)
        anon.get(path)
        assert not os.path.exists(app.config["BACKUP_DIR"])

    def test_une_etape_en_echec_n_empeche_pas_l_autre(self, app, monkeypatch):
        appels = []
        monkeypatch.setattr(maintenance.backup, "run", lambda **k: (_ for _ in ()).throw(RuntimeError("boom")))
        monkeypatch.setattr(maintenance.cleanup, "run", lambda **k: appels.append("nettoyage"))
        maintenance.run_daily_maintenance(app)
        assert appels == ["nettoyage"]
