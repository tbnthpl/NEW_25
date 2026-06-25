const loadButton = document.querySelector("#load-logs");
const downloadButton = document.querySelector("#download-logs");
const downloadExcelButton = document.querySelector("#download-excel");
const logMessage = document.querySelector("#log-message");
const tableWrapper = document.querySelector("#log-table-wrapper");
const paginationEl = document.querySelector("#log-pagination");
const entityTypeSelect = document.querySelector("#log-entity-type");
const statusCodeSelect = document.querySelector("#log-status-code");
const fromDateInput = document.querySelector("#log-from-date");
const toDateInput = document.querySelector("#log-to-date");
const limitSelect = document.querySelector("#log-limit");
const apiBase = window.API_BASE || "";

let currentLogType = "audit";
let currentOffset = 0;
let currentTotal = 0;
let currentLimit = 500;

const buildListUrl = (offset = 0) => {
  const params = new URLSearchParams();
  params.set("limit", limitSelect?.value || "500");
  params.set("offset", String(offset));
  if (currentLogType === "audit") {
    if (entityTypeSelect?.value) params.set("entity_type", entityTypeSelect.value);
  } else {
    if (statusCodeSelect?.value) params.set("status_code", statusCodeSelect.value);
  }
  if (fromDateInput?.value) params.set("from_date", fromDateInput.value);
  if (toDateInput?.value) params.set("to_date", toDateInput.value);
  const base = currentLogType === "audit" ? "audit-logs" : "api-logs";
  return `${apiBase}/api/reports/${base}/list?${params.toString()}`;
};

const loadLogs = async (offset = 0) => {
  logMessage.textContent = "Loading...";
  logMessage.style.color = "#0f4c81";

  try {
    const response = await fetch(buildListUrl(offset), {
      headers: window.getAuthHeaders(),
    });
    if (!response.ok) {
      let detail = "";
      try {
        const data = await response.json();
        detail = Array.isArray(data?.detail) ? data.detail.map((d) => d?.msg || "").join("; ") : data?.detail || "";
      } catch (_) {}
      throw new Error(detail || "Unable to load logs.");
    }
    const data = await response.json();
    currentTotal = data.total;
    currentLimit = data.limit;
    currentOffset = data.offset;
    if (currentLogType === "audit") {
      renderAuditLogs(data.items);
      populateEntityTypes(data.items);
    } else {
      renderApiLogs(data.items);
    }
    renderPagination(data);
    logMessage.textContent = `Showing ${data.items.length} of ${data.total} log entries.`;
    logMessage.style.color = "#0f4c81";
  } catch (error) {
    logMessage.textContent = error.message || "Unable to load logs.";
    logMessage.style.color = "#b42318";
    tableWrapper.innerHTML = "";
    paginationEl.innerHTML = "";
  }
};

const escapeHtml = (s) => {
  if (s == null || s === "") return "";
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
};

const renderAuditLogs = (items) => {
  if (!items || !items.length) {
    tableWrapper.innerHTML = "<p class='empty-state'>No audit log entries found.</p>";
    return;
  }

  const rows = items
    .map(
      (row) => `
      <tr>
        <td>${escapeHtml(row.changed_at ? (window.formatDateTime || (s => s))(row.changed_at) : "")}</td>
        <td>${escapeHtml(row.entity_type || "")}</td>
        <td>${escapeHtml(row.entity_id != null ? String(row.entity_id) : "")}</td>
        <td>${escapeHtml(row.action || "")}</td>
        <td>${escapeHtml(row.changed_by || "")}</td>
        <td class="log-data-cell">${escapeHtml((row.old_data || "").slice(0, 200))}${(row.old_data || "").length > 200 ? "…" : ""}</td>
        <td class="log-data-cell">${escapeHtml((row.new_data || "").slice(0, 200))}${(row.new_data || "").length > 200 ? "…" : ""}</td>
      </tr>
    `,
    )
    .join("");

  tableWrapper.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Date & Time</th>
          <th>Entity Type</th>
          <th>Entity ID</th>
          <th>Action</th>
          <th>Changed By</th>
          <th>Old Data</th>
          <th>New Data</th>
        </tr>
      </thead>
      <tbody>
        ${rows}
      </tbody>
    </table>
  `;
};

const renderApiLogs = (items) => {
  if (!items || !items.length) {
    tableWrapper.innerHTML = "<p class='empty-state'>No API error entries found.</p>";
    return;
  }

  const rows = items
    .map(
      (row) => `
      <tr>
        <td>${escapeHtml(row.created_at ? (window.formatDateTime || (s => s))(row.created_at) : "")}</td>
        <td>${escapeHtml(row.method || "")}</td>
        <td class="log-data-cell">${escapeHtml((row.path || "").slice(0, 80))}${(row.path || "").length > 80 ? "…" : ""}</td>
        <td><span class="status ${row.status_code >= 500 ? "mismatch" : "warn"}">${row.status_code || ""}</span></td>
        <td>${escapeHtml(row.level || "")}</td>
        <td>${escapeHtml(row.user_id || "-")}</td>
        <td class="log-data-cell">${escapeHtml((row.message || "").slice(0, 150))}${(row.message || "").length > 150 ? "…" : ""}</td>
        <td class="log-data-cell">${escapeHtml((row.detail || "").slice(0, 150))}${(row.detail || "").length > 150 ? "…" : ""}</td>
      </tr>
    `,
    )
    .join("");

  tableWrapper.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Date & Time</th>
          <th>Method</th>
          <th>Path</th>
          <th>Status</th>
          <th>Level</th>
          <th>User</th>
          <th>Message</th>
          <th>Detail</th>
        </tr>
      </thead>
      <tbody>
        ${rows}
      </tbody>
    </table>
  `;
};

const renderPagination = (data) => {
  if (!data || data.total <= data.limit) {
    paginationEl.innerHTML = "";
    return;
  }

  const totalPages = Math.ceil(data.total / data.limit);
  const currentPage = Math.floor(data.offset / data.limit) + 1;
  const hasPrev = data.offset > 0;
  const hasNext = data.offset + data.items.length < data.total;

  paginationEl.innerHTML = `
    <div class="pagination-controls">
      <span class="pagination-info">Page ${currentPage} of ${totalPages} (${data.total} total)</span>
      <button class="secondary-btn pagination-btn" ${!hasPrev ? "disabled" : ""} data-offset="0">First</button>
      <button class="secondary-btn pagination-btn" ${!hasPrev ? "disabled" : ""} data-offset="${Math.max(0, data.offset - data.limit)}">Previous</button>
      <button class="secondary-btn pagination-btn" ${!hasNext ? "disabled" : ""} data-offset="${data.offset + data.limit}">Next</button>
      <button class="secondary-btn pagination-btn" ${!hasNext ? "disabled" : ""} data-offset="${(totalPages - 1) * data.limit}">Last</button>
    </div>
  `;

  paginationEl.querySelectorAll(".pagination-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const offset = parseInt(btn.dataset.offset, 10);
      if (!isNaN(offset)) loadLogs(offset);
    });
  });
};

loadButton?.addEventListener("click", () => loadLogs(0));

downloadButton?.addEventListener("click", async () => {
  logMessage.textContent = "Preparing download...";
  logMessage.style.color = "#0f4c81";
  try {
    const params = new URLSearchParams();
    if (currentLogType === "audit") {
      if (entityTypeSelect?.value) params.set("entity_type", entityTypeSelect.value);
    } else {
      if (statusCodeSelect?.value) params.set("status_code", statusCodeSelect.value);
    }
    if (fromDateInput?.value) params.set("from_date", fromDateInput.value);
    if (toDateInput?.value) params.set("to_date", toDateInput.value);
    const base = currentLogType === "audit" ? "audit-logs" : "api-logs";
    const url = `${apiBase}/api/reports/${base}${params.toString() ? "?" + params.toString() : ""}`;
    const response = await fetch(url, { headers: window.getAuthHeaders() });
    if (!response.ok) throw new Error("Download failed");
    const blob = await response.blob();
    window.saveBlob(blob, currentLogType === "audit" ? "audit-log.xlsx" : "api-logs.xlsx");
    logMessage.textContent = "Download complete.";
  } catch (error) {
    logMessage.textContent = error.message || "Download failed.";
    logMessage.style.color = "#b42318";
  }
});

const buildListUrlForExport = (offset, limit = 2000) => {
  const params = new URLSearchParams();
  params.set("limit", String(limit));
  params.set("offset", String(offset));
  if (currentLogType === "audit") {
    if (entityTypeSelect?.value) params.set("entity_type", entityTypeSelect.value);
  } else {
    if (statusCodeSelect?.value) params.set("status_code", statusCodeSelect.value);
  }
  if (fromDateInput?.value) params.set("from_date", fromDateInput.value);
  if (toDateInput?.value) params.set("to_date", toDateInput.value);
  const base = currentLogType === "audit" ? "audit-logs" : "api-logs";
  return `${apiBase}/api/reports/${base}/list?${params.toString()}`;
};

downloadExcelButton?.addEventListener("click", async () => {
  logMessage.textContent = "Preparing Excel download...";
  logMessage.style.color = "#0f4c81";
  try {
    const allItems = [];
    let offset = 0;
    const limit = 2000;
    let hasMore = true;
    while (hasMore) {
      const response = await fetch(buildListUrlForExport(offset, limit), {
        headers: window.getAuthHeaders(),
      });
      if (!response.ok) throw new Error("Download failed");
      const data = await response.json();
      allItems.push(...data.items);
      hasMore = data.items.length === limit && allItems.length < data.total;
      offset += limit;
    }
    if (!allItems.length) {
      logMessage.textContent = "No log entries to export.";
      return;
    }
    const payload =
      currentLogType === "audit"
        ? allItems.map((row) => ({
            "Date & Time": row.changed_at ? (window.formatDateTime || (s => s))(row.changed_at) : "",
            "Entity Type": row.entity_type || "",
            "Entity ID": row.entity_id != null ? row.entity_id : "",
            Action: row.action || "",
            "Changed By": row.changed_by || "",
            "Old Data": row.old_data || "",
            "New Data": row.new_data || "",
          }))
        : allItems.map((row) => ({
            "Date & Time": row.created_at ? (window.formatDateTime || (s => s))(row.created_at) : "",
            Method: row.method || "",
            Path: row.path || "",
            "Status Code": row.status_code ?? "",
            Level: row.level || "",
            "User ID": row.user_id || "",
            Message: row.message || "",
            Detail: row.detail || "",
          }));
    const sheetName = currentLogType === "audit" ? "Audit Log" : "API Log";
    const worksheet = XLSX.utils.json_to_sheet(payload);
    const workbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(workbook, worksheet, sheetName);
    XLSX.writeFile(workbook, currentLogType === "audit" ? "audit-log.xlsx" : "api-logs.xlsx");
    logMessage.textContent = "Excel download complete.";
  } catch (error) {
    logMessage.textContent = error.message || "Excel download failed.";
    logMessage.style.color = "#b42318";
  }
});

const KNOWN_ENTITY_TYPES = [
  "ADMIN_CLEANUP", "APPROVAL", "BANK_STORE_MASTER", "CHARGE_CONFIG", "EXCEPTION",
  "FINACLE_FORMAT", "MONTH_LOCK", "PICKUP_RULE", "REPORT", "REMITTANCE",
  "STORE_MAPPING", "UPLOAD", "VENDOR_CHARGE", "VENDOR_FILE_FORMAT", "VENDOR_MASTER",
  "WAIVER", "RECONCILIATION", "RECONCILIATION_CORRECTION",
];

const populateEntityTypes = (items = []) => {
  const types = new Set(KNOWN_ENTITY_TYPES);
  items.forEach((i) => i.entity_type && types.add(i.entity_type));
  const existing = entityTypeSelect?.querySelectorAll('option:not([value=""])') || [];
  existing.forEach((o) => o.remove());
  [...types].sort().forEach((t) => {
    const opt = document.createElement("option");
    opt.value = t;
    opt.textContent = t;
    entityTypeSelect?.appendChild(opt);
  });
};

const setLogType = (type) => {
  currentLogType = type;
  document.querySelectorAll(".log-type-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.logType === type);
  });
  document.querySelector(".log-filter-audit")?.classList.toggle("hidden", type !== "audit");
  document.querySelector(".log-filter-api")?.classList.toggle("hidden", type !== "api");
  loadLogs(0);
};

document.querySelectorAll(".log-type-btn").forEach((btn) => {
  btn.addEventListener("click", () => setLogType(btn.dataset.logType));
});

document.addEventListener("DOMContentLoaded", () => {
  populateEntityTypes();
  loadLogs(0);
});
