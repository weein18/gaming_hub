"use strict";
function showToast(message, kind = "info") {
    let box = document.getElementById("toast-box");
    if (!box) {
        box = document.createElement("div");
        box.id = "toast-box";
        document.body.appendChild(box);
    }
    const toast = document.createElement("div");
    toast.className = `toast toast-${kind}`;
    toast.textContent = message;
    box.appendChild(toast);
    requestAnimationFrame(() => toast.classList.add("toast-show"));
    window.setTimeout(() => {
        toast.classList.remove("toast-show");
        window.setTimeout(() => toast.remove(), 300);
    }, 3500);
}
(function showFlashedMessages() {
    const el = document.getElementById("flash-show");
    if (!el || !el.textContent)
        return;
    try {
        const items = JSON.parse(el.textContent);
        items.forEach(([category, text]) => {
            const kind = category === "danger" || category === "error" ? "error" :
                category === "success" ? "success" : "info";
            showToast(text, kind);
        });
    }
    catch {
    }
})();
