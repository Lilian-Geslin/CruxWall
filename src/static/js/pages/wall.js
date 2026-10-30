// --------------------------------------------------
// VUE DU MUR — Liste des blocs : filtre, tri, navigation directe
// --------------------------------------------------
// Un clic sur un bloc mène directement à sa page (/block/<id>).
// Plus de panneau ni de canvas intermédiaire sur cette page : c'était
// redondant avec la page du bloc qui montre exactement la même chose.

document.addEventListener("DOMContentLoaded", () => {
    // Clic sur un bloc de la liste -> navigation directe vers sa page
    document.querySelectorAll(".block-item").forEach(item => {
        item.addEventListener("click", () => {
            const blockId = item.dataset.blockId;
            window.location.href = `/block/${blockId}`;
        });
    });

    // Filtre par tranche de difficulté
    document.querySelectorAll(".filter-btn[data-grade]").forEach(btn => {
        btn.addEventListener("click", () => {
            document.querySelectorAll(".filter-btn[data-grade]").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            const filter = btn.dataset.grade;
            document.querySelectorAll(".block-item").forEach(item => {
                const grade = item.dataset.grade || "";
                let show = true;
                if (filter === "facile") show = isEasyGrade(grade);
                else if (filter === "inter") show = isInterGrade(grade);
                else if (filter === "dur") show = isHardGrade(grade);
                item.style.display = show ? "" : "none";
            });
        });
    });

    // Tri par cotation, facile→dur ou dur→facile
    document.getElementById("sortEasyToHard")?.addEventListener("click", () => sortBlocks(1));
    document.getElementById("sortHardToEasy")?.addEventListener("click", () => sortBlocks(-1));
});

// --------------------------------------------------
// TRI PAR COTATION
// --------------------------------------------------

function sortBlocks(direction) {
    const list = document.getElementById("blocksList");
    if (!list) return;
    const items = Array.from(list.querySelectorAll(".block-item"));
    items.sort((a, b) => {
        const ia = gradeIdx(a.dataset.grade);
        const ib = gradeIdx(b.dataset.grade);
        // Les blocs sans cotation restent à la fin, quel que soit le sens du tri
        if (ia === -1 && ib === -1) return 0;
        if (ia === -1) return 1;
        if (ib === -1) return -1;
        return direction * (ia - ib);
    });
    items.forEach(item => list.appendChild(item));
}

// --------------------------------------------------
// COTATIONS — ordre et tranches de difficulté
// --------------------------------------------------
// Même liste que GRADES dans src/constants.py.

const GRADE_ORDER = [
    "3a","3a+","3b","3b+","3c","3c+",
    "4a","4a+","4b","4b+","4c","4c+",
    "5a","5a+","5b","5b+","5c","5c+",
    "6a","6a+","6b","6b+","6c","6c+",
    "7a","7a+","7b","7b+","7c","7c+",
    "8a","8a+","8b","8b+","8c","8c+",
    "9a","9a+","9b","9b+","9c"
];

function gradeIdx(g) {
    const i = GRADE_ORDER.indexOf((g || "").toLowerCase());
    return i === -1 ? -1 : i;
}
function isEasyGrade(g) { const i = gradeIdx(g); return i >= 0 && i <= GRADE_ORDER.indexOf("5c+"); }
function isInterGrade(g) { const i = gradeIdx(g); return i > GRADE_ORDER.indexOf("5c+") && i <= GRADE_ORDER.indexOf("7a"); }
function isHardGrade(g) { const i = gradeIdx(g); return i > GRADE_ORDER.indexOf("7a"); }
