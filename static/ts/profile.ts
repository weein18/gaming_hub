document.addEventListener('DOMContentLoaded', function() {
// ── Stat Counter Animation ──
const animateCounter = (element: HTMLElement, target: number): void => {
    const duration = 2000;
    let current = 0;
    const increment = target / (duration / 16);

    const counter = (): void => {
        current += increment;
        if (current >= target) {
            element.textContent = target.toLocaleString();
        } else {
            element.textContent = Math.floor(current).toLocaleString();
            requestAnimationFrame(counter);
        }
    };

    counter();
};

document.querySelectorAll<HTMLElement>('[data-target]').forEach(el => {
    const targetAttr = el.dataset.target;
    if(targetAttr) {
        const target = parseInt(targetAttr);
        if (!isNaN(target)) {
            animateCounter(el, target);
        }
    }
});

// ── Heatmap Generation ──
const grid = document.getElementById('heatmapGrid');
if (!grid) return;

const rawDates: string[] = (window as any).playerPredictionDates || [];

const counts: Record<string, number> = {};
rawDates.forEach(d => {
    counts[d] = (counts[d] || 0) + 1;
});

const today = new Date();
today.setHours(0, 0, 0, 0);
const totalDays = 26 * 7;
const startDate = new Date(today);
startDate.setDate(today.getDate() - totalDays + 1);

const countValues = Object.values(counts);
const maxCount = countValues.length > 0 ? Math.max(...countValues, 1) : 1;

for (let i = 0; i < totalDays; i++) {
    const d = new Date(startDate);
    d.setDate(startDate.getDate() + i);
    const key = d.toISOString().slice(0, 10);
    const c = counts[key] || 0;

    let v = 0;
    if (c > 0) v = Math.min(4, Math.ceil((c / maxCount) * 4));

    const cell = document.createElement('div');
    cell.className = 'hm-cell';
    cell.setAttribute('data-v', v.toString());

    const label = d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
    cell.title = c > 0 ? `${c} prediction${c > 1 ? 's' : ''} on ${label}` : `No predictions on ${label}`;

    grid.appendChild(cell);
}
});
