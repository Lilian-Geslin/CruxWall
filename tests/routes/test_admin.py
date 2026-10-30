"""Administration : accès, signalements, rôles, suppression de comptes, journal."""
import pytest

from tests.helpers import create_block, create_wall, post, post_json


def signaler(client, kind, target, reason="inappropriate"):
    return post(client, "/report", {"target_type": kind, "target_id": str(target), "reason": reason})


class TestAcces:
    @pytest.mark.parametrize("path", ["/admin"])
    def test_page_reservee(self, anon, bob, admin, path):
        assert anon.get(path).status_code == 302
        assert bob.get(path).status_code == 403
        assert admin.get(path).status_code == 200

    @pytest.mark.parametrize("path", ["/admin/report/1/dismiss", "/admin/report/1/remove", "/admin/user/1/role", "/admin/user/1/delete"])
    def test_actions_reservees(self, anon, bob, path):
        assert anon.post(path, data={}).status_code in (400, 302)
        assert post(bob, path, {"role": "admin"}).status_code == 403

    def test_un_retrait_de_droits_prend_effet_immediatement(self, admin, dbq_write):
        assert admin.get("/admin").status_code == 200
        dbq_write("UPDATE user SET role='user' WHERE name='Admin'")
        assert admin.get("/admin").status_code == 403

    def test_page_admin_contenu(self, admin, bob, decor):
        signaler(bob, "wall", decor["wall"])
        page = admin.get("/admin").get_data(as_text=True)
        assert "Mur Public" in page and "Bob" in page

    def test_recherche_de_comptes(self, admin, bob):
        assert "bob@example.fr" in admin.get("/admin?q=bob").get_data(as_text=True)
        assert "bob@example.fr" not in admin.get("/admin?q=zzzz").get_data(as_text=True)

    def test_recherche_avec_jokers_echappes(self, admin, bob):
        assert "bob@example.fr" not in admin.get("/admin?q=%25").get_data(as_text=True)


class TestSignalements:
    @pytest.fixture
    def ouvert(self, bob, decor):
        signaler(bob, "wall", decor["wall"])

    def test_ignorer(self, admin, ouvert, dbq):
        r = post(admin, "/admin/report/1/dismiss")
        assert r.status_code == 302 and r.headers["Location"].endswith("/admin")
        row = dbq("SELECT status, handled_by FROM report")[0]
        assert row["status"] == "dismissed" and row["handled_by"]
        assert dbq("SELECT action FROM admin_log")[0][0] == "Signalement ignoré"
        assert dbq("SELECT 1 FROM wall")

    def test_ignorer_deux_fois_sans_effet(self, admin, ouvert, dbq):
        post(admin, "/admin/report/1/dismiss"); post(admin, "/admin/report/1/dismiss")
        assert len(dbq("SELECT 1 FROM admin_log")) == 1

    def test_retirer_un_mur(self, admin, alice, bob, ouvert, decor, dbq):
        signaler(alice, "wall", decor["wall"], "person")
        post(admin, "/admin/report/1/remove")
        assert dbq("SELECT 1 FROM wall") == [] and dbq("SELECT 1 FROM block") == []
        assert {r["status"] for r in dbq("SELECT status FROM report")} == {"removed"}      # tous les signalements clos
        n = dbq("SELECT * FROM notification WHERE user_id = (SELECT id FROM user WHERE name='Alice')")
        assert "supprimé suite à un signalement" in n[0]["message"]
        assert dbq("SELECT action FROM admin_log")[0][0] == "Contenu supprimé suite à un signalement"

    def test_retirer_un_bloc(self, admin, bob, decor, dbq):
        signaler(bob, "block", decor["block"])
        post(admin, "/admin/report/1/remove")
        assert dbq("SELECT 1 FROM block") == [] and dbq("SELECT 1 FROM wall")
        assert "Votre bloc" in dbq("SELECT message FROM notification WHERE user_id = (SELECT id FROM user WHERE name='Alice')")[0][0]

    def test_contenu_deja_supprime_est_classe(self, admin, alice, ouvert, decor, dbq):
        post(alice, f"/wall/{decor['wall']}/delete")
        assert dbq("SELECT status FROM report")[0][0] == "gone"

    def test_signalement_inexistant(self, admin):
        assert post(admin, "/admin/report/99/remove").status_code == 302
        assert post(admin, "/admin/report/99/dismiss").status_code == 302

    def test_la_page_distingue_attente_et_traites(self, admin, ouvert):
        post(admin, "/admin/report/1/dismiss")
        assert "Ignoré" in admin.get("/admin").get_data(as_text=True)


class TestRoles:
    def test_promotion_et_retrait(self, admin, bob, dbq):
        assert post(admin, "/admin/user/3/role", {"role": "admin"}).status_code == 302
        assert dbq("SELECT role FROM user WHERE name='Bob'")[0][0] == "admin"
        assert bob.get("/admin").status_code == 200
        post(admin, "/admin/user/3/role", {"role": "user"})
        assert bob.get("/admin").status_code == 403
        assert [r["action"] for r in dbq("SELECT action FROM admin_log ORDER BY id")] == \
            ["Droits administrateur accordés", "Droits administrateur retirés"]

    def test_role_invalide_ou_sur_soi_meme(self, admin, bob, dbq):
        assert post(admin, "/admin/user/3/role", {"role": "root"}).status_code == 400
        moi = [r for r in dbq("SELECT id FROM user WHERE name='Admin'")][0][0]
        assert post(admin, f"/admin/user/{moi}/role", {"role": "user"}).status_code == 400
        assert admin.get("/admin").status_code == 200

    def test_utilisateur_inexistant(self, admin):
        assert post(admin, "/admin/user/99/role", {"role": "admin"}).status_code == 404


class TestSuppressionDeCompte:
    def test_supprime_le_compte_et_ses_contenus_publics(self, admin, alice, bob, decor, dbq):
        alice_id = dbq("SELECT id FROM user WHERE name='Alice'")[0][0]
        post_json(bob, f"/api/block/{decor['block']}/ascent", {"done": True})
        r = post(admin, f"/admin/user/{alice_id}/delete")
        assert r.status_code == 302
        assert dbq("SELECT 1 FROM user WHERE name='Alice'") == []
        for t in ["wall", "block", "gym"]:
            assert dbq(f"SELECT 1 FROM {t}") == [], t
        assert "Compte supprimé par un admin" in dbq("SELECT action FROM admin_log")[0][0]

    def test_on_ne_se_supprime_pas_soi_meme(self, admin, dbq):
        me = dbq("SELECT id FROM user WHERE name='Admin'")[0][0]
        assert post(admin, f"/admin/user/{me}/delete").status_code == 400
        assert dbq("SELECT 1 FROM user WHERE name='Admin'")

    def test_compte_inexistant(self, admin):
        assert post(admin, "/admin/user/99/delete").status_code == 302

    def test_le_compte_supprime_ne_peut_plus_agir(self, admin, bob, dbq):
        bob_id = dbq("SELECT id FROM user WHERE name='Bob'")[0][0]
        post(admin, f"/admin/user/{bob_id}/delete")
        assert bob.get("/profil").status_code == 302


class TestJournal:
    def test_actions_d_admin_sur_le_contenu_d_autrui_journalisees(self, admin, decor, dbq):
        post(admin, f"/wall/{decor['wall']}/delete")
        row = dbq("SELECT * FROM admin_log")[0]
        assert "Mur supprimé par un admin" in row["action"]
        assert "Mur Public" in " ".join(str(v) for v in tuple(row))

    def test_pas_de_journal_pour_ses_propres_contenus(self, admin, find, dbq):
        from tests.helpers import create_gym
        create_gym(admin, "Gym Admin")
        create_wall(admin, "Mon Mur", find("gym", "Gym Admin")["id"])
        post(admin, f"/wall/{find('wall', 'Mon Mur')['id']}/delete")
        assert dbq("SELECT 1 FROM admin_log") == []

    def test_visible_dans_la_page(self, admin, decor):
        post(admin, f"/wall/{decor['wall']}/delete")
        assert "Mur supprimé par un admin" in admin.get("/admin").get_data(as_text=True)
