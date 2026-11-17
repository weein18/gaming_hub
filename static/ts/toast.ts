type ToastKind = "success" | "error" | "info";

function showToast(message: string, kind: ToastKind = "info"): void {
    let box = document.getElementById("toast-box");
    if(!box) {
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

(function showFlashedMessages(): void {
    const el = document.getElementById("flash-data");
    if(!el || !el.textContent) return;
    try {
        const items = JSON.parse(el.textContent) as [string, string][];
        items.forEach(([category, text]) => {
            const kind: ToastKind =
                category === "danger" || category === "error" ? "error" :
                category === "success" ? "success" : "info";
            showToast(text, kind);
        });
    } catch (error) {
        console.error("Could not display flashed messages:", error);
    }
})();