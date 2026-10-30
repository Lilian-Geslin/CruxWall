// --------------------------------------------------
// RECHERCHE DANS UNE SALLE : propositions pendant la frappe
// --------------------------------------------------
(function () {
    const input = document.getElementById("gymSearch");
    const list = document.getElementById("gymSuggest");
    if (!input || !list) return;
    let timer = null, seq = 0, active = -1;

    const close = () => { list.hidden = true; list.innerHTML = ""; active = -1; };
    const items = () => Array.from(list.querySelectorAll("a"));
    const highlight = (i) => {
        const els = items();
        els.forEach((el, k) => el.classList.toggle("active", k === i));
        active = i;
    };
    const section = (title) => {
        const li = document.createElement("li");
        li.className = "suggest-title";
        li.textContent = title;
        list.appendChild(li);
    };
    const entry = (href, main, sub, badge) => {
        const li = document.createElement("li");
        const a = document.createElement("a");
        a.href = href;
        const m = document.createElement("span");
        m.className = "suggest-main";
        m.textContent = main;
        a.appendChild(m);
        if (badge) {
            const g = document.createElement("span");
            g.className = "grade-badge";
            g.textContent = badge;
            a.appendChild(g);
        }
        if (sub) {
            const s = document.createElement("span");
            s.className = "suggest-sub";
            s.textContent = sub;
            a.appendChild(s);
        }
        li.appendChild(a);
        list.appendChild(li);
    };

    input.addEventListener("input", () => {
        clearTimeout(timer);
        const q = input.value.trim();
        if (q.length < 2) { close(); return; }
        timer = setTimeout(async () => {
            const mine = ++seq;
            try {
                const res = await fetch(`${input.dataset.suggestUrl}?q=${encodeURIComponent(q)}`);
                if (!res.ok || mine !== seq) return;
                const data = await res.json();
                if (mine !== seq) return;
                list.innerHTML = "";
                if (!data.walls.length && !data.blocks.length) {
                    const li = document.createElement("li");
                    li.className = "suggest-title";
                    li.textContent = "Aucun résultat";
                    list.appendChild(li);
                } else {
                    if (data.walls.length) {
                        section("Murs");
                        data.walls.forEach(w => entry(`/wall/${w.id}`, w.name, "", ""));
                    }
                    if (data.blocks.length) {
                        section("Blocs");
                        data.blocks.forEach(b => entry(`/block/${b.id}`, b.name,
                            b.wall + (b.creator ? " · " + b.creator : ""), b.grade));
                    }
                }
                active = -1;
                list.hidden = false;
            } catch (err) { /* pas de proposition : Entrée lance la recherche complète */ }
        }, 200);
    });

    input.addEventListener("keydown", (e) => {
        const els = items();
        if (e.key === "Escape") { close(); return; }
        if (!els.length || list.hidden) return;
        if (e.key === "ArrowDown") { e.preventDefault(); highlight((active + 1) % els.length); }
        else if (e.key === "ArrowUp") { e.preventDefault(); highlight((active - 1 + els.length) % els.length); }
        else if (e.key === "Enter" && active >= 0) { e.preventDefault(); els[active].click(); }
    });
    document.addEventListener("click", (e) => { if (!list.contains(e.target) && e.target !== input) close(); });
})();
