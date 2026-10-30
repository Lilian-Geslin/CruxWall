"""Blocs : création par l'éditeur (API), page, modification, suppression, données des prises, accès."""
import pytest

from src import constants as C
from tests.helpers import HOLDS, block_payload, create_block, post, post_json


def save(client, wall_id, name="Nouveau", **over):
    return post_json(client, "/api/block/save", block_payload(wall_id, name, **over))


class TestCreation:
    def test_creation_complete(self, alice, decor, dbq):
        r = save(alice, decor["wall"], "  Mon Bloc ", grade="6b+", color="#ef4444", description="Départ assis", link="https://exemple.fr/video")
        assert r.status_code == 200 and r.get_json()["success"]
        b = dbq("SELECT * FROM block WHERE name = 'Mon Bloc'")[0]
        assert (b["grade"], b["color"], b["description"], b["link"]) == ("6b+", "#ef4444", "Départ assis", "https://exemple.fr/video")
        assert [h["hold_type"] for h in dbq("SELECT * FROM hold WHERE block_id = ?", b["id"])] == ["start", "mid", "top"]

    def test_cotation_optionnelle(self, alice, decor):
        assert save(alice, decor["wall"], grade="").status_code == 200

    def test_types_de_prises_dont_pied(self, alice, decor, dbq):
        holds = HOLDS + [{"x": 0.3, "y": 0.9, "type": "foot", "w": 0.05, "h": 0.04}]
        r = save(alice, decor["wall"], "Avec pied", holds=holds)
        assert r.status_code == 200
        assert dbq("SELECT hold_type, w, h FROM hold WHERE hold_type='foot'")[0][:] == ("foot", 0.05, 0.04)

    def test_exige_connexion(self, anon, decor):
        assert anon.post("/api/block/save", json=block_payload(decor["wall"])).status_code in (400, 401, 302)

    def test_exige_csrf(self, alice, decor):
        assert alice.post("/api/block/save", json=block_payload(decor["wall"])).status_code == 400

    @pytest.mark.parametrize("over,msg", [
        ({"name": ""}, "Nom et mur requis"),
        ({"name": "x" * 101}, "limité à 100"),
        ({"grade": "9z"}, "Cotation invalide"),
        ({"color": "#123456"}, "Couleur invalide"),
        ({"description": "d" * 501}, "limitée à 500"),
        ({"link": "ftp://x.fr"}, ""),
        ({"link": "x" * 301}, ""),
        ({"link": "mailto:a@b.fr"}, ""),
        ({"holds": HOLDS[:1]}, "au moins 2 prises"),
        ({"holds": HOLDS * 40}, "plus de 100 prises"),
        ({"holds": "pas une liste"}, "Prises invalides"),
        ({"holds": [{"x": 2, "y": 0.1}, {"x": 0.1, "y": 0.1}]}, "Position"),
        ({"holds": [{"x": 0.1, "y": 0.1, "type": "zzz"}, {"x": 0.2, "y": 0.1}]}, "Type de prise"),
        ({"holds": [{"x": 0.1, "y": 0.1, "w": 5}, {"x": 0.2, "y": 0.1}]}, "Taille"),
    ])
    def test_refus_400(self, alice, decor, over, msg):
        r = save(alice, decor["wall"], **over)
        assert r.status_code == 400 and msg in r.get_json()["error"]

    def test_corps_non_json(self, alice, decor):
        r = alice.post("/api/block/save", data="x", headers={"X-CSRF-Token": "?"})
        assert r.status_code == 400

    def test_100_prises_acceptees(self, alice, decor):
        holds = [{"x": 0.5, "y": i / 200, "type": "mid"} for i in range(100)]
        assert save(alice, decor["wall"], holds=holds).status_code == 200

    def test_lien_sans_schema_complete(self, alice, decor, dbq):
        save(alice, decor["wall"], "Lien", link="exemple.fr/v")
        assert dbq("SELECT link FROM block WHERE name='Lien'")[0][0] == "https://exemple.fr/v"

    def test_nom_unique_par_mur_sans_casse(self, alice, decor):
        r = save(alice, decor["wall"], "BLOC PUBLIC")
        assert r.status_code == 400 and "existe déjà" in r.get_json()["error"]

    def test_meme_nom_sur_un_autre_mur(self, alice, decor, find):
        from tests.helpers import create_wall
        create_wall(alice, "Autre Mur", decor["gym"])
        assert save(alice, find("wall", "Autre Mur")["id"], "Bloc Public").status_code == 200

    def test_mur_inexistant(self, alice):
        assert save(alice, 999).status_code == 404

    def test_mur_prive_inaccessible(self, bob, prive):
        assert save(bob, prive["wall"], "Intrus").status_code in (403, 404)

    def test_quotas(self, alice, decor, monkeypatch):
        monkeypatch.setitem(C.QUOTAS["block"], "daily", 3)
        assert save(alice, decor["wall"], "B2").status_code == 200
        assert save(alice, decor["wall"], "B3").status_code == 200
        r = save(alice, decor["wall"], "B4")
        assert r.status_code == 429 and "Limite journalière" in r.get_json()["error"]

    def test_quota_total_et_admin_exempt(self, alice, admin, decor, monkeypatch):
        monkeypatch.setitem(C.QUOTAS["block"], "total", 1)
        assert save(alice, decor["wall"], "B2").status_code == 429
        assert save(admin, decor["wall"], "Admin B").status_code == 200

    def test_creation_maintient_le_mur_actif(self, alice, decor, dbq, dbq_write):
        dbq_write("UPDATE wall SET last_activity_at='2020-01-01 00:00:00'")
        save(alice, decor["wall"], "Actif")
        assert dbq("SELECT last_activity_at FROM wall")[0][0] > "2020"


class TestPages:
    def test_page_bloc(self, anon, decor):
        page = anon.get(f"/block/{decor['block']}").get_data(as_text=True)
        assert "Bloc Public" in page and "6a" in page

    def test_lien_cliquable_securise(self, anon, alice, decor):
        bid = save(alice, decor["wall"], "Avec lien", link="https://exemple.fr/v?a=1&b=2").get_json()["block_id"]
        page = anon.get(f"/block/{bid}").get_data(as_text=True)
        assert 'href="https://exemple.fr/v?a=1&amp;b=2"' in page and "noopener" in page

    def test_bloc_inexistant(self, anon):
        assert anon.get("/block/999").status_code == 404

    def test_bloc_d_un_mur_prive_cache(self, anon, bob, prive):
        for c in (anon, bob):
            page = c.get(f"/block/{prive['block']}").get_data(as_text=True)
            assert "Bloc Secret" not in page and "Mur Privé" in page
        assert f"/wall/{prive['wall']}/unlock" in bob.get(f"/block/{prive['block']}").get_data(as_text=True)

    def test_nouvelle_page_bloc(self, alice, bob, anon, decor, prive):
        assert alice.get(f"/wall/{decor['wall']}/block/new").status_code == 200
        assert anon.get(f"/wall/{decor['wall']}/block/new").status_code == 302
        assert bob.get(f"/wall/{prive['wall']}/block/new").status_code in (403, 404)
        assert alice.get("/wall/999/block/new").status_code == 404


class TestAPI:
    def test_holds(self, anon, decor):
        j = anon.get(f"/api/block/{decor['block']}/holds").get_json()
        assert [h["hold_type"] for h in j] == ["start", "mid", "top"]

    def test_full(self, anon, alice, decor):
        j = anon.get(f"/api/block/{decor['block']}/full").get_json()
        assert j["block"]["name"] == "Bloc Public" and j["block"]["creator_name"] == "Alice"
        assert len(j["holds"]) == 3 and j["logged_in"] is False and j["my_note"] is None
        assert alice.get(f"/api/block/{decor['block']}/full").get_json()["logged_in"] is True

    def test_full_inexistant(self, anon):
        assert anon.get("/api/block/999/full").status_code == 404
        assert anon.get("/api/block/999/holds").status_code == 404

    def test_mur_prive_ferme(self, anon, bob, prive):
        for c in (anon, bob):
            assert c.get(f"/api/block/{prive['block']}/full").status_code == 404
            assert c.get(f"/api/block/{prive['block']}/holds").status_code == 404
        assert prive["block"]

    def test_mur_prive_ouvert_pour_le_proprietaire_et_apres_code(self, alice, bob, prive):
        assert alice.get(f"/api/block/{prive['block']}/full").status_code == 200
        post(bob, f"/wall/{prive['wall']}/unlock", {"code": prive["code"]})
        assert bob.get(f"/api/block/{prive['block']}/full").status_code == 200

    def test_full_expose_notes_et_ascensions(self, alice, bob, decor):
        post_json(bob, f"/api/block/{decor['block']}/note", {"note": "6b"})
        post_json(bob, f"/api/block/{decor['block']}/ascent", {"flash": True})
        j = alice.get(f"/api/block/{decor['block']}/full").get_json()
        assert j["notes"] == [{"note": "6b", "user_name": "Bob"}]
        assert j["ascents"][0]["user_name"] == "Bob" and j["ascents"][0]["flash"] == 1
        assert bob.get(f"/api/block/{decor['block']}/full").get_json()["my_note"] == "6b"


class TestModification:
    def edit(self, client, bid, **over):
        data = {"name": "Renommé", "grade": "7a", "color": "#22c55e", "description": "nouvelle desc", "link": ""}
        data.update(over)
        return post(client, f"/block/{bid}/edit", data)

    def test_modification(self, alice, decor, dbq):
        r = self.edit(alice, decor["block"], link="https://a.fr")
        assert r.status_code == 302 and r.headers["Location"] == f"/block/{decor['block']}"
        b = dbq("SELECT * FROM block")[0]
        assert (b["name"], b["grade"], b["color"], b["description"], b["link"]) == ("Renommé", "7a", "#22c55e", "nouvelle desc", "https://a.fr")

    def test_met_a_jour_le_carnet(self, alice, decor, dbq):
        post_json(alice, f"/api/block/{decor['block']}/ascent", {"done": True})
        self.edit(alice, decor["block"])
        row = dbq("SELECT block_name, grade FROM climb_log")[0]
        assert tuple(row) == ("Renommé", "7a")

    def test_la_page_de_modification(self, alice, decor):
        assert alice.get(f"/block/{decor['block']}/edit").status_code == 200

    @pytest.mark.parametrize("over,msg", [
        ({"name": ""}, "requis"), ({"name": "x" * 101}, "limité"), ({"grade": "x"}, "Cotation"),
        ({"color": "#000001"}, "Couleur"), ({"description": "d" * 501}, "limitée"), ({"link": "javascript:alert(1)"}, ""),
    ])
    def test_validations(self, alice, decor, over, msg):
        page = self.edit(alice, decor["block"], **over)
        assert page.status_code == 200 and msg in page.get_data(as_text=True)

    def test_doublon_de_nom(self, alice, decor):
        other = save(alice, decor["wall"], "Autre").get_json()["block_id"]
        assert "existe déjà" in self.edit(alice, other, name="bloc public").get_data(as_text=True)

    def test_autre_compte_refuse(self, bob, decor, dbq):
        assert self.edit(bob, decor["block"]).status_code == 403
        assert dbq("SELECT name FROM block")[0][0] == "Bloc Public"

    def test_mur_prive_inaccessible_donne_404(self, bob, prive):
        assert self.edit(bob, prive["block"]).status_code == 404

    def test_admin_autorise(self, admin, decor):
        assert self.edit(admin, decor["block"]).status_code == 302

    def test_inexistant(self, alice):
        assert alice.get("/block/999/edit").status_code == 404


class TestSuppression:
    def test_suppression_en_cascade(self, alice, bob, decor, dbq):
        b = decor["block"]
        post_json(bob, f"/api/block/{b}/ascent", {"done": True})
        post_json(bob, f"/api/block/{b}/note", {"note": "6a"})
        post(bob, f"/block/{b}/favorite"); post(bob, f"/block/{b}/todo")
        r = post(alice, f"/block/{b}/delete")
        assert r.status_code == 302 and r.headers["Location"] == f"/wall/{decor['wall']}"
        for t in ["block", "hold", "ascent", "block_note", "block_favorite", "block_todo"]:
            assert dbq(f"SELECT 1 FROM {t}") == [], t
        assert dbq("SELECT 1 FROM climb_log")     # le carnet survit

    def test_autre_compte_refuse(self, bob, decor, dbq):
        assert post(bob, f"/block/{decor['block']}/delete").status_code == 403 and dbq("SELECT 1 FROM block")

    def test_mur_prive_donne_404(self, bob, prive):
        assert post(bob, f"/block/{prive['block']}/delete").status_code == 404

    def test_inexistant(self, alice):
        assert post(alice, "/block/999/delete").status_code in (403, 404)

    def test_admin_journalise(self, admin, decor, dbq):
        assert post(admin, f"/block/{decor['block']}/delete").status_code == 302
        assert "Bloc supprimé par un admin" in dbq("SELECT action FROM admin_log")[0][0]

    def test_get_interdit(self, alice, decor):
        assert alice.get(f"/block/{decor['block']}/delete").status_code == 405
