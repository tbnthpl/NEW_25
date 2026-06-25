const approvalRows = document.querySelector("#approval-rows");
const approvalMessage = document.querySelector("#approval-message");
const approvalSearchInput = document.querySelector("#approval-search");
const apiBase = window.API_BASE || "";
let vendorLookup = {};
let approvalsCache = [];
const escapeHtml = (value) => {
  if (value == null) return "";
  const div = document.createElement("div");
  div.textContent = String(value);
  return div.innerHTML;
};
const escapeValue = escapeHtml;

const formatEntityType = (value) =>
  window.formatEntityType ? window.formatEntityType(value) : value ?? "";

const formatRequestRef = (id) =>
  window.formatRequestRef ? window.formatRequestRef(id) : id ?? "";

const currentUser = () =>
  sessionStorage.getItem("currentUser")
    ? JSON.parse(sessionStorage.getItem("currentUser"))
    : { employeeId: "SYSTEM" };

const formatHistory = (raw) => {
  if (!raw) return "";
  try {
    const items = JSON.parse(raw);
    if (!Array.isArray(items)) return "";
    return items
      .map((entry) => {
        const when = entry.timestamp
          ? (window.formatDateTime || ((s) => s))(entry.timestamp)
          : "";
        const whenHtml = when ? ` <span class="history-time">(${escapeValue(when)})</span>` : "";
        return `${escapeValue(entry.role || "")} ${escapeValue(entry.user_id || "")}${whenHtml}: ${escapeValue(entry.comment || "")}`;
      })
      .join("<br/>");
  } catch (error) {
    return "";
  }
};

const parseProposedData = (raw) => {
  if (!raw) return {};
  try {
    return JSON.parse(raw);
  } catch (error) {
    return {};
  }
};

const SKIP_FIELDS = ["maker_id", "status", "reason"];

const RECON_STATUS_LABELS = {
  AMOUNT_MISMATCH: "Amount Mismatch",
  MISSING_VENDOR: "Missing Vendor",
  MISSING_FINACLE: "Missing Finacle",
  MATCHED: "Matched",
  DATE_MISMATCH: "Date Mismatch",
};

const formatReconStatus = (code) => RECON_STATUS_LABELS[code] || code || "";

const formatMakerEntered = (entityType, proposed, vendorLookup, original = {}) => {
  if (!proposed || typeof proposed !== "object") return "<em>No data</em>";
  const p = proposed;

  const label = (key) =>
    key
      .replace(/_/g, " ")
      .replace(/\b\w/g, (c) => c.toUpperCase());

  const row = (k, v) => {
    if (v === null || v === undefined) return "";
    const s = String(v);
    if (s === "") return "";
    return `<div class="maker-row"><span class="maker-label">${escapeHtml(label(k))}:</span> <span class="maker-value">${escapeHtml(s)}</span></div>`;
  };

  const formatHeaderMapping = (jsonStr) => {
    if (!jsonStr) return "";
    try {
      const obj = typeof jsonStr === "string" ? JSON.parse(jsonStr) : jsonStr;
      if (typeof obj !== "object") return escapeHtml(String(jsonStr));
      return Object.entries(obj)
        .map(([k, v]) => row(k, v))
        .join("");
    } catch {
      return row("Header Mapping", jsonStr);
    }
  };

  const vendorName = (id) => {
    if (!id) return "";
    const v = vendorLookup[String(id)];
    return v ? `${v.name || v.code || id}` : id;
  };

  const entityConfig = {
    VENDOR_MASTER: () => {
      if (p.action === "DEACTIVATE")
        return [row("Action", "Deactivate Vendor"), row("Vendor ID", p.vendor_id)].join("");
      return [row("Vendor Name", p.vendor_name), row("Vendor Code", p.vendor_code), row("Effective From", p.effective_from)].join("");
    },
    BANK_STORE_MASTER: () => {
      if (p.action === "DEACTIVATE")
        return [row("Action", "Deactivate Store"), row("Store ID", p.store_id)].join("");
      const isCall = (p.pickup_type || "BEAT") === "CALL";
      const pricing = isCall
        ? [
            row("CALL - included pickups / month", p.call_included_pickups),
            row("CALL - monthly bank package (₹)", p.call_monthly_bank_charge),
            row("CALL - bank per extra pickup (₹)", p.call_additional_bank_per_pickup),
            row("CALL - vendor pay per pickup (₹)", p.call_vendor_pay_per_pickup),
          ]
        : [
            row("Daily Pickup Limit", p.daily_pickup_limit),
            row("Monthly Bank Charge (Beat)", p.fixed_charge),
            row("Monthly Vendor Charge (Beat)", p.vendor_charge),
          ];
      const head =
        p.action === "UPDATE" ? [row("Action", "Update Store"), row("Store ID", p.store_id)] : [];
      return [
        ...head,
        row("Bank Store Code", p.bank_store_code),
        row("Store Name", p.store_name),
        row("Pickup Type", p.pickup_type || "BEAT"),
        row("Customer ID", p.customer_id),
        row("Customer Name", p.customer_name),
        row("Account No", p.account_no),
        row("SOL ID", p.sol_id),
        ...pricing,
        row("Waiver %", p.waiver_percentage),
        row("Waiver cap (₹)", p.waiver_cap_amount),
        row("Waiver cap from", p.waiver_cap_from),
        row("Waiver cap to", p.waiver_cap_to),
        row("Effective From", p.effective_from),
      ].join("");
    },
    STORE_MAPPING: () => {
      if (p.action === "DEACTIVATE") return row("Action", "Deactivate");
      return [
        row("Vendor", vendorName(p.vendor_id) || p.vendor_id),
        row("Vendor Store Code", p.vendor_store_code),
        row("Bank Store Code", p.bank_store_code),
        row("Customer ID", p.customer_id),
        row("Customer Name", p.customer_name),
        row("Account No", p.account_no),
        row("Effective From", p.effective_from),
      ].join("");
    },
    VENDOR_FILE_FORMAT: () =>
      [
        row("Vendor", vendorName(p.vendor_id) || p.vendor_id),
        row("Format Name", p.format_name),
        formatHeaderMapping(p.header_mapping_json),
        row("Effective From", p.effective_from),
      ].join(""),
    CHARGE_CONFIG: () =>
      [
        row("Config Code", p.config_code),
        row("Config Name", p.config_name),
        row("Value Number", p.value_number),
        row("Value Text", p.value_text),
        row("Effective From", p.effective_from),
      ].join(""),
    VENDOR_CHARGE: () =>
      [
        row("Vendor", vendorName(p.vendor_id) || p.vendor_id),
        row("Pickup Type", p.pickup_type),
        row("Base Charge", p.base_charge),
        row("Effective From", p.effective_from),
      ].join(""),
    WAIVER: () =>
      [
        row("Customer ID", p.customer_id),
        row("Waiver Type", p.waiver_type),
        row("Waiver Percentage", p.waiver_percentage),
        row("Waiver Cap Amount", p.waiver_cap_amount),
        row("Waiver From", p.waiver_from),
        row("Waiver To", p.waiver_to),
      ].join(""),
    PICKUP_RULE: () =>
      [
        row("Pickup Type", p.pickup_type),
        row("Free Limit", p.free_limit),
        row("Effective From", p.effective_from),
      ].join(""),
    CUSTOMER_CHARGE_SLAB: () => {
      const parts = [];
      if (p.action === "EDIT") {
        parts.push(row("Action", "Edit"));
        parts.push(row("Slab ID", p.slab_id));
      }
      return [
        ...parts,
        row("Store ID", p.store_id),
        row("Amount From", p.amount_from),
        row("Amount To", p.amount_to),
        row("Charge Amount", p.charge_amount),
        row("Slab Label", p.slab_label),
        row("Effective From", p.effective_from),
      ].join("");
    },
    VENDOR_BEAT_SLAB: () => {
      const parts = [];
      if (p.action === "EDIT") {
        parts.push(row("Action", "Edit"));
        parts.push(row("Slab ID", p.slab_id));
      }
      return [
        ...parts,
        row("Vendor", vendorName(p.vendor_id, p.vendor_name)),
        row("Amount From", p.amount_from),
        row("Amount To", p.amount_to),
        row("Charge Amount", p.charge_amount),
        row("Slab Label", p.slab_label),
        row("Effective From", p.effective_from),
      ].join("");
    },
    REMITTANCE: () =>
      [
        row("Remittance ID", p.remittance_id),
        row("Action", p.action),
        row("Rejection Reason", p.rejection_reason),
      ].join(""),
    EXCEPTION_RESOLUTION: () =>
      [
        row("Exception ID", p.exception_id),
        row("Proposed Status", p.proposed_status),
        row("Remarks", p.remarks),
      ].join(""),
    RECONCILIATION_CORRECTION: () => {
      const actionLabels = {
        AMOUNT_EDIT: "Amount Edit",
        FIELD_EDIT: "Edit Reconciliation Row",
      };
      let d = p.details;
      if (typeof d === "string") {
        try {
          d = JSON.parse(d);
        } catch (_) {
          d = null;
        }
      }
      let detailsHtml = row("Details", p.details);
      if (d && typeof d === "object") {
        if (p.requested_action === "AMOUNT_EDIT") {
          const reconStatus = d.current_status || original.status;
          detailsHtml = [
            row("Reconciliation Status", formatReconStatus(reconStatus)),
            row("Vendor Amount", d.vendor_amount),
            row("Finacle Amount", d.finacle_amount),
          ].join("");
        } else if (p.requested_action === "FIELD_EDIT") {
          const reconStatus = d.current_status || original.status;
          detailsHtml = [
            row("Reconciliation Status", formatReconStatus(reconStatus)),
            row("Bank Store Code", d.bank_store_code),
            row("Vendor Name", d.vendor_name),
            row("Vendor Pickup Date", d.pickup_date),
            row("Vendor Amount", d.vendor_amount),
            row("Finacle Date", d.remittance_date),
            row("Finacle Amount", d.finacle_amount),
          ].join("");
        } else {
          detailsHtml = Object.entries(d)
            .map(([k, v]) => row(k, v))
            .join("");
        }
      }
      return [
        row("Requested Action", actionLabels[p.requested_action] || p.requested_action),
        detailsHtml,
      ].join("");
    },
  };

  const fn = entityConfig[entityType];
  if (fn) {
    const html = fn();
    if (html) return `<div class="maker-entered">${html}</div>`;
  }

  const fallback = Object.entries(p)
    .filter(([k]) => !SKIP_FIELDS.includes(k))
    .map(([k, v]) => row(k, v))
    .join("");
  return fallback ? `<div class="maker-entered">${fallback}</div>` : "<em>No data</em>";
};

const labelKey = (key) =>
  key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());

// Render any value (including nested JSON strings / objects / arrays) as HTML.
const renderDetailValue = (key, value) => {
  if (value === null || value === undefined) return "<em>-</em>";
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (
      (trimmed.startsWith("{") && trimmed.endsWith("}")) ||
      (trimmed.startsWith("[") && trimmed.endsWith("]"))
    ) {
      try {
        return renderNestedDetail(JSON.parse(trimmed));
      } catch (_) {
        /* fall through to plain string */
      }
    }
    if (trimmed === "") return "<em>-</em>";
  }
  if (value && typeof value === "object") {
    return renderNestedDetail(value);
  }
  let display = String(value);
  if (key === "vendor_id" && vendorLookup[String(value)]) {
    const v = vendorLookup[String(value)];
    display = `${value} (${v.name || v.code || value})`;
  }
  return escapeHtml(display);
};

const renderNestedDetail = (val) => {
  if (Array.isArray(val)) {
    if (!val.length) return "<em>-</em>";
    return val
      .map((item) =>
        item && typeof item === "object" ? detailsTable(item) : escapeHtml(String(item))
      )
      .join("<br/>");
  }
  if (val && typeof val === "object") return detailsTable(val);
  return escapeHtml(String(val));
};

const detailsTable = (obj) => {
  if (!obj || typeof obj !== "object") return "<p>No data</p>";
  const entries = Object.entries(obj);
  if (!entries.length) return '<p class="config-empty">No fields.</p>';
  const rows = entries
    .map(
      ([k, v]) =>
        `<tr><td class="config-key">${escapeHtml(labelKey(k))}</td><td>${renderDetailValue(k, v)}</td></tr>`
    )
    .join("");
  return `<table class="config-modal-table">${rows}</table>`;
};

const renderApprovalDetails = (item) => {
  const proposed = parseProposedData(item.proposed_data);
  let original = {};
  try {
    original = item.original_data ? JSON.parse(item.original_data) : {};
  } catch (_) {
    original = {};
  }
  const hasOriginal = original && typeof original === "object" && Object.keys(original).length > 0;

  const meta = `
    <table class="config-modal-table">
      <tr><td class="config-key">Request ID</td><td>${escapeHtml(formatRequestRef(item.approval_id))}</td></tr>
      <tr><td class="config-key">Type</td><td>${escapeHtml(formatEntityType(item.entity_type))}</td></tr>
      <tr><td class="config-key">Maker</td><td>${escapeHtml(item.maker_id)}</td></tr>
      <tr><td class="config-key">Status</td><td>${escapeHtml(item.status)}</td></tr>
      <tr><td class="config-key">Submitted</td><td>${escapeHtml(item.created_date ? (window.formatDateTime || ((s) => s))(item.created_date) : "")}</td></tr>
      <tr><td class="config-key">Maker Comment</td><td>${escapeHtml(item.reason ?? "")}</td></tr>
    </table>`;

  const history = formatHistory(item.comments_history);
  const makerEntered = formatMakerEntered(item.entity_type, proposed, vendorLookup, original);

  return `
    <div class="config-modal-section">${meta}</div>
    <div class="config-modal-section">
      <h3 class="config-modal-subtitle">Maker Entered</h3>
      ${makerEntered}
    </div>
    ${
      hasOriginal
        ? `<div class="config-modal-section">
             <h3 class="config-modal-subtitle">Previous values</h3>
             ${detailsTable(original)}
           </div>`
        : ""
    }
    ${
      history
        ? `<div class="config-modal-section">
             <h3 class="config-modal-subtitle">History</h3>
             <div>${history}</div>
           </div>`
        : ""
    }
  `;
};

const showApprovalDetails = (item) => {
  const modal = document.getElementById("approval-details-modal");
  const body = document.getElementById("approval-details-body");
  const title = document.getElementById("approval-details-title");
  if (!modal || !body) return;
  if (title) title.textContent = `Request ${formatRequestRef(item.approval_id)} - ${formatEntityType(item.entity_type)}`;
  body.innerHTML = renderApprovalDetails(item);
  modal.hidden = false;
  modal.classList.add("approval-modal-visible");
};

const hideApprovalDetails = () => {
  const modal = document.getElementById("approval-details-modal");
  if (!modal) return;
  modal.hidden = true;
  modal.classList.remove("approval-modal-visible");
};

const loadVendorsForApprovals = async () => {
  try {
    const response = await fetch(`${apiBase}/api/vendors?include_inactive=1`, {
      headers: window.getAuthHeaders(),
    });
    if (!response.ok) {
      throw new Error("Failed to load vendors");
    }
    const vendors = await response.json();
    vendorLookup = {};
    vendors.forEach((vendor) => {
      vendorLookup[String(vendor.vendor_id)] = vendor;
    });
  } catch (error) {
    vendorLookup = {};
  }
};

const resolveEndpoint = async (entityType, approvalId, action) => {
  const base = action === "APPROVE" ? "approve" : "reject";
  const directMap = {
    VENDOR_MASTER: `${apiBase}/api/vendors/requests/${approvalId}/${base}`,
    BANK_STORE_MASTER: `${apiBase}/api/bank-stores/requests/${approvalId}/${base}`,
    CHARGE_CONFIG: `${apiBase}/api/charge-configs/requests/${approvalId}/${base}`,
    VENDOR_CHARGE: `${apiBase}/api/vendor-charges/requests/${approvalId}/${base}`,
    WAIVER: `${apiBase}/api/waivers/requests/${approvalId}/${base}`,
    VENDOR_FILE_FORMAT: `${apiBase}/api/vendor-file-formats/requests/${approvalId}/${base}`,
    STORE_MAPPING: `${apiBase}/api/store-mappings/requests/${approvalId}/${base}`,
    PICKUP_RULE: `${apiBase}/api/pickup-rules/requests/${approvalId}/${base}`,
    CUSTOMER_CHARGE_SLAB: `${apiBase}/api/customer-charge-slabs/requests/${approvalId}/${base}`,
    VENDOR_BEAT_SLAB: `${apiBase}/api/vendor-beat-slabs/requests/${approvalId}/${base}`,
    REMITTANCE: `${apiBase}/api/remittances/requests/${approvalId}/${base}`,
    EXCEPTION_RESOLUTION: `${apiBase}/api/exceptions/requests/${approvalId}/${base}`,
  };

  if (entityType === "RECONCILIATION_CORRECTION") {
    return `${apiBase}/api/reconciliation/corrections/requests/${approvalId}/${base}`;
  }

  if (!directMap[entityType]) {
    throw new Error("Unsupported approval type");
  }

  return directMap[entityType];
};

const getFilteredApprovals = () => {
  const q = (approvalSearchInput?.value || "").trim().toLowerCase();
  if (!q) return approvalsCache;
  return approvalsCache.filter(
    (item) =>
      String(item.approval_id || "").toLowerCase().includes(q) ||
      formatRequestRef(item.approval_id).toLowerCase().includes(q),
  );
};

const currentRole = () => {
  const cached = sessionStorage.getItem("currentUser");
  return cached ? (JSON.parse(cached).role || "").toUpperCase() : "";
};

const renderApprovalRows = (approvals) => {
  approvalRows.innerHTML = "";
  if (!approvals.length) {
    const q = (approvalSearchInput?.value || "").trim();
    approvalMessage.textContent = q
      ? `No requests match Request ID "${q}".`
      : "No pending approvals.";
    approvalMessage.style.color = q ? "#5a6b86" : "#0f4c81";
    return;
  }

  const isMaker = currentRole() === "MAKER";

  approvals.forEach((item) => {
      const tr = document.createElement("tr");
      const history = formatHistory(item.comments_history);
      const proposed = parseProposedData(item.proposed_data);
      let original = {};
      try {
        original = item.original_data ? JSON.parse(item.original_data) : {};
      } catch (_) {
        original = {};
      }
      const makerEnteredHtml = formatMakerEntered(item.entity_type, proposed, vendorLookup, original);
      const viewBtn = `<button type="button" class="secondary-btn btn-view" data-view-details>View</button>`;
      const actionCell = isMaker
        ? `<td class="button-row">${viewBtn}</td>`
        : `<td class="button-row">
          ${viewBtn}
          <button class="secondary-btn btn-approve" data-action="APPROVE">Approve</button>
          <button class="secondary-btn btn-reject" data-action="REJECT">Reject</button>
          <button class="secondary-btn btn-clarify" data-action="CLARIFY">Clarify</button>
        </td>`;
      tr.innerHTML = `
        <td>${escapeValue(formatRequestRef(item.approval_id))}</td>
        <td>${escapeValue(formatEntityType(item.entity_type))}</td>
        <td>${escapeValue(item.maker_id)}</td>
        <td class="maker-entered-cell">${makerEnteredHtml}</td>
        <td>${escapeValue(item.reason ?? "")}</td>
        <td><span class="status pending">${escapeValue(item.status)}</span></td>
        <td>${escapeValue(item.created_date ? (window.formatDateTime || (s => s))(item.created_date) : "")}</td>
        <td>${history}</td>
        ${actionCell}
      `;

      // Full-width comment row directly below this request so the checker can
      // read the whole comment while typing.
      const commentTr = document.createElement("tr");
      commentTr.className = "approval-comment-row";
      commentTr.innerHTML = `
        <td colspan="9">
          <label class="approval-comment-label">Comment:</label>
          <textarea class="approval-comment" rows="2" placeholder="Type your comment for this request..."></textarea>
        </td>
      `;
      const viewBtnEl = tr.querySelector("[data-view-details]");
      if (viewBtnEl) {
        viewBtnEl.addEventListener("click", () => showApprovalDetails(item));
      }

      // Makers get a read-only view: no comment box, no approve/reject/clarify.
      if (isMaker) {
        approvalRows.appendChild(tr);
        return;
      }

      const commentInput = commentTr.querySelector(".approval-comment");

      tr.querySelectorAll("[data-action]").forEach((button) => {
        button.addEventListener("click", async () => {
          const comment = commentInput.value.trim();
          if (!comment) {
            approvalMessage.textContent = "Comment required.";
            approvalMessage.style.color = "#b42318";
            return;
          }
          try {
            const action = button.dataset.action;
            const endpoint =
              action === "CLARIFY"
                ? `${apiBase}/api/approvals/${item.approval_id}/clarify`
                : await resolveEndpoint(item.entity_type, item.approval_id, action);
            const response = await fetch(endpoint, {
              method: "POST",
              headers: { "Content-Type": "application/json", ...window.getAuthHeaders() },
              body: JSON.stringify({
                checker_id: currentUser().employeeId,
                comment,
              }),
            });
            if (!response.ok) {
              throw new Error("Approval failed");
            }
            approvalMessage.textContent = "Action submitted.";
            approvalMessage.style.color = "#0f4c81";
            loadApprovals();
          } catch (error) {
            approvalMessage.textContent = "Unable to submit action.";
            approvalMessage.style.color = "#b42318";
          }
        });
      });
      approvalRows.appendChild(tr);
      approvalRows.appendChild(commentTr);
    });

  approvalMessage.textContent = "";
};

const loadApprovals = async () => {
  approvalRows.innerHTML = "";
  approvalMessage.textContent = "Loading approvals...";
  approvalMessage.style.color = "#0f4c81";

  let response;
  try {
    response = await fetch(`${apiBase}/api/approvals/pending`, {
      headers: (window.getAuthHeaders && window.getAuthHeaders()) || {},
      credentials: "same-origin",
    });
  } catch (error) {
    console.error("approvals fetch failed", error);
    approvalsCache = [];
    approvalMessage.textContent = "Unable to reach the server. Check your network and try again.";
    approvalMessage.style.color = "#b42318";
    return;
  }

  if (response.status === 403) {
    approvalsCache = [];
    approvalMessage.textContent =
      "You do not have access to view this queue.";
    approvalMessage.style.color = "#5a6b86";
    return;
  }
  if (response.status === 401) {
    approvalsCache = [];
    approvalMessage.textContent = "Session expired. Please sign in again.";
    approvalMessage.style.color = "#b42318";
    return;
  }
  if (!response.ok) {
    let detail = "";
    try {
      const err = await response.json();
      detail = err?.detail || "";
    } catch (_) {
      detail = "";
    }
    approvalsCache = [];
    approvalMessage.textContent = `Unable to load approvals (HTTP ${response.status})${detail ? `: ${detail}` : ""}.`;
    approvalMessage.style.color = "#b42318";
    return;
  }

  let data;
  try {
    data = await response.json();
  } catch (error) {
    console.error("approvals JSON parse failed", error);
    approvalsCache = [];
    approvalMessage.textContent = "Server returned an unexpected response. Please retry.";
    approvalMessage.style.color = "#b42318";
    return;
  }
  approvalsCache = Array.isArray(data) ? data : [];

  try {
    renderApprovalRows(getFilteredApprovals());
  } catch (error) {
    console.error("approvals render failed", error);
    approvalMessage.textContent =
      "Approvals loaded but could not be displayed. One of the requests has data we cannot render - check the browser console for details.";
    approvalMessage.style.color = "#b42318";
  }
};

const init = async () => {
  await loadVendorsForApprovals();
  loadApprovals();

  approvalSearchInput?.addEventListener("input", () => {
    renderApprovalRows(getFilteredApprovals());
  });

  const modal = document.getElementById("approval-details-modal");
  if (modal) {
    modal.querySelector(".approval-modal-backdrop")?.addEventListener("click", hideApprovalDetails);
    modal.querySelector(".approval-modal-close")?.addEventListener("click", hideApprovalDetails);
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && modal.classList.contains("approval-modal-visible")) {
        hideApprovalDetails();
      }
    });
  }
};

init();
