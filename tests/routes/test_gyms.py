"""Salles : liste, création (normale et rapide), page avec recherche/propositions, privé + code, modification, suppression."""
import html
import os

import pytest

from src import constants as C
from tests.helpers import create_block, create_gym, create_wall, csrf, post


def nouvelle(client, name="Salle A", **extra):
    return post(client, "/gym/new", {"name": name, "location": "Lyon", **extra})


class TestCreation:
    def test_creation_et_redirection(self, alice, dbq):
        r = nouvelle(alice, "  Climb Up  ")
        assert r.status_code == 302 and r.headers["Location"].endswith("/gyms")
        gym = dbq("SELECT * FROM gym")[0]
        assert gym["name"] == "Climb Up" and gym["location"] == "Lyon" and gym["is_private"] == 0 and gym["access_code"] is None

    def test_exige_connexion_et_csrf(self, anon, alice):
        assert anon.post("/gym/new", data={"name": "X"}).status_code == 400
        assert alice.post("/gym/new", data={"name": "X"}).status_code == 400

    def test_nom_vide_ou_trop_long_ignore(self, alice, dbq):
        nouvelle(alice, "   ")
        nouvelle(alice, "x" * (C.NAME_MAX + 1))
        post(alice, "/gym/new", {"name": "ok", "location": "v" * (C.LOCATION_MAX + 1)})
        assert dbq("SELECT 1 FROM gym") == []

    def test_noms_de_100_caracteres_et_ville_de_60_acceptes(self, alice, dbq):
        post(alice, "/gym/new", {"name": "s" * 100, "location": "v" * 60})
        assert len(dbq("SELECT 1 FROM gym")) == 1

    def test_doublon_insensible_a_la_casse(self, alice, dbq):
        nouvelle(alice, "Bloc Session")
        r = nouvelle(alice, "BLOC session")
        assert r.status_code == 400 and "porte déjà ce nom" in r.get_data(as_text=True)
        assert len(dbq("SELECT 1 FROM gym")) == 1

    def test_salle_privee_recoit_un_code(self, alice, dbq):
        nouvelle(alice, "Privée", is_private="1")
        code = dbq("SELECT access_code FROM gym")[0][0]
        assert len(code) == C.ACCESS_CODE_LENGTH

    def test_quota_journalier_et_total(self, alice, bob, monkeypatch):
        monkeypatch.setitem(C.QUOTAS["gym"], "daily", 2)
        nouvelle(alice, "G1"); nouvelle(alice, "G2")
        assert "Limite journalière" in nouvelle(alice, "G3").get_data(as_text=True)
        monkeypatch.setitem(C.QUOTAS["gym"], "total", 2)
        assert "Limite atteinte" in nouvelle(alice, "G4").get_data(as_text=True)
        assert nouvelle(bob, "G5").status_code == 302      # le plafond total est propre à chaque compte

    def test_admin_exempte(self, admin, monkeypatch, dbq):
        monkeypatch.setitem(C.QUOTAS["gym"], "total", 0)
        nouvelle(admin, "Admin Gym")
        assert len(dbq("SELECT 1 FROM gym")) == 1


class TestCreationRapide:
    def quick(self, client, **data):
        return client.post("/api/gym/quick_create", data={"csrf_token": csrf(client), **data})

    def test_succes_json(self, alice, dbq):
        r = self.quick(alice, name="Rapide", location="Nice", is_private="1")
        j = r.get_json()
        assert r.status_code == 200 and j["success"] and j["name"] == "Rapide" and len(j["access_code"]) == 10
        assert dbq("SELECT name FROM gym")[0][0] == "Rapide"

    @pytest.mark.parametrize("data,status", [({"name": ""}, 400), ({"name": "x" * 101}, 400)])
    def test_refus(self, alice, data, status):
        assert self.quick(alice, **data).status_code == status

    def test_doublon(self, alice):
        self.quick(alice, name="Même")
        r = self.quick(alice, name="MÊME".lower())
        assert r.status_code == 400 and "porte déjà" in r.get_json()["error"]

    def test_quota_429(self, alice, monkeypatch):
        monkeypatch.setitem(C.QUOTAS["gym"], "daily", 1)
        self.quick(alice, name="A")
        assert self.quick(alice, name="B").status_code == 429

    def test_exige_connexion(self, anon):
        assert anon.post("/api/gym/quick_create", data={"name": "X"}).status_code in (400, 401, 302)


class TestListeEtPage:
    def test_liste_affiche_aussi_les_salles_privees(self, anon, alice):
        create_gym(alice, "Publique"); create_gym(alice, "Cachée", private=True)
        page = anon.get("/gyms").get_data(as_text=True)
        assert "Publique" in page and "Cachée" in page

    def test_tri_alphabetique_sans_casse(self, anon, alice):
        for n in ["zebra", "Alpha", "beta"]:
            create_gym(alice, n)
        page = anon.get("/gyms").get_data(as_text=True)
        assert page.index("Alpha") < page.index("beta") < page.index("zebra")

    def test_page_salle_liste_ses_murs(self, anon, decor):
        page = anon.get(f"/gym/{decor['gym']}").get_data(as_text=True)
        assert "Mur Public" in page and "Salle Publique" in page

    def test_salle_inexistante(self, anon):
        assert anon.get("/gym/99").status_code == 404

    def test_salle_privee_demande_le_code(self, alice, bob, find):
        create_gym(alice, "Close", private=True)
        gid = find("gym", "Close")["id"]
        create_wall(alice, "Mur Dedans", gid)
        page = bob.get(f"/gym/{gid}").get_data(as_text=True)
        assert "Mur Dedans" not in page and f"/gym/{gid}/unlock" in page
        assert "Mur Dedans" in alice.get(f"/gym/{gid}").get_data(as_text=True)      # le créateur y a accès

    def test_murs_prives_caches_dans_une_salle_publique(self, alice, bob, prive, find):
        gid = find("gym", "Salle Ouverte")["id"]
        assert "Mur Privé" not in bob.get(f"/gym/{gid}").get_data(as_text=True)
        assert "Mur Privé" in alice.get(f"/gym/{gid}").get_data(as_text=True)

    def test_visite_ecrit_pas_de_session(self, anon, decor):
        anon.get(f"/gym/{decor['gym']}")      # simple lecture, pas d'erreur
        assert anon.get("/gyms").status_code == 200


class TestRecherche:
    @pytest.fixture
    def salle(self, app, alice, bob, find):
        create_gym(alice, "Gym Recherche")
        gid = find("gym", "Gym Recherche")["id"]
        create_wall(alice, "Dévers Bleu", gid); create_wall(alice, "Dalle Rouge", gid)
        w1, w2 = find("wall", "Dévers Bleu")["id"], find("wall", "Dalle Rouge")["id"]
        create_block(alice, w1, "Crimpy", grade="6a"); create_block(alice, w1, "Dynamo", grade="6a+")
        create_block(bob, w2, "Sloper Fou", grade="7a")
        return gid

    def test_recherche_par_nom_de_mur(self, anon, salle):
        page = anon.get(f"/gym/{salle}?q=dévers").get_data(as_text=True)
        assert "Dévers Bleu" in page and "Dalle Rouge" not in page

    def test_recherche_par_nom_de_bloc(self, anon, salle):
        page = anon.get(f"/gym/{salle}?q=sloper").get_data(as_text=True)
        assert "Sloper Fou" in page and "Crimpy" not in page

    def test_recherche_par_ouvreur(self, anon, salle):
        page = anon.get(f"/gym/{salle}?q=bob").get_data(as_text=True)
        assert "Sloper Fou" in page and "Crimpy" not in page

    def test_recherche_par_cotation_prefixe(self, anon, salle):
        page = anon.get(f"/gym/{salle}?q=6a").get_data(as_text=True)
        assert "Crimpy" in page and "Dynamo" in page and "Sloper Fou" not in page

    def test_moins_de_2_caracteres_ne_recherche_pas(self, anon, salle):
        page = anon.get(f"/gym/{salle}?q=s").get_data(as_text=True)
        assert "Dévers Bleu" in page and "Dalle Rouge" in page

    def test_texte_tronque_a_100_caracteres(self, anon, salle):
        assert anon.get(f"/gym/{salle}?q=" + "a" * 500).status_code == 200

    def test_injection_echappee(self, anon, salle):
        page = anon.get(f"/gym/{salle}?q=<script>alert(1)</script>").get_data(as_text=True)
        assert "<script>alert(1)</script>" not in page

    def test_suggestions_json(self, anon, salle):
        j = anon.get(f"/gym/{salle}/suggest?q=6a").get_json()
        assert {b["name"] for b in j["blocks"]} == {"Crimpy", "Dynamo"}
        assert all(set(b) == {"id", "name", "grade", "wall", "creator"} for b in j["blocks"])
        assert anon.get(f"/gym/{salle}/suggest?q=dal").get_json()["walls"][0]["name"] == "Dalle Rouge"

    def test_suggestions_court_vide(self, anon, salle):
        assert anon.get(f"/gym/{salle}/suggest?q=a").get_json() == {"walls": [], "blocks": []}

    def test_suggestions_plafonnees(self, app, alice, find, anon):
        create_gym(alice, "Grosse")
        gid = find("gym", "Grosse")["id"]
        for i in range(C.SUGGEST_WALLS_MAX + 5):
            create_wall(alice, f"Mur numéro {i}", gid)
        wid = find("wall", "Mur numéro 0")["id"]
        for i in range(C.SUGGEST_BLOCKS_MAX + 5):
            create_block(alice, wid, f"Bloc numéro {i}")
        j = anon.get(f"/gym/{gid}/suggest?q=numéro").get_json()
        assert len(j["walls"]) == C.SUGGEST_WALLS_MAX and len(j["blocks"]) == C.SUGGEST_BLOCKS_MAX

    def test_suggestions_ne_fuient_pas_les_murs_prives(self, anon, bob, prive, find):
        gid = find("gym", "Salle Ouverte")["id"]
        for c in (anon, bob):
            j = c.get(f"/gym/{gid}/suggest?q=secret").get_json()
            assert j == {"walls": [], "blocks": []}

    def test_suggestions_salle_privee_404(self, bob, alice, find):
        create_gym(alice, "Close2", private=True)
        assert bob.get(f"/gym/{find('gym', 'Close2')['id']}/suggest?q=abc").status_code == 404

    def test_suggestions_salle_inexistante(self, anon):
        assert anon.get("/gym/99/suggest?q=abc").status_code == 404


class TestDeblocage:
    @pytest.fixture
    def close(self, alice, find):
        create_gym(alice, "Close", private=True)
        return find("gym", "Close")

    def test_bon_code_donne_acces(self, bob, close):
        r = post(bob, f"/gym/{close['id']}/unlock", {"code": close["access_code"].lower()})
        assert r.status_code == 302
        assert "unlock" not in bob.get(f"/gym/{close['id']}").get_data(as_text=True)

    def test_mauvais_code(self, bob, close):
        assert "Code incorrect" in post(bob, f"/gym/{close['id']}/unlock", {"code": "NOPE"}).get_data(as_text=True)

    def test_limite_d_essais(self, bob, close):
        for _ in range(C.UNLOCK_USER_MAX):
            post(bob, f"/gym/{close['id']}/unlock", {"code": "NOPE"})
        assert post(bob, f"/gym/{close['id']}/unlock", {"code": close["access_code"]}).status_code == 429

    def test_salle_inexistante(self, bob):
        assert post(bob, "/gym/99/unlock", {"code": "X"}).status_code == 404

    def test_acces_a_la_salle_ouvre_ses_murs(self, alice, bob, close):
        create_wall(alice, "Mur Interne", close["id"])
        assert "/wall/1/unlock" in bob.get("/wall/1").get_data(as_text=True)      # page de code : le contenu reste caché
        post(bob, f"/gym/{close['id']}/unlock", {"code": close["access_code"]})
        assert "/wall/1/unlock" not in bob.get("/wall/1").get_data(as_text=True)


class TestModification:
    @pytest.fixture
    def gym(self, alice, find):
        create_gym(alice, "Avant")
        return find("gym", "Avant")["id"]

    def test_renommage(self, alice, gym, dbq):
        r = post(alice, f"/gym/{gym}/edit", {"name": "Après", "location": "Paris"})
        assert r.status_code == 302
        row = dbq("SELECT * FROM gym")[0]
        assert (row["name"], row["location"]) == ("Après", "Paris")

    def test_confidentialite_et_code(self, alice, gym, dbq):
        post(alice, f"/gym/{gym}/edit", {"name": "Avant", "is_private": "1"})
        code = dbq("SELECT access_code FROM gym")[0][0]
        assert code
        post(alice, f"/gym/{gym}/edit", {"name": "Avant", "is_private": "1"})
        assert dbq("SELECT access_code FROM gym")[0][0] == code
        post(alice, f"/gym/{gym}/edit", {"name": "Avant", "is_private": "1", "regenerate_code": "1"})
        assert dbq("SELECT access_code FROM gym")[0][0] != code
        post(alice, f"/gym/{gym}/edit", {"name": "Avant"})
        assert dbq("SELECT access_code FROM gym")[0][0] is None

    def test_validations(self, alice, gym):
        assert "requis" in post(alice, f"/gym/{gym}/edit", {"name": ""}).get_data(as_text=True)
        assert "limités" in post(alice, f"/gym/{gym}/edit", {"name": "x" * 101}).get_data(as_text=True)
        create_gym(alice, "Autre")
        assert "porte déjà" in post(alice, f"/gym/{gym}/edit", {"name": "autre"}).get_data(as_text=True)

    def test_garder_son_propre_nom_est_possible(self, alice, gym):
        assert post(alice, f"/gym/{gym}/edit", {"name": "Avant", "location": "X"}).status_code == 302

    def test_autre_compte_refuse(self, bob, gym):
        assert bob.get(f"/gym/{gym}/edit").status_code == 403
        assert post(bob, f"/gym/{gym}/edit", {"name": "Hack"}).status_code == 403

    def test_admin_autorise(self, admin, gym):
        assert post(admin, f"/gym/{gym}/edit", {"name": "Admin"}).status_code == 302

    def test_inexistante(self, alice):
        assert alice.get("/gym/99/edit").status_code == 404


class TestSuppression:
    @pytest.fixture
    def plein(self, app, alice, find):
        create_gym(alice, "À Supprimer")
        gid = find("gym", "À Supprimer")["id"]
        create_wall(alice, "M1", gid); create_wall(alice, "M2", gid)
        create_block(alice, find("wall", "M1")["id"], "B1")
        return gid

    def test_supprime_murs_blocs_et_photos(self, app, alice, plein, dbq):
        photos = [os.path.join(app.config["UPLOAD_FOLDER"], r[0]) for r in dbq("SELECT image_filename FROM wall")]
        assert all(os.path.exists(p) for p in photos)
        r = post(alice, f"/gym/{plein}/delete")
        assert r.status_code == 302 and r.headers["Location"].endswith("/gyms")
        for t in ["gym", "wall", "block", "hold"]:
            assert dbq(f"SELECT 1 FROM {t}") == [], t
        assert not any(os.path.exists(p) for p in photos)

    def test_autre_compte_refuse(self, bob, plein, dbq):
        assert post(bob, f"/gym/{plein}/delete").status_code == 403
        assert dbq("SELECT 1 FROM gym")

    def test_admin_supprime(self, admin, plein, dbq):
        assert post(admin, f"/gym/{plein}/delete").status_code == 302 and dbq("SELECT 1 FROM gym") == []

    def test_inexistante_redirige(self, alice):
        assert post(alice, "/gym/99/delete").status_code == 302

    def test_get_interdit(self, alice, plein):
        assert alice.get(f"/gym/{plein}/delete").status_code == 405

    def test_favoris_de_salle_nettoyes(self, alice, plein, dbq):
        post(alice, f"/gym/{plein}/favorite")
        post(alice, f"/gym/{plein}/delete")
        assert dbq("SELECT 1 FROM gym_favorite") == []
