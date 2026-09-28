(function () {
    function citeSelector(key) {
        var safe = window.CSS && CSS.escape ? CSS.escape(key) : String(key).replace(/"/g, "");
        return '.source-item[data-cite="' + safe + '"]';
    }

    function onClick(event) {
        var chip = event.target.closest ? event.target.closest(".cite-chip") : null;
        if (!chip) return;
        var content = chip.closest(".bubble-content") || chip.closest(".bubble");
        if (!content) return;
        var details = content.querySelector(".source-details");
        if (details) details.open = true;
        content.querySelectorAll(".source-item.is-cited").forEach(function (item) {
            item.classList.remove("is-cited");
        });
        var match = content.querySelector(citeSelector(chip.getAttribute("data-cite") || ""));
        if (!match) return;
        match.classList.add("is-cited");
        match.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }

    document.querySelectorAll("#historico-chat").forEach(function (root) {
        if (root.dataset.citationsBound) return;
        root.dataset.citationsBound = "1";
        root.addEventListener("click", onClick);
    });
})();
