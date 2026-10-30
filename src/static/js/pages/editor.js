// --------------------------------------------------
// ÉDITEUR DE BLOCS — Détection IA + sélection prises
// --------------------------------------------------

const canvas  = document.getElementById("editorCanvas");
const ctx     = canvas.getContext("2d");
const img     = document.getElementById("editorImage");
const wrapper = document.getElementById("canvasWrapper");

// Prises détectées par l'IA : [{x, y, w, h}, ...]  (coordonnées en % 0-1)
let detectedHolds = [];

// Prises sélectionnées par l'utilisateur : [{x, y, w, h, type}, ...]
let selectedHolds = [];

// Outil actif
let currentTool = "start";

// Couleurs par type
const TOOL_COLORS = {
    start: "#22c55e",
    mid:   "#3b82f6",
    top:   "#ef4444",
    foot:  "#eab308"
};

// Style des prises non sélectionnées (contour discret)
const IDLE_STROKE  = "rgba(255,255,255,0.35)";
const IDLE_FILL    = "rgba(255,255,255,0.06)";

// Taille par défaut (en % de l'image) d'une prise posée manuellement. Elle
// peut ensuite être ajustée précisément via sa poignée de redimensionnement.
const MANUAL_HOLD_SIZE = 0.035;

// Index (dans selectedHolds) de la prise qui affiche actuellement sa poignée
// de redimensionnement au coin bas-droit — comme pour redimensionner une
// photo sur PC. -1 = aucune poignée affichée.
let activeHoldIndex = -1;

// Index de la prise en cours de redimensionnement pendant un glisser (drag),
// et l'identifiant du pointeur (souris/doigt) qui le fait.
let resizingIndex = -1;
let resizePointerId = null;
const HANDLE_RADIUS = 7;       // taille visuelle de la poignée (px canvas)
const HANDLE_HIT_RADIUS = 14;  // zone cliquable autour, plus grande pour le doigt

// Suivi des doigts posés sur l'écran (position de chacun, pas juste leur
// nombre) : sert à la fois à ignorer les taps pendant un pincement, et à
// calculer le zoom à partir de l'écart entre les deux doigts.
let activePointers = new Map(); // pointerId -> {x, y}
let gestureIsMultiTouch = false;
let pinchStartDist = null;
let pinchStartZoom = 1;

// --------------------------------------------------
// ZOOM — n'agrandit que l'image, jamais le reste de la page
// --------------------------------------------------

let zoomLevel = 1;
const ZOOM_MIN = 1;
const ZOOM_MAX = 6;
const ZOOM_STEP = 0.5;

function updateTouchAction() {
    // À 100 % : on laisse le navigateur faire défiler la page quand on glisse
    // verticalement sur l'image (fluide, avec inertie, sans conflit avec la
    // barre d'adresse de Safari iOS). Dès que l'image est zoomée : tout
    // geste est à nous (déplacer l'image, pincer).
    canvas.style.touchAction = zoomLevel <= ZOOM_MIN + 0.001 ? "pan-y" : "none";
}

function applyZoom() {
    updateTouchAction();
    // Tailles en pixels, mesurées sur le viewport : des pourcentages sont
    // ignorés quand le parent n'a pas de hauteur fixe (cas du téléphone), ce
    // qui faisait changer la taille de l'image d'un coup au premier zoom.
    const vp = document.getElementById("canvasViewport");
    if (zoomLevel <= ZOOM_MIN + 0.001) {
        wrapper.style.width = "100%";
        wrapper.style.height = "100%";
    } else {
        wrapper.style.width = (vp.offsetWidth * zoomLevel) + "px";
        wrapper.style.height = (vp.offsetHeight * zoomLevel) + "px";
    }
    const label = document.getElementById("zoomLevelLabel");
    if (label) label.textContent = Math.round(zoomLevel * 100) + "%";
    resizeCanvas(); // recalcule canvas.width/height sur la nouvelle taille et redessine
}

/** Recentre le défilement sur le milieu de l'image, pour que le zoom agrandisse
 *  depuis le centre plutôt que depuis le coin haut-gauche. N'est appelé que
 *  pour les boutons +/- : pendant un pincement, les doigts font déjà office
 *  de point de référence, le recentrer en continu créerait un à-coup. */
function centerViewport() {
    const vp = document.getElementById("canvasViewport");
    if (!vp) return;
    vp.scrollLeft = (wrapper.clientWidth - vp.clientWidth) / 2;
    vp.scrollTop = (wrapper.clientHeight - vp.clientHeight) / 2;
}

function zoomBy(delta) {
    zoomLevel = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, zoomLevel + delta));
    applyZoom();
    centerViewport();
}

function zoomReset() {
    zoomLevel = ZOOM_MIN;
    applyZoom();
    centerViewport();
}

function pointerDist(a, b) {
    return Math.hypot(a.x - b.x, a.y - b.y);
}

// --------------------------------------------------
// DÉPLACEMENT (PAN) — glisser pour naviguer dans l'image zoomée
// --------------------------------------------------
// Un simple tap pose/sélectionne une prise comme avant ; dès que le geste
// dépasse quelques pixels de mouvement, on bascule en déplacement de l'image
// au lieu de poser une prise — comme la main qu'on utilise pour naviguer
// dans une image zoomée sur ordinateur.

let isPanning = false;
let panStart = null;       // {x, y} au moment du clic/toucher
let panScrollStart = null; // position de défilement à ce moment-là
let panMoved = false;
let panPageScrollY = 0;   // position de la page au début du glisser (défilement à 100%)
function setPageSmoothScroll(on) {
    // Le CSS du site met "scroll-behavior: smooth" sur <html> : pendant un
    // glisser au doigt, chaque mise à jour lance une animation qui se
    // bat avec la suivante (d'où les petits allers-retours). On la coupe le
    // temps du geste.
    document.documentElement.style.scrollBehavior = on ? "" : "auto";
}
let panLast = null;       // dernière position du doigt (pour faire défiler la page à 100%)
const PAN_THRESHOLD = 6; // px avant de considérer que c'est un glisser, pas un tap

// --------------------------------------------------
// INIT
// --------------------------------------------------

document.addEventListener("DOMContentLoaded", async () => {
    if (img.complete) { resizeCanvas(); }
    img.addEventListener("load", resizeCanvas);
    let lastWinWidth = window.innerWidth;
    window.addEventListener("resize", () => {
        if (window.innerWidth === lastWinWidth) return;
        lastWinWidth = window.innerWidth;
        applyZoom();
    });

    // Outils
    document.querySelectorAll(".tool-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            const type = btn.dataset.type;
            if (type === "undo") { undoLast(); return; }
            if (type === "erase") { currentTool = "erase"; }
            else { currentTool = type || "mid"; }
            document.querySelectorAll(".tool-btn").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
        });
    });

    // Interaction sur le canvas : les Pointer Events couvrent souris, doigt
    // et stylet avec le même code (fini le double système clic + touch).
    canvas.addEventListener("pointerdown", onPointerDown);
    canvas.addEventListener("pointermove", onPointerMove);
    canvas.addEventListener("pointerup", onPointerUp);
    canvas.addEventListener("pointercancel", onPointerCancel);

    // À 100 % le canvas est en "touch-action: pan-y" (pour que la page défile
    // d'un doigt). Mais dès que DEUX doigts sont posés, on veut que ce soit
    // un pincement : on interdit alors au navigateur de transformer le moindre
    // mouvement en défilement (sinon il annulait le geste et arrêtait le
    // zoom dès que les doigts bougeaient un peu).
    const blockIfMultiTouch = (e) => {
        if (e.touches.length >= 2 && e.cancelable) e.preventDefault();
    };
    canvas.addEventListener("touchstart", blockIfMultiTouch, { passive: false });
    canvas.addEventListener("touchmove", blockIfMultiTouch, { passive: false });
    // Safari iOS : empêche aussi son propre zoom de page par pincement
    ["gesturestart", "gesturechange", "gestureend"].forEach(ev =>
        canvas.addEventListener(ev, (e) => e.preventDefault())
    );

    // Sauvegarde
    document.getElementById("saveBlock")?.addEventListener("click", saveBlock);

    // Zoom : boutons +/- et réinitialisation (le pincement à deux doigts
    // sur l'image fait la même chose, voir onPointerDown/onPointerMove)
    document.getElementById("zoomIn")?.addEventListener("click", () => zoomBy(ZOOM_STEP));
    document.getElementById("zoomOut")?.addEventListener("click", () => zoomBy(-ZOOM_STEP));
    document.getElementById("zoomReset")?.addEventListener("click", zoomReset);

    // Refaire la détection à la demande (utile si le résultat était mauvais,
    // ou après avoir réglé un souci de crédit/connexion côté IA en ligne)
    document.getElementById("btnRetryAi")?.addEventListener("click", () => detectHolds(true));

    // Activer / désactiver la détection IA pour ce mur précis
    document.getElementById("btnToggleAi")?.addEventListener("click", toggleAiForWall);

    // La détection est toujours lancée à l'arrivée sur la page : le bouton
    // "Désactiver" ne vaut que pour la visite en cours, rien n'est mémorisé.
    updateTouchAction();
    await detectHolds();
});

// --------------------------------------------------
// CANVAS — redimensionnement
// --------------------------------------------------

function resizeCanvas() {
    canvas.width  = wrapper.clientWidth;
    canvas.height = wrapper.clientHeight;
    drawAll();
}

// --------------------------------------------------
// COORDONNÉES
// --------------------------------------------------

/**
 * Zone réellement occupée par la photo à l'intérieur de son cadre.
 *
 * Le cadre (canvasWrapper) a un ratio fixe, mais la photo (surtout depuis
 * la correction de l'orientation EXIF, qui peut désormais être bien plus
 * haute que large) ne fait pas forcément le même ratio : "object-fit:
 * contain" laisse alors des bandes vides à gauche/droite ou en haut/bas.
 * Sans ce calcul, une prise posée à 50% de la largeur du CADRE atterrissait
 * dans une bande vide au lieu du centre réel de la photo.
 */
function getImageContentRect() {
    const r  = img.getBoundingClientRect();
    const wr = wrapper.getBoundingClientRect();
    const naturalRatio = img.naturalWidth / img.naturalHeight;
    const boxRatio = r.width / r.height;

    let contentWidth, contentHeight, offsetX, offsetY;
    if (naturalRatio > boxRatio) {
        // Photo relativement plus large que le cadre → bandes en haut/bas
        contentWidth  = r.width;
        contentHeight = r.width / naturalRatio;
        offsetX = 0;
        offsetY = (r.height - contentHeight) / 2;
    } else {
        // Photo relativement plus haute que le cadre → bandes à gauche/droite
        // (le cas classique d'une photo de téléphone en portrait)
        contentHeight = r.height;
        contentWidth  = r.height * naturalRatio;
        offsetY = 0;
        offsetX = (r.width - contentWidth) / 2;
    }

    return {
        left:   (r.left - wr.left) + offsetX,
        top:    (r.top  - wr.top)  + offsetY,
        width:  contentWidth,
        height: contentHeight
    };
}

/** Coordonnées % → pixels canvas */
function pctToCanvas(px, py) {
    const rect = getImageContentRect();
    return {
        cx: rect.left + px * rect.width,
        cy: rect.top  + py * rect.height
    };
}

/** Pixels canvas → coordonnées % */
function canvasToPct(cx, cy) {
    const rect = getImageContentRect();
    return {
        x: (cx - rect.left) / rect.width,
        y: (cy - rect.top)  / rect.height
    };
}

/** Taille w/h en % → pixels canvas */
function pctSizeToCanvas(pw, ph) {
    const rect = getImageContentRect();
    return { cw: pw * rect.width, ch: ph * rect.height };
}

// --------------------------------------------------
// DESSIN
// --------------------------------------------------

function drawAll() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    drawDetectedHolds();
    drawSelectedHolds();
}

/** Dessine toutes les prises détectées (non sélectionnées) en contour discret */
function drawDetectedHolds() {
    detectedHolds.forEach((hold, i) => {
        if (isAlreadySelected(i)) return; // skip si déjà sélectionnée

        const { cx, cy } = pctToCanvas(hold.x, hold.y);
        const { cw, ch } = pctSizeToCanvas(hold.w, hold.h);
        const rx = cw / 2;
        const ry = ch / 2;

        ctx.save();
        ctx.beginPath();
        ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2);
        ctx.fillStyle   = IDLE_FILL;
        ctx.fill();
        ctx.strokeStyle = IDLE_STROKE;
        ctx.lineWidth   = 1.5;
        ctx.stroke();
        ctx.restore();
    });
}

/** Dessine les prises sélectionnées avec surbrillance */
function drawSelectedHolds() {
    selectedHolds.forEach((hold, i) => {
        const color = TOOL_COLORS[hold.type] || TOOL_COLORS.mid;
        const { cx, cy } = pctToCanvas(hold.x, hold.y);
        const { cw, ch } = pctSizeToCanvas(hold.w, hold.h);
        const rx = cw / 2;
        const ry = ch / 2;

        ctx.save();

        // Juste un anneau de couleur fluo, vide à l'intérieur — pas de
        // remplissage ni de numéro, pour bien voir la prise en dessous.
        ctx.beginPath();
        ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2);
        ctx.strokeStyle = color;
        ctx.lineWidth   = 3;
        ctx.stroke();

        ctx.restore();

        // Poignée de redimensionnement, uniquement sur la prise active —
        // comme le petit carré au coin d'une photo qu'on agrandit sur PC.
        if (i === activeHoldIndex) {
            const hx = cx + rx;
            const hy = cy + ry;
            ctx.save();
            ctx.beginPath();
            ctx.arc(hx, hy, HANDLE_RADIUS, 0, Math.PI * 2);
            ctx.fillStyle = "#ffffff";
            ctx.fill();
            ctx.strokeStyle = color;
            ctx.lineWidth = 2;
            ctx.stroke();
            // petite flèche diagonale, pour signaler "on peut tirer ici"
            ctx.strokeStyle = color;
            ctx.lineWidth = 1.5;
            ctx.beginPath();
            ctx.moveTo(hx - 3, hy + 3);
            ctx.lineTo(hx + 3, hy - 3);
            ctx.stroke();
            ctx.restore();
        }
    });
}

// --------------------------------------------------
// INTERACTION — tap, glisser la poignée, pincement à ignorer
// --------------------------------------------------

function getHandlePos(hold) {
    const { cx, cy } = pctToCanvas(hold.x, hold.y);
    const { cw, ch } = pctSizeToCanvas(hold.w, hold.h);
    return { hx: cx + cw / 2, hy: cy + ch / 2 };
}

function hitsHandle(cx, cy, hold) {
    const { hx, hy } = getHandlePos(hold);
    return Math.hypot(cx - hx, cy - hy) <= HANDLE_HIT_RADIUS;
}

function onPointerDown(e) {
    activePointers.set(e.pointerId, { x: e.clientX, y: e.clientY });

    if (activePointers.size >= 2) {
        // Deuxième doigt posé : c'est un pincement pour zoomer l'image, pas
        // une pose de prise. On annule tout geste à un doigt déjà commencé
        // (déplacement, redimensionnement, tap) pour qu'il ne reprenne pas
        // avec des données périmées quand on relâchera un doigt.
        if (!gestureIsMultiTouch) {
            gestureIsMultiTouch = true;
            panStart = null;
            panLast = null;
            panMoved = false;
            isPanning = false;
            setPageSmoothScroll(true);
            resizingIndex = -1;
            resizePointerId = null;
            wrapper.style.cursor = "grab";
        }
        if (activePointers.size === 2) {
            const pts = Array.from(activePointers.values());
            pinchStartDist = pointerDist(pts[0], pts[1]);
            pinchStartZoom = zoomLevel;
        }
        return;
    }

    const wr = wrapper.getBoundingClientRect();
    const cx = e.clientX - wr.left;
    const cy = e.clientY - wr.top;

    if (activeHoldIndex !== -1 && selectedHolds[activeHoldIndex] &&
        hitsHandle(cx, cy, selectedHolds[activeHoldIndex])) {
        resizingIndex = activeHoldIndex;
        resizePointerId = e.pointerId;
        canvas.setPointerCapture(e.pointerId);
        e.preventDefault(); // évite que le glisser fasse défiler la page
        return;
    }

    // Pas sur la poignée : on prépare un éventuel déplacement (pan). On ne
    // bascule réellement en mode "glisser" que si le pointeur bouge assez
    // (voir onPointerMove) — un tap immobile reste une pose de prise normale.
    const vp = document.getElementById("canvasViewport");
    panStart = { x: e.clientX, y: e.clientY };
    panLast = { x: e.clientX, y: e.clientY };
    panPageScrollY = window.scrollY;
    panScrollStart = { left: vp.scrollLeft, top: vp.scrollTop };
    panMoved = false;
}

function onPointerMove(e) {
    if (activePointers.has(e.pointerId)) {
        activePointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    }

    if (gestureIsMultiTouch) {
        if (activePointers.size === 2 && pinchStartDist > 10) {
            const pts = Array.from(activePointers.values());
            const newDist = pointerDist(pts[0], pts[1]);
            const newZoom = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, pinchStartZoom * (newDist / pinchStartDist)));

            // Zoom vers l'endroit visé par les doigts, pas vers un coin fixe :
            // on repère quel point de l'image se trouve sous le milieu des deux
            // doigts AVANT le changement de taille, puis on règle le défilement
            // APRÈS pour que ce même point reste sous les doigts.
            const vp = document.getElementById("canvasViewport");
            const vpRect = vp.getBoundingClientRect();
            const midX = (pts[0].x + pts[1].x) / 2;
            const midY = (pts[0].y + pts[1].y) / 2;

            const beforeW = wrapper.clientWidth;
            const beforeH = wrapper.clientHeight;
            const fracX = beforeW > 0 ? (vp.scrollLeft + (midX - vpRect.left)) / beforeW : 0.5;
            const fracY = beforeH > 0 ? (vp.scrollTop + (midY - vpRect.top)) / beforeH : 0.5;

            zoomLevel = newZoom;
            applyZoom();

            vp.scrollLeft = fracX * wrapper.clientWidth - (midX - vpRect.left);
            vp.scrollTop = fracY * wrapper.clientHeight - (midY - vpRect.top);
        }
        // Tant qu'il reste un doigt d'un geste à plusieurs doigts, on ne fait
        // rien d'autre : pas de déplacement ni de pose de prise.
        return;
    }

    const isActivelyResizing = resizingIndex !== -1 && e.pointerId === resizePointerId;

    if (!isActivelyResizing && panStart && activePointers.size === 1) {
        const dx = e.clientX - panStart.x;
        const dy = e.clientY - panStart.y;
        if (!panMoved && Math.hypot(dx, dy) > PAN_THRESHOLD) {
            panMoved = true;
            isPanning = true;
            wrapper.style.cursor = "grabbing";
        }
        if (isPanning) {
            if (zoomLevel > ZOOM_MIN + 0.001) {
                // Image zoomée : on déplace l'image dans son cadre
                const vp = document.getElementById("canvasViewport");
                vp.scrollLeft = panScrollStart.left - dx;
                vp.scrollTop = panScrollStart.top - dy;
            }
            panLast = { x: e.clientX, y: e.clientY };
            return;
        }
    }

    if (resizingIndex === -1 || e.pointerId !== resizePointerId || activePointers.size > 1) return;

    const wr = wrapper.getBoundingClientRect();
    const cx = e.clientX - wr.left;
    const cy = e.clientY - wr.top;

    const hold = selectedHolds[resizingIndex];
    const { cx: hcx, cy: hcy } = pctToCanvas(hold.x, hold.y);
    const rect = getImageContentRect();

    let rx = cx - hcx;
    let ry = cy - hcy;
    const minR = 8;
    const maxR = Math.min(rect.width, rect.height) * 0.15;
    rx = Math.max(minR, Math.min(maxR, rx));
    ry = Math.max(minR, Math.min(maxR, ry));

    hold.w = (rx * 2) / rect.width;
    hold.h = (ry * 2) / rect.height;
    drawAll();
}

function onPointerUp(e) {
    activePointers.delete(e.pointerId);

    if (gestureIsMultiTouch) {
        // Un geste à plusieurs doigts reste "en cours" tant qu'il reste au
        // moins un doigt à l'écran. Avant, on le terminait dès qu'un seul
        // doigt était levé : le doigt restant déclenchait alors un
        // déplacement avec une position de départ périmée (l'image sautait)
        // puis une pose de prise involontaire à son relâchement.
        if (activePointers.size === 0) {
            gestureIsMultiTouch = false;
            pinchStartDist = null;
            panStart = null;
            panLast = null;
        }
        return;
    }

    if (resizingIndex !== -1 && e.pointerId === resizePointerId) {
        resizingIndex = -1;
        resizePointerId = null;
        activeHoldIndex = -1; // la poignée disparaît une fois le redimensionnement fini
        drawAll();
        updateCounter();
        return;
    }

    if (isPanning) {
        // On vient de finir un glisser : on ne pose pas de prise à l'endroit
        // où le doigt/la souris se relâche.
        isPanning = false;
        panStart = null;
        panLast = null;
        setPageSmoothScroll(true);
        wrapper.style.cursor = "grab";
        return;
    }
    panStart = null;
    panLast = null;

    const wr = wrapper.getBoundingClientRect();
    const cx = e.clientX - wr.left;
    const cy = e.clientY - wr.top;
    handleTap(cx, cy);
}

function onPointerCancel(e) {
    activePointers.delete(e.pointerId);
    if (activePointers.size === 0) {
        gestureIsMultiTouch = false;
        pinchStartDist = null;
    }
    if (e.pointerId === resizePointerId) {
        resizingIndex = -1;
        resizePointerId = null;
    }
    if (isPanning) {
        isPanning = false;
        wrapper.style.cursor = "grab";
    }
    setPageSmoothScroll(true);
    panStart = null;
    panLast = null;
}

/** Gère un tap simple : sélectionner (pour redimensionner) ou poser une prise */
function handleTap(cx, cy) {
    if (currentTool === "erase") {
        eraseAt(cx, cy);
        return;
    }

    // 1. Clic sur une prise déjà posée → on l'active pour afficher sa
    //    poignée de redimensionnement. On ne la supprime plus ici : la
    //    suppression se fait uniquement via l'outil "Effacer", pour éviter
    //    de perdre une prise par erreur en voulant juste la redimensionner.
    const selIdx = findSelectedAt(cx, cy);
    if (selIdx !== -1) {
        activeHoldIndex = selIdx;
        drawAll();
        return;
    }

    // 2. Clic sur une prise détectée par l'IA → sélectionner
    const detIdx = findDetectedAt(cx, cy);
    if (detIdx !== -1) {
        const hold = detectedHolds[detIdx];
        selectedHolds.push({ x: hold.x, y: hold.y, w: hold.w, h: hold.h, type: currentTool });
        activeHoldIndex = selectedHolds.length - 1;
        drawAll();
        updateCounter();
        return;
    }

    // 3. Aucune prise détectée à cet endroit → on la crée manuellement,
    //    et sa poignée de redimensionnement apparaît aussitôt.
    const { x, y } = canvasToPct(cx, cy);
    if (x < 0 || x > 1 || y < 0 || y > 1) return; // clic en dehors de la photo
    // La taille de départ est divisée par le niveau de zoom : sans ça,
    // l'anneau gardait la même taille en % de l'image quel que soit le zoom,
    // donc paraissait énorme à l'écran une fois zoomé sur une petite prise.
    // Ainsi, plus on zoome, plus l'anneau proposé par défaut est petit et
    // adapté à ce qu'on regarde de près.
    const initialSize = MANUAL_HOLD_SIZE / zoomLevel;
    selectedHolds.push({
        x, y,
        w: initialSize,
        h: initialSize,
        type: currentTool,
        manual: true
    });
    activeHoldIndex = selectedHolds.length - 1;
    drawAll();
    updateCounter();
}

/** Cherche une prise sélectionnée à la position (cx, cy) */
function findSelectedAt(cx, cy) {
    for (let i = selectedHolds.length - 1; i >= 0; i--) {
        if (hitsHold(cx, cy, selectedHolds[i])) return i;
    }
    return -1;
}

/** Cherche une prise détectée (non sélectionnée) à la position (cx, cy) */
function findDetectedAt(cx, cy) {
    for (let i = detectedHolds.length - 1; i >= 0; i--) {
        if (isAlreadySelected(i)) continue;
        if (hitsHold(cx, cy, detectedHolds[i])) return i;
    }
    return -1;
}

/** Test de collision avec une ellipse */
function hitsHold(cx, cy, hold) {
    const { cx: hx, cy: hy } = pctToCanvas(hold.x, hold.y);
    const { cw, ch }         = pctSizeToCanvas(hold.w, hold.h);
    // Pas de marge ajoutée : avec des prises collées, une tolérance généreuse
    // empêchait de poser une nouvelle prise juste à côté d'une déjà placée
    // (le clic "mordait" sur la voisine). Zoomez pour viser précisément.
    const rx = cw / 2;
    const ry = ch / 2;
    return ((cx - hx) ** 2) / (rx ** 2) + ((cy - hy) ** 2) / (ry ** 2) <= 1;
}

/** Vérifie si une prise détectée (par index) est déjà sélectionnée */
function isAlreadySelected(detIdx) {
    const hold = detectedHolds[detIdx];
    return selectedHolds.some(s => Math.abs(s.x - hold.x) < 0.005 && Math.abs(s.y - hold.y) < 0.005);
}

/** Supprime la prise sélectionnée la plus proche du clic */
function eraseAt(cx, cy) {
    const idx = findSelectedAt(cx, cy);
    if (idx !== -1) {
        selectedHolds.splice(idx, 1);
        activeHoldIndex = -1;
        drawAll();
        updateCounter();
    }
}

function undoLast() {
    selectedHolds.pop();
    activeHoldIndex = -1;
    drawAll();
    updateCounter();
}

function updateCounter() {
    const el = document.getElementById("holdsCount");
    if (el) el.textContent = selectedHolds.length;
}

// --------------------------------------------------
// DÉTECTION IA
// --------------------------------------------------

// Vrai tant que la détection automatique est active. Ce n'est PAS mémorisé :
// à chaque arrivée sur la page de création de bloc, elle est active.
let aiEnabled = true;
let detectionRunId = 0; // pour ignorer le résultat d'une détection abandonnée entre-temps

async function detectHolds(force = false) {
    if (!aiEnabled) return;

    const wallId   = window.WALL_ID;
    const statusEl = document.getElementById("aiStatus");
    const overlayEl = document.getElementById("aiOverlay");
    const runId = ++detectionRunId;

    if (overlayEl) overlayEl.style.display = "flex";
    if (statusEl)  statusEl.textContent    = "Analyse du mur en cours…";

    try {
        const res  = await fetch(`/api/wall/${wallId}/detect_holds${force ? "?force=1" : ""}`, {
            method: "POST",
            headers: { "X-CSRF-Token": window.csrfToken() }
        });
        const data = await res.json();

        // La détection a été désactivée (ou relancée) pendant l'attente
        if (runId !== detectionRunId || !aiEnabled) return;

        if (res.status === 429) {
            if (statusEl) statusEl.textContent = "Trop de détections en peu de temps — réessayez plus tard, ou cliquez directement sur le mur pour placer vos prises";
            return;
        }

        if (data.success && data.holds?.length > 0) {
            detectedHolds = data.holds;
            const via = data.source === "roboflow" ? "en ligne, Roboflow" : "modèle local";
            if (statusEl) statusEl.textContent = `${detectedHolds.length} prises détectées (${via}) — cliquez dessus, ou ailleurs sur le mur pour en ajouter`;
            drawAll();
        } else {
            // Le détail technique (crédits, modèle absent, etc.) est utile pour nous
            // mais pas pour la personne qui utilise l'appli : elle voit juste qu'il
            // y a un souci, et peut continuer en plaçant les prises à la main.
            if (statusEl) statusEl.textContent = "Détection des prises indisponible pour le moment — cliquez directement sur le mur pour placer vos prises";
            console.warn("Détection IA:", data.error || "Aucune prise retournée");
        }
    } catch (err) {
        if (runId !== detectionRunId || !aiEnabled) return;
        if (statusEl) statusEl.textContent = "Détection des prises indisponible pour le moment — cliquez directement sur le mur pour placer vos prises";
        console.error("Erreur détection:", err);
    } finally {
        if (runId === detectionRunId && overlayEl) overlayEl.style.display = "none";
    }
}

// --------------------------------------------------
// ACTIVER / DÉSACTIVER L'IA (pour cette visite uniquement)
// --------------------------------------------------

async function toggleAiForWall() {
    const btn = document.getElementById("btnToggleAi");
    const statusEl = document.getElementById("aiStatus");
    const overlayEl = document.getElementById("aiOverlay");

    aiEnabled = !aiEnabled;

    if (!aiEnabled) {
        detectionRunId++;                       // abandonne une éventuelle détection en cours
        if (overlayEl) overlayEl.style.display = "none";
        if (btn) btn.textContent = "✅ Réactiver la détection des prises";
        detectedHolds = [];
        drawAll();
        if (statusEl) statusEl.textContent = "Détection des prises désactivée — cliquez directement sur le mur pour placer vos prises.";
    } else {
        if (btn) btn.textContent = "🚫 Désactiver la détection des prises";
        await detectHolds();
    }
}

// --------------------------------------------------
// SAUVEGARDE
// --------------------------------------------------

async function saveBlock() {
    const name        = document.getElementById("blockName").value.trim();
    const grade       = document.getElementById("blockGrade").value;
    const color       = document.querySelector('input[name="blockColor"]:checked')?.value || "#3b82f6";
    const description = document.getElementById("blockDescription").value.trim();
    const link        = (document.getElementById("blockLink")?.value || "").trim();
    const errorEl     = document.getElementById("formError");

    errorEl.style.display = "none";

    if (!name) {
        errorEl.textContent    = "Le nom du bloc est requis.";
        errorEl.style.display  = "block";
        return;
    }
    if (selectedHolds.length < 2) {
        errorEl.textContent    = "Sélectionnez au moins 2 prises sur le mur.";
        errorEl.style.display  = "block";
        return;
    }

    const btn = document.getElementById("saveBlock");
    btn.disabled    = true;
    btn.textContent = "Enregistrement…";

    try {
        const res = await fetch(window.SAVE_URL, {
            method:  "POST",
            headers: { "Content-Type": "application/json", "X-CSRF-Token": window.csrfToken() },
            body:    JSON.stringify({
                wall_id:     window.WALL_ID,
                name, grade, color, description, link,
                holds: selectedHolds.map(h => ({ x: h.x, y: h.y, type: h.type, w: h.w, h: h.h }))
            })
        });
        const data = await res.json();
        if (data.success) {
            window.location.href = `/block/${data.block_id}`;
        } else {
            errorEl.textContent   = data.error || "Erreur lors de l\'enregistrement.";
            errorEl.style.display = "block";
            btn.disabled          = false;
            btn.textContent       = "Enregistrer le bloc →";
        }
    } catch {
        errorEl.textContent   = "Erreur réseau.";
        errorEl.style.display = "block";
        btn.disabled          = false;
        btn.textContent       = "Enregistrer le bloc →";
    }
}
