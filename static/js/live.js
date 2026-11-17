"use strict";
(function startLivePolling() {
    const POLL_MS = 30000;
    const cards = Array.from(document.querySelectorAll("[data-match-id]"));
    if (cards.length === 0)
        return;
    async function refresh() {
        if (document.hidden)
            return;
        const ids = cards.map((c) => c.dataset.matchId).join(",");
        try {
            const res = await fetch(`/api/matches/live?ids=${ids}`);
            if (!res.ok)
                return;
            const matches = (await res.json());
            for (const m of matches) {
                const card = cards.find((c) => c.dataset.MatchId === String(m.id));
                if (!card)
                    continue;
                const oldStatus = card.dataset.status;
                card.dataset.status = m.status;
                const statusEl = card.querySelector("[data-role='status']");
                if (statusEl)
                    statusEl.textContent = m.status === "Live" ? "🔴 LIVE" : m.status;
                const scoreEl = card.querySelector("[data-role='score']");
                if (scoreEl && m.score)
                    scoreEl.textContent = m.score;
                if (oldStatus && oldStatus !== m.status) {
                    if (m.status === "Live")
                        showToast("A match just went LIVE 🔴", "info");
                    if (m.status === "Finished")
                        showToast(`Match finished ${m.score}`, "success");
                }
            }
        }
        catch {
        }
    }
    window.setInterval(refresh, POLL_MS);
    document.addEventListener("visibilitychange", () => {
        if (!document.hidden)
            void refresh();
    });
})();
