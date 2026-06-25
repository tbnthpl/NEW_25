const API_BASE = window.API_BASE || "";

const ENTITY_TYPE_LABELS = {
  VENDOR_MASTER: "Vendor Onboarding",
  BANK_STORE_MASTER: "Store Onboarding",
  STORE_MAPPING: "Store Mapping",
  CHARGE_CONFIG: "Charge Configuration",
  VENDOR_FILE_FORMAT: "Vendor File Format",
  VENDOR_BEAT_SLAB: "Vendor Beat Slab",
  CUSTOMER_CHARGE_SLAB: "Customer Charge Slab",
  PICKUP_RULE: "Pickup Rule",
  RECONCILIATION_CORRECTION: "Reconciliation Correction",
  WAIVER: "Waiver",
};

window.formatEntityType = (value) => {
  if (value == null || value === "") return "";
  const key = String(value).toUpperCase();
  if (ENTITY_TYPE_LABELS[key]) return ENTITY_TYPE_LABELS[key];
  return key
    .toLowerCase()
    .split("_")
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
};

window.REQUEST_REF_PREFIX = "DSBRID";
window.REQUEST_REF_BASE = 999;

window.formatRequestRef = (id) => {
  if (id == null || id === "") return "";
  const n = Number(id);
  if (!Number.isFinite(n)) return String(id);
  return window.REQUEST_REF_PREFIX + (n + window.REQUEST_REF_BASE);
};

window.parseRequestRef = (input) => {
  if (input == null) return null;
  const s = String(input).trim().toUpperCase().replace(/\s+/g, "");
  if (!s) return null;
  const digits = s.replace(/[^0-9]/g, "");
  if (!digits) return null;
  const n = parseInt(digits, 10);
  if (!Number.isFinite(n)) return null;
  if (s.includes(window.REQUEST_REF_PREFIX) || n > window.REQUEST_REF_BASE) {
    return n - window.REQUEST_REF_BASE;
  }
  return n;
};

const parseBackendInstant = (value) => {
  if (value == null || value === "") return null;
  const s = String(value).trim();
  if (!s) return null;
  let toParse = s;
  if (!s.endsWith("Z") && !/[-+]\d{2}:?\d{2}$/.test(s)) {
    toParse = s + "Z";
  }
  const d = new Date(toParse);
  if (Number.isNaN(d.getTime())) return null;
  return d;
};

window.formatDateTime = (isoString) => {
  const d = parseBackendInstant(isoString);
  if (!d) return typeof isoString === "string" ? isoString : "";
  return d.toLocaleString("en-IN", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
};

window.formatDate = (isoString) => {
  const d = parseBackendInstant(isoString);
  if (!d) return typeof isoString === "string" ? isoString : "";
  return d.toLocaleDateString("en-IN", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
};

const roleConfig = {
  MAKER: [
    "dashboard",
    "uploads",
    "finacle-upload",
    "vendor-upload",
    "mapping",
    "vendor-onboarding",
    "store-onboarding",
    "reconciliation",
    "reconciliation-results",
    "charges",
    "approvals",
  ],
  CHECKER: [
    "dashboard",
    "approvals",
    "reconciliation",
    "reconciliation-results",
    "charges",
    "store-onboarding",
    "vendor-onboarding",
    "finacle-upload",
    "vendor-upload",
  ],
  ADMIN: [
    "dashboard",
    "uploads",
    "finacle-upload",
    "vendor-upload",
    "mapping",
    "vendor-onboarding",
    "store-onboarding",
    "reconciliation",
    "reconciliation-results",
    "approvals",
    "masters",
    "charges",
    "reports",
    "application-log",
    "admin-tools",
  ],
  AUDITOR: ["dashboard", "reports", "application-log", "reconciliation", "reconciliation-results", "charges"],
};

window.getAuthHeaders = () => {
  const token = sessionStorage.getItem("authToken");
  return token ? { Authorization: `Bearer ${token}` } : {};
};

window.escapeHtml = (value) => {
  if (value == null) return "";
  const div = document.createElement("div");
  div.textContent = String(value);
  return div.innerHTML;
};

// Entity types whose draft row is kept in sync when a maker edits a
// clarification request, so the approved record reflects the edits.
window.CLARIFICATION_EDITABLE_TYPES = new Set([
  "VENDOR_MASTER",
  "BANK_STORE_MASTER",
  "STORE_MAPPING",
]);

const CLARIF_HIDDEN_KEYS = new Set(["maker_id", "status", "reason", "action"]);
const CLARIF_READONLY_KEYS = new Set([
  "vendor_id",
  "store_id",
  "slab_id",
  "mapping_id",
  "config_id",
  "exception_id",
  "remittance_id",
]);

const clarifLabel = (key) =>
  String(key)
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());

const clarifParseProposed = (raw) => {
  if (!raw) return {};
  if (typeof raw === "object") return raw;
  try {
    const obj = JSON.parse(raw);
    return obj && typeof obj === "object" ? obj : {};
  } catch (_) {
    return {};
  }
};

const isDateLike = (val) =>
  typeof val === "string" && /^\d{4}-\d{2}-\d{2}/.test(val.trim());

/**
 * Open a modal that lets the request's maker edit the submitted fields and
 * resubmit a clarification request back to the checker.
 * @param {object} item - clarification item (must include approval_id, proposed_data)
 * @param {function} onDone - called after a successful resubmit
 */
window.clarificationEditAndResubmit = (item, onDone) => {
  const proposed = clarifParseProposed(item.proposed_data);
  const typeLabel = window.formatEntityType
    ? window.formatEntityType(item.entity_type)
    : item.entity_type || "";

  const overlay = document.createElement("div");
  overlay.className = "clarif-edit-overlay";

  const fieldsHtml = Object.entries(proposed)
    .filter(([k]) => !CLARIF_HIDDEN_KEYS.has(k))
    .map(([k, v]) => {
      const readonly = CLARIF_READONLY_KEYS.has(k);
      const isObj = v && typeof v === "object";
      const looksJson =
        typeof v === "string" &&
        (v.trim().startsWith("{") || v.trim().startsWith("["));
      if (isObj || looksJson) {
        const text = isObj ? JSON.stringify(v, null, 2) : v;
        return `<label class="clarif-field">
            <span>${window.escapeHtml(clarifLabel(k))}</span>
            <textarea data-field-key="${window.escapeHtml(k)}" data-json="1" rows="4" ${
          readonly ? "readonly" : ""
        }>${window.escapeHtml(text)}</textarea>
          </label>`;
      }
      const type = isDateLike(v) ? "date" : "text";
      const val = v == null ? "" : String(v);
      return `<label class="clarif-field">
          <span>${window.escapeHtml(clarifLabel(k))}</span>
          <input type="${type}" data-field-key="${window.escapeHtml(k)}" value="${window.escapeHtml(
        val,
      )}" ${readonly ? "disabled" : ""} />
        </label>`;
    })
    .join("");

  overlay.innerHTML = `
    <div class="clarif-edit-card" role="dialog" aria-modal="true">
      <div class="clarif-edit-head">
        <h2>Edit &amp; Resubmit - Request #${window.escapeHtml(item.approval_id)}</h2>
        <button type="button" class="clarif-edit-close" aria-label="Close">&times;</button>
      </div>
      <p class="clarif-edit-type">${window.escapeHtml(typeLabel)}</p>
      ${
        item.checker_comment
          ? `<div class="clarif-edit-checker"><strong>Checker asked:</strong> ${window.escapeHtml(
              item.checker_comment,
            )}</div>`
          : ""
      }
      <div class="clarif-edit-fields">${
        fieldsHtml || '<p class="dash-empty">No editable fields.</p>'
      }</div>
      <label class="clarif-field">
        <span>Reply / comment to checker <em>(required)</em></span>
        <textarea class="clarif-edit-comment" rows="3" placeholder="Describe what you changed"></textarea>
      </label>
      <p class="clarif-edit-msg" hidden></p>
      <div class="clarif-edit-actions">
        <button type="button" class="secondary-btn clarif-edit-cancel">Cancel</button>
        <button type="button" class="primary-btn clarif-edit-submit">Resubmit to checker</button>
      </div>
    </div>`;

  const close = () => overlay.remove();
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) close();
  });
  overlay.querySelector(".clarif-edit-close").addEventListener("click", close);
  overlay.querySelector(".clarif-edit-cancel").addEventListener("click", close);

  const msg = overlay.querySelector(".clarif-edit-msg");
  const showMsg = (text, ok) => {
    msg.textContent = text;
    msg.style.color = ok ? "#0f7b3f" : "#b42318";
    msg.hidden = false;
  };

  overlay.querySelector(".clarif-edit-submit").addEventListener("click", async () => {
    const comment = overlay.querySelector(".clarif-edit-comment").value.trim();
    if (!comment) {
      showMsg("Reply comment is required.", false);
      return;
    }
    const edited = {};
    overlay.querySelectorAll("[data-field-key]").forEach((el) => {
      const key = el.dataset.fieldKey;
      let value = el.value;
      if (el.dataset.json === "1") {
        try {
          value = JSON.parse(el.value);
        } catch (_) {
          /* keep raw string if not valid JSON */
        }
      }
      edited[key] = value;
    });

    const btn = overlay.querySelector(".clarif-edit-submit");
    btn.disabled = true;
    try {
      const res = await fetch(`${API_BASE}/api/approvals/${item.approval_id}/resubmit`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...window.getAuthHeaders() },
        body: JSON.stringify({ comment, proposed_data: edited }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Resubmit failed");
      }
      close();
      if (typeof onDone === "function") onDone();
    } catch (error) {
      btn.disabled = false;
      showMsg(error.message || "Unable to resubmit.", false);
    }
  });

  document.body.appendChild(overlay);
};

/**
 * Download a same-origin static file (e.g. bulk Excel templates).
 * Uses fetch + object URL + in-DOM anchor click so saves work on Windows/Edge
 * (detached <a>.click() often does not trigger a download there).
 */
window.downloadStaticFile = async (path, filename) => {
  const url = new URL(path, window.location.href).href;
  const response = await fetch(url, { credentials: "same-origin" });
  if (!response.ok) {
    throw new Error(`Download failed (${response.status})`);
  }
  const blob = await response.blob();
  window.saveBlob(blob, filename || path.split("/").pop() || "download");
};

/**
 * Save a Blob to disk using an in-DOM anchor + object URL.
 * Appending the anchor to document.body before .click() is required for
 * reliable downloads on Windows/Edge; detached .click() silently fails there.
 */
window.saveBlob = (blob, filename) => {
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename || "download";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(objectUrl);
};

const getCurrentUser = () => {
  const stored = sessionStorage.getItem("currentUser");
  if (!stored) return null;
  try {
    return JSON.parse(stored);
  } catch (error) {
    return null;
  }
};

const enforceAuth = async () => {
  const isLoginPage = window.location.pathname.endsWith("index.html");
  if (isLoginPage) {
    return;
  }

  try {
    const response = await fetch(`${API_BASE}/api/auth/me`, {
      headers: window.getAuthHeaders(),
    });
    if (!response.ok) {
      if (response.status === 401 || response.status === 403) {
        sessionStorage.removeItem("currentUser");
        sessionStorage.removeItem("authToken");
        window.location.replace("index.html");
      }
      return;
    }
    const user = await response.json();
    sessionStorage.setItem("currentUser", JSON.stringify(user));
    applyRoleVisibility(user);
  } catch (error) {
    return;
  }
};

const applyRoleVisibility = (user) => {
  const activeUser = user || getCurrentUser();
  const role = activeUser?.role || "MAKER";
  const allowed = new Set(roleConfig[role] || []);

  if (/reports\.html$/i.test(window.location.pathname) && !allowed.has("reports")) {
    window.location.replace("dashboard.html");
    return;
  }

  document.querySelectorAll("[data-page]").forEach((el) => {
    const pageKey = el.dataset.page;
    el.style.display = allowed.has(pageKey) ? "inline-flex" : "none";
  });

  const userBadge = document.querySelector("[data-user-badge]");
  if (userBadge) {
    const displayName = activeUser?.name || "User";
    const displayId = activeUser?.employeeId ? ` (${activeUser.employeeId})` : "";
    userBadge.textContent = activeUser
      ? `${displayName}${displayId} - ${activeUser.role}`
      : "Guest";
  }

  if (allowed.has("approvals")) {
    updateApprovalNotificationBadge();
  }
  if (
    allowed.has("vendor-onboarding") ||
    allowed.has("store-onboarding") ||
    allowed.has("mapping") ||
    allowed.has("charges")
  ) {
    updateClarificationNotificationBadge();
  }

  document.querySelectorAll("[data-admin-only]").forEach((el) => {
    el.hidden = activeUser?.role !== "ADMIN";
  });

  document.querySelectorAll("[data-maker-hide]").forEach((el) => {
    el.hidden = activeUser?.role === "MAKER";
  });

  document.querySelectorAll("[data-checker-hide]").forEach((el) => {
    el.hidden = activeUser?.role === "CHECKER";
  });

  document.querySelectorAll("[data-clarifications-maker-admin]").forEach((el) => {
    el.hidden = role !== "MAKER" && role !== "ADMIN";
  });
};

const updateClarificationNotificationBadge = async () => {
  const topbarActions = document.querySelector(".topbar-actions");
  if (!topbarActions) return;

  try {
    const response = await fetch(`${API_BASE}/api/approvals/clarifications/count`, {
      headers: window.getAuthHeaders(),
    });
    if (!response.ok) return;
    const data = await response.json();
    const count = data?.count ?? 0;

    const existing = topbarActions.querySelectorAll(".clarification-badge");
    let badge = existing[0] || null;
    for (let i = 1; i < existing.length; i += 1) existing[i].remove();

    if (count > 0) {
      if (!badge) {
        badge = document.createElement("span");
        badge.className = "clarification-badge";
        badge.setAttribute("aria-live", "polite");
        const userBadge = topbarActions.querySelector("[data-user-badge]");
        topbarActions.insertBefore(badge, userBadge?.nextSibling || topbarActions.firstChild);
      }
      badge.textContent = count > 99 ? "99+" : String(count);
      badge.title = `${count} clarification request${count !== 1 ? "s" : ""} from checker - check Vendor Onboarding, Store Onboarding, Store Mapping, or Charges`;
      badge.hidden = false;
    } else if (badge) {
      badge.hidden = true;
    }
  } catch (error) {
    const badge = topbarActions.querySelector(".clarification-badge");
    if (badge) badge.hidden = true;
  }
};

const updateApprovalNotificationBadge = async () => {
  const approvalsCard = document.querySelector('[data-page="approvals"]');
  if (!approvalsCard) return;

  try {
    const response = await fetch(`${API_BASE}/api/approvals/pending/count`, {
      headers: window.getAuthHeaders(),
    });
    if (!response.ok) return;
    const data = await response.json();
    const count = data?.count ?? 0;

    let badge = approvalsCard.querySelector(".nav-card-badge");
    if (count > 0) {
      if (!badge) {
        badge = document.createElement("span");
        badge.className = "nav-card-badge";
        badge.setAttribute("aria-live", "polite");
        approvalsCard.appendChild(badge);
      }
      badge.textContent = count > 99 ? "99+" : String(count);
      badge.title = `${count} pending approval${count !== 1 ? "s" : ""}`;
      badge.hidden = false;
    } else if (badge) {
      badge.hidden = true;
    }
  } catch (error) {
    /* ignore */
  }
};

const wireLogout = () => {
  document.querySelectorAll("[data-logout]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await fetch(`${API_BASE}/api/auth/logout`, {
          method: "POST",
          headers: window.getAuthHeaders(),
        });
      } catch (error) {
        /* ignore */
      } finally {
        sessionStorage.removeItem("currentUser");
        sessionStorage.removeItem("authToken");
        window.location.replace("index.html");
      }
    });
  });
};

/** Global required-field validation: show red "Required" when submit is pressed with empty required fields */
document.addEventListener(
  "submit",
  (e) => {
    const form = e.target;
    if (form.tagName !== "FORM" || form.dataset.skipRequiredValidation === "true") return;

    const required = form.querySelectorAll("input[required], select[required], textarea[required]");
    const firstEmpty = Array.from(required).find((el) => {
      if (el.type === "file") return !el.files || el.files.length === 0;
      const v = (el.value || "").toString().trim();
      return v === "";
    });

    if (firstEmpty) {
      e.preventDefault();
      e.stopImmediatePropagation();
      const msgEl = form.querySelector(".form-message") || form.querySelector("[role=status]") || form.parentElement?.querySelector(".form-message");
      if (msgEl) {
        msgEl.textContent = "Required";
        msgEl.style.color = "#b42318";
      }
      firstEmpty.focus();
    }
  },
  true
);

const hydrateUser = async () => {
  const cached = getCurrentUser();
  if (cached) {
    applyRoleVisibility(cached);
  }

  try {
    const response = await fetch(`${API_BASE}/api/auth/me`, {
      headers: window.getAuthHeaders(),
    });
    if (!response.ok) {
      if (response.status === 401 || response.status === 403) {
        sessionStorage.removeItem("currentUser");
        sessionStorage.removeItem("authToken");
        const isLoginPage = window.location.pathname.endsWith("index.html");
        if (!isLoginPage) {
          window.location.replace("index.html");
        }
      }
      return;
    }
    const user = await response.json();
    sessionStorage.setItem("currentUser", JSON.stringify(user));
    applyRoleVisibility(user);
  } catch (error) {
    if (!cached) {
      applyRoleVisibility(null);
    }
  }
};

window.addEventListener("pageshow", () => {
  enforceAuth();
});

enforceAuth();
hydrateUser();
wireLogout();
