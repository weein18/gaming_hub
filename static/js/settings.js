"use strict";
function togglePw() {
    const btn = document.getElementById('pwBtn');
    const fields = document.getElementById('pwFields');
    if (fields && btn) {
        const open = fields.classList.toggle('visible');
        btn.classList.toggle('open', open);
        if (!open) {
            ['old_password', 'new_password', 'confirm_password'].forEach(n => {
                const el = document.getElementsByName(n)[0];
                if (el)
                    el.value = '';
            });
        }
    }
}
;
function previewAvatar(event) {
    const target = event.target;
    if (!target.files || target.files.length === 0)
        return;
    const file = target.files[0];
    const url = URL.createObjectURL(file);
    const preview = document.getElementById('avatar-preview');
    const placeholder = document.getElementById('avatar-placeholder');
    if (preview) {
        preview.src = url;
        preview.style.display = 'block';
        preview.onload = () => URL.revokeObjectURL(url);
    }
    if (placeholder) {
        placeholder.style.display = "none";
    }
}
const openTgModal = async () => {
    const modal = document.getElementById("tgModal");
    if (modal) {
        modal.classList.add("open");
    }
    const res = await fetch("/generate-teleram-code");
    const data = await res.json();
    const botUrl = "https://t.me/elitehubcs2_bot?start=" + data.code;
    const tgCodeEl = document.getElementById("tgCode");
    if (tgCodeEl) {
        tgCodeEl.textContent = 'Tap "Open Elitehub Bot" to connect.';
    }
    const botButton = document.querySelector(".tg-open-btn");
    if (botButton) {
        botButton.href = botUrl;
    }
};
const closeTgModal = () => {
    const modal = document.getElementById("tgModal");
    if (modal) {
        modal.classList.remove("open");
    }
};
const copyCode = () => {
    const codeElement = document.getElementById('tgCode');
    const btn = document.querySelector(".tg-copy-btn");
    if (codeElement && codeElement.textContent && btn) {
        const code = codeElement.textContent;
        navigator.clipboard.writeText(code).then(() => {
            btn.textContent = 'Copied!';
            setTimeout(() => {
                btn.textContent = 'Copy';
            }, 2000);
        });
    }
};
const tgModal = document.getElementById("tgModal");
if (tgModal) {
    tgModal.addEventListener("click", (e) => {
        if (e.target === tgModal) {
            closeTgModal();
        }
    });
}
