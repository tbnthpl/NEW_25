const apiBase = window.API_BASE || "";
const esc = window.escapeHtml || ((v) => String(v ?? ""));

let storeCache = [];

const fmtDate = (v) => {
  if (!v) return "-";
  const s = String(v);
  return s.length >= 10 ? s.slice(0, 10) : s;
};

const renderStores = (rows) => {
  const tbody = document.querySelector("#active-store-rows");
  const countEl = document.querySelector("#store-count");
  if (!tbody) return;
  if (countEl) countEl.textContent = rows.length ? `(${rows.length})` : "";
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty-state">No active stores.</td></tr>`;
    return;
  }
  tbody.innerHTML = rows
    .map((s) => {
      const customer = [s.customer_name, s.customer_id].filter(Boolean).join(" / ") || "-";
      return `
      <tr>
        <td>${esc(s.bank_store_code)}</td>
        <td>${esc(s.store_name ?? "")}</td>
        <td>${esc(customer)}</td>
        <td>${esc(s.pickup_type || "BEAT")}</td>
        <td>${esc(fmtDate(s.effective_from))}</td>
        <td><span class="status-pill status-active">${esc(s.status)}</span></td>
      </tr>`;
    })
    .join("");
};

const filterStores = () => {
  const q = (document.querySelector("#store-search")?.value || "").trim().toLowerCase();
  if (!q) return renderStores(storeCache);
  renderStores(
    storeCache.filter((s) =>
      [s.bank_store_code, s.store_name, s.customer_name, s.customer_id]
        .filter(Boolean)
        .some((f) => String(f).toLowerCase().includes(q)),
    ),
  );
};

const loadStores = async () => {
  const msg = document.querySelector("#store-message");
  try {
    const res = await fetch(`${apiBase}/api/bank-stores`, { headers: window.getAuthHeaders() });
    if (!res.ok) throw new Error();
    const data = await res.json();
    storeCache = (data || []).filter((s) => (s.status || "").toUpperCase() === "ACTIVE");
    renderStores(storeCache);
    if (msg) msg.textContent = "";
  } catch (_) {
    if (msg) {
      msg.textContent = "Unable to load stores.";
      msg.style.color = "#b42318";
    }
  }
};

document.querySelector("#store-search")?.addEventListener("input", filterStores);

loadStores();
