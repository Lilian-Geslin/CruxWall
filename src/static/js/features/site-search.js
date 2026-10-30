// --------------------------------------------------
// RECHERCHE GLOBALE
// --------------------------------------------------
document.addEventListener("DOMContentLoaded", () => {
    const searchInput = document.getElementById("searchInput");
    const searchResults = document.getElementById("searchResults");

    if (searchInput && searchResults) {
        let debounceTimer;
        searchInput.addEventListener("input", () => {
            clearTimeout(debounceTimer);
            const q = searchInput.value.trim();
            if (q.length < 2) {
                searchResults.innerHTML = "";
                searchResults.style.display = "none";
                return;
            }
            debounceTimer = setTimeout(async () => {
                const res = await fetch(`/search?q=${encodeURIComponent(q)}`);
                const data = await res.json();
                searchResults.innerHTML = "";
                if (data.length === 0) {
                    searchResults.style.display = "none";
                    return;
                }
                data.forEach(item => {
                    const li = document.createElement("li");
                    if (item.type === "gym") {
                        li.textContent = (item.is_private ? "🔒 " : "🏢 ") + item.name;
                        li.addEventListener("click", () => {
                            window.location.href = `/gym/${item.id}`;
                        });
                    } else {
                        li.textContent = item.name + (item.gym_name ? ` — ${item.gym_name}` : "");
                        li.addEventListener("click", () => {
                            window.location.href = `/wall/${item.id}`;
                        });
                    }
                    searchResults.appendChild(li);
                });
                searchResults.style.display = "block";
            }, 250);
        });

        document.addEventListener("click", (e) => {
            if (!searchInput.contains(e.target)) {
                searchResults.style.display = "none";
            }
        });
    }
});
