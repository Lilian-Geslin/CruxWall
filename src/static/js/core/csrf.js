// --------------------------------------------------
// SÉCURITÉ — jeton CSRF et confirmations
// --------------------------------------------------

// Jeton CSRF à joindre (en-tête X-CSRF-Token) à tout fetch() qui modifie des données
window.csrfToken = () =>
    document.querySelector('meta[name="csrf-token"]')?.content || "";

// Confirmation avant les actions destructrices : le texte vient de l'attribut
// data-confirm du formulaire, jamais injecté dans du JavaScript (sinon un nom
// de mur piégé pouvait exécuter du code chez les autres visiteurs).
document.addEventListener("submit", (e) => {
    const msg = e.target.dataset ? e.target.dataset.confirm : null;
    if (msg && !window.confirm(msg)) e.preventDefault();
});
