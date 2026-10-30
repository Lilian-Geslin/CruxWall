"""Contrôle de base : l'application démarre et les pages publiques répondent."""
import pytest

PUBLIC_PAGES = ["/", "/walls", "/gyms", "/login", "/register", "/cgu", "/confidentialite", "/mentions-legales", "/health"]


@pytest.mark.parametrize("path", PUBLIC_PAGES)
def test_pages_publiques(anon, path):
    assert anon.get(path).status_code == 200


def test_inscription_puis_profil(alice):
    assert alice.get("/profil").status_code == 200


def test_page_inexistante(anon):
    assert anon.get("/nope").status_code == 404
