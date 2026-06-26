/* ═══════════════════════════════════════════════════════
   DeployAIX — app.js
   Global utilities: HMC selector, sidebar toggle, toast
   ═══════════════════════════════════════════════════════ */

window.activeHMCId = null;

// ── Sidebar toggle (mobile) ──────────────────────────────
document.getElementById("sidebar-toggle")?.addEventListener("click", () => {
  document.getElementById("sidebar").classList.toggle("open");
});

// ── HMC Selector ────────────────────────────────────────
const hmcSel = document.getElementById("hmc-selector");
const statusDot = document.getElementById("hmc-status-dot");
const statusLabel = document.getElementById("hmc-status-label");

async function refreshHMCSelector(hmcs) {
  if (!hmcs) {
    hmcs = await fetch("/api/hmcs").then(r => r.json()).catch(() => []);
  }
  hmcSel.innerHTML = '<option value="">— No HMC —</option>' +
    hmcs.map(h => `<option value="${h.id}">${h.name} (${h.host})</option>`).join("");

  // Restore previously selected
  const saved = sessionStorage.getItem("activeHMCId");
  if (saved && hmcs.find(h => h.id === saved)) {
    hmcSel.value = saved;
    window.activeHMCId = saved;
    updateStatusIndicator(hmcs.find(h => h.id === saved));
  }
}

hmcSel.addEventListener("change", () => {
  const id = hmcSel.value;
  window.activeHMCId = id || null;
  sessionStorage.setItem("activeHMCId", id || "");
  fetch("/api/hmcs").then(r => r.json()).then(hmcs => {
    const hmc = hmcs.find(h => h.id === id);
    updateStatusIndicator(hmc);
  });
  document.dispatchEvent(new CustomEvent("hmc-changed", { detail: { id } }));
});

function updateStatusIndicator(hmc) {
  if (hmc) {
    statusDot.className = "status-dot connected";
    statusLabel.textContent = hmc.name;
  } else {
    statusDot.className = "status-dot";
    statusLabel.textContent = "No HMC connected";
  }
}

// ── Toast ────────────────────────────────────────────────
(function () {
  const container = document.createElement("div");
  container.id = "toast-container";
  document.body.appendChild(container);
})();

function showToast(msg, type = "") {
  const el = document.createElement("div");
  el.className = "toast" + (type ? " " + type : "");
  el.textContent = msg;
  document.getElementById("toast-container").appendChild(el);
  setTimeout(() => el.remove(), 3500);
}

// ── Initial load ─────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  refreshHMCSelector();
});
