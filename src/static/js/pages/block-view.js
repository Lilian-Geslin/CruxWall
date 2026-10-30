// --------------------------------------------------
// VUE D'UN BLOC — Prises + ascensions + cotations
// --------------------------------------------------

const HOLD_COLORS = { start: "#22c55e", mid: "#3b82f6", top: "#ef4444", foot: "#eab308" };
// Taille du point affiché en consultation : proportionnelle à la taille
// choisie à la création (via la poignée de redimensionnement), mais réduite
// et plafonnée pour ne pas cacher les prises voisines.
const HOLD_DOT_DEFAULT_SIZE = 0.035; // pour les anciennes prises sans taille enregistrée
const HOLD_DOT_SCALE = 0.55;
const HOLD_DOT_MIN = 4;
const HOLD_DOT_MAX = 13;

let canvas, ctx, img, wrap, viewport;

// Zoom de l'image (boutons + / − / ⟲, pincement à deux doigts, glisser pour se déplacer)
let zoomLevel = 1;
const ZOOM_MIN = 1;
const ZOOM_MAX = 6;
const ZOOM_STEP = 0.5;

document.addEventListener("DOMContentLoaded", async () => {
    canvas = document.getElementById("blockCanvas");
    ctx = canvas.getContext("2d");
    img = document.getElementById("blockImage");
    wrap = document.getElementById("blockImageWrap");
    viewport = document.getElementById("blockViewport");

    if (img.complete) resizeCanvas();
    img.addEventListener("load", resizeCanvas);
    let lastWinWidth = window.innerWidth;
    window.addEventListener("resize", () => {
        if (window.innerWidth === lastWinWidth) return;
        lastWinWidth = window.innerWidth;
        applyZoom();
    });
    setupZoom();

    // Charger ascensions et cotations
    await loadAscentsAndNotes();

    // Boutons ascension
    document.getElementById("btnDone")?.addEventListener("click", () => toggleAscent("done"));
    document.getElementById("btnFlash")?.addEventListener("click", () => toggleAscent("flash"));

    // Bouton cotation
    document.getElementById("btnSubmitNote")?.addEventListener("click", submitNote);

    // Recherche par nom dans les cotations
    document.getElementById("noteSearch")?.addEventListener("input", (e) => {
        renderFilteredNotes(e.target.value);
    });
});

// --------------------------------------------------
// CANVAS
// --------------------------------------------------

function resizeCanvas() {
    canvas.width = wrap.clientWidth;
    canvas.height = wrap.clientHeight;
    drawAll();
}

// --------------------------------------------------
// ZOOM
// --------------------------------------------------

function applyZoom() {
    // Tailles en pixels mesurées sur le cadre (viewport) : à 100 % l'image
    // remplit le cadre, au-delà elle déborde et le cadre devient défilable.
    if (zoomLevel <= ZOOM_MIN + 0.001) {
        wrap.style.width = "100%";
        wrap.style.height = "100%";
    } else {
        wrap.style.width = (viewport.offsetWidth * zoomLevel) + "px";
        wrap.style.height = (viewport.offsetHeight * zoomLevel) + "px";
    }
    const label = document.getElementById("blockZoomLabel");
    if (label) label.textContent = Math.round(zoomLevel * 100) + "%";
    resizeCanvas();
}

function centerViewport() {
    viewport.scrollLeft = (wrap.clientWidth - viewport.clientWidth) / 2;
    viewport.scrollTop = (wrap.clientHeight - viewport.clientHeight) / 2;
}

function zoomBy(delta) {
    zoomLevel = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, zoomLevel + delta));
    applyZoom();
    centerViewport();
}

function setupZoom() {
    document.getElementById("blockZoomIn")?.addEventListener("click", () => zoomBy(ZOOM_STEP));
    document.getElementById("blockZoomOut")?.addEventListener("click", () => zoomBy(-ZOOM_STEP));
    document.getElementById("blockZoomReset")?.addEventListener("click", () => { zoomLevel = ZOOM_MIN; applyZoom(); centerViewport(); });

    // Pincement à deux doigts (zoom vers l'endroit pincé) et glisser à la souris.
    // Le défilement à un doigt est géré par le navigateur (cadre en overflow:auto).
    const pointers = new Map();
    let pinchStartDist = 0, pinchStartZoom = 1;
    let mouseDrag = null;

    viewport.addEventListener("pointerdown", (e) => {
        pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
        if (pointers.size === 2) {
            const [a, b] = Array.from(pointers.values());
            pinchStartDist = Math.hypot(a.x - b.x, a.y - b.y);
            pinchStartZoom = zoomLevel;
        } else if (e.pointerType === "mouse" && e.button === 0 && zoomLevel > ZOOM_MIN + 0.001) {
            mouseDrag = { x: e.clientX, y: e.clientY, left: viewport.scrollLeft, top: viewport.scrollTop };
            viewport.setPointerCapture(e.pointerId);
            wrap.style.cursor = "grabbing";
        }
    });

    viewport.addEventListener("pointermove", (e) => {
        if (pointers.has(e.pointerId)) pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
        if (pointers.size === 2 && pinchStartDist > 10) {
            const [a, b] = Array.from(pointers.values());
            const newDist = Math.hypot(a.x - b.x, a.y - b.y);
            const newZoom = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, pinchStartZoom * (newDist / pinchStartDist)));
            const vpRect = viewport.getBoundingClientRect();
            const midX = (a.x + b.x) / 2, midY = (a.y + b.y) / 2;
            const beforeW = wrap.clientWidth, beforeH = wrap.clientHeight;
            const fracX = beforeW > 0 ? (viewport.scrollLeft + (midX - vpRect.left)) / beforeW : 0.5;
            const fracY = beforeH > 0 ? (viewport.scrollTop + (midY - vpRect.top)) / beforeH : 0.5;
            zoomLevel = newZoom;
            applyZoom();
            viewport.scrollLeft = fracX * wrap.clientWidth - (midX - vpRect.left);
            viewport.scrollTop = fracY * wrap.clientHeight - (midY - vpRect.top);
            return;
        }
        if (mouseDrag) {
            viewport.scrollLeft = mouseDrag.left - (e.clientX - mouseDrag.x);
            viewport.scrollTop = mouseDrag.top - (e.clientY - mouseDrag.y);
        }
    });

    const endPointer = (e) => {
        pointers.delete(e.pointerId);
        if (pointers.size < 2) pinchStartDist = 0;
        if (mouseDrag) { mouseDrag = null; wrap.style.cursor = ""; }
    };
    viewport.addEventListener("pointerup", endPointer);
    viewport.addEventListener("pointercancel", endPointer);

    // Dès que deux doigts sont posés, on interdit au navigateur de transformer
    // le geste en défilement ou en zoom de page (sinon il interrompt le pincement).
    const blockIfMultiTouch = (e) => { if (e.touches.length >= 2 && e.cancelable) e.preventDefault(); };
    viewport.addEventListener("touchstart", blockIfMultiTouch, { passive: false });
    viewport.addEventListener("touchmove", blockIfMultiTouch, { passive: false });
    ["gesturestart", "gesturechange", "gestureend"].forEach(ev =>
        viewport.addEventListener(ev, (e) => e.preventDefault())
    );
}

/**
 * Zone réellement occupée par la photo à l'intérieur de son cadre
 * (object-fit: contain laisse des bandes vides si le ratio de la photo ne
 * correspond pas à celui du cadre — sans ce calcul, les prises atterrissaient
 * dans ces bandes au lieu d'être sur la vraie position de la photo).
 */
function getImageContentRect() {
    const rect = img.getBoundingClientRect();
    const wrapRect = wrap.getBoundingClientRect();
    const naturalRatio = img.naturalWidth / img.naturalHeight;
    const boxRatio = rect.width / rect.height;

    let contentWidth, contentHeight, offsetX, offsetY;
    if (naturalRatio > boxRatio) {
        contentWidth = rect.width;
        contentHeight = rect.width / naturalRatio;
        offsetX = 0;
        offsetY = (rect.height - contentHeight) / 2;
    } else {
        contentHeight = rect.height;
        contentWidth = rect.height * naturalRatio;
        offsetY = 0;
        offsetX = (rect.width - contentWidth) / 2;
    }

    return {
        left: (rect.left - wrapRect.left) + offsetX,
        top: (rect.top - wrapRect.top) + offsetY,
        width: contentWidth,
        height: contentHeight
    };
}

function percentToCanvas(px, py) {
    const rect = getImageContentRect();
    return {
        cx: rect.left + px * rect.width,
        cy: rect.top + py * rect.height
    };
}

function pctSizeToCanvas(pw, ph) {
    const rect = getImageContentRect();
    return { cw: pw * rect.width, ch: ph * rect.height };
}

function drawAll() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const holds = window.BLOCK_HOLDS || [];
    const blockColor = window.BLOCK_COLOR || "#3b82f6";
    holds.forEach((hold) => {
        const { cx, cy } = percentToCanvas(hold.x, hold.y);
        const { cw, ch } = pctSizeToCanvas(
            hold.w || HOLD_DOT_DEFAULT_SIZE,
            hold.h || HOLD_DOT_DEFAULT_SIZE
        );
        const rawRadius = (cw + ch) / 4; // moyenne des deux demi-diamètres
        // le plafond grandit avec le zoom : les anneaux restent proportionnés à la prise
        const radius = Math.max(HOLD_DOT_MIN, Math.min(HOLD_DOT_MAX * zoomLevel, rawRadius * HOLD_DOT_SCALE));
        const color = HOLD_COLORS[hold.hold_type] || blockColor;
        ctx.beginPath();
        ctx.arc(cx, cy, radius, 0, Math.PI * 2);
        // Juste un anneau de couleur fluo, vide à l'intérieur — pour bien
        // voir la vraie prise en dessous, sans la cacher derrière un rond plein.
        ctx.strokeStyle = color;
        ctx.lineWidth = 2.5;
        ctx.stroke();
    });
}

// --------------------------------------------------
// CHARGEMENT INITIAL
// --------------------------------------------------

let myAscent = { done: 0, flash: 0 };
let allNotes = [];

async function loadAscentsAndNotes() {
    const blockId = window.BLOCK_ID;
    const res = await fetch(`/api/block/${blockId}/full`);
    const data = await res.json();
    myAscent = data.my_ascent || { done: 0, flash: 0 };

    // Pré-sélectionner la cotation de l'utilisateur si elle existe
    const noteSelect = document.getElementById("noteSelect");
    if (noteSelect && data.my_note) {
        noteSelect.value = data.my_note;
    }

    renderAscents(data.ascents, myAscent);
    renderNotes(data.notes);
}

// --------------------------------------------------
// RENDER
// --------------------------------------------------

function renderAscents(ascents, my_ascent) {
    const btnDone  = document.getElementById("btnDone");
    const btnFlash = document.getElementById("btnFlash");
    const isDone   = !!my_ascent?.done;
    const isFlash  = !!my_ascent?.flash;

    if (btnDone) btnDone.classList.toggle("ascent-active", isDone);
    if (btnFlash) {
        btnFlash.classList.toggle("ascent-active", isFlash);
        btnFlash.classList.toggle("flash-active", isFlash);
    }

    const list = document.getElementById("ascentList");
    if (!list) return;
    list.innerHTML = "";
    if (!ascents || ascents.length === 0) {
        list.innerHTML = '<p class="ascent-empty">Personne n\'a encore grimpé ce bloc.</p>';
        return;
    }
    ascents.forEach(a => {
        const div = document.createElement("div");
        div.className = "ascent-entry";
        // textContent (et non innerHTML) : un pseudo ne doit jamais être interprété comme du HTML
        const nameEl = document.createElement("span");
        nameEl.className = "ascent-name";
        nameEl.textContent = a.user_name;
        const badge = document.createElement("span");
        badge.className = a.flash ? "flash-badge" : "done-badge";
        badge.textContent = a.flash ? "⚡ Flash" : "✓ Fait";
        div.append(nameEl, badge);
        list.appendChild(div);
    });
}

function renderNotes(notes) {
    allNotes = notes || [];
    renderAverage(allNotes);
    renderFilteredNotes(document.getElementById("noteSearch")?.value || "");
}

function gradeToIndex(g) {
    return (window.GRADES || []).indexOf(g);
}

function indexToGrade(i) {
    const grades = window.GRADES || [];
    if (grades.length === 0) return "";
    const idx = Math.round(i);
    return grades[Math.max(0, Math.min(grades.length - 1, idx))];
}

/**
 * Cotation communautaire = la cotation la plus proposée (mode).
 * La cotation de l'ouvreur compte comme un vote. En cas d'égalité :
 *  - deux cotations voisines -> "6a/+" (ou "6a+/6b") ;
 *  - sinon, la cotation la plus proche de celle de l'ouvreur.
 * Fonction pure : retourne { label, votes } ou null.
 */
function communityGrade(noteGrades, openerGrade, grades) {
    const votes = [];
    (noteGrades || []).forEach(g => { if (grades.indexOf(g) !== -1) votes.push(grades.indexOf(g)); });
    const openerIdx = grades.indexOf(openerGrade || "");
    if (openerIdx !== -1) votes.push(openerIdx);
    if (votes.length === 0) return null;

    const counts = {};
    votes.forEach(i => { counts[i] = (counts[i] || 0) + 1; });
    const max = Math.max(...Object.values(counts));
    let tied = Object.keys(counts).filter(i => counts[i] === max).map(Number).sort((a, b) => a - b);

    if (tied.length > 1) {
        const lo = tied[0], hi = tied[tied.length - 1];
        if (tied.length === 2 && hi - lo === 1) {
            const low = grades[lo], high = grades[hi];
            const label = (high === low + "+") ? `${low}/+` : `${low}/${high}`;
            return { label, votes: votes.length };
        }
        // Trop éloignées : on garde celle qui se rapproche le plus de l'ouvreur
        // (à défaut d'ouvreur, de la moyenne des votes), la plus basse si égalité.
        const ref = openerIdx !== -1 ? openerIdx : votes.reduce((a, b) => a + b, 0) / votes.length;
        tied.sort((a, b) => Math.abs(a - ref) - Math.abs(b - ref) || a - b);
        return { label: grades[tied[0]], votes: votes.length };
    }
    return { label: grades[tied[0]], votes: votes.length };
}

function renderAverage(notes) {
    const el = document.getElementById("noteAverage");
    if (!el) return;
    const result = communityGrade((notes || []).map(n => n.note), window.BLOCK_GRADE, window.GRADES || []);
    if (!result) {
        el.textContent = "Aucune cotation pour l'instant.";
        return;
    }
    el.textContent = `Cotation communautaire : ${result.label} (${result.votes} vote${result.votes > 1 ? "s" : ""}, ouvreur inclus)`;
}

function renderFilteredNotes(query) {
    const list = document.getElementById("notesList");
    if (!list) return;
    const q = query.trim().toLowerCase();
    const filtered = q ? allNotes.filter(n => n.user_name.toLowerCase().includes(q)) : allNotes;
    list.innerHTML = "";
    if (!filtered || filtered.length === 0) {
        list.innerHTML = q
            ? '<p class="notes-empty">Aucun résultat pour cette recherche.</p>'
            : '<p class="notes-empty">Aucune cotation pour l\'instant.</p>';
        return;
    }
    filtered.forEach(n => {
        const div = document.createElement("div");
        div.className = "note-entry";
        const gradeEl = document.createElement("span");
        gradeEl.className = "note-grade";
        gradeEl.textContent = n.note;
        const userEl = document.createElement("span");
        userEl.className = "note-user";
        userEl.textContent = n.user_name;
        div.append(gradeEl, userEl);
        list.appendChild(div);
    });
}

// --------------------------------------------------
// ASCENSION
// --------------------------------------------------

async function toggleAscent(type) {
    const wasDone  = !!myAscent.done;
    const wasFlash = !!myAscent.flash;

    let newDone  = wasDone;
    let newFlash = wasFlash;

    if (type === "flash") {
        newFlash = !wasFlash;
        if (newFlash) newDone = true;
    } else {
        newDone = !wasDone;
        if (!newDone) newFlash = false;
    }

    const res = await fetch(`/api/block/${window.BLOCK_ID}/ascent`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": window.csrfToken() },
        body: JSON.stringify({ done: newDone ? 1 : 0, flash: newFlash ? 1 : 0 })
    });
    const data = await res.json();
    if (data.success) {
        myAscent = data.my_ascent;
        renderAscents(data.ascents, myAscent);
    }
}

// --------------------------------------------------
// COTATION
// --------------------------------------------------

async function submitNote() {
    const note = document.getElementById("noteSelect")?.value;
    if (!note) return;

    const res = await fetch(`/api/block/${window.BLOCK_ID}/note`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": window.csrfToken() },
        body: JSON.stringify({ note })
    });
    const data = await res.json();
    const msgEl = document.getElementById("noteMessage");
    if (data.success) {
        renderNotes(data.notes);
        if (msgEl) {
            msgEl.textContent = data.message;
            setTimeout(() => { msgEl.textContent = ""; }, 3000);
        }
    }
}
