"""Sécurité transversale : CSRF, HTTPS forcé, en-têtes (CSP, HSTS), relecture du compte à chaque requête, redirections sûres."""
import re

from tests.helpers import PASSWORD, csrf, post, post_json


class TestCsrf:
    def test_post_sans_jeton_refuse_page_html(self, alice):
        r = alice.post("/gym/new", data={"name": "X"})
        assert r.status_code == 400 and "Session expirée" in r.get_data(as_text=True)

    def test_post_sans_jeton_refuse_api_json(self, alice):
        r = alice.post("/api/gym/quick_create", data={"name": "X"})
        assert r.status_code == 400 and r.is_json and "Session expirée" in r.get_json()["error"]

    def test_jeton_faux_refuse(self, alice):
        assert alice.post("/gym/new", data={"name": "X", "csrf_token": "faux"}).status_code == 400

    def test_jeton_en_en_tete_accepte(self, alice):
        r = alice.post("/api/gym/quick_create", data={"name": "ViaEntete"}, headers={"X-CSRF-Token": csrf(alice)})
        assert r.status_code == 200

    def test_jeton_d_une_autre_session_refuse(self, alice, bob):
        assert alice.post("/gym/new", data={"name": "X", "csrf_token": csrf(bob)}).status_code == 400

    def test_les_get_n_exigent_pas_de_jeton(self, anon):
        assert anon.get("/gyms").status_code == 200

    def test_meta_csrf_dans_chaque_page(self, anon):
        assert re.search(r'<meta name="csrf-token" content="[^"]{20,}">', anon.get("/login").get_data(as_text=True))


class TestEnTetes:
    def test_en_tetes_de_base(self, anon):
        h = anon.get("/login").headers
        assert h["X-Content-Type-Options"] == "nosniff" and h["X-Frame-Options"] == "DENY"
        assert h["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert "geolocation=()" in h["Permissions-Policy"]

    def test_csp_et_nonce_different_a_chaque_requete(self, anon):
        csp1 = anon.get("/login").headers["Content-Security-Policy"]
        csp2 = anon.get("/login").headers["Content-Security-Policy"]
        assert "frame-ancestors 'none'" in csp1 and "object-src 'none'" in csp1 and "script-src 'self' 'nonce-" in csp1
        assert "unsafe-eval" not in csp1 and "googleapis" not in csp1
        assert re.search(r"nonce-([^']+)", csp1).group(1) != re.search(r"nonce-([^']+)", csp2).group(1)

    def test_le_nonce_de_la_page_correspond_a_celui_de_l_en_tete(self, alice, app):
        from tests.helpers import create_gym, create_wall
        create_gym(alice, "G")
        create_wall(alice, "M", 1)
        r = alice.get("/wall/1/block/new")
        nonce = re.search(r"nonce-([^']+)", r.headers["Content-Security-Policy"]).group(1)
        assert f'nonce="{nonce}"' in r.get_data(as_text=True)

    def test_pas_de_hsts_en_developpement(self, anon):
        assert "Strict-Transport-Security" not in anon.get("/login").headers

    def test_hsts_en_production(self, anon, monkeypatch):
        monkeypatch.setattr("src.security.IS_DEV", False)
        assert "max-age=15552000" in anon.get("/login").headers["Strict-Transport-Security"]

    def test_pas_de_csp_sur_les_fichiers_statiques_ni_le_json(self, anon):
        assert "Content-Security-Policy" not in anon.get("/static/css/base.css").headers
        assert "Content-Security-Policy" not in anon.get("/api/block/1/notes").headers

    def test_polices_hebergees_localement(self, anon):
        for path in ["/", "/login", "/register", "/gyms", "/walls", "/cgu"]:
            body = anon.get(path).get_data(as_text=True)
            assert "googleapis" not in body and "gstatic" not in body
        css = anon.get("/static/css/base.css").get_data(as_text=True)
        assert "../fonts/dm-sans-latin-400-normal.woff2" in css
        assert anon.get("/static/fonts/dm-sans-latin-400-normal.woff2").status_code == 200

    def test_version_des_fichiers_statiques_dans_les_urls(self, anon):
        assert re.search(r"css/base\.css\?v=\d+", anon.get("/login").get_data(as_text=True))


class TestHttpsForce:
    def test_redirige_http_vers_https(self, anon, monkeypatch):
        monkeypatch.setattr("src.security.FORCE_HTTPS", True)
        r = anon.get("/gyms?x=1", headers={"X-Forwarded-Proto": "http"})
        assert r.status_code == 301 and r.headers["Location"] == "https://localhost/gyms?x=1"

    def test_pas_de_redirection_si_https_ou_en_tete_absent(self, anon, monkeypatch):
        monkeypatch.setattr("src.security.FORCE_HTTPS", True)
        assert anon.get("/gyms", headers={"X-Forwarded-Proto": "https"}).status_code == 200
        assert anon.get("/gyms").status_code == 200

    def test_desactivable(self, anon):
        assert anon.get("/gyms", headers={"X-Forwarded-Proto": "http"}).status_code == 200


class TestSessionRelue:
    def test_compte_supprime_deconnecte(self, alice, dbq_write):
        assert alice.get("/profil").status_code == 200
        dbq_write("DELETE FROM user WHERE name = 'Alice'")
        assert alice.get("/profil").status_code == 302

    def test_changement_de_role_applique_immediatement(self, admin, dbq_write):
        assert admin.get("/admin").status_code == 200
        dbq_write("UPDATE user SET role = 'user' WHERE name = 'Admin'")
        assert admin.get("/admin").status_code in (403, 404)

    def test_changement_de_pseudo_visible_sans_reconnexion(self, alice, dbq_write):
        dbq_write("UPDATE user SET name = 'Renommee' WHERE name = 'Alice'")
        assert "Renommee" in alice.get("/gyms").get_data(as_text=True)

    def test_changement_de_mot_de_passe_deconnecte_les_autres_appareils(self, app, alice):
        from tests.routes.test_auth import login
        autre, _ = login(app, "alice@example.fr", PASSWORD)
        assert autre.get("/profil").status_code == 200
        r = post(alice, "/profil/settings", {"action": "password", "current_password": PASSWORD, "new_password": "nouveaumdp1", "confirm_password": "nouveaumdp1"})
        assert r.status_code in (200, 302)
        assert autre.get("/profil").status_code == 302          # l'autre appareil est déconnecté
        assert alice.get("/profil").status_code == 200          # celui qui a changé le mot de passe reste connecté


class TestRedirectionsSures:
    def test_safe_next_url(self):
        from src.services.validation import safe_next_url
        assert safe_next_url("/wall/3") == "/wall/3"
        for bad in ["http://x.fr", "//x.fr", "/\\x.fr", "javascript:1", "", None, 3, "/a\nb"]:
            assert safe_next_url(bad) == "/"
