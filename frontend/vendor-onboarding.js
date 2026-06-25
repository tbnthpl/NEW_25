const vendorForm = document.querySelector("#vendor-form");
const vendorMessage = document.querySelector("#vendor-message");
const vendorRows = document.querySelector("#vendor-rows");
const vendorSearchInput = document.querySelector("#vendor-search");
const clarificationRows = document.querySelector("#clarification-rows");
const clarificationMessage = document.querySelector("#clarification-message");
const apiBase = window.API_BASE || "";
let vendorCache = [];
const escapeHtml = window.escapeHtml || ((value) => String(value ?? ""));

const EYE_ICON =
  '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8S1 12 1 12z"/><circle cx="12" cy="12" r="3"/></svg>';

const formatDecidedAt = (iso) => {
  if (!iso) return "";
  return (window.formatDateTime || ((s) => String(s)))(iso);
};

/* Shared "checker decision" view-only modal (eye-icon). */
const checkerModal = document.querySelector("#checker-comment-modal");
const showCheckerCommentModal = (entity) => {
  if (!checkerModal) return;
  const set = (id, value) => {
    const el = checkerModal.querySelector(`#${id}`);
    if (el) el.textContent = value || "-";
  };
  set("checker-comment-decision", entity.approval_status || "");
  set("checker-comment-checker", entity.checker_id || "");
  set("checker-comment-decided-at", formatDecidedAt(entity.approval_decided_at));
  set("checker-comment-maker", entity.maker_id || "");
  set("checker-comment-created-at", formatDecidedAt(entity.approval_created_at));
  set("checker-comment-text", entity.checker_comment || "");
  checkerModal.hidden = false;
  checkerModal.classList.add("approval-modal-visible");
};
const hideCheckerCommentModal = () => {
  if (!checkerModal) return;
  checkerModal.hidden = true;
  checkerModal.classList.remove("approval-modal-visible");
};

const currentUser = () =>
  sessionStorage.getItem("currentUser")
    ? JSON.parse(sessionStorage.getItem("currentUser"))
    : { employeeId: "SYSTEM" };

/* Vendor File Format Config (modal) */
const fileConfigBtn = document.querySelector("#file-config-btn");
const fileConfigModal = document.querySelector("#file-config-modal");
const voFormatVendorSelect = document.querySelector("#vo-vendor-format-vendor");
const voFormatForm = document.querySelector("#vo-vendor-format-form");
const voFormatMessage = document.querySelector("#vo-vendor-format-message");
const voMappingRows = document.querySelector("#vo-vendor-format-mapping-rows");
const voMappingTextarea = document.querySelector("#vo-header-mapping");
const voGenerateBtn = document.querySelector("#vo-generate-vendor-mapping");
const voSampleInput = document.querySelector("#vo-vendor-format-sample");
const voExistingFormatsWrapper = document.querySelector("#vo-existing-formats-wrapper");
const voExistingFormatsRows = document.querySelector("#vo-existing-formats-rows");
const voExistingFormatsPlaceholder = document.querySelector("#vo-existing-formats-placeholder");
const voExistingFormatsTable = document.querySelector("#vo-existing-formats-table");
let voHeaderOptions = [];
let voExistingFormatsCache = [];

const voMappingFields = [
  { key: "pickup_date_column", label: "Pickup Date (required)" },
  { key: "pickup_amount_column", label: "Pickup Amount (required)" },
  { key: "vendor_store_code_column", label: "Vendor Store Code (required)" },
  { key: "pickup_type_column", label: "Pickup Type (optional)" },
  { key: "account_no_column", label: "Account Number (optional)" },
  { key: "customer_id_column", label: "Customer ID (optional)" },
  { key: "customer_name_column", label: "Customer Name (optional)" },
  { key: "remittance_amount_column", label: "Remittance Amount (optional)" },
  { key: "remittance_date_column", label: "Remittance Date (optional)" },
];

const formatHistory = (raw) => {
  if (!raw) return "";
  try {
    const items = JSON.parse(raw);
    if (!Array.isArray(items)) return "";
    return items
      .map(
        (entry) =>
          `${escapeHtml(entry.role || "")} ${escapeHtml(entry.user_id || "")}: ${escapeHtml(entry.comment || "")}`,
      )
      .join("<br/>");
  } catch (error) {
    return "";
  }
};

const loadVendorsForFormat = async () => {
  if (!voFormatVendorSelect) return;
  voFormatVendorSelect.innerHTML = '<option value="">Select vendor</option>';
  try {
    const response = await fetch(`${apiBase}/api/vendors?include_inactive=1`, {
      headers: window.getAuthHeaders(),
    });
    if (!response.ok) return;
    const vendors = await response.json();
    vendors.forEach((v) => {
      const opt = document.createElement("option");
      opt.value = v.vendor_id;
      opt.textContent = `${v.name || v.vendor_name || ""} (${v.code || v.vendor_code || ""})`.trim() || v.vendor_id;
      voFormatVendorSelect.appendChild(opt);
    });
  } catch (_) {}
};

const voUpdateMappingSelectOptions = () => {
  if (!voMappingRows) return;
  const allOptions = [...new Set(voHeaderOptions)];
  voMappingRows.querySelectorAll("select[data-mapping-key]").forEach((select) => {
    const current = select.value;
    select.innerHTML = '<option value="">Select column</option>';
    allOptions.forEach((opt) => {
      const o = document.createElement("option");
      o.value = opt;
      o.textContent = opt;
      select.appendChild(o);
    });
    select.value = current;
  });
};

const voRenderMappingBuilder = () => {
  if (!voMappingRows) return;
  voMappingRows.innerHTML = voMappingFields
    .map(
      (f) => `
      <tr>
        <td>${f.label}</td>
        <td><select data-mapping-key="${f.key}"><option value="">Select column</option></select></td>
      </tr>
    `
    )
    .join("");
  voUpdateMappingSelectOptions();
};

const voGenerateMappingJson = () => {
  if (!voMappingTextarea || !voMappingRows) return;
  const payload = {};
  voMappingRows.querySelectorAll("select[data-mapping-key]").forEach((select) => {
    const key = select.dataset.mappingKey;
    const value = select.value.trim();
    if (value) payload[key] = value;
  });
  voMappingTextarea.value = JSON.stringify(payload, null, 2);
};

const EDIT_ICON =
  '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>';
const REMOVE_ICON =
  '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>';

const loadVoExistingFormats = async (vendorId) => {
  if (!voExistingFormatsRows || !voExistingFormatsWrapper) return;
  voExistingFormatsRows.innerHTML = "";
  if (!vendorId) {
    if (voExistingFormatsPlaceholder) {
      voExistingFormatsPlaceholder.hidden = false;
      voExistingFormatsPlaceholder.textContent = "Select a vendor to view existing formats.";
    }
    if (voExistingFormatsTable) voExistingFormatsTable.hidden = true;
    return;
  }
  if (voExistingFormatsPlaceholder) {
    voExistingFormatsPlaceholder.hidden = false;
    voExistingFormatsPlaceholder.textContent = "Loading...";
  }
  if (voExistingFormatsTable) voExistingFormatsTable.hidden = true;
  try {
    const response = await fetch(
      `${apiBase}/api/vendor-file-formats?vendor_id=${encodeURIComponent(vendorId)}`,
      { headers: window.getAuthHeaders() }
    );
    if (!response.ok) throw new Error("Failed to load formats");
    voExistingFormatsCache = await response.json();
    if (voExistingFormatsPlaceholder) {
      voExistingFormatsPlaceholder.hidden = voExistingFormatsCache.length > 0;
      if (voExistingFormatsCache.length === 0) {
        voExistingFormatsPlaceholder.textContent = "No existing formats for this vendor.";
      }
    }
    if (voExistingFormatsTable) voExistingFormatsTable.hidden = voExistingFormatsCache.length === 0;
    voExistingFormatsRows.innerHTML = voExistingFormatsCache
      .map(
        (f, idx) => `
        <tr>
          <td>${escapeHtml(f.format_name ?? "")}</td>
          <td>${escapeHtml(f.effective_from ?? "")}</td>
          <td>
            <button type="button" class="action-icon-btn" data-vo-edit-index="${idx}" title="Edit" aria-label="Edit format">${EDIT_ICON}</button>
            <button type="button" class="action-icon-btn action-icon-btn-danger" data-vo-remove-format-id="${f.format_id}" title="Remove" aria-label="Remove format">${REMOVE_ICON}</button>
          </td>
        </tr>
      `
      )
      .join("");
    voExistingFormatsRows.querySelectorAll("[data-vo-edit-index]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const idx = Number(btn.dataset.voEditIndex);
        const f = voExistingFormatsCache[idx];
        if (!f) return;
        if (voFormatVendorSelect) voFormatVendorSelect.value = f.vendor_id;
        const nameInput = voFormatForm?.querySelector('[name="formatName"]');
        if (nameInput) nameInput.value = f.format_name ?? "";
        if (voMappingTextarea) voMappingTextarea.value = f.header_mapping_json ? JSON.stringify(JSON.parse(f.header_mapping_json), null, 2) : "{}";
        const dateInput = voFormatForm?.querySelector('[name="effectiveFrom"]');
        if (dateInput) dateInput.value = f.effective_from ?? "";
        try {
          const parsed = JSON.parse(f.header_mapping_json || "{}");
          const values = Object.values(parsed).filter(Boolean);
          voHeaderOptions = [...new Set([...voHeaderOptions, ...values])];
        } catch (_) {}
        voRenderMappingBuilder();
        try {
          const parsed = JSON.parse(f.header_mapping_json || "{}");
          voMappingRows?.querySelectorAll("select[data-mapping-key]").forEach((sel) => {
            const v = parsed[sel.dataset.mappingKey];
            if (v) sel.value = v;
          });
        } catch (_) {}
      });
    });
    voExistingFormatsRows.querySelectorAll("[data-vo-remove-format-id]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const formatId = btn.dataset.voRemoveFormatId;
        if (!formatId || !confirm("Remove this file format config? It will be deactivated.")) return;
        if (voFormatMessage) voFormatMessage.textContent = "";
        try {
          const res = await fetch(`${apiBase}/api/vendor-file-formats/${formatId}`, {
            method: "DELETE",
            headers: window.getAuthHeaders(),
          });
          if (!res.ok) {
            const data = await res.json().catch(() => ({}));
            throw new Error(data?.detail || "Remove failed");
          }
          loadVoExistingFormats(voFormatVendorSelect?.value || "");
        } catch (err) {
          if (voFormatMessage) {
            voFormatMessage.textContent = err.message || "Unable to remove format.";
            voFormatMessage.style.color = "#b42318";
          }
        }
      });
    });
  } catch (_) {
    if (voExistingFormatsPlaceholder) {
      voExistingFormatsPlaceholder.hidden = false;
      voExistingFormatsPlaceholder.textContent = "Unable to load formats.";
    }
    if (voExistingFormatsTable) voExistingFormatsTable.hidden = true;
  }
};

const showFileConfigModal = () => {
  if (!fileConfigModal) return;
  loadVendorsForFormat();
  voRenderMappingBuilder();
  loadVoExistingFormats(voFormatVendorSelect?.value || "");
  fileConfigModal.hidden = false;
  fileConfigModal.classList.add("approval-modal-visible");
};

const hideFileConfigModal = () => {
  if (!fileConfigModal) return;
  fileConfigModal.hidden = true;
  fileConfigModal.classList.remove("approval-modal-visible");
};

const deactivateVendorModal = document.querySelector("#deactivate-vendor-modal");
const deactivateVendorForm = document.querySelector("#deactivate-vendor-form");
const deactivateVendorIdInput = document.querySelector("#deactivate-vendor-id");
const deactivateVendorNameInput = document.querySelector("#deactivate-vendor-name");
const deactivateMakerCommentInput = document.querySelector("#deactivate-maker-comment");
const deactivateVendorMessage = document.querySelector("#deactivate-vendor-message");
const vendorSubmitBtn = vendorForm?.querySelector('button[type="submit"]');

const showDeactivateVendorModal = (vendorId, vendorName) => {
  if (!deactivateVendorModal) return;
  if (deactivateVendorIdInput) deactivateVendorIdInput.value = vendorId;
  if (deactivateVendorNameInput) deactivateVendorNameInput.value = vendorName || "";
  if (deactivateMakerCommentInput) deactivateMakerCommentInput.value = "";
  if (deactivateVendorMessage) deactivateVendorMessage.textContent = "";
  deactivateVendorModal.hidden = false;
  deactivateVendorModal.classList.add("approval-modal-visible");
};

const hideDeactivateVendorModal = () => {
  if (!deactivateVendorModal) return;
  deactivateVendorModal.hidden = true;
  deactivateVendorModal.classList.remove("approval-modal-visible");
};

const requestDeactivateVendor = async (vendorId, makerComment) => {
  try {
    const response = await fetch(`${apiBase}/api/vendors/requests/${vendorId}/deactivate`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...window.getAuthHeaders() },
      body: JSON.stringify({
        vendor_id: Number(vendorId),
        maker_id: currentUser().employeeId,
        reason: makerComment || undefined,
      }),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data?.detail || "Failed to submit request");
    }
    if (vendorMessage) {
      vendorMessage.textContent = "Deactivation request submitted for checker approval.";
      vendorMessage.style.color = "#0f4c81";
    }
    hideDeactivateVendorModal();
    loadVendors();
    loadVendorsForFormat();
  } catch (error) {
    if (deactivateVendorMessage) {
      deactivateVendorMessage.textContent = error.message || "Unable to submit request.";
      deactivateVendorMessage.style.color = "#b42318";
    }
  }
};

const getFilteredVendors = () => {
  const q = (vendorSearchInput?.value || "").trim().toLowerCase();
  if (!q) return vendorCache;
  return vendorCache.filter(
    (v) =>
      (v.name || "").toLowerCase().includes(q) ||
      (v.code || "").toLowerCase().includes(q)
  );
};

const beginEditVendor = (vendor) => {
  if (!vendorForm || !vendor) return;
  const nameInput = vendorForm.querySelector('[name="vendorName"]');
  const codeInput = vendorForm.querySelector('[name="vendorCode"]');
  const effectiveFromInput = vendorForm.querySelector('[name="effectiveFrom"]');
  const commentInput = vendorForm.querySelector('[name="makerComment"]');

  if (nameInput) nameInput.value = vendor.name || "";
  if (codeInput) codeInput.value = vendor.code || "";
  if (effectiveFromInput && !effectiveFromInput.value) {
    effectiveFromInput.value = new Date().toISOString().slice(0, 10);
  }
  if (commentInput) {
    commentInput.focus();
    commentInput.placeholder = "Enter maker comment for checker (update request)";
  }
  if (vendorSubmitBtn) vendorSubmitBtn.textContent = "Update Vendor";
  if (vendorMessage) {
    vendorMessage.textContent =
      "Edit mode enabled. Update values and submit request for checker approval.";
    vendorMessage.style.color = "#0f4c81";
  }
  vendorForm.scrollIntoView({ behavior: "smooth", block: "start" });
};

const buildStatusCell = (entity) => {
  const status = (entity.status || "").toUpperCase();
  const approval = (entity.approval_status || "").toUpperCase();
  const action = (entity.approval_action || "").toUpperCase();

  if (status === "ACTIVE") {
    if (approval === "PENDING" && action === "DEACTIVATE") {
      return { label: "Deactivation Pending", cls: "status-pending" };
    }
    return { label: "Active", cls: "status-active" };
  }
  if (status === "INACTIVE") {
    if (approval === "REJECTED") {
      return { label: "Rejected", cls: "status-rejected" };
    }
    if (approval === "PENDING" || approval === "CLARIFICATION") {
      return { label: "Pending Approval", cls: "status-pending" };
    }
    return { label: "Inactive", cls: "status-inactive" };
  }
  return { label: status || "-", cls: "status-inactive" };
};

const renderVendors = (vendors) => {
  if (!vendorRows) return;
  vendorRows.innerHTML = "";
  const cachedUser = sessionStorage.getItem("currentUser");
  const role = cachedUser ? (JSON.parse(cachedUser).role || "").toUpperCase() : "";
  const isChecker = role === "CHECKER";
  vendors.forEach((vendor) => {
    const statusInfo = buildStatusCell(vendor);
    const isRejected =
      (vendor.status || "").toUpperCase() === "INACTIVE" &&
      (vendor.approval_status || "").toUpperCase() === "REJECTED";
    const row = document.createElement("tr");

    const editBtn =
      !isChecker && vendor.status === "ACTIVE"
        ? `<button type="button" class="secondary-btn action-icon-btn" data-edit-vendor="${vendor.vendor_id}" title="Edit" aria-label="Edit"><span aria-hidden="true">✏</span></button>`
        : "";
    const inactiveBtn =
      !isChecker && vendor.status === "ACTIVE"
        ? `<button type="button" class="secondary-btn action-icon-btn action-icon-btn-danger" data-deactivate-vendor="${vendor.vendor_id}" title="Make Inactive" aria-label="Make Inactive"><span aria-hidden="true">✕</span></button>`
        : "";
    const eyeBtn = isRejected
      ? `<button type="button" class="secondary-btn action-icon-btn" data-view-checker="${vendor.vendor_id}" title="View checker comment" aria-label="View checker comment">${EYE_ICON}</button>`
      : "";

    row.innerHTML = `
      <td>${escapeHtml(vendor.name)}</td>
      <td>${escapeHtml(vendor.code)}</td>
      <td><span class="status-pill ${statusInfo.cls}">${escapeHtml(statusInfo.label)}</span></td>
      <td class="inline-actions">${eyeBtn}${editBtn}${inactiveBtn}</td>
    `;
    row.querySelector("[data-edit-vendor]")?.addEventListener("click", () => beginEditVendor(vendor));
    row.querySelector("[data-deactivate-vendor]")?.addEventListener("click", () =>
      showDeactivateVendorModal(vendor.vendor_id, vendor.name)
    );
    row.querySelector("[data-view-checker]")?.addEventListener("click", () =>
      showCheckerCommentModal(vendor)
    );
    vendorRows.appendChild(row);
  });
};

const loadVendors = async () => {
  if (!vendorRows) return;
  vendorRows.innerHTML = "";

  try {
    const response = await fetch(`${apiBase}/api/vendors?include_inactive=1`, {
      headers: window.getAuthHeaders(),
    });
    if (!response.ok) {
      throw new Error("Failed to load vendors");
    }
    vendorCache = await response.json();
    renderVendors(getFilteredVendors());
  } catch (error) {
    if (vendorMessage) {
      vendorMessage.textContent = "Unable to load vendors.";
      vendorMessage.style.color = "#b42318";
    }
  }
};

const loadClarifications = async () => {
  if (!clarificationRows) return;
  clarificationRows.innerHTML = "";
  clarificationMessage.textContent = "Loading clarifications...";
  clarificationMessage.style.color = "#0f4c81";

  try {
    const response = await fetch(`${apiBase}/api/approvals/clarifications`, {
      headers: window.getAuthHeaders(),
    });
    if (!response.ok) {
      throw new Error("Failed to load clarifications");
    }
    const items = await response.json();
    if (!items.length) {
      clarificationMessage.textContent = "No clarification requests.";
      return;
    }

    const cachedUser = sessionStorage.getItem("currentUser");
    const role = cachedUser ? (JSON.parse(cachedUser).role || "").toUpperCase() : "";
    const isChecker = role === "CHECKER";

    items.forEach((item) => {
      const row = document.createElement("tr");
      const history = formatHistory(item.comments_history);
      const canEdit = window.CLARIFICATION_EDITABLE_TYPES?.has(item.entity_type);
      const actionCells = isChecker
        ? `<td>-</td><td>-</td>`
        : `<td><input type="text" class="maker-reply" placeholder="Reply to checker" /></td>
           <td class="inline-actions">${
             canEdit
               ? `<button class="secondary-btn" data-edit-clarif>Edit</button>`
               : ""
           }<button class="secondary-btn" data-resubmit="${item.approval_id}">Resubmit</button></td>`;
      row.innerHTML = `
        <td>${escapeHtml(window.formatRequestRef(item.approval_id))}</td>
        <td>${escapeHtml(window.formatEntityType ? window.formatEntityType(item.entity_type) : item.entity_type)}</td>
        <td>${escapeHtml(item.status)}</td>
        <td>${escapeHtml(item.reason ?? "")}</td>
        <td>${escapeHtml(item.checker_comment ?? "")}</td>
        <td>${history}</td>
        ${actionCells}
      `;
      if (isChecker) {
        clarificationRows.appendChild(row);
        return;
      }
      row.querySelector("[data-edit-clarif]")?.addEventListener("click", () => {
        window.clarificationEditAndResubmit(item, loadClarifications);
      });
      row.querySelector("[data-resubmit]").addEventListener("click", async () => {
        const reply = row.querySelector(".maker-reply").value.trim();
        if (!reply) {
          clarificationMessage.textContent = "Reply comment required.";
          clarificationMessage.style.color = "#b42318";
          return;
        }
        try {
          const res = await fetch(`${apiBase}/api/approvals/${item.approval_id}/resubmit`, {
            method: "POST",
            headers: { "Content-Type": "application/json", ...window.getAuthHeaders() },
            body: JSON.stringify({ comment: reply }),
          });
          if (!res.ok) {
            throw new Error("Resubmit failed");
          }
          clarificationMessage.textContent = "Resubmitted to checker.";
          clarificationMessage.style.color = "#0f4c81";
          loadClarifications();
        } catch (error) {
          clarificationMessage.textContent = "Unable to resubmit.";
          clarificationMessage.style.color = "#b42318";
        }
      });
      clarificationRows.appendChild(row);
    });

    clarificationMessage.textContent = "";
  } catch (error) {
    clarificationMessage.textContent = "Unable to load clarifications.";
    clarificationMessage.style.color = "#b42318";
  }
};

const submitVendor = async (event) => {
  event.preventDefault();
  if (!vendorForm) return;

  const formData = new FormData(vendorForm);
  const name = formData.get("vendorName").trim();
  const code = formData.get("vendorCode").trim();
  const effectiveFrom = formData.get("effectiveFrom");
  const makerComment = formData.get("makerComment").trim();

  if (!name || !code || !effectiveFrom || !makerComment) {
    vendorMessage.textContent = "Please enter vendor name, code, date, and comment.";
    vendorMessage.style.color = "#b42318";
    return;
  }

  vendorMessage.textContent = "Saving vendor...";
  vendorMessage.style.color = "#0f4c81";

  try {
    const response = await fetch(`${apiBase}/api/vendors`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...window.getAuthHeaders() },
      body: JSON.stringify({
        vendor_name: name,
        vendor_code: code,
        status: "INACTIVE",
        effective_from: effectiveFrom,
        reason: makerComment,
        maker_id: sessionStorage.getItem("currentUser")
          ? JSON.parse(sessionStorage.getItem("currentUser")).employeeId
          : "SYSTEM",
      }),
    });

    if (!response.ok) {
      if (response.status === 403) {
        vendorMessage.textContent =
          "You do not have permission to add or edit vendors. Checkers can only review and approve requests.";
        vendorMessage.style.color = "#b42318";
        return;
      }
      if (response.status === 401) {
        vendorMessage.textContent = "Session expired. Please login again.";
        vendorMessage.style.color = "#b42318";
        return;
      }
      let detail = "";
      try {
        const payload = await response.json();
        detail = payload?.detail || "";
      } catch (error) {
        detail = "";
      }
      vendorMessage.textContent = detail || "Unable to save vendor.";
      vendorMessage.style.color = "#b42318";
      return;
    }

    vendorMessage.textContent = "Vendor request submitted for approval.";
    vendorForm.reset();
    loadVendors();
  } catch (error) {
    if (!vendorMessage.textContent) {
      vendorMessage.textContent = "Unable to save vendor.";
    }
    vendorMessage.style.color = "#b42318";
  }
};

const submitVoFormatForm = async (event) => {
  event.preventDefault();
  if (!voFormatForm || !voFormatMessage) return;
  const formData = new FormData(voFormatForm);
  const vendorId = formData.get("vendorId");
  const formatName = formData.get("formatName");
  const headerMapping = formData.get("headerMapping");
  const effectiveFrom = formData.get("effectiveFrom");
  const makerComment = formData.get("makerComment") || "";

  if (!vendorId || !formatName || !headerMapping || !effectiveFrom) {
    voFormatMessage.textContent = "Please fill vendor, format name, header mapping, and effective from.";
    voFormatMessage.style.color = "#b42318";
    return;
  }

  voFormatMessage.textContent = "Submitting...";
  voFormatMessage.style.color = "#0f4c81";

  try {
    const response = await fetch(`${apiBase}/api/vendor-file-formats/requests`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...window.getAuthHeaders() },
      body: JSON.stringify({
        vendor_id: Number(vendorId),
        format_name: formatName,
        header_mapping_json: headerMapping,
        effective_from: effectiveFrom,
        status: "ACTIVE",
        maker_id: currentUser().employeeId,
        reason: makerComment || undefined,
      }),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data?.detail || "Request failed");
    }
    voFormatMessage.textContent = "Request submitted for approval.";
    voFormatMessage.style.color = "#0f4c81";
    voFormatForm.reset();
    hideFileConfigModal();
  } catch (error) {
    voFormatMessage.textContent = error.message || "Request failed.";
    voFormatMessage.style.color = "#b42318";
  }
};

const init = () => {
  if (!vendorForm) return;
  vendorForm.addEventListener("submit", submitVendor);
  loadVendors();
  loadClarifications();

  vendorSearchInput?.addEventListener("input", () => {
    renderVendors(getFilteredVendors());
  });

  /* Checker comment (eye-icon) modal */
  if (checkerModal) {
    checkerModal.querySelector(".approval-modal-backdrop")?.addEventListener("click", hideCheckerCommentModal);
    checkerModal.querySelector(".approval-modal-close")?.addEventListener("click", hideCheckerCommentModal);
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && checkerModal.classList.contains("approval-modal-visible")) {
        hideCheckerCommentModal();
      }
    });
  }

  /* Vendor File Format Config modal */
  if (fileConfigBtn) {
    fileConfigBtn.addEventListener("click", showFileConfigModal);
  }
  if (fileConfigModal) {
    fileConfigModal.querySelector(".approval-modal-backdrop")?.addEventListener("click", hideFileConfigModal);
    fileConfigModal.querySelector(".approval-modal-close")?.addEventListener("click", hideFileConfigModal);
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && fileConfigModal.classList.contains("approval-modal-visible")) {
        hideFileConfigModal();
      }
    });
  }
  if (deactivateVendorForm) {
    deactivateVendorForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const vendorId = deactivateVendorIdInput?.value;
      const comment = deactivateMakerCommentInput?.value?.trim();
      if (!vendorId || !comment) {
        if (deactivateVendorMessage) {
          deactivateVendorMessage.textContent = "Maker comment is required.";
          deactivateVendorMessage.style.color = "#b42318";
        }
        return;
      }
      deactivateVendorMessage.textContent = "Submitting...";
      deactivateVendorMessage.style.color = "#0f4c81";
      await requestDeactivateVendor(vendorId, comment);
    });
  }
  if (deactivateVendorModal) {
    deactivateVendorModal.querySelector(".approval-modal-backdrop")?.addEventListener("click", hideDeactivateVendorModal);
    deactivateVendorModal.querySelector(".approval-modal-close")?.addEventListener("click", hideDeactivateVendorModal);
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && deactivateVendorModal.classList.contains("approval-modal-visible")) {
        hideDeactivateVendorModal();
      }
    });
  }
  if (voFormatVendorSelect) {
    voFormatVendorSelect.addEventListener("change", () => {
      loadVoExistingFormats(voFormatVendorSelect.value || "");
    });
  }
  if (voFormatForm) {
    voFormatForm.addEventListener("submit", submitVoFormatForm);
  }
  if (voGenerateBtn) {
    voGenerateBtn.addEventListener("click", voGenerateMappingJson);
  }
  if (voSampleInput) {
    voSampleInput.addEventListener("change", async (event) => {
      const file = event.target.files[0];
      if (!file || !window.XLSX) return;
      try {
        const data = await file.arrayBuffer();
        const workbook = window.XLSX.read(data, { type: "array" });
        const sheetName = workbook.SheetNames[0];
        const sheetData = workbook.Sheets[sheetName];
        const rows = window.XLSX.utils.sheet_to_json(sheetData, { header: 1 });
        const headerRow = rows[0] || [];
        voHeaderOptions = headerRow.map((c) => String(c || "").trim()).filter(Boolean);
        voUpdateMappingSelectOptions();
      } catch (_) {
        voHeaderOptions = [];
        voUpdateMappingSelectOptions();
      }
    });
  }
};

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
