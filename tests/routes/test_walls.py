"""Murs : création (photo, quotas, stockage), page, modification, murs privés et codes, déblocage, suppression."""
import io
import os

import pytest

from src import constants as C
from tests.helpers import create_block, create_gym, create_wall, csrf, png, post


@pytest.fixture
def salle(alice):
    create_gym(alice, "Salle A")
    return 1


def nouveau_mur(client, **over):
    data = {"csrf_token": csrf(client, "/wall/new"), "name": "Mur X", "gym_id": "1", "image": (png(), "m.png")}
    data.update(over)
    return client.post("/wall/new", data=data, content_type="multipart/form-data")


def photos(app):
    return [f for f in os.listdir(app.config["UPLOAD_FOLDER"]) if f.endswith(".jpg")]


class TestCreation:
    def test_creation_enregistre_le_mur_et_une_photo_jpeg(self, app, alice, salle, dbq):
        r = nouveau_mur(alice, name="  Pan Rouge  ")
        assert r.status_code == 302 and r.headers["Location"] == "/wall/1"
        wall = dbq("SELECT * FROM wall")[0]
        assert wall["name"] == "Pan Rouge" and wall["is_private"] == 0 and wall["access_code"] is None
        assert photos(app) == [wall["image_filename"]]

    def test_page_de_creation_exige_une_connexion(self, anon):
        assert anon.get("/wall/new").status_code == 302
        assert anon.post("/wall/new", data={}).status_code == 400   # pas de jeton CSRF

    def test_salle_preselectionnee(self, alice, salle):
        assert 'value="1" selected' in alice.get("/wall/new?gym_id=1").get_data(as_text=True).replace("  ", " ") or "selected" in alice.get("/wall/new?gym_id=1").get_data(as_text=True)

    @pytest.mark.parametrize("over,message", [
        ({"name": "  "}, "nom du mur est requis"),
        ({"name": "x" * (C.NAME_MAX + 1)}, "limité à 100"),
        ({"gym_id": ""}, "salle est requise"),
        ({"gym_id": "999"}, "n'existe pas"),
    ])
    def test_refus(self, alice, salle, over, message):
        import html
        assert message in html.unescape(nouveau_mur(alice, **over).get_data(as_text=True))

    def test_nom_de_100_caracteres_accepte(self, alice, salle):
        assert nouveau_mur(alice, name="m" * 100).status_code == 302

    def test_sans_image(self, alice, salle):
        r = alice.post("/wall/new", data={"csrf_token": csrf(alice, "/wall/new"), "name": "X", "gym_id": "1"}, content_type="multipart/form-data")
        assert "uploader une image" in r.get_data(as_text=True)

    def test_fichier_qui_n_est_pas_une_image(self, app, alice, salle, dbq):
        r = nouveau_mur(alice, image=(io.BytesIO(b"pas une image"), "a.png"))
        assert "Image invalide" in r.get_data(as_text=True) and dbq("SELECT 1 FROM wall") == [] and photos(app) == []

    def test_photo_trop_grande_en_pixels(self, app, alice, salle, monkeypatch):
        monkeypatch.setattr("src.services.images.MAX_IMAGE_PIXELS", 1000)
        assert "trop grande" in nouveau_mur(alice).get_data(as_text=True)
        assert photos(app) == []

    def test_requete_trop_volumineuse_413(self, alice, salle, app):
        app.config["MAX_CONTENT_LENGTH"] = 1000
        r = nouveau_mur(alice, image=(io.BytesIO(b"x" * 5000), "gros.png"))
        assert r.status_code == 413 and "Fichier trop volumineux" in r.get_data(as_text=True)

    def test_la_photo_est_recompressee_en_jpeg_1600_max(self, app, alice, salle, dbq):
        from PIL import Image
        nouveau_mur(alice, image=(png(4000, 3000), "grosse.png"))
        with Image.open(os.path.join(app.config["UPLOAD_FOLDER"], dbq("SELECT image_filename FROM wall")[0]["image_filename"])) as img:
            assert img.format == "JPEG" and max(img.size) == C.MAX_IMAGE_DIMENSION if hasattr(C, "MAX_IMAGE_DIMENSION") else max(img.size) == 1600

    def test_salle_privee_sans_acces_refuse(self, app, alice, bob):
        create_gym(alice, "Privée", private=True)
        assert "salle est privée" in nouveau_mur(bob, gym_id="1").get_data(as_text=True)


class TestQuotas:
    def test_quota_journalier_sans_fichier_orphelin(self, app, alice, salle, monkeypatch):
        monkeypatch.setitem(C.QUOTAS["wall"], "daily", 2)
        assert nouveau_mur(alice, name="M1").status_code == 302 and nouveau_mur(alice, name="M2").status_code == 302
        r = nouveau_mur(alice, name="M3")
        assert r.status_code == 200 and "Limite journalière" in r.get_data(as_text=True)
        assert len(photos(app)) == 2

    def test_quota_total(self, alice, salle, monkeypatch):
        monkeypatch.setitem(C.QUOTAS["wall"], "total", 1)
        nouveau_mur(alice, name="M1")
        assert "Limite atteinte" in nouveau_mur(alice, name="M2").get_data(as_text=True)

    def test_les_quotas_sont_par_compte(self, alice, bob, salle, monkeypatch):
        monkeypatch.setitem(C.QUOTAS["wall"], "total", 1)
        nouveau_mur(alice, name="M1")
        assert nouveau_mur(bob, name="M2").status_code == 302

    def test_admin_exempte(self, admin, salle, monkeypatch):
        monkeypatch.setitem(C.QUOTAS["wall"], "total", 0)
        assert nouveau_mur(admin).status_code == 302

    def test_plafond_de_stockage(self, alice, salle, monkeypatch):
        assert nouveau_mur(alice, name="Premier").status_code == 302   # le dossier n'est plus vide
        monkeypatch.setattr("src.routes.walls.MAX_UPLOADS_MB", 0)
        assert "capacité de stockage" in nouveau_mur(alice).get_data(as_text=True)


class TestPageDuMur:
    def test_page_publique_avec_blocs(self, anon, alice, salle):
        nouveau_mur(alice, name="Mur Public")
        create_block(alice, 1, "Bloc Un")
        page = anon.get("/wall/1").get_data(as_text=True)
        assert "Mur Public" in page and "Bloc Un" in page and 'href="/gym/1" class="back-link" data-back' in page

    def test_mur_inexistant(self, anon):
        assert anon.get("/wall/999").status_code == 404

    def test_la_visite_d_un_anonyme_n_ecrit_rien(self, anon, alice, salle, dbq, dbq_write):
        nouveau_mur(alice)
        dbq_write("UPDATE wall SET last_activity_at = '2020-01-01 00:00:00'")
        anon.get("/wall/1")
        assert dbq("SELECT last_activity_at FROM wall")[0][0] == "2020-01-01 00:00:00"

    def test_la_visite_d_un_connecte_garde_le_mur_actif_et_annule_l_avertissement(self, alice, salle, dbq, dbq_write):
        nouveau_mur(alice)
        dbq_write("UPDATE wall SET last_activity_at = '2020-01-01 00:00:00', warning_sent_at = '2026-01-01'")
        alice.get("/wall/1")
        row = dbq("SELECT * FROM wall")[0]
        assert row["last_activity_at"] > "2020" and row["warning_sent_at"] is None

    def test_les_robots_ne_gardent_pas_un_mur_en_vie(self, alice, salle, dbq, dbq_write):
        nouveau_mur(alice)
        dbq_write("UPDATE wall SET last_activity_at = '2020-01-01 00:00:00'")
        alice.get("/wall/1", headers={"User-Agent": "Googlebot/2.1"})
        assert dbq("SELECT last_activity_at FROM wall")[0][0] == "2020-01-01 00:00:00"

    def test_liste_des_murs(self, anon, alice, salle):
        nouveau_mur(alice, name="Mur Liste")
        page = anon.get("/walls").get_data(as_text=True)
        assert "Mur Liste" in page and "/media/" in page


class TestMurPrive:
    @pytest.fixture
    def prive(self, alice, salle):
        nouveau_mur(alice, name="Mur Secret", is_private="1")
        create_block(alice, 1, "Bloc Secret")

    def test_code_genere_10_caracteres(self, prive, dbq):
        code = dbq("SELECT access_code FROM wall")[0][0]
        assert len(code) == C.ACCESS_CODE_LENGTH and set(code) <= set(C.ACCESS_CODE_ALPHABET)

    def test_le_proprietaire_voit_son_code(self, alice, prive, dbq):
        assert dbq("SELECT access_code FROM wall")[0][0] in alice.get("/wall/1").get_data(as_text=True)

    def test_un_etranger_voit_le_formulaire_de_code_sans_le_contenu(self, bob, prive):
        page = bob.get("/wall/1").get_data(as_text=True)
        assert "code" in page.lower() and "Bloc Secret" not in page

    def test_un_anonyme_ne_voit_pas_le_mur(self, anon, prive):
        assert "Bloc Secret" not in anon.get("/wall/1").get_data(as_text=True)

    def test_bloc_et_api_d_un_mur_prive_sont_introuvables(self, bob, anon, prive):
        for client in (bob, anon):
            assert client.get("/api/block/1/holds").status_code == 404
            assert client.get("/api/block/1/notes").status_code == 404
            assert client.get("/block/1").status_code in (200, 404)
            assert "Bloc Secret" not in client.get("/block/1").get_data(as_text=True)

    def test_deblocage_avec_le_bon_code(self, bob, prive, dbq):
        code = dbq("SELECT access_code FROM wall")[0][0]
        r = post(bob, "/wall/1/unlock", {"code": f" {code[:5].lower()}-{code[5:].lower()} "})   # espaces, tiret et casse tolérés
        assert r.status_code == 302 and "Bloc Secret" in bob.get("/wall/1").get_data(as_text=True)

    def test_mauvais_code(self, bob, prive):
        assert "Code incorrect" in post(bob, "/wall/1/unlock", {"code": "FAUX"}).get_data(as_text=True)
        assert "Bloc Secret" not in bob.get("/wall/1").get_data(as_text=True)

    def test_limite_d_essais(self, bob, prive, dbq):
        for _ in range(C.UNLOCK_USER_MAX):
            post(bob, "/wall/1/unlock", {"code": "FAUX"})
        code = dbq("SELECT access_code FROM wall")[0][0]
        r = post(bob, "/wall/1/unlock", {"code": code})
        assert r.status_code == 429 and "Bloc Secret" not in bob.get("/wall/1").get_data(as_text=True)

    def test_deblocage_exige_une_connexion(self, anon, prive):
        assert anon.post("/wall/1/unlock", data={"code": "X"}).status_code == 400   # CSRF d'abord

    def test_un_mur_prive_n_apparait_pas_dans_les_listes(self, anon, prive):
        for path in ["/", "/walls", "/gym/1"]:
            assert "Mur Secret" not in anon.get(path).get_data(as_text=True)

    def test_un_mur_dans_une_salle_privee_suit_la_salle(self, alice, bob, dbq):
        create_gym(alice, "Salle Close", private=True)
        nouveau_mur(alice, name="Mur Public Dans Salle Privée", gym_id="1")
        assert "Mur Public Dans Salle Privée" not in bob.get("/walls").get_data(as_text=True)


class TestModification:
    @pytest.fixture
    def mur(self, alice, salle):
        nouveau_mur(alice, name="Ancien Nom")

    def edit(self, client, **over):
        data = {"name": "Nouveau Nom", "gym_id": "1"}
        data.update(over)
        return post(client, "/wall/1/edit", data)

    def test_renommage(self, alice, mur, dbq):
        assert self.edit(alice).status_code == 302
        assert dbq("SELECT name FROM wall")[0][0] == "Nouveau Nom"

    def test_rendre_prive_genere_un_code_puis_public_l_efface(self, alice, mur, dbq):
        self.edit(alice, is_private="1")
        row = dbq("SELECT * FROM wall")[0]
        assert row["is_private"] == 1 and row["access_code"]
        self.edit(alice, is_private="1")
        assert dbq("SELECT access_code FROM wall")[0][0] == row["access_code"]      # code conservé
        self.edit(alice, is_private="1", regenerate_code="1")
        assert dbq("SELECT access_code FROM wall")[0][0] != row["access_code"]      # code régénéré
        self.edit(alice)
        assert dbq("SELECT is_private, access_code FROM wall")[0][:] == (0, None)

    def test_le_renommage_met_a_jour_le_carnet(self, alice, mur, dbq):
        create_block(alice, 1, "B")
        post_ascent = alice.post("/api/block/1/ascent", json={"done": True}, headers={"X-CSRF-Token": csrf(alice)})
        assert post_ascent.status_code == 200
        self.edit(alice)
        assert dbq("SELECT wall_name FROM climb_log")[0][0] == "Nouveau Nom"

    def test_un_autre_compte_ne_peut_pas_modifier(self, bob, mur, dbq):
        assert self.edit(bob).status_code == 403
        assert dbq("SELECT name FROM wall")[0][0] == "Ancien Nom"

    def test_un_admin_peut_modifier(self, admin, mur, dbq):
        assert self.edit(admin).status_code == 302

    def test_validations(self, alice, mur):
        assert "requis" in self.edit(alice, name="").get_data(as_text=True)
        assert "n'existe pas" in self.edit(alice, gym_id="99").get_data(as_text=True).replace("&#39;", "'")

    def test_mur_inexistant(self, alice):
        assert alice.get("/wall/99/edit").status_code == 404


class TestSuppression:
    @pytest.fixture
    def mur(self, alice, salle):
        nouveau_mur(alice)
        create_block(alice, 1, "B1")
        alice.post("/api/block/1/ascent", json={"flash": True}, headers={"X-CSRF-Token": csrf(alice)})
        alice.post("/api/block/1/note", json={"note": "6a"}, headers={"X-CSRF-Token": csrf(alice)})

    def test_suppression_en_cascade_et_photo_effacee(self, app, alice, mur, dbq):
        photo = os.path.join(app.config["UPLOAD_FOLDER"], dbq("SELECT image_filename FROM wall")[0][0])
        post(alice, "/wall/1/favorite")
        r = post(alice, "/wall/1/delete")
        assert r.status_code == 302 and r.headers["Location"] == "/"
        for table in ["wall", "block", "hold", "ascent", "block_note", "wall_favorite"]:
            assert dbq(f"SELECT 1 FROM {table}") == [], table
        assert not os.path.exists(photo)

    def test_le_carnet_de_progression_survit(self, alice, mur, dbq):
        post(alice, "/wall/1/delete")
        assert dbq("SELECT block_name, flash FROM climb_log")[0][:] == ("B1", 1)

    def test_un_autre_compte_ne_peut_pas_supprimer(self, bob, mur, dbq):
        assert post(bob, "/wall/1/delete").status_code == 403
        assert dbq("SELECT 1 FROM wall")

    def test_un_etranger_ne_peut_pas_supprimer_un_mur_prive_il_est_introuvable(self, alice, bob, salle, dbq):
        nouveau_mur(alice, name="Secret", is_private="1")
        assert post(bob, "/wall/1/delete").status_code == 404

    def test_un_admin_supprime_et_l_action_est_journalisee(self, admin, alice, mur, dbq):
        assert post(admin, "/wall/1/delete").status_code == 302
        assert dbq("SELECT 1 FROM wall") == []
        assert "Mur supprimé par un admin" in dbq("SELECT action FROM admin_log")[0][0]

    def test_suppression_exige_post_et_csrf(self, alice, mur):
        assert alice.get("/wall/1/delete").status_code == 405
        assert alice.post("/wall/1/delete").status_code == 400

    def test_signalements_en_attente_marques_supprimes(self, alice, bob, mur, dbq):
        post(bob, "/report", {"target_type": "wall", "target_id": "1", "reason": "other", "details": "contenu inapproprié"})
        post(alice, "/wall/1/delete")
        assert dbq("SELECT status FROM report")[0][0] == "gone"
