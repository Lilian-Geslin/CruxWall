"""Profil : réglages du compte (pseudo, email, mot de passe), export JSON, suppression du compte."""
import html
import json
import os

import pytest

from src import constants as C
from tests.helpers import PASSWORD, create_block, create_gym, create_wall, post
from tests.routes.test_auth import login


def settings(client, action, **fields):
    return post(client, "/profil/settings", {"action": action, "current_password": fields.pop("current", PASSWORD), **fields})


class TestPageProfil:
    def test_profil_exige_une_connexion(self, anon):
        assert anon.get("/profil").status_code == 302

    def test_profil_et_onglets(self, alice, decor_alice):
        page = alice.get("/profil").get_data(as_text=True)
        assert "Alice" in page and "Mur Public" in page
        for tab in ["/favoris", "/a-faire", "/carnet"]:
            assert tab in page


@pytest.fixture
def decor_alice(alice):
    create_gym(alice, "Salle Publique")
    create_wall(alice, "Mur Public", 1)
    create_block(alice, 1, "Bloc Public")


class TestPseudo:
    def test_changement_de_pseudo(self, alice, dbq):
        r = settings(alice, "pseudo", new_pseudo="Alice_2")
        assert r.status_code == 302 and r.headers["Location"].endswith("ok=pseudo")
        assert dbq("SELECT name FROM user")[0]["name"] == "Alice_2"
        assert "Alice_2" in alice.get("/profil").get_data(as_text=True)

    @pytest.mark.parametrize("pseudo,message", [("ab", "Pseudo invalide"), ("Alice", "déjà votre pseudo"), ("bob", "déjà pris")])
    def test_refus(self, alice, bob, pseudo, message):
        assert message in settings(alice, "pseudo", new_pseudo=pseudo).get_data(as_text=True)

    def test_trois_changements_par_24_heures(self, alice):
        for i in range(C.PSEUDO_CHANGE_MAX):
            assert settings(alice, "pseudo", new_pseudo=f"Nom_{i}").status_code == 302
        assert "3 fois aujourd'hui" in html.unescape(settings(alice, "pseudo", new_pseudo="Nom_9").get_data(as_text=True))

    def test_mot_de_passe_actuel_faux(self, alice, dbq):
        assert "Mot de passe actuel incorrect" in settings(alice, "pseudo", new_pseudo="Nom_x", current="faux").get_data(as_text=True)
        assert dbq("SELECT name FROM user")[0]["name"] == "Alice"

    def test_action_inconnue(self, alice):
        assert post(alice, "/profil/settings", {"action": "role"}).status_code == 400


class TestEmail:
    def test_changement_d_email(self, alice, dbq):
        assert settings(alice, "email", new_email="Nouveau@Example.fr").status_code == 302
        assert dbq("SELECT email FROM user")[0]["email"] == "nouveau@example.fr"

    @pytest.mark.parametrize("email,message", [("nimporte", "invalide"), ("alice@example.fr", "déjà votre adresse"), ("bob@example.fr", "déjà utilisée")])
    def test_refus(self, alice, bob, email, message):
        assert message in settings(alice, "email", new_email=email).get_data(as_text=True)


class TestMotDePasse:
    def test_changement_puis_connexion_avec_le_nouveau(self, app, alice):
        assert settings(alice, "password", new_password="nouveau-mdp-1", confirm_password="nouveau-mdp-1").status_code == 302
        assert login(app, "alice@example.fr", "nouveau-mdp-1")[1].status_code == 302
        assert login(app, "alice@example.fr", PASSWORD)[1].status_code == 200

    @pytest.mark.parametrize("fields,message", [
        ({"new_password": "court", "confirm_password": "court"}, "entre 8 et 128"),
        ({"new_password": "nouveau-mdp-1", "confirm_password": "autre-chose-1"}, "confirmation ne correspond pas"),
        ({"new_password": PASSWORD, "confirm_password": PASSWORD}, "différent de l'ancien"),
    ])
    def test_refus(self, alice, fields, message):
        assert message in html.unescape(settings(alice, "password", **fields).get_data(as_text=True))

    def test_verrou_apres_cinq_mots_de_passe_actuels_faux(self, alice):
        for _ in range(C.ACCOUNT_FAIL_MAX):
            settings(alice, "pseudo", new_pseudo="Nom_x", current="faux")
        r = settings(alice, "pseudo", new_pseudo="Nom_x", current=PASSWORD)
        assert r.status_code == 429 and "Trop de tentatives" in r.get_data(as_text=True)


class TestExport:
    def test_export_json_complet(self, alice, bob, decor_alice):
        post(alice, "/block/1/favorite")
        post(alice, "/block/1/todo")
        post(alice, "/wall/1/favorite")
        post(alice, "/gym/1/favorite")
        r = alice.get("/profil/export")
        assert r.status_code == 200 and "attachment" in r.headers["Content-Disposition"]
        data = json.loads(r.get_data(as_text=True))
        for key in ["blocs_favoris", "blocs_a_faire", "murs_favoris", "salles_favorites", "carnet_de_progression"]:
            assert key in data
        assert "password" not in r.get_data(as_text=True).lower()
        assert "Bloc Public" in r.get_data(as_text=True)

    def test_export_exige_une_connexion(self, anon):
        assert anon.get("/profil/export").status_code == 302

    def test_export_contient_le_lien_du_bloc(self, alice, decor_alice, dbq_write):
        dbq_write("UPDATE block SET link = 'https://exemple.fr/v' WHERE id = 1")
        assert "exemple.fr/v" in alice.get("/profil/export").get_data(as_text=True)

    def test_export_ne_contient_pas_les_donnees_des_autres(self, alice, bob, decor_alice):
        post(bob, "/block/1/favorite")
        assert "Bob" not in alice.get("/profil/export").get_data(as_text=True)


class TestSuppressionDeCompte:
    def delete(self, client, password=PASSWORD, confirm=True, public=False):
        data = {"password": password}
        if confirm:
            data["confirm"] = "1"
        if public:
            data["delete_public"] = "1"
        return post(client, "/profil/delete", data)

    def test_page_de_confirmation(self, alice, decor_alice):
        assert alice.get("/profil/delete").status_code == 200

    def test_refus_sans_case_ou_avec_mauvais_mot_de_passe(self, alice, dbq):
        assert "Cochez la case" in self.delete(alice, confirm=False).get_data(as_text=True)
        assert "Mot de passe incorrect" in self.delete(alice, password="faux").get_data(as_text=True)
        assert len(dbq("SELECT 1 FROM user")) == 1

    def test_verrou_apres_cinq_mots_de_passe_faux(self, alice):
        for _ in range(5):
            self.delete(alice, password="faux")
        assert self.delete(alice).status_code == 429

    def test_le_compte_disparait_avec_ses_donnees_personnelles(self, app, alice, bob, decor_alice, dbq):
        post(bob, "/block/1/favorite")
        r = self.delete(bob)
        assert "Compte supprimé" in r.get_data(as_text=True)
        assert dbq("SELECT 1 FROM user WHERE name = 'Bob'") == [] and dbq("SELECT 1 FROM block_favorite") == []
        assert bob.get("/profil").status_code == 302

    def test_contenu_public_conserve_sans_createur_par_defaut(self, alice, decor_alice, dbq):
        self.delete(alice)
        assert dbq("SELECT created_by FROM wall")[0]["created_by"] is None
        assert dbq("SELECT created_by FROM gym")[0]["created_by"] is None

    def test_contenu_public_supprime_si_demande_et_photo_effacee(self, app, alice, decor_alice, dbq):
        photo = os.path.join(app.config["UPLOAD_FOLDER"], dbq("SELECT image_filename FROM wall")[0]["image_filename"])
        assert os.path.exists(photo)
        self.delete(alice, public=True)
        assert dbq("SELECT 1 FROM wall") == [] and dbq("SELECT 1 FROM gym") == [] and not os.path.exists(photo)

    def test_murs_prives_toujours_supprimes(self, alice, dbq):
        create_gym(alice, "S")
        create_wall(alice, "Privé", 1, private=True)
        self.delete(alice)
        assert dbq("SELECT 1 FROM wall") == []

    def test_les_blocs_crees_sur_le_mur_d_un_autre_sont_supprimes(self, alice, bob, decor_alice, dbq):
        create_block(bob, 1, "Bloc De Bob")
        self.delete(bob)
        assert [r["name"] for r in dbq("SELECT name FROM block")] == ["Bloc Public"]

    def test_dernier_administrateur_ne_peut_pas_se_supprimer(self, admin, dbq):
        assert "dernier administrateur" in self.delete(admin).get_data(as_text=True)
        assert len(dbq("SELECT 1 FROM user")) == 1

    def test_un_administrateur_peut_se_supprimer_s_il_en_reste_un_autre(self, admin, alice, dbq_write, dbq):
        dbq_write("UPDATE user SET role = 'admin' WHERE name = 'Alice'")
        assert "Compte supprimé" in self.delete(admin).get_data(as_text=True)
