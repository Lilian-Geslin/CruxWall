"""Inscription, connexion, déconnexion : règles de saisie, anti-robots, verrouillage des tentatives, sessions."""
import re
import time

import pytest

from src import constants as C
from tests.helpers import PASSWORD, csrf, register


def login(app, email, password, ip=None, client=None, redirect=None):
    client = client or app.test_client()
    path = "/login" + (f"?redirect={redirect}" if redirect else "")
    token = csrf(client, path)
    headers = {"X-Real-IP": ip} if ip else {}
    return client, client.post("/login", data={"csrf_token": token, "email": email, "password": password}, headers=headers)


class TestInscription:
    def test_inscription_connecte_et_enregistre_les_cgu(self, app, dbq):
        client, r = register(app, "Nouveau_1", "n1@example.fr")
        assert r.status_code == 302
        assert client.get("/profil").status_code == 200
        user = dbq("SELECT * FROM user WHERE name = 'Nouveau_1'")[0]
        assert user["terms_accepted_at"] and user["role"] == "user"
        assert user["password"] != PASSWORD          # jamais en clair

    def test_cgu_obligatoires(self, app, dbq):
        _, r = register(app, "SansCgu", "sc@example.fr", terms=False)
        assert r.status_code == 200 and "conditions d'utilisation" in r.get_data(as_text=True)
        assert dbq("SELECT 1 FROM user") == []

    @pytest.mark.parametrize("name", ["ab", "a" * 31, "accentué", "with space", "bad!"])
    def test_pseudo_invalide(self, app, name):
        _, r = register(app, name, "p@example.fr")
        assert r.status_code == 200 and "Pseudo invalide" in r.get_data(as_text=True)

    @pytest.mark.parametrize("email", ["pas-un-email", "a@b", "@x.fr", "a b@c.fr"])
    def test_email_invalide(self, app, email):
        _, r = register(app, "Valide_1", email)
        assert "Adresse email invalide" in r.get_data(as_text=True)

    @pytest.mark.parametrize("password", ["1234567", "x" * 129])
    def test_longueur_du_mot_de_passe(self, app, password):
        _, r = register(app, "Valide_2", "v2@example.fr", password=password)
        assert "entre 8 et 128" in r.get_data(as_text=True)

    def test_mot_de_passe_limites_acceptees(self, app):
        assert register(app, "Court_8", "c8@example.fr", password="12345678")[1].status_code == 302
        assert register(app, "Long_128", "l128@example.fr", password="x" * 128)[1].status_code == 302

    def test_doublons_insensibles_a_la_casse(self, app, alice):
        _, r = register(app, "ALICE", "autre@example.fr")
        assert "pseudo est déjà pris" in r.get_data(as_text=True)
        _, r = register(app, "Autre_Nom", "ALICE@EXAMPLE.FR")
        assert "compte existe" in r.get_data(as_text=True)

    def test_email_normalise_en_minuscules(self, app, dbq):
        register(app, "Casse_1", "  Casse@Example.FR ")
        assert dbq("SELECT email FROM user WHERE name = 'Casse_1'")[0]["email"] == "casse@example.fr"

    def test_champ_piege_rempli_refuse(self, app, dbq):
        _, r = register(app, "Robot_1", "r1@example.fr", company_url="http://spam")
        assert "expiré ou a été envoyé trop vite" in r.get_data(as_text=True) and dbq("SELECT 1 FROM user") == []

    def test_jeton_falsifie_refuse(self, app):
        _, r = register(app, "Robot_2", "r2@example.fr", form_ts="falsifie")
        assert "expiré ou a été envoyé trop vite" in r.get_data(as_text=True)

    def test_envoi_trop_rapide_refuse_puis_accepte_apres_le_delai(self, app, monkeypatch):
        monkeypatch.setattr("src.services.antibot.REGISTER_MIN_SECONDS", 1)
        _, r = register(app, "Rapide_1", "rap@example.fr")
        assert "trop vite" in r.get_data(as_text=True)
        client = app.test_client()
        html = client.get("/register").get_data(as_text=True)
        time.sleep(1.2)
        data = {"csrf_token": re.search(r'name="csrf_token" value="([^"]+)"', html).group(1),
                "form_ts": re.search(r'name="form_ts" value="([^"]+)"', html).group(1),
                "name": "Humain_1", "email": "h1@example.fr", "password": PASSWORD, "accept_terms": "1"}
        assert client.post("/register", data=data).status_code == 302

    def test_formulaire_contient_le_piege_cache(self, anon):
        html = anon.get("/register").get_data(as_text=True)
        assert 'name="company_url"' in html and 'name="form_ts"' in html

    def test_limite_d_inscriptions_par_adresse(self, app, monkeypatch):
        monkeypatch.setattr("src.routes.auth.REGISTER_IP_MAX", 2)
        for i in range(2):
            assert register(app, f"Lot_{i}", f"lot{i}@example.fr")[1].status_code == 302
        assert register(app, "Lot_9", "lot9@example.fr")[1].status_code == 429


class TestConnexion:
    def test_connexion_reussie_et_deconnexion(self, app, alice):
        client, r = login(app, "alice@example.fr", PASSWORD)
        assert r.status_code == 302 and client.get("/profil").status_code == 200
        r = client.post("/logout", data={"csrf_token": csrf(client, "/profil")})
        assert r.status_code == 302 and client.get("/profil").status_code == 302

    def test_email_insensible_a_la_casse(self, app, alice):
        assert login(app, "ALICE@Example.fr", PASSWORD)[1].status_code == 302

    def test_message_identique_si_email_inconnu_ou_mot_de_passe_faux(self, app, alice):
        a = login(app, "alice@example.fr", "mauvais-mdp")[1].get_data(as_text=True)
        b = login(app, "inconnu@example.fr", "mauvais-mdp")[1].get_data(as_text=True)
        assert "Email ou mot de passe incorrect" in a and "Email ou mot de passe incorrect" in b

    def test_mot_de_passe_trop_long_refuse_sans_calcul(self, app, alice):
        assert "incorrect" in login(app, "alice@example.fr", "x" * 500)[1].get_data(as_text=True)

    def test_page_protegee_redirige_vers_login_avec_retour(self, app, alice):
        anon = app.test_client()
        r = anon.get("/wall/new")
        assert r.status_code == 302 and r.headers["Location"] == "/login?redirect=/wall/new"
        client, r = login(app, "alice@example.fr", PASSWORD, redirect="/gyms")
        assert r.headers["Location"] == "/gyms"

    @pytest.mark.parametrize("cible", ["https://evil.example/", "//evil.example", "/\\evil.example", "javascript:alert(1)"])
    def test_redirection_externe_ignoree(self, app, alice, cible):
        _, r = login(app, "alice@example.fr", PASSWORD, redirect=cible)
        assert r.headers["Location"] == "/"

    def test_deconnexion_exige_post_et_csrf(self, alice):
        assert alice.get("/logout").status_code == 405
        assert alice.post("/logout", data={}).status_code == 400
        assert alice.get("/profil").status_code == 200


class TestVerrouillage:
    @pytest.fixture(autouse=True)
    def proxy(self, monkeypatch):
        monkeypatch.setenv("TRUST_PROXY", "1")

    def test_cinq_echecs_bloquent_le_couple_email_ip(self, app, alice):
        for _ in range(C.LOGIN_PAIR_MAX):
            assert login(app, "alice@example.fr", "faux", ip="1.1.1.1")[1].status_code == 200
        assert login(app, "alice@example.fr", "faux", ip="1.1.1.1")[1].status_code == 429
        assert login(app, "alice@example.fr", PASSWORD, ip="1.1.1.1")[1].status_code == 429   # même avec le bon mot de passe

    def test_le_vrai_proprietaire_n_est_pas_bloque_par_un_tiers(self, app, alice):
        for _ in range(C.LOGIN_PAIR_MAX):
            login(app, "alice@example.fr", "faux", ip="1.1.1.1")
        client, r = login(app, "alice@example.fr", PASSWORD, ip="2.2.2.2")
        assert r.status_code == 302 and client.get("/profil").status_code == 200

    def test_l_attaquant_peut_essayer_un_autre_compte(self, app, alice, bob):
        for _ in range(C.LOGIN_PAIR_MAX):
            login(app, "alice@example.fr", "faux", ip="1.1.1.1")
        assert login(app, "bob@example.fr", "faux", ip="1.1.1.1")[1].status_code == 200

    def test_garde_fou_par_adresse_ip(self, app, alice, dbq_write):
        for _ in range(C.LOGIN_IP_MAX):
            dbq_write("INSERT INTO auth_attempt(bucket, ts) VALUES('login:ip:9.9.9.9', ?)", int(time.time()))
        assert login(app, "alice@example.fr", PASSWORD, ip="9.9.9.9")[1].status_code == 429

    def test_garde_fou_par_email(self, app, alice, dbq_write):
        for _ in range(C.LOGIN_EMAIL_MAX):
            dbq_write("INSERT INTO auth_attempt(bucket, ts) VALUES('login:email:alice@example.fr', ?)", int(time.time()))
        assert login(app, "alice@example.fr", PASSWORD, ip="3.3.3.3")[1].status_code == 429

    def test_un_succes_remet_le_compteur_du_couple_a_zero(self, app, alice):
        for _ in range(C.LOGIN_PAIR_MAX - 1):
            login(app, "alice@example.fr", "faux", ip="4.4.4.4")
        assert login(app, "alice@example.fr", PASSWORD, ip="4.4.4.4")[1].status_code == 302
        assert login(app, "alice@example.fr", "faux", ip="4.4.4.4")[1].status_code == 200

    def test_sans_trust_proxy_l_adresse_du_proxy_est_utilisee(self, app, alice, monkeypatch):
        monkeypatch.delenv("TRUST_PROXY")
        for _ in range(C.LOGIN_PAIR_MAX):
            login(app, "alice@example.fr", "faux", ip="1.1.1.1")
        # l'en-tête X-Real-IP est ignoré : une « autre » adresse est en réalité la même
        assert login(app, "alice@example.fr", "faux", ip="2.2.2.2")[1].status_code == 429
