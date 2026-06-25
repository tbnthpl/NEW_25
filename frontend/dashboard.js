const apiBase = window.API_BASE || "";
const esc = window.escapeHtml || ((v) => String(v ?? ""));

const fmtInt = (n) => Number(n || 0).toLocaleString("en-IN");
const fmtMoney = (n) =>
  "₹" + Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 });

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const monthLabel = (mk) => {
  if (!mk || mk.length !== 6) return mk || "";
  const y = mk.slice(2, 4);
  const m = parseInt(mk.slice(4, 6), 10);
  return `${MONTHS[m - 1] || mk.slice(4, 6)} ${y}`;
};

const RECON_LABELS = {
  MATCHED: "Matched",
  AMOUNT_MISMATCH: "Amount mismatch",
  DATE_MISMATCH: "Date mismatch",
  MISSING_FINACLE: "Missing in Finacle",
  MISSING_VENDOR: "Missing in vendor MIS",
};

const setMsg = (text, isError = false) => {
  const el = document.querySelector("#dash-message");
  if (!el) return;
  el.textContent = text || "";
  el.style.display = text ? "block" : "none";
  el.style.color = isError ? "#b42318" : "#0f4c81";
};

const kpiCard = (label, value, sub, tone, icon, href) => {
  const inner = `
    <span class="dash-kpi-icon">${icon || "📌"}</span>
    <div class="dash-kpi-body">
      <span class="dash-kpi-value">${esc(value)}</span>
      <span class="dash-kpi-label">${esc(label)}</span>
      ${sub ? `<span class="dash-kpi-sub">${esc(sub)}</span>` : ""}
    </div>
    ${href ? `<span class="dash-kpi-arrow" aria-hidden="true">›</span>` : ""}`;
  const cls = `dash-kpi${tone ? ` dash-kpi-${tone}` : ""}${href ? " dash-kpi-link" : ""}`;
  return href
    ? `<a class="${cls}" href="${href}">${inner}</a>`
    : `<div class="${cls}">${inner}</div>`;
};

const renderKpis = (d) => {
  const el = document.querySelector("#dash-kpis");
  if (!el) return;
  const masters = d.masters || {};
  const approvals = d.approvals || {};

  el.innerHTML = [
    kpiCard("Pending approvals", fmtInt(approvals.pending), approvals.clarification ? `${fmtInt(approvals.clarification)} in clarification` : "", approvals.pending ? "warn" : "good", "📝", "approvals.html"),
    kpiCard("Active stores", fmtInt(masters.active_stores), "", null, "🏦", "active-stores.html"),
    kpiCard("Active vendors", fmtInt(masters.active_vendors), "", null, "👥", "active-vendors.html"),
  ].join("");
};

const renderActions = (d) => {
  const el = document.querySelector("#dash-actions");
  if (!el) return;
  const a = d.actions || {};
  const items = [];
  if (a.pending_approvals > 0) {
    items.push({ tone: "warn", text: `${fmtInt(a.pending_approvals)} approval request(s) waiting`, href: "approvals.html" });
  }
  if (a.unreconciled_dates_count > 0) {
    items.push({
      tone: "warn",
      text: `${fmtInt(a.unreconciled_dates_count)} Finacle date(s) this month not yet reconciled${a.unreconciled_dates && a.unreconciled_dates.length ? ` (${a.unreconciled_dates.slice(0, 5).join(", ")}${a.unreconciled_dates.length > 5 ? "…" : ""})` : ""}`,
      href: "reconciliation.html",
    });
  }
  if (a.vendors_no_mis_count > 0) {
    items.push({
      tone: "info",
      text: `${fmtInt(a.vendors_no_mis_count)} active vendor(s) with no MIS this month${a.vendors_no_mis && a.vendors_no_mis.length ? `: ${a.vendors_no_mis.slice(0, 5).join(", ")}${a.vendors_no_mis.length > 5 ? "…" : ""}` : ""}`,
      href: "vendor-upload.html",
    });
  }
  if (a.month_unlocked) {
    items.push({ tone: "info", text: `Current month (${monthLabel(d.month_key)}) is not locked yet`, href: null });
  }

  if (!items.length) {
    el.innerHTML = `<li class="dash-action dash-action-good">All clear - nothing needs attention right now.</li>`;
    return;
  }
  el.innerHTML = items
    .map((it) => {
      const inner = `<span class="dash-action-dot dash-dot-${it.tone}"></span><span>${esc(it.text)}</span>`;
      return it.href
        ? `<li class="dash-action"><a href="${esc(it.href)}">${inner}</a></li>`
        : `<li class="dash-action">${inner}</li>`;
    })
    .join("");
};

const renderReconBars = (d) => {
  const el = document.querySelector("#dash-recon-bars");
  if (!el) return;
  const recon = d.reconciliation || {};
  const breakdown = recon.breakdown || {};
  const total = recon.total || 0;
  if (!total) {
    el.innerHTML = `<p class="dash-empty">No reconciliation runs recorded this month yet.</p>`;
    return;
  }
  const order = ["MATCHED", "AMOUNT_MISMATCH", "DATE_MISMATCH", "MISSING_FINACLE", "MISSING_VENDOR"];
  el.innerHTML = order
    .filter((k) => breakdown[k])
    .map((k) => {
      const n = breakdown[k];
      const pct = total ? Math.round((n / total) * 100) : 0;
      const tone = k === "MATCHED" ? "good" : "bad";
      return `
        <div class="dash-bar-row">
          <span class="dash-bar-label">${esc(RECON_LABELS[k] || k)}</span>
          <span class="dash-bar-track"><span class="dash-bar-fill dash-bar-${tone}" style="width:${pct}%"></span></span>
          <span class="dash-bar-val">${fmtInt(n)} (${pct}%)</span>
        </div>`;
    })
    .join("");
};

const renderTrend = (d) => {
  const el = document.querySelector("#dash-trend");
  if (!el) return;
  const trend = d.charge_trend || [];
  const max = Math.max(1, ...trend.map((t) => Math.max(t.vendor_total || 0, t.customer_total || 0)));
  if (!trend.some((t) => (t.vendor_total || 0) + (t.customer_total || 0) > 0)) {
    el.innerHTML = `<p class="dash-empty">No charges computed in the last 6 months yet.</p>`;
    return;
  }
  el.innerHTML = trend
    .map((t) => {
      const vH = Math.round(((t.vendor_total || 0) / max) * 100);
      const cH = Math.round(((t.customer_total || 0) / max) * 100);
      return `
        <div class="dash-trend-col">
          <div class="dash-trend-bars">
            <span class="dash-trend-bar dash-dot-vendor" style="height:${vH}%" title="Vendor: ${esc(fmtMoney(t.vendor_total))}"></span>
            <span class="dash-trend-bar dash-dot-customer" style="height:${cH}%" title="Store: ${esc(fmtMoney(t.customer_total))}"></span>
          </div>
          <span class="dash-trend-label">${esc(monthLabel(t.month_key))}</span>
        </div>`;
    })
    .join("");
};

const STATUS_TONE = { PENDING: "warn", APPROVED: "good", REJECTED: "bad", CLARIFICATION: "info" };
const fmtDT = (s) => (s ? (window.formatDateTime || ((x) => x))(s) : "-");

const renderCommentHistory = (raw) => {
  let items = [];
  try {
    items = raw ? JSON.parse(raw) : [];
  } catch (_) {
    items = [];
  }
  if (!Array.isArray(items) || !items.length) {
    return '<p class="dash-empty">No comments yet.</p>';
  }
  const rows = items
    .map((e) => {
      const when = e.timestamp ? fmtDT(e.timestamp) : "-";
      return `<li class="dash-comment">
          <div class="dash-comment-head">
            <span class="dash-comment-role">${esc(e.role || "")} ${esc(e.user_id || "")}</span>
            <span class="dash-comment-time">${esc(when)}</span>
          </div>
          <div class="dash-comment-body">${esc(e.comment || "")}</div>
        </li>`;
    })
    .join("");
  return `<ul class="dash-comments">${rows}</ul>`;
};

const renderStatusResult = (r) => {
  const tone = STATUS_TONE[r.status] || "info";
  const rows = [
    ["Request ID", window.formatRequestRef ? window.formatRequestRef(r.approval_id) : r.approval_id],
    ["Type", window.formatEntityType ? window.formatEntityType(r.entity_type) : r.entity_type],
    ["Submitted by (Maker)", r.maker_id],
    ["Acted by (Checker)", r.checker_id || "-"],
    ["Submitted on", fmtDT(r.created_date)],
    ["Last action on", fmtDT(r.approved_date)],
  ]
    .map(([k, v]) => `<tr><td class="config-key">${esc(k)}</td><td>${esc(v)}</td></tr>`)
    .join("");
  return `
    <div class="dash-status-card">
      <span class="dash-status-badge dash-status-${tone}">${esc(r.status)}</span>
      <table class="config-modal-table">${rows}</table>
      <h3 class="dash-comments-title">Comments</h3>
      ${renderCommentHistory(r.comments_history)}
    </div>`;
};

const initStatusSearch = () => {
  const form = document.querySelector("#dash-status-form");
  const input = document.querySelector("#dash-status-input");
  const result = document.querySelector("#dash-status-result");
  if (!form || !input || !result) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const raw = (input.value || "").trim();
    if (!raw) {
      result.innerHTML = `<p class="dash-status-msg dash-status-bad-text">Enter a Request ID to check.</p>`;
      return;
    }
    const numericId = window.parseRequestRef ? window.parseRequestRef(raw) : Number(raw);
    const label = window.formatRequestRef ? window.formatRequestRef(numericId) : raw;
    if (numericId == null || !Number.isFinite(numericId) || numericId <= 0) {
      result.innerHTML = `<p class="dash-status-msg dash-status-bad-text">Enter a valid Request ID (e.g. ${window.REQUEST_REF_PREFIX || "DSBRID"}1000).</p>`;
      return;
    }
    result.innerHTML = `<p class="dash-status-msg">Looking up request ${esc(label)}…</p>`;
    try {
      const res = await fetch(`${apiBase}/api/approvals/${encodeURIComponent(numericId)}/status`, {
        headers: window.getAuthHeaders(),
      });
      if (res.status === 404) {
        result.innerHTML = `<p class="dash-status-msg dash-status-bad-text">No request found with ID ${esc(label)}.</p>`;
        return;
      }
      if (!res.ok) {
        result.innerHTML = `<p class="dash-status-msg dash-status-bad-text">Unable to look up that request (HTTP ${res.status}).</p>`;
        return;
      }
      const data = await res.json();
      result.innerHTML = renderStatusResult(data);
    } catch (err) {
      result.innerHTML = `<p class="dash-status-msg dash-status-bad-text">Unable to reach the server. Try again.</p>`;
    }
  });
};

const loadDashboard = async () => {
  try {
    const res = await fetch(`${apiBase}/api/dashboard/summary`, { headers: window.getAuthHeaders() });
    if (!res.ok) {
      setMsg("Unable to load dashboard metrics. The rest of the application is unaffected.", true);
      return;
    }
    const data = await res.json();
    setMsg("");
    const asOf = document.querySelector("#dash-asof");
    if (asOf && data.as_of) {
      asOf.textContent = `As of ${(window.formatDateTime || ((s) => s))(data.as_of)}`;
    }
    renderKpis(data);
  } catch (e) {
    setMsg("Unable to load dashboard metrics. The rest of the application is unaffected.", true);
  }
};

initStatusSearch();
loadDashboard();
