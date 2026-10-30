"""Services : limites de tentatives, droits d'accès, quotas, anti-robots, photos, activité, journal admin, recherche, suppression."""
import io
import os
import time

import pytest
from PIL import Image
from werkzeug.datastructures import FileStorage

from src import constants as C
from src.services import access, activity, admin_log as alog, antibot, deletion, images, legal, quotas, ratelimit, search
from tests.helpers import insert_user, png


# --------------------------------------------------------------------------- limites de tentatives
class TestRateLimit:
    def test_compte_et_fenetre(self, conn):
        for _ in range(3):
            ratelimit.rl_hit(conn, "b")
        assert ratelimit.rl_count(conn, "b", 60) == 3 and ratelimit.rl_count(conn, "autre", 60) == 0
        conn.execute("UPDATE auth_attempt SET ts = ?", (int(time.time()) - 120,))
        assert ratelimit.rl_count(conn, "b", 60) == 0 and ratelimit.rl_count(conn, "b", 300) == 3

    def test_purge_apres_24h(self, conn):
        conn.execute("INSERT INTO auth_attempt(bucket, ts) VALUES('vieux', ?)", (int(time.time()) - 25 * 3600,))
        ratelimit.rl_hit(conn, "neuf")
        assert conn.execute("SELECT COUNT(*) FROM auth_attempt WHERE bucket='vieux'").fetchone()[0] == 0

    def test_reset(self, conn):
        ratelimit.rl_hit(conn, "x"); ratelimit.rl_hit(conn, "y")
        ratelimit.rl_reset(conn, "x")
        assert ratelimit.rl_count(conn, "x", 60) == 0 and ratelimit.rl_count(conn, "y", 60) == 1

    def test_blocage_du_deblocage_par_compte(self, conn, uid, as_user):
        with as_user(uid):
            assert not ratelimit.unlock_rate_limited(conn)
            for _ in range(C.UNLOCK_USER_MAX):
                ratelimit.unlock_register_failure(conn)
            assert ratelimit.unlock_rate_limited(conn)

    def test_blocage_du_deblocage_par_ip(self, conn, uid, uid2, as_user):
        with as_user(uid):
            for _ in range(C.UNLOCK_IP_MAX):
                ratelimit.rl_hit(conn, f"unlock:ip:{ratelimit.client_ip()}")
        with as_user(uid2):
            assert ratelimit.unlock_rate_limited(conn)

    def test_ip_directe(self, as_user):
        with as_user(environ_base={"REMOTE_ADDR": "1.2.3.4"}):
            assert ratelimit.client_ip() == "1.2.3.4"

    def test_ip_derriere_proxy(self, as_user, monkeypatch):
        monkeypatch.setenv("TRUST_PROXY", "1")
        with as_user(headers={"X-Real-IP": "9.9.9.9"}):
            assert ratelimit.client_ip() == "9.9.9.9"
        with as_user(headers={"X-Forwarded-For": "6.6.6.6, 8.8.8.8"}):
            assert ratelimit.client_ip() == "8.8.8.8"      # dernière adresse : celle ajoutée par le proxy de confiance

    def test_en_tetes_ignores_sans_proxy_de_confiance(self, as_user, monkeypatch):
        monkeypatch.delenv("TRUST_PROXY", raising=False)
        with as_user(headers={"X-Real-IP": "9.9.9.9"}, environ_base={"REMOTE_ADDR": "1.1.1.1"}):
            assert ratelimit.client_ip() == "1.1.1.1"


# --------------------------------------------------------------------------- droits d'accès
class TestAccess:
    def test_normalisation_du_code(self):
        assert access.normalize_access_code(" ab-cd ef ") == "ABCDEF" and access.normalize_access_code(None) == ""
        assert len(access.normalize_access_code("x" * 100)) == 32

    def test_comparaison(self):
        assert access.codes_match("ABC", "ABC")
        assert not access.codes_match("ABC", "ABD") and not access.codes_match(None, "ABC") and not access.codes_match("ABC", "")

    def test_generation(self):
        codes = {access.generate_access_code() for _ in range(200)}
        assert len(codes) == 200
        assert all(len(c) == 10 and set(c) <= set(C.ACCESS_CODE_ALPHABET) for c in codes)
        assert not set("01IO") & set(C.ACCESS_CODE_ALPHABET)

    def test_salle_publique_visible_par_tous(self, conn, add_gym, as_user):
        g = conn.execute("SELECT * FROM gym WHERE id = ?", (add_gym(),)).fetchone()
        with as_user():
            assert access.can_view_gym(conn, g)

    def test_salle_privee(self, conn, uid, uid2, add_gym, as_user):
        gid = add_gym("P", created_by=uid, private=True, code="CODE")
        g = conn.execute("SELECT * FROM gym WHERE id = ?", (gid,)).fetchone()
        with as_user():
            assert not access.can_view_gym(conn, g)
        with as_user(uid2):
            assert not access.can_view_gym(conn, g)
            conn.execute("INSERT INTO gym_access(gym_id, user_id) VALUES(?, ?)", (gid, uid2)); conn.commit()
            assert access.can_view_gym(conn, g)
        with as_user(uid):
            assert access.can_view_gym(conn, g)
        admin = insert_user(conn, "Adm", "adm@example.fr", role="admin")
        conn.execute("DELETE FROM gym_access"); conn.commit()
        with as_user(admin, "admin"):
            assert access.can_view_gym(conn, g)

    def test_mur_prive(self, conn, uid, uid2, add_wall, as_user):
        wid = add_wall(created_by=uid, private=True, code="X")
        w = conn.execute("SELECT * FROM wall WHERE id = ?", (wid,)).fetchone()
        with as_user():
            assert not access.can_view_wall(conn, w)
        with as_user(uid2):
            assert not access.can_view_wall(conn, w)
            conn.execute("INSERT INTO wall_access(wall_id, user_id) VALUES(?, ?)", (wid, uid2)); conn.commit()
            assert access.can_view_wall(conn, w)
        with as_user(uid):
            assert access.can_view_wall(conn, w)

    def test_la_salle_privee_prime_sur_un_mur_public(self, conn, uid, uid2, add_gym, add_wall, as_user):
        gid = add_gym("P", created_by=uid, private=True)
        w = conn.execute("SELECT * FROM wall WHERE id = ?", (add_wall(created_by=uid, gym_id=gid),)).fetchone()
        with as_user(uid2):
            assert not access.can_view_wall(conn, w)

    def test_mur_public_dans_salle_publique(self, conn, uid, add_gym, add_wall, as_user):
        w = conn.execute("SELECT * FROM wall WHERE id = ?", (add_wall(created_by=uid, gym_id=add_gym()),)).fetchone()
        with as_user():
            assert access.can_view_wall(conn, w)

    # Ces fonctions ferment la connexion avant d'interrompre la requête (404/403) : chaque cas ouvre donc la sienne.
    def test_require_wall_access(self, conn, db_path, uid, uid2, add_wall, as_user):
        from werkzeug.exceptions import NotFound
        from src.db import connect
        wid = add_wall(created_by=uid, private=True)
        with as_user(uid2), pytest.raises(NotFound):
            access.require_wall_access(connect(db_path), wid)
        with as_user(uid2), pytest.raises(NotFound):
            access.require_wall_access(connect(db_path), 999)
        with as_user(uid):
            assert access.require_wall_access(connect(db_path), wid)["id"] == wid

    def test_forbid_or_hide(self, conn, db_path, uid, uid2, add_wall, as_user):
        from werkzeug.exceptions import Forbidden, NotFound
        from src.db import connect
        pub, priv = add_wall("a", created_by=uid), add_wall("b", created_by=uid, private=True)

        def mur(i):
            return conn.execute("SELECT * FROM wall WHERE id=?", (i,)).fetchone()
        with as_user(uid2), pytest.raises(Forbidden):          # visible : 403
            access.forbid_or_hide(connect(db_path), mur(pub))
        with as_user(uid2), pytest.raises(NotFound):           # invisible : 404, on ne révèle rien
            access.forbid_or_hide(connect(db_path), mur(priv))
        with as_user(uid2), pytest.raises(NotFound):
            access.forbid_or_hide(connect(db_path), None)

    def test_require_block_access(self, conn, db_path, uid, uid2, add_wall, add_block, as_user):
        from werkzeug.exceptions import NotFound
        from src.db import connect
        bid = add_block(add_wall(created_by=uid, private=True))
        with as_user(uid2), pytest.raises(NotFound):
            access.require_block_access(connect(db_path), bid)
        with as_user(uid2), pytest.raises(NotFound):
            access.require_block_access(connect(db_path), 999)
        with as_user(uid):
            assert access.require_block_access(connect(db_path), bid)


# --------------------------------------------------------------------------- quotas
class TestQuotas:
    @pytest.mark.parametrize("kind,total,daily", [("wall", 250, 50), ("gym", 100, 25), ("block", 500, 100)])
    def test_valeurs_officielles(self, kind, total, daily):
        assert (C.QUOTAS[kind]["total"], C.QUOTAS[kind]["daily"]) == (total, daily)

    def test_plafond_total(self, conn, uid, add_gym, as_user, monkeypatch):
        monkeypatch.setitem(C.QUOTAS["gym"], "total", 2)
        add_gym("a", uid); add_gym("b", uid)
        with as_user(uid):
            assert "Limite atteinte" in quotas.quota_error(conn, "gym")

    def test_plafond_journalier(self, conn, uid, as_user, monkeypatch):
        monkeypatch.setitem(C.QUOTAS["gym"], "daily", 2)
        with as_user(uid):
            assert quotas.quota_error(conn, "gym") is None
            quotas.quota_register(conn, "gym"); quotas.quota_register(conn, "gym")
            assert "Limite journalière" in quotas.quota_error(conn, "gym")

    def test_par_compte_et_admin_exempte(self, conn, uid, uid2, as_user, monkeypatch):
        monkeypatch.setitem(C.QUOTAS["gym"], "daily", 1)
        with as_user(uid):
            quotas.quota_register(conn, "gym")
        with as_user(uid2):
            assert quotas.quota_error(conn, "gym") is None
        with as_user(uid, "admin"):
            assert quotas.quota_error(conn, "gym") is None

    def test_taille_des_photos(self, app, as_user):
        os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
        open(os.path.join(app.config["UPLOAD_FOLDER"], "a.jpg"), "wb").write(b"x" * 1000)
        os.makedirs(os.path.join(app.config["UPLOAD_FOLDER"], "sous-dossier"))
        with as_user():
            assert quotas.uploads_size_bytes() == 1000

    def test_dossier_absent(self, app, as_user, tmp_path):
        app.config["UPLOAD_FOLDER"] = str(tmp_path / "rien")
        with as_user():
            assert quotas.uploads_size_bytes() == 0


# --------------------------------------------------------------------------- anti-robots
class TestAntibot:
    def test_jeton_trop_rapide_refuse(self, as_user, monkeypatch):
        monkeypatch.setattr(antibot, "REGISTER_MIN_SECONDS", 60)
        with as_user():
            assert not antibot.form_token_ok(antibot.make_form_token())

    def test_jeton_valide(self, as_user, monkeypatch):
        monkeypatch.setattr(antibot, "REGISTER_MIN_SECONDS", 0)
        with as_user():
            assert antibot.form_token_ok(antibot.make_form_token())

    def test_jeton_expire(self, as_user, monkeypatch):
        monkeypatch.setattr(antibot, "REGISTER_MIN_SECONDS", 0)
        monkeypatch.setattr(antibot, "REGISTER_MAX_SECONDS", -1)
        with as_user():
            assert not antibot.form_token_ok(antibot.make_form_token())

    @pytest.mark.parametrize("token", ["", "n'importe quoi", None])
    def test_jetons_invalides(self, as_user, token):
        with as_user():
            assert not antibot.form_token_ok(token)

    def test_jeton_d_une_autre_cle_refuse(self, app, as_user):
        from itsdangerous import URLSafeTimedSerializer
        faux = URLSafeTimedSerializer("autre-cle", salt="cruxwall-register-form").dumps("register")
        with as_user():
            assert not antibot.form_token_ok(faux)

    def test_jeton_d_un_autre_usage_refuse(self, app, as_user):
        from itsdangerous import URLSafeTimedSerializer
        with as_user():
            autre = URLSafeTimedSerializer(app.secret_key, salt="cruxwall-register-form").dumps("login")
            assert not antibot.form_token_ok(autre)


# --------------------------------------------------------------------------- photos
def fichier(buf, name="p.png"):
    return FileStorage(stream=buf, filename=name)


class TestImages:
    def test_extensions(self):
        assert images.allowed_file("a.JPG") and images.allowed_file("a.webp") and images.allowed_file("b.c.png")
        assert not images.allowed_file("a.gif") and not images.allowed_file("noext") and not images.allowed_file("a.exe")

    @pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP"])
    def test_formats_acceptes_et_convertis_en_jpeg(self, tmp_path, fmt):
        dest = str(tmp_path / "o.jpg")
        images.save_optimized_image(fichier(png(300, 200, fmt)), dest)
        with Image.open(dest) as img:
            assert img.format == "JPEG" and img.size == (300, 200)

    def test_reduction_a_1600_en_gardant_le_ratio(self, tmp_path):
        dest = str(tmp_path / "o.jpg")
        images.save_optimized_image(fichier(png(3200, 1600)), dest)
        with Image.open(dest) as img:
            assert img.size == (1600, 800)

    def test_pas_d_agrandissement(self, tmp_path):
        dest = str(tmp_path / "o.jpg")
        images.save_optimized_image(fichier(png(100, 50)), dest)
        with Image.open(dest) as img:
            assert img.size == (100, 50)

    def test_transparence_aplatie(self, tmp_path):
        buf = io.BytesIO(); Image.new("RGBA", (50, 50), (255, 0, 0, 0)).save(buf, "PNG"); buf.seek(0)
        dest = str(tmp_path / "o.jpg")
        images.save_optimized_image(fichier(buf), dest)
        with Image.open(dest) as img:
            assert img.mode == "RGB"

    def test_rotation_exif_appliquee_et_metadonnees_supprimees(self, tmp_path):
        buf = io.BytesIO()
        img = Image.new("RGB", (200, 100), "gray")
        exif = Image.Exif(); exif[0x0112] = 6; exif[0x010F] = "AppareilSecret"        # rotation 90° + fabricant
        img.save(buf, "JPEG", exif=exif); buf.seek(0)
        dest = str(tmp_path / "o.jpg")
        images.save_optimized_image(fichier(buf, "p.jpg"), dest)
        with Image.open(dest) as out:
            assert out.size == (100, 200)
            assert not out.getexif()

    def test_format_refuse_meme_avec_bonne_extension(self, tmp_path):
        buf = io.BytesIO(); Image.new("RGB", (10, 10)).save(buf, "GIF"); buf.seek(0)
        with pytest.raises(images.ImageRejected, match="Format non accepté"):
            images.save_optimized_image(fichier(buf, "x.png"), str(tmp_path / "o.jpg"))

    def test_trop_de_pixels(self, tmp_path, monkeypatch):
        monkeypatch.setattr(images, "MAX_IMAGE_PIXELS", 1000)
        with pytest.raises(images.ImageRejected, match="trop grande"):
            images.save_optimized_image(fichier(png(100, 100)), str(tmp_path / "o.jpg"))
        assert not os.path.exists(tmp_path / "o.jpg")

    def test_bombe_de_decompression(self, tmp_path, monkeypatch):
        monkeypatch.setattr(images, "MAX_IMAGE_PIXELS", 100)
        with pytest.raises(images.ImageRejected):
            images.save_optimized_image(fichier(png(1000, 1000)), str(tmp_path / "o.jpg"))

    def test_fichier_corrompu_ne_laisse_rien(self, tmp_path):
        dest = str(tmp_path / "o.jpg")
        with pytest.raises(Exception):
            images.save_optimized_image(fichier(io.BytesIO(b"pas une image")), dest)
        assert not os.path.exists(dest)

    def test_migration_des_anciennes_photos(self, tmp_path):
        old, new = tmp_path / "old", tmp_path / "new"; old.mkdir(); new.mkdir()
        (old / "a.jpg").write_bytes(b"1"); (old / "b.jpg").write_bytes(b"2"); (old / ".gitkeep").write_bytes(b""); (old / "d").mkdir()
        (new / "b.jpg").write_bytes(b"deja")
        images.migrate_legacy_uploads(str(old), str(new))
        assert (new / "a.jpg").read_bytes() == b"1" and (new / "b.jpg").read_bytes() == b"deja"    # jamais d'écrasement
        assert not (new / ".gitkeep").exists() and not (old / "a.jpg").exists()

    def test_migration_sans_ancien_dossier(self, tmp_path):
        images.migrate_legacy_uploads(str(tmp_path / "rien"), str(tmp_path))


# --------------------------------------------------------------------------- activité des murs
class TestActivite:
    def anciennete(self, conn, wid):
        conn.execute("UPDATE wall SET last_activity_at='2020-01-01 00:00:00' WHERE id=?", (wid,)); conn.commit()

    def valeur(self, conn, wid):
        return conn.execute("SELECT last_activity_at, warning_sent_at FROM wall WHERE id=?", (wid,)).fetchone()

    def test_anonyme_n_ecrit_rien(self, conn, add_wall, as_user):
        w = add_wall(); self.anciennete(conn, w)
        with as_user():
            activity.touch_wall_activity(conn, w)
        assert self.valeur(conn, w)[0] == "2020-01-01 00:00:00"

    def test_connecte_met_a_jour(self, conn, uid, add_wall, as_user):
        w = add_wall(); self.anciennete(conn, w)
        with as_user(uid):
            activity.touch_wall_activity(conn, w)
        assert self.valeur(conn, w)[0] > "2025"

    def test_limite_a_une_ecriture_par_periode(self, conn, uid, add_wall, as_user):
        w = add_wall()
        before = self.valeur(conn, w)[0]
        with as_user(uid):
            activity.touch_wall_activity(conn, w)
        assert self.valeur(conn, w)[0] == before

    def test_annule_l_avertissement_immediatement(self, conn, uid, add_wall, as_user):
        w = add_wall()
        conn.execute("UPDATE wall SET warning_sent_at = CURRENT_TIMESTAMP"); conn.commit()
        with as_user(uid):
            activity.touch_wall_activity(conn, w)
        assert self.valeur(conn, w)[1] is None

    @pytest.mark.parametrize("ua", ["Googlebot/2.1", "UptimeRobot/2.0", "bingbot", "curl crawler"])
    def test_robots_ignores(self, conn, uid, add_wall, as_user, ua):
        w = add_wall(); self.anciennete(conn, w)
        with as_user(uid, headers={"User-Agent": ua}):
            activity.touch_wall_activity(conn, w)
        assert self.valeur(conn, w)[0] == "2020-01-01 00:00:00"

    def test_un_navigateur_normal_compte(self, conn, uid, add_wall, as_user):
        w = add_wall(); self.anciennete(conn, w)
        with as_user(uid, headers={"User-Agent": "Mozilla/5.0 (iPhone) Safari"}):
            activity.touch_wall_activity(conn, w)
        assert self.valeur(conn, w)[0] > "2025"


# --------------------------------------------------------------------------- journal d'administration
class TestJournalAdmin:
    def test_enregistrement_et_troncature(self, conn, uid, as_user):
        with as_user(uid, "admin", name="Boss"):
            alog.admin_log(conn, "a" * 300, "t" * 500, "d" * 900)
        r = conn.execute("SELECT * FROM admin_log").fetchone()
        assert (r["admin_name"], len(r["action"]), len(r["target"]), len(r["details"])) == ("Boss", 100, 200, 500)

    def test_purge_au_bout_d_un_an(self, conn, uid, as_user):
        conn.execute("INSERT INTO admin_log(admin_id, admin_name, action, created_at) VALUES(?, 'x', 'vieux', datetime('now', '-400 days'))", (uid,))
        conn.execute("INSERT INTO admin_log(admin_id, admin_name, action, created_at) VALUES(?, 'x', 'recent', datetime('now', '-300 days'))", (uid,))
        with as_user(uid, "admin"):
            alog.admin_log(conn, "nouveau")
        assert {r[0] for r in conn.execute("SELECT action FROM admin_log")} == {"recent", "nouveau"}

    def test_seulement_pour_un_admin_sur_le_contenu_d_autrui(self, conn, uid, uid2, as_user):
        with as_user(uid, "admin"):
            alog.log_if_admin_on_foreign(conn, uid2, "Action", "cible")
            alog.log_if_admin_on_foreign(conn, uid, "Sur soi", "cible")
        with as_user(uid2, "user"):
            alog.log_if_admin_on_foreign(conn, uid, "Utilisateur", "cible")
        assert [r[0] for r in conn.execute("SELECT action FROM admin_log")] == ["Action"]


# --------------------------------------------------------------------------- recherche
class TestRecherche:
    @pytest.fixture
    def salle(self, conn, uid, uid2, add_gym, add_wall, add_block, as_user):
        gid = add_gym("S", uid)
        w1, w2 = add_wall("Dévers", uid, gid), add_wall("Dalle", uid, gid)
        add_block(w1, "Crimp", "6a", uid); add_block(w1, "Pince", "6a+", uid2); add_block(w1, "100%_Fou", "7a", uid)
        add_block(w2, "Réglette", "5c", uid2)
        return conn.execute("SELECT * FROM gym WHERE id=?", (gid,)).fetchone()

    def run(self, conn, gym, q, as_user, limit=100):
        with as_user():
            return search.gym_search(conn, search.gym_visible_walls(conn, gym), q, limit)

    def test_murs(self, conn, salle, as_user):
        walls, blocks = self.run(conn, salle, "dév", as_user)
        assert [w["name"] for w in walls] == ["Dévers"]

    def test_blocs_par_nom_ouvreur_et_cotation(self, conn, salle, as_user):
        assert {b["name"] for b in self.run(conn, salle, "crimp", as_user)[1]} == {"Crimp"}
        assert {b["name"] for b in self.run(conn, salle, "autre", as_user)[1]} == {"Pince", "Réglette"}      # ouvreur « Autre »
        assert {b["name"] for b in self.run(conn, salle, "6a", as_user)[1]} == {"Crimp", "Pince"}               # 6a trouve aussi 6a+
        assert {b["name"] for b in self.run(conn, salle, "6a+", as_user)[1]} == {"Pince"}

    def test_jokers_litteraux(self, conn, salle, as_user):
        assert [b["name"] for b in self.run(conn, salle, "%", as_user)[1]] == ["100%_Fou"]
        assert [b["name"] for b in self.run(conn, salle, "_", as_user)[1]] == ["100%_Fou"]

    def test_limite(self, conn, salle, as_user):
        assert len(self.run(conn, salle, "a", as_user, limit=2)[1]) <= 2

    def test_tri_par_cotation(self, conn, salle, as_user):
        grades = [b["grade"] for b in self.run(conn, salle, "e", as_user)[1]]
        assert grades == sorted(grades)

    def test_sans_mur_visible(self, conn, as_user, salle):
        with as_user():
            assert search.gym_search(conn, [], "x", 10) == ([], [])

    def test_murs_prives_exclus(self, conn, uid, uid2, add_gym, add_wall, add_block, as_user):
        gid = add_gym("S2", uid); w = add_wall("Secret", uid, gid, private=True); add_block(w, "Caché", "6a", uid)
        gym = conn.execute("SELECT * FROM gym WHERE id=?", (gid,)).fetchone()
        walls, blocks = self.run(conn, gym, "cach", as_user)
        assert blocks == [] and self.run(conn, gym, "secret", as_user)[0] == []

    @pytest.mark.parametrize("texte,attendu", [("a%b", "%a\\%b%"), ("a_b", "%a\\_b%"), ("a\\b", "%a\\\\b%"), ("abc", "%abc%")])
    def test_like_pattern(self, texte, attendu):
        assert search.like_pattern(texte) == attendu


# --------------------------------------------------------------------------- suppression de compte
class TestSuppressionDeCompte:
    @pytest.fixture(autouse=True)
    def contexte(self, app):
        """La suppression d'un mur efface aussi sa photo : il lui faut le contexte de l'application (dossier des photos)."""
        with app.app_context():
            yield

    @pytest.fixture
    def monde(self, conn, uid, uid2, add_gym, add_wall, add_block):
        g_pub, g_priv = add_gym("Pub", uid), add_gym("Priv", uid, private=True)
        w_pub, w_priv = add_wall("Mur pub", uid, g_pub, image="a.jpg"), add_wall("Mur priv", uid, g_pub, private=True, image="b.jpg")
        w_autre = add_wall("Mur autre", uid2, g_pub, image="c.jpg")
        b1, b2 = add_block(w_pub, "B1", created_by=uid), add_block(w_autre, "B2", created_by=uid)
        conn.execute("INSERT INTO ascent(block_id, user_id, done) VALUES(?, ?, 1)", (b1, uid2))
        conn.execute("INSERT INTO block_note(block_id, user_id, note) VALUES(?, ?, '6a')", (b2, uid))
        conn.commit()
        return dict(uid=uid, g_pub=g_pub, g_priv=g_priv, w_pub=w_pub, w_priv=w_priv, w_autre=w_autre)

    def test_plan(self, conn, monde, uid):
        plan = deletion.account_deletion_plan(conn, uid)
        assert [w["name"] for w in plan["private_walls"]] == ["Mur priv"] and [w["name"] for w in plan["public_walls"]] == ["Mur pub"]
        assert [g["name"] for g in plan["private_gyms"]] == ["Priv"] and [g["name"] for g in plan["public_gyms"]] == ["Pub"]

    def test_un_mur_dans_une_salle_privee_compte_comme_prive(self, conn, uid, add_gym, add_wall):
        g = add_gym("P", uid, private=True); add_wall("Dedans", uid, g)
        assert [w["name"] for w in deletion.account_deletion_plan(conn, uid)["private_walls"]] == ["Dedans"]

    def test_conserver_le_contenu_public(self, conn, monde, uid):
        s = deletion.delete_user_account(conn, uid, delete_public=False); conn.commit()
        assert s == {"walls_deleted": 1, "walls_kept": 1, "gyms_deleted": 1, "gyms_kept": 1}
        assert conn.execute("SELECT created_by FROM wall WHERE name='Mur pub'").fetchone()[0] is None
        assert conn.execute("SELECT 1 FROM wall WHERE name='Mur priv'").fetchone() is None
        assert conn.execute("SELECT created_by FROM gym WHERE name='Pub'").fetchone()[0] is None
        assert conn.execute("SELECT 1 FROM gym WHERE name='Priv'").fetchone() is None
        assert conn.execute("SELECT 1 FROM user WHERE id=?", (uid,)).fetchone() is None

    def test_supprimer_aussi_le_contenu_public(self, conn, monde, uid):
        deletion.delete_user_account(conn, uid, delete_public=True); conn.commit()
        assert conn.execute("SELECT name FROM wall").fetchall()[0][0] == "Mur autre"      # le mur d'un autre compte reste

    def test_ses_blocs_sur_les_murs_des_autres_sont_supprimes(self, conn, monde, uid):
        deletion.delete_user_account(conn, uid, delete_public=False); conn.commit()
        assert conn.execute("SELECT 1 FROM block WHERE name='B2'").fetchone() is None
        assert conn.execute("SELECT 1 FROM block_note").fetchone() is None

    def test_une_salle_avec_des_murs_d_autres_n_est_jamais_supprimee(self, conn, monde, uid):
        deletion.delete_user_account(conn, uid, delete_public=True); conn.commit()
        assert conn.execute("SELECT created_by FROM gym WHERE name='Pub'").fetchone()[0] is None

    def test_nettoie_les_donnees_rattachees(self, conn, monde, uid, uid2):
        conn.execute("INSERT INTO notification(user_id, message) VALUES(?, 'x')", (uid,))
        conn.execute("INSERT INTO auth_attempt(bucket, ts) VALUES(?, 1e12)", (f"unlock:user:{uid}",))
        conn.execute("INSERT INTO auth_attempt(bucket, ts) VALUES(?, 1e12)", (f"quota:wall:{uid}",))
        conn.execute("INSERT INTO auth_attempt(bucket, ts) VALUES(?, 1e12)", (f"unlock:user:{uid2}",))
        conn.execute("INSERT INTO climb_log(user_id, block_id, block_name, wall_name, grade, flash, done_at) VALUES(?, 99, 'x', 'y', '6a', 0, '2026-01-01')", (uid,))
        conn.commit()
        deletion.delete_user_account(conn, uid, delete_public=False); conn.commit()
        assert conn.execute("SELECT COUNT(*) FROM notification WHERE user_id=?", (uid,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM climb_log WHERE user_id=?", (uid,)).fetchone()[0] == 0
        assert [r[0] for r in conn.execute("SELECT bucket FROM auth_attempt")] == [f"unlock:user:{uid2}"]


# --------------------------------------------------------------------------- informations légales
class TestLegal:
    def test_lecture_de_l_environnement(self, monkeypatch):
        monkeypatch.setenv("LEGAL_PUBLISHER_NAME", "  Jean  ")
        monkeypatch.setenv("LEGAL_CONTACT_EMAIL", "a@b.fr")
        monkeypatch.delenv("LEGAL_HOST", raising=False)
        info = legal.legal_info()
        assert info["publisher"] == "Jean" and info["email"] == "a@b.fr" and "PythonAnywhere" in info["host"]

    def test_valeurs_par_defaut_vides(self, monkeypatch):
        for k in ("LEGAL_PUBLISHER_NAME", "LEGAL_PUBLISHER_ADDRESS", "LEGAL_CONTACT_EMAIL"):
            monkeypatch.delenv(k, raising=False)
        info = legal.legal_info()
        assert info["publisher"] == info["publisher_address"] == info["email"] == ""
