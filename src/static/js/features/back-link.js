// --------------------------------------------------
// FLÈCHE RETOUR : revient à la page d'avant (celle d'où l'on vient),
// sinon suit le lien de secours (ex. la salle du mur, ou l'accueil).
// --------------------------------------------------
(function () {
    document.addEventListener("click", (e) => {
        const link = e.target.closest && e.target.closest("a[data-back]");
        if (!link || e.ctrlKey || e.metaKey || e.shiftKey || e.button !== 0) return;
        try {
            if (!document.referrer || window.history.length < 2) return;
            const ref = new URL(document.referrer);
            if (ref.origin !== window.location.origin) return;
            // Pages vers lesquelles un retour n'aurait pas de sens
            if (/^\/(login|register|logout|block|api)/.test(ref.pathname) || /\/unlock$/.test(ref.pathname)) return;
            if (ref.pathname === window.location.pathname && ref.search === window.location.search) return;
            e.preventDefault();
            window.history.back();
        } catch (err) { /* lien normal en secours */ }
    });
})();
