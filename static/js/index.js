"use strict";
document.addEventListener('DOMContentLoaded', function () {
    const animateCounter = (element, target) => {
        const duration = 2000;
        let current = 0;
        const increment = target / (duration / 16);
        const startTime = performance.now();
        const counter = () => {
            current += increment;
            if (current >= target) {
                element.textContent = target.toLocaleString();
            }
            else {
                element.textContent = Math.floor(current).toLocaleString();
                requestAnimationFrame(counter);
            }
        };
        counter();
    };
    document.querySelectorAll('[data-target]').forEach(el => {
        const targetAttr = el.dataset.target;
        if (targetAttr) {
            const target = parseInt(targetAttr);
            if (!isNaN(target)) {
                animateCounter(el, target);
            }
        }
    });
    // for scroll animations
    const observerOptions = {
        threshold: 0.1,
        rootMargin: '0px 0px -100px 0px'
    };
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.style.animationPlayState = 'running';
            }
        });
    }, observerOptions);
    document.querySelectorAll('.section-gap, .matches-section').forEach(section => {
        observer.observe(section);
    });
});
