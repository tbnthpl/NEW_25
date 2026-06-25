const runReconButton = document.querySelector("#run-recon");
const reconMessage = document.querySelector("#recon-message");
const tableWrapper = document.querySelector("#recon-table-wrapper");
const misDateInput = document.querySelector("#recon-mis-date");
const vendorFilterSelect = document.querySelector("#recon-vendor-filter");
const downloadButton = document.querySelector("#download-recon");
const saveButton = document.querySelector("#save-recon");
const progressContainer = document.querySelector("#recon-progress");
const progressLabel = document.querySelector("#recon-progress-label");
const progressFill = document.querySelector("#recon-progress-fill");
const progressPercent = document.querySelector("#recon-progress-percent");
const apiBase = window.API_BASE || "";
const escapeHtml = window.escapeHtml || ((value) => String(value ?? ""));

const showReconProgress = () => {
  if (progressContainer && progressLabel) {
    progressLabel.textContent = "Running reconciliation...";
    progressContainer.hidden = false;
  }
  if (progressFill) progressFill.style.width = "0%";
  if (progressPercent) progressPercent.textContent = "0%";
};

const updateReconProgress = (pct) => {
  const val = Math.min(100, Math.round(pct));
  if (progressFill) progressFill.style.width = `${val}%`;
  if (progressPercent) progressPercent.textContent = `${val}%`;
};

const hideReconProgress = () => {
  if (progressContainer) progressContainer.hidden = true;
  if (progressFill) progressFill.style.width = "0%";
  if (progressPercent) progressPercent.textContent = "0%";
};

const startSimulatedProgress = (onComplete) => {
  let pct = 0;
  const maxPct = 90;
  const interval = setInterval(() => {
    pct += Math.random() * 8 + 4;
    if (pct >= maxPct) {
      pct = maxPct;
      clearInterval(interval);
    }
    updateReconProgress(pct);
  }, 200);
  return () => {
    clearInterval(interval);
    updateReconProgress(100);
    setTimeout(() => {
      hideReconProgress();
      if (onComplete) onComplete();
    }, 300);
  };
};

let latestResults = [];

const currentUser = () =>
  sessionStorage.getItem("currentUser")
    ? JSON.parse(sessionStorage.getItem("currentUser"))
    : { employeeId: "SYSTEM" };

let reconMappingData = null;

const loadReconMappingData = async () => {
  if (reconMappingData) return reconMappingData;
  const headers = window.getAuthHeaders();
  const safeJson = async (path) => {
    try {
      const r = await fetch(path, { headers });
      return r.ok ? await r.json() : [];
    } catch (_) {
      return [];
    }
  };
  const [stores, vendors, maps] = await Promise.all([
    safeJson(`${apiBase}/api/bank-stores`),
    safeJson(`${apiBase}/api/vendors`),
    safeJson(`${apiBase}/api/store-mappings`),
  ]);
  const vendorsById = {};
  (vendors || []).forEach((v) => {
    vendorsById[v.vendor_id] = v.name || v.vendor_name || `Vendor ${v.vendor_id}`;
  });
  const vendorsByStore = {};
  (maps || []).forEach((m) => {
    if (!m.bank_store_code || m.vendor_id == null) return;
    const code = String(m.bank_store_code);
    (vendorsByStore[code] = vendorsByStore[code] || []).push(Number(m.vendor_id));
  });
  reconMappingData = {
    stores: (stores || [])
      .filter((s) => (s.status || "") === "ACTIVE")
      .map((s) => ({ code: String(s.bank_store_code), name: s.store_name || "" })),
    vendorsById,
    vendorsByStore,
  };
  return reconMappingData;
};

const openReconEditModal = async (row) => {
  document.querySelectorAll(".recon-edit-overlay").forEach((el) => el.remove());

  const dateVal = (v) => (v ? String(v).slice(0, 10) : "");
  const numVal = (v) => (v == null || v === "" ? "" : String(v));

  const data = await loadReconMappingData();
  const stores = data.stores.slice();
  if (row.bank_store_code && !stores.some((s) => s.code === String(row.bank_store_code))) {
    stores.unshift({ code: String(row.bank_store_code), name: row.store_name || "" });
  }
  const storeLabel = (s) => (s.name ? `${s.name} (${s.code})` : s.code);
  const storeOptionsHtml = stores
    .map(
      (s) =>
        `<option value="${escapeHtml(s.code)}" ${
          String(s.code) === String(row.bank_store_code) ? "selected" : ""
        }>${escapeHtml(storeLabel(s))}</option>`,
    )
    .join("");

  const vendorOptionsHtml = (storeCode, selectedId) => {
    const ids = [...new Set(data.vendorsByStore[String(storeCode)] || [])];
    const opts = ids
      .map(
        (id) =>
          `<option value="${id}" ${
            String(id) === String(selectedId) ? "selected" : ""
          }>${escapeHtml(data.vendorsById[id] || `Vendor ${id}`)}</option>`,
      )
      .join("");
    return `<option value="">-- Select vendor --</option>${opts}`;
  };

  let defaultVendorId = "";
  if (row.vendor_names) {
    const firstName = String(row.vendor_names).split(",")[0].trim();
    const ids = data.vendorsByStore[String(row.bank_store_code)] || [];
    const match = ids.find((id) => (data.vendorsById[id] || "") === firstName);
    if (match != null) defaultVendorId = String(match);
  }

  const overlay = document.createElement("div");
  overlay.className = "clarif-edit-overlay recon-edit-overlay";
  overlay.innerHTML = `
    <div class="clarif-edit-card" role="dialog" aria-modal="true">
      <div class="clarif-edit-head">
        <h2>Edit Reconciliation Row</h2>
        <button type="button" class="clarif-edit-close" data-recon-edit-close aria-label="Close">×</button>
      </div>
      <p class="clarif-edit-type">Status: ${escapeHtml(row.status || "")}</p>
      <div class="clarif-edit-fields">
        <label class="clarif-field"><span>Store Name</span>
          <select data-field="store_select">${storeOptionsHtml}</select></label>
        <label class="clarif-field"><span>Vendor Name</span>
          <select data-field="vendor_select">${vendorOptionsHtml(row.bank_store_code, defaultVendorId)}</select></label>
        <label class="clarif-field"><span>Bank Store Code</span>
          <input type="text" data-field="bank_store_code_display" value="${escapeHtml(row.bank_store_code || "")}" readonly /></label>
        <label class="clarif-field"><span>Vendor Pickup Date</span>
          <input type="date" data-field="pickup_date" value="${escapeHtml(dateVal(row.pickup_date))}" /></label>
        <label class="clarif-field"><span>Vendor Amount</span>
          <input type="number" step="0.01" data-field="vendor_amount" value="${escapeHtml(numVal(row.pickup_amount))}" /></label>
        <label class="clarif-field"><span>Finacle Date</span>
          <input type="date" data-field="remittance_date" value="${escapeHtml(dateVal(row.remittance_date))}" /></label>
        <label class="clarif-field"><span>Finacle Amount</span>
          <input type="number" step="0.01" data-field="finacle_amount" value="${escapeHtml(numVal(row.remittance_amount))}" /></label>
      </div>
      <label class="clarif-field"><span>Reason for edit (required)</span>
        <textarea rows="3" data-field="reason"></textarea></label>
      <p class="clarif-edit-msg" data-recon-edit-msg></p>
      <div class="clarif-edit-actions">
        <button type="button" class="secondary-btn" data-recon-edit-close>Cancel</button>
        <button type="button" class="primary-btn" data-recon-edit-submit>Submit for approval</button>
      </div>
    </div>`;

  document.body.appendChild(overlay);

  const storeSelect = overlay.querySelector('[data-field="store_select"]');
  const vendorSelect = overlay.querySelector('[data-field="vendor_select"]');
  const codeDisplay = overlay.querySelector('[data-field="bank_store_code_display"]');
  if (storeSelect) {
    storeSelect.addEventListener("change", () => {
      const code = storeSelect.value;
      if (codeDisplay) codeDisplay.value = code;
      if (vendorSelect) vendorSelect.innerHTML = vendorOptionsHtml(code, "");
    });
  }

  const close = () => overlay.remove();
  overlay.querySelectorAll("[data-recon-edit-close]").forEach((b) => b.addEventListener("click", close));
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) close();
  });

  const msg = overlay.querySelector("[data-recon-edit-msg]");
  const getVal = (field) => overlay.querySelector(`[data-field="${field}"]`)?.value ?? "";

  overlay.querySelector("[data-recon-edit-submit]").addEventListener("click", async () => {
    const reason = getVal("reason").trim();
    if (!reason) {
      msg.textContent = "Reason is required.";
      msg.style.color = "#b42318";
      return;
    }
    const vendorAmountRaw = getVal("vendor_amount").trim();
    const finacleAmountRaw = getVal("finacle_amount").trim();
    if (vendorAmountRaw !== "" && Number.isNaN(Number(vendorAmountRaw))) {
      msg.textContent = "Vendor Amount must be a valid number.";
      msg.style.color = "#b42318";
      return;
    }
    if (finacleAmountRaw !== "" && Number.isNaN(Number(finacleAmountRaw))) {
      msg.textContent = "Finacle Amount must be a valid number.";
      msg.style.color = "#b42318";
      return;
    }
    const selectedStoreCode = (getVal("store_select") || row.bank_store_code || "").trim();
    const selectedVendorRaw = getVal("vendor_select").trim();
    const selectedVendorId = selectedVendorRaw === "" ? null : Number(selectedVendorRaw);
    const selectedVendorName = selectedVendorId != null ? data.vendorsById[selectedVendorId] || null : null;
    const details = {
      current_status: row.status || null,
      bank_store_code: selectedStoreCode || null,
      vendor_id: selectedVendorId,
      vendor_name: selectedVendorName,
      pickup_date: getVal("pickup_date") || null,
      remittance_date: getVal("remittance_date") || null,
      vendor_amount: vendorAmountRaw === "" ? null : Number(vendorAmountRaw),
      finacle_amount: finacleAmountRaw === "" ? null : Number(finacleAmountRaw),
    };
    msg.textContent = "Submitting...";
    msg.style.color = "#0f4c81";
    try {
      const response = await fetch(`${apiBase}/api/reconciliation/corrections/requests`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...window.getAuthHeaders() },
        body: JSON.stringify({
          recon_id: row.recon_id,
          requested_action: "FIELD_EDIT",
          details: JSON.stringify(details),
          maker_id: currentUser().employeeId,
          reason,
        }),
      });
      if (!response.ok) {
        let detail = "";
        try {
          detail = (await response.json())?.detail || "";
        } catch (_) {
          detail = "";
        }
        throw new Error(detail || "Unable to submit correction.");
      }
      close();
      reconMessage.textContent =
        "Correction submitted for approval. Run Reconciliation again to see approval status.";
      reconMessage.style.color = "#0f4c81";
    } catch (error) {
      msg.textContent = error.message || "Unable to submit correction.";
      msg.style.color = "#b42318";
    }
  });
};

const downloadReconciliationXlsx = (rows, misDate) => {
  if (!rows.length || typeof XLSX === "undefined") return;
  const editStatusDisplay = (s) =>
    s === "PENDING" ? "Pending" : s === "APPROVED" ? "Approved" : s === "REJECTED" ? "Rejected" : "";
  const payload = rows.map((row) => ({
    Saved: row.is_final ? "Yes" : "",
    "Bank Store Code": row.bank_store_code || "",
    "Store Name": row.store_name || "",
    "Vendor Name": row.vendor_names || "",
    "Vendor Pickup Date": row.pickup_date || "",
    "Vendor Amount": row.pickup_amount ?? "",
    "Finacle Date": row.remittance_date || "",
    "Finacle Amount": row.remittance_amount ?? "",
    Status: row.status || "",
    Reason: row.reason || "",
    "Edit Status": editStatusDisplay(row.correction_status) || "",
  }));
  const worksheet = XLSX.utils.json_to_sheet(payload);
  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, worksheet, "Reconciliation");
  XLSX.writeFile(workbook, `reconciliation_${misDate || "report"}.xlsx`);
};

const updateSaveButtonState = () => {
  const matchedUnsaved = latestResults.filter((r) => r.status === "MATCHED" && !r.is_final);
  const hasMatchedUnsaved = matchedUnsaved.length > 0;
  const selectedCount = tableWrapper?.querySelectorAll('input.recon-save-checkbox:checked').length ?? 0;
  if (saveButton) {
    saveButton.hidden = !hasMatchedUnsaved;
    saveButton.disabled = selectedCount === 0;
  }
};

const renderTable = (results) => {
  if (!results.length) {
    tableWrapper.innerHTML = "";
    latestResults = [];
    downloadButton.disabled = true;
    downloadButton.hidden = true;
    if (saveButton) saveButton.hidden = true;
    return;
  }

  latestResults = results;
  downloadButton.disabled = false;
  downloadButton.hidden = false;
  const matchedUnsaved = results.filter((r) => r.status === "MATCHED" && !r.is_final);
  const hasMatchedUnsaved = matchedUnsaved.length > 0;
  if (saveButton) {
    saveButton.hidden = !hasMatchedUnsaved;
    saveButton.disabled = true;
  }

  const rows = results
    .map(
      (row) => {
        const showEdit =
          row.status !== "MATCHED" &&
          row.correction_status !== "PENDING" &&
          row.correction_status !== "APPROVED";
        const editStatusDisplay =
          row.correction_status === "PENDING"
            ? "Pending"
            : row.correction_status === "APPROVED"
              ? "Approved"
              : row.correction_status === "REJECTED"
                ? "Rejected"
                : "";
        const isMatched = row.status === "MATCHED";
        const isSaved = row.is_final === true;
        const canSelect = isMatched && !isSaved;
        const saveCell = isSaved
          ? '<span class="status match">Saved</span>'
          : canSelect
            ? `<input type="checkbox" class="recon-save-checkbox" data-recon-id="${row.recon_id}" aria-label="Select to save" />`
            : '<span class="recon-save-empty" aria-hidden="true">-</span>';
        const fmtAmount = (v) =>
          v != null && v !== "" && !Number.isNaN(Number(v))
            ? Number(v).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
            : "";
        return `
      <tr>
        <td class="recon-save-cell">${saveCell}</td>
        <td>${escapeHtml(row.bank_store_code || "")}</td>
        <td>${escapeHtml(row.store_name || "")}</td>
        <td>${escapeHtml(row.vendor_names || "")}</td>
        <td>${escapeHtml(row.pickup_date || "")}</td>
        <td class="recon-amount-cell">${escapeHtml(fmtAmount(row.pickup_amount))}</td>
        <td>${escapeHtml(row.remittance_date || "")}</td>
        <td class="recon-amount-cell">${escapeHtml(fmtAmount(row.remittance_amount))}</td>
        <td class="recon-status-cell"><span class="status ${row.status === "MATCHED" ? "match" : "mismatch"}">${escapeHtml(row.status)}</span></td>
        <td class="recon-reason-cell">${escapeHtml(row.reason || "")}</td>
        <td class="recon-edit-status-cell">${escapeHtml(editStatusDisplay || "")}</td>
        <td class="recon-action-cell">
          ${showEdit ? `<button class="secondary-btn" data-action="edit-row" data-recon-id="${row.recon_id}">Edit</button>` : ""}
        </td>
      </tr>
    `;
      },
    )
    .join("");

  const hasSelectable = matchedUnsaved.length > 0;
  const headerCheckbox = hasSelectable
    ? `<input type="checkbox" id="recon-select-all-header" class="recon-save-checkbox-header" aria-label="Select all matched rows" title="Select all matched" />`
    : '<span class="recon-save-empty" aria-hidden="true">✓</span>';

  tableWrapper.innerHTML = `
    <table class="recon-table">
      <thead>
        <tr>
          <th class="recon-save-cell" title="Select matched rows to save">${headerCheckbox}</th>
          <th>Bank Store Code</th>
          <th>Store Name</th>
          <th>Vendor Name</th>
          <th>Vendor Pickup Date</th>
          <th>Vendor Amount</th>
          <th>Finacle Date</th>
          <th>Finacle Amount</th>
          <th>Status</th>
          <th>Reason</th>
          <th>Edit Status</th>
          <th>Action</th>
        </tr>
      </thead>
      <tbody>
        ${rows}
      </tbody>
    </table>
  `;

  tableWrapper.querySelectorAll(".recon-save-checkbox").forEach((cb) => {
    cb.addEventListener("change", updateSaveButtonState);
  });

  const headerCb = tableWrapper.querySelector(".recon-save-checkbox-header");
  if (headerCb) {
    headerCb.addEventListener("change", () => {
      const checked = headerCb.checked;
      tableWrapper.querySelectorAll(".recon-save-checkbox").forEach((cb) => {
        cb.checked = checked;
      });
      updateSaveButtonState();
    });
  }

  tableWrapper.querySelectorAll('[data-action="edit-row"]').forEach((button) => {
    button.addEventListener("click", () => {
      const reconId = Number(button.dataset.reconId);
      const row = latestResults.find((item) => item.recon_id === reconId);
      if (row) openReconEditModal(row);
    });
  });
};

const loadReconVendorFilter = async () => {
  if (!vendorFilterSelect) return;
  const keepValue = vendorFilterSelect.value;
  vendorFilterSelect.innerHTML = '<option value="">All vendors</option>';
  try {
    const res = await fetch(`${apiBase}/api/vendors`, { headers: window.getAuthHeaders() });
    if (!res.ok) return;
    const vendors = await res.json();
    const active = (vendors || []).filter((v) => v.status === "ACTIVE");
    active.forEach((v) => {
      const opt = document.createElement("option");
      opt.value = String(v.vendor_id);
      const label = `${v.name || ""} (${v.code || ""})`.trim() || String(v.vendor_id);
      opt.textContent = label;
      vendorFilterSelect.appendChild(opt);
    });
    if (keepValue && Array.from(vendorFilterSelect.options).some((o) => o.value === keepValue)) {
      vendorFilterSelect.value = keepValue;
    }
  } catch (_) {}
};

runReconButton.addEventListener("click", async () => {
  const misDate = misDateInput?.value;
  if (!misDate) {
    reconMessage.textContent = "Please select MIS date.";
    reconMessage.style.color = "#b42318";
    return;
  }
  const vendorIdRaw = vendorFilterSelect?.value?.trim() || "";
  reconMessage.textContent = "Running reconciliation...";
  reconMessage.style.color = "#0f4c81";
  showReconProgress();

  let finishProgress;
  const progressPromise = new Promise((resolve) => {
    finishProgress = startSimulatedProgress(resolve);
  });

  try {
    const body = { misDate };
    if (vendorIdRaw) {
      body.vendor_id = Number(vendorIdRaw);
    }
    const response = await fetch(`${apiBase}/api/reconciliation/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...window.getAuthHeaders() },
      body: JSON.stringify(body),
    });
    finishProgress();
    await progressPromise;

    if (!response.ok) {
      let detail = "";
      try {
        const data = await response.json();
        detail = data?.detail || "";
      } catch (error) {
        detail = "";
      }
      throw new Error(detail || "Reconciliation failed");
    }
    const results = await response.json();
    renderTable(results);
    const vendorNote = vendorIdRaw
      ? ` Filter: one vendor (${vendorFilterSelect?.selectedOptions[0]?.textContent || vendorIdRaw}).`
      : "";
    reconMessage.textContent = results.length
      ? `Reconciliation completed.${vendorNote}`
      : `Reconciliation completed. No results found.${vendorNote}`;
  } catch (error) {
    if (finishProgress) finishProgress();
    await progressPromise;
    reconMessage.textContent = error.message || "Unable to run reconciliation.";
    reconMessage.style.color = "#b42318";
  }
});

downloadButton.addEventListener("click", () => {
  const misDate = misDateInput?.value;
  downloadReconciliationXlsx(latestResults, misDate);
});

saveButton?.addEventListener("click", async () => {
  const misDate = misDateInput?.value;
  if (!misDate) {
    reconMessage.textContent = "Please select MIS date.";
    reconMessage.style.color = "#b42318";
    return;
  }
  const checked = tableWrapper?.querySelectorAll(".recon-save-checkbox:checked") ?? [];
  const reconIds = Array.from(checked)
    .map((cb) => Number(cb.dataset.reconId))
    .filter((id) => !Number.isNaN(id));
  if (!reconIds.length) {
    reconMessage.textContent = "Select at least one matched row to save.";
    reconMessage.style.color = "#b42318";
    return;
  }
  reconMessage.textContent = "Saving reconciliation as final...";
  reconMessage.style.color = "#0f4c81";
  try {
    const response = await fetch(`${apiBase}/api/reconciliation/save`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...window.getAuthHeaders() },
      body: JSON.stringify({ misDate, recon_ids: reconIds }),
    });
    if (!response.ok) {
      let detail = "";
      try {
        const data = await response.json();
        detail = data?.detail || "";
      } catch (error) {
        detail = "";
      }
      throw new Error(detail || "Save failed");
    }
    reconMessage.innerHTML = `Saved ${reconIds.length} row(s) as final. <a href="reconciliation-results.html?misDate=${encodeURIComponent(misDate)}" class="secondary-link">View in Daily Reconciliation Results</a>`;
    reconMessage.style.color = "#0f4c81";
    reconIds.forEach((id) => {
      const r = latestResults.find((x) => x.recon_id === id);
      if (r) r.is_final = true;
    });
    renderTable(latestResults);
  } catch (error) {
    reconMessage.textContent = error.message || "Unable to save reconciliation.";
    reconMessage.style.color = "#b42318";
  }
});

loadReconVendorFilter();
