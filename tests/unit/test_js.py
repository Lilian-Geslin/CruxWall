"""JavaScript : syntaxe de chaque fichier, et cotation communautaire (fonction pure de block-view.js) exécutée avec Node."""
import glob
import json
import os
import re
import shutil
import subprocess

import pytest

from src.constants import GRADES

RACINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
JS = sorted(glob.glob(os.path.join(RACINE, "src", "static", "js", "**", "*.js"), recursive=True))
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js absent")


@pytest.mark.parametrize("path", JS, ids=lambda p: os.path.relpath(p, RACINE))
def test_syntaxe(path):
    r = subprocess.run([NODE, "--check", path], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def community(notes, opener):
    """Évalue communityGrade (extraite du fichier source) pour un jeu de votes."""
    src = open(os.path.join(RACINE, "src", "static", "js", "pages", "block-view.js"), encoding="utf-8").read()
    fonction = re.search(r"function communityGrade\(.*?\n}\n", src, re.S).group(0)
    script = fonction + f"\nconsole.log(JSON.stringify(communityGrade({json.dumps(notes)}, {json.dumps(opener)}, {json.dumps(GRADES)})));"
    out = subprocess.run([NODE, "-e", script], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


@pytest.mark.parametrize("notes,opener,attendu", [
    ([], "", None),                                            # aucun vote
    ([], "6a", {"label": "6a", "votes": 1}),                   # l'ouvreur compte pour un vote
    (["6b", "6b"], "6a", {"label": "6b", "votes": 3}),         # mode des votes
    (["6a"], "6a+", {"label": "6a/+", "votes": 2}),            # égalité entre cotations voisines
    (["6b"], "6a+", {"label": "6a+/6b", "votes": 2}),
    (["7a"], "6a", {"label": "6a", "votes": 2}),               # égalité éloignée : la plus proche de l'ouvreur
    (["6a"], "7a", {"label": "7a", "votes": 2}),
    (["7a", "6a"], "", {"label": "6a", "votes": 2}),           # sans ouvreur : proche de la moyenne, la plus basse si égalité
    (["pas une cote", "6c"], "", {"label": "6c", "votes": 1}), # votes invalides ignorés
])
def test_cotation_communautaire(notes, opener, attendu):
    assert community(notes, opener) == attendu
