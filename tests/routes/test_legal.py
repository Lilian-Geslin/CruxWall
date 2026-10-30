"""Pages légales : mentions légales, confidentialité, CGU, pied de page, polices hébergées."""
import os
import re

import pytest

PAGES = ["/", "/login", "/register", "/gyms", "/walls", "/cgu", "/confidentialite", "/mentions-legales"]


@pytest.mark.parametrize("path", PAGES)
def test_pied_de_page_et_aucune_ressource_google(anon, path):
    body = anon.get(path).get_data(as_text=True)
    assert 'class="site-footer"' in body
    for lien in ("/mentions-legales", "/confidentialite", "/cgu"):
        assert f'href="{lien}"' in body
    assert "googleapis" not in body and "gstatic" not in body


def test_la_page_404_a_aussi_le_pied_de_page(anon):
    assert 'class="site-footer"' in anon.get("/nimporte-quoi").get_data(as_text=True)


def test_mentions_affichent_editeur_et_contact(anon):
    page = anon.get("/mentions-legales").get_data(as_text=True)
    assert "Jean Test" in page and "contact@exemple.fr" in page


def test_mentions_rappellent_le_contact_manquant(anon, monkeypatch):
    monkeypatch.delenv("LEGAL_CONTACT_EMAIL")
    assert "LEGAL_CONTACT_EMAIL" in anon.get("/mentions-legales").get_data(as_text=True)


def test_confidentialite_et_cgu_se_chargent(anon):
    assert "confidentialité" in anon.get("/confidentialite").get_data(as_text=True).lower()
    assert anon.get("/cgu").status_code == 200


def test_csp_sans_google_et_polices_locales(anon):
    csp = anon.get("/login").headers["Content-Security-Policy"]
    assert "google" not in csp and "font-src 'self'" in csp


def test_polices_hebergees_servies(anon, app):
    css = open(os.path.join(app.static_folder, "css", "base.css"), encoding="utf-8").read()
    fonts = re.findall(r"url\('\.\./fonts/([^']+)'\)", css)
    assert len(fonts) == 6
    for f in fonts:
        assert os.path.exists(os.path.join(app.static_folder, "fonts", f))
        assert anon.get("/static/fonts/" + f).status_code == 200
    assert os.path.exists(os.path.join(app.static_folder, "fonts", "LICENSE-DM-Sans.txt"))


def test_inscription_cite_cgu_et_pseudo_unique(anon):
    html = anon.get("/register").get_data(as_text=True)
    assert 'name="accept_terms"' in html and 'href="/cgu"' in html and 'href="/confidentialite"' in html
    assert "Ce pseudo est unique" in html and "vrai nom" not in html.lower()
