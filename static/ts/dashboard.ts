document.addEventListener('DOMContentLoaded', function() {
    const animateCounter = (element: HTMLElement, target: number): void => {
        const duration = 2000;
        let current = 0;
        const increment = target / (duration / 16);

        const counter = () => {
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
        const targetArrt = el.dataset.target;
        if(targetArrt) {
            const target = parseInt(targetArrt);
            if (!isNaN(target)) {
                animateCounter(el, target);
            }
        }
    });
});
