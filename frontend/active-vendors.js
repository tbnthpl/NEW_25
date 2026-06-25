const apiBase = window.API_BASE || "";
const esc = window.escapeHtml || ((v) => String(v ?? ""));

let vendorCache = [];

const renderVendors = (rows) => {
  const tbody = document.querySelector("#active-vendor-rows");
  const countEl = document.querySelector("#vendor-count");
  if (!tbody) return;
  if (countEl) countEl.textContent = rows.length ? `(${rows.length})` : "";
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="3" class="empty-state">No active vendors.</td></tr>`;
    return;
  }
  tbody.innerHTML = rows
    .map(
      (v) => `
      <tr>
        <td>${esc(v.name)}</td>
        <td>${esc(v.code)}</td>
        <td><span class="status-pill status-active">${esc(v.status)}</span></td>
      </tr>`,
    )
    .join("");
};

const filterVendors = () => {
  const q = (document.querySelector("#vendor-search")?.value || "").trim().toLowerCase();
  if (!q) return renderVendors(vendorCache);
  renderVendors(
    vendorCache.filter(
      (v) =>
        (v.name || "").toLowerCase().includes(q) || (v.code || "").toLowerCase().includes(q),
    ),
  );
};

const loadVendors = async () => {
  const msg = document.querySelector("#vendor-message");
  try {
    const res = await fetch(`${apiBase}/api/vendors`, { headers: window.getAuthHeaders() });
    if (!res.ok) throw new Error();
    const data = await res.json();
    vendorCache = (data || []).filter((v) => (v.status || "").toUpperCase() === "ACTIVE");
    renderVendors(vendorCache);
    if (msg) msg.textContent = "";
  } catch (_) {
    if (msg) {
      msg.textContent = "Unable to load vendors.";
      msg.style.color = "#b42318";
    }
  }
};

document.querySelector("#vendor-search")?.addEventListener("input", filterVendors);

loadVendors();
