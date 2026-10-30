"""Pages légales : mentions légales, confidentialité, conditions d'utilisation."""

from flask import Blueprint
from flask import render_template


bp = Blueprint("legal", __name__)

@bp.route("/mentions-legales")
def legalnotice_page():
    return render_template("pages/legal.html")

@bp.route("/confidentialite")
def privacy():
    return render_template("pages/privacy.html")

@bp.route("/cgu")
def terms():
    return render_template("pages/terms.html")
