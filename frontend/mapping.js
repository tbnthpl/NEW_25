const form = document.querySelector("#mapping-form");
const rowsContainer = document.querySelector("#mapping-rows");
const bulkMappingForm = document.querySelector("#bulk-mapping-form");
const bulkMappingFile = document.querySelector("#bulk-mapping-file");
const bulkMappingMessage = document.querySelector("#bulk-mapping-message");
const listRowsContainer = document.querySelector("#mapping-list-rows");
const addRowButton = document.querySelector("#add-row");
const message = document.querySelector("#mapping-message");
const clarificationRows = document.querySelector("#clarification-rows");
const clarificationMessage = document.querySelector("#clarification-message");
const apiBase = window.API_BASE || "";
let vendorOptions = [];
let storeOptions = [];
let mappingsCache = [];
const escapeHtml = window.escapeHtml || ((value) => String(value ?? ""));

const MAP_EYE_ICON =
  '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8S1 12 1 12z"/><circle cx="12" cy="12" r="3"/></svg>';

const formatTs = (iso) => {
  if (!iso) return "";
  return (window.formatDateTime || ((s) => String(s)))(iso);
};

const checkerModal = document.querySelector("#checker-comment-modal");
const showCheckerCommentModal = (entity) => {
  if (!checkerModal) return;
  const set = (id, value) => {
    const el = checkerModal.querySelector(`#${id}`);
    if (el) el.textContent = value || "-";
  };
  set("checker-comment-decision", entity.approval_status || "");
  set("checker-comment-checker", entity.checker_id || "");
  set("checker-comment-decided-at", formatTs(entity.approval_decided_at));
  set("checker-comment-maker", entity.maker_id || "");
  set("checker-comment-created-at", formatTs(entity.approval_created_at));
  set("checker-comment-text", entity.checker_comment || "");
  checkerModal.hidden = false;
  checkerModal.classList.add("approval-modal-visible");
};
const hideCheckerCommentModal = () => {
  if (!checkerModal) return;
  checkerModal.hidden = true;
  checkerModal.classList.remove("approval-modal-visible");
};

const buildMappingStatusCell = (row) => {
  const status = (row.status || "").toUpperCase();
  const approval = (row.approval_status || "").toUpperCase();
  const action = (row.approval_action || "").toUpperCase();
  if (status === "ACTIVE") {
    if (approval === "PENDING" && action === "DEACTIVATE") {
      return { label: "Deletion Pending", cls: "status-pending" };
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
const currentUser = () =>
  sessionStorage.getItem("currentUser")
    ? JSON.parse(sessionStorage.getItem("currentUser"))
    : { employeeId: "SYSTEM" };

const loadVendors = async () => {
  try {
    const response = await fetch(`${apiBase}/api/vendors`, {
      headers: window.getAuthHeaders(),
    });
    if (!response.ok) {
      throw new Error("Failed to load vendors");
    }
    const vendors = await response.json();
    vendorOptions = vendors.map((vendor) => ({
      id: vendor.vendor_id,
      label: `${vendor.name} (${vendor.code})`,
    }));
  } catch (error) {
    vendorOptions = [];
  }
};

const loadStores = async () => {
  try {
    const response = await fetch(`${apiBase}/api/bank-stores`, {
      headers: window.getAuthHeaders(),
    });
    if (!response.ok) {
      throw new Error("Failed to load stores");
    }
    const stores = await response.json();
    storeOptions = stores.map((store) => ({
      bank_store_code: store.bank_store_code,
      store_name: store.store_name || "",
      customer_id: store.customer_id || "",
      customer_name: store.customer_name || "",
      account_no: store.account_no || "",
      label: `${store.bank_store_code}${store.store_name ? ` - ${store.store_name}` : ""}`,
    }));
  } catch (error) {
    storeOptions = [];
  }
};

const createInput = (placeholder) => {
  const input = document.createElement("input");
  input.type = "text";
  input.placeholder = placeholder;
  return input;
};

const createVendorSelect = (selectedId) => {
  const select = document.createElement("select");
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "Select vendor";
  select.appendChild(placeholder);
  vendorOptions.forEach((vendor) => {
    const option = document.createElement("option");
    option.value = vendor.id;
    option.textContent = vendor.label;
    if (String(selectedId) === String(vendor.id)) {
      option.selected = true;
    }
    select.appendChild(option);
  });
  return select;
};

const createBankStoreSelect = (selectedCode, customerIdInput, customerNameInput, accountNoInput) => {
  const select = document.createElement("select");
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = storeOptions.length ? "Select bank store" : "No stores – onboard first";
  select.appendChild(placeholder);
  if (selectedCode && !storeOptions.some((s) => s.bank_store_code === selectedCode)) {
    const legacyOpt = document.createElement("option");
    legacyOpt.value = selectedCode;
    legacyOpt.textContent = `${selectedCode} (not in active list)`;
    legacyOpt.dataset.customerId = "";
    legacyOpt.dataset.customerName = "";
    legacyOpt.dataset.accountNo = "";
    select.appendChild(legacyOpt);
  }
  storeOptions.forEach((store) => {
    const option = document.createElement("option");
    option.value = store.bank_store_code;
    option.textContent = store.label;
    option.dataset.customerId = store.customer_id;
    option.dataset.customerName = store.customer_name;
    option.dataset.accountNo = store.account_no;
    if (selectedCode && store.bank_store_code === selectedCode) {
      option.selected = true;
    }
    select.appendChild(option);
  });
  select.addEventListener("change", () => {
    const opt = select.options[select.selectedIndex];
    if (opt && opt.value && customerIdInput && customerNameInput && accountNoInput) {
      customerIdInput.value = opt.dataset.customerId || "";
      customerNameInput.value = opt.dataset.customerName || "";
      accountNoInput.value = opt.dataset.accountNo || "";
    }
  });
  return select;
};

const getVendorLabel = (vendorId) => {
  const match = vendorOptions.find((vendor) => String(vendor.id) === String(vendorId));
  return match ? match.label : vendorId ?? "";
};

const formatToInputDate = (value) => {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return String(value).slice(0, 10);
  }
  return parsed.toISOString().slice(0, 10);
};

const createFieldBlock = (labelText, control) => {
  const block = document.createElement("label");
  block.className = "field";
  const span = document.createElement("span");
  span.className = "label";
  span.textContent = labelText;
  block.appendChild(span);
  block.appendChild(control);
  return block;
};

const buildRow = (row = {}) => {
  const block = document.createElement("div");
  block.className = "mapping-row-block";

  const customerIdInput = createInput("Customer ID");
  customerIdInput.value = row.customer_id || "";
  customerIdInput.dataset.field = "customer_id";

  const customerNameInput = createInput("Customer name");
  customerNameInput.value = row.customer_name || "";
  customerNameInput.dataset.field = "customer_name";

  const accountNoInput = createInput("Account number");
  accountNoInput.value = row.account_no || "";
  accountNoInput.dataset.field = "account_no";

  const vendorSelect = createVendorSelect(row.vendor_id);
  vendorSelect.dataset.field = "vendor";

  const bankStoreSelect = createBankStoreSelect(
    row.bank_store_code,
    customerIdInput,
    customerNameInput,
    accountNoInput,
  );
  bankStoreSelect.dataset.field = "bank_store";
  if (row.bank_store_code && storeOptions.length) {
    const store = storeOptions.find((s) => s.bank_store_code === row.bank_store_code);
    if (store) {
      customerIdInput.value = row.customer_id ?? store.customer_id;
      customerNameInput.value = row.customer_name ?? store.customer_name;
      accountNoInput.value = row.account_no ?? store.account_no;
    }
  }

  const vendorStoreInput = createInput("Vendor store code");
  vendorStoreInput.value = row.vendor_store_code || "";
  vendorStoreInput.dataset.field = "vendor_store";

  const effectiveFromInput = document.createElement("input");
  effectiveFromInput.type = "date";
  effectiveFromInput.value = formatToInputDate(row.effective_from);
  effectiveFromInput.dataset.field = "effective_from";

  const commentTextarea = document.createElement("textarea");
  commentTextarea.rows = 2;
  commentTextarea.placeholder = "Maker comment for this mapping";
  commentTextarea.value = row.comment || "";
  commentTextarea.dataset.field = "comment";

  block.append(
    createFieldBlock("Vendor", vendorSelect),
    createFieldBlock("Bank Store Code", bankStoreSelect),
    createFieldBlock("Vendor Store Code", vendorStoreInput),
    createFieldBlock("Customer ID", customerIdInput),
    createFieldBlock("Customer Name", customerNameInput),
    createFieldBlock("Account No", accountNoInput),
    createFieldBlock("Effective From", effectiveFromInput),
    createFieldBlock("Comment", commentTextarea),
  );

  return block;
};


const loadRows = async () => {
  rowsContainer.innerHTML = "";
  rowsContainer.appendChild(buildRow());
};

const loadMappingsList = async () => {
  if (!listRowsContainer) return;
  listRowsContainer.innerHTML = "";
  try {
    const response = await fetch(`${apiBase}/api/store-mappings?include_inactive=1`, {
      headers: window.getAuthHeaders(),
    });
    if (!response.ok) {
      throw new Error("Failed to load mappings");
    }
    const mappings = await response.json();
    mappingsCache = mappings || [];
    if (!mappingsCache.length) {
      return;
    }
    mappingsCache.forEach((row, index) => {
      const tr = document.createElement("tr");
      const statusValue = (row.status || "").toUpperCase();
      const approvalStatus = (row.approval_status || "").toUpperCase();
      const isRejected = statusValue === "INACTIVE" && approvalStatus === "REJECTED";
      const statusInfo = buildMappingStatusCell(row);
      const deleteDisabled = statusValue === "INACTIVE" ? "disabled" : "";
      const requestId =
        row.approval_id != null && row.approval_id !== ""
          ? window.formatRequestRef(row.approval_id)
          : row.mapping_id ?? "";

      const eyeBtn = isRejected
        ? `<button class="secondary-btn action-icon-btn" type="button" data-view-checker-index="${index}" title="View checker comment" aria-label="View checker comment">${MAP_EYE_ICON}</button>`
        : "";
      // Edit is hidden on REJECTED rows - pre-filling that form would amount to
      // a silent re-submit, and the bank wants rejected requests to stay
      // read-only history. The maker can still raise a fresh mapping via the
      // top-of-page form.
      const editBtn = isRejected
        ? ""
        : `<button class="secondary-btn action-icon-btn" type="button" data-edit-index="${index}" title="Edit" aria-label="Edit"><span aria-hidden="true">✏</span></button>`;

      tr.innerHTML = `
        <td>${escapeHtml(requestId)}</td>
        <td>${escapeHtml(getVendorLabel(row.vendor_id))}</td>
        <td>${escapeHtml(row.bank_store_code ?? "")}</td>
        <td>${escapeHtml(row.vendor_store_code ?? "")}</td>
        <td>${escapeHtml(row.customer_id ?? "")}</td>
        <td>${escapeHtml(row.customer_name ?? "")}</td>
        <td>${escapeHtml(row.account_no ?? "")}</td>
        <td>${escapeHtml(row.effective_from ?? "")}</td>
        <td><span class="status-pill ${statusInfo.cls}">${escapeHtml(statusInfo.label)}</span></td>
        <td>
          ${eyeBtn}
          ${editBtn}
          <button class="secondary-btn action-icon-btn" type="button" data-delete-index="${index}" ${deleteDisabled} title="Delete" aria-label="Delete"><span aria-hidden="true">✕</span></button>
        </td>
      `;
      listRowsContainer.appendChild(tr);
    });
  } catch (error) {
    message.textContent = "Unable to load mappings list.";
    message.style.color = "#b42318";
  }
};

const collectRows = () => {
  const rows = [];
  rowsContainer.querySelectorAll(".mapping-row-block").forEach((block) => {
    const vendorSelect = block.querySelector('select[data-field="vendor"]');
    const bankStoreSelect = block.querySelector('select[data-field="bank_store"]');
    const vendorStoreInput = block.querySelector('input[data-field="vendor_store"]');
    const customerIdInput = block.querySelector('input[data-field="customer_id"]');
    const customerNameInput = block.querySelector('input[data-field="customer_name"]');
    const accountNoInput = block.querySelector('input[data-field="account_no"]');
    const effectiveFromInput = block.querySelector('input[data-field="effective_from"]');
    const commentInput = block.querySelector('[data-field="comment"]');

    const row = {
      vendor_id: vendorSelect?.value ? Number(vendorSelect.value) : null,
      bank_store_code: bankStoreSelect?.value?.trim() || "",
      vendor_store_code: vendorStoreInput?.value?.trim() || "",
      customer_id: customerIdInput?.value?.trim() || "",
      customer_name: customerNameInput?.value?.trim() || "",
      account_no: accountNoInput?.value?.trim() || "",
      effective_from: effectiveFromInput?.value || null,
      comment: commentInput?.value?.trim() || "",
    };

    const hasData = [row.vendor_id, row.bank_store_code, row.vendor_store_code].some((v) => v);
    if (hasData) {
      rows.push(row);
    }
  });
  return rows;
};

const buildReasonFromRows = (rows) => {
  const parts = rows.map((r, i) => {
    const label = `Row ${i + 1} (${getVendorLabel(r.vendor_id)} - ${r.bank_store_code || r.vendor_store_code || "?"})`;
    const comment = (r.comment || "").trim();
    return comment ? `${label}: ${comment}` : label + ": (no comment)";
  });
  return parts.join("; ");
};

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
    const filtered = items.filter((item) => item.entity_type === "STORE_MAPPING");
    if (!filtered.length) {
      clarificationMessage.textContent = "No clarification requests.";
      return;
    }

    const cachedUser = sessionStorage.getItem("currentUser");
    const role = cachedUser ? (JSON.parse(cachedUser).role || "").toUpperCase() : "";
    const isChecker = role === "CHECKER";

    filtered.forEach((item) => {
      const row = document.createElement("tr");
      const history = formatHistory(item.comments_history);
      const canEdit = window.CLARIFICATION_EDITABLE_TYPES?.has(item.entity_type);
      const actionCells = isChecker
        ? `<td>-</td><td>-</td>`
        : `<td><input type="text" class="maker-reply" placeholder="Reply to checker" /></td>
           <td class="inline-actions">${
             canEdit ? `<button class="secondary-btn" data-edit-clarif>Edit</button>` : ""
           }<button class="secondary-btn" data-resubmit="${item.approval_id}">Resubmit</button></td>`;
      row.innerHTML = `
        <td>${escapeHtml(window.formatRequestRef(item.approval_id))}</td>
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

window.addMappingRow = () => {
  if (!rowsContainer) return;
  rowsContainer.appendChild(buildRow());
};

const bindEditMapping = () => {
  if (!listRowsContainer || !rowsContainer) return;
  listRowsContainer.addEventListener("click", (event) => {
    const viewBtn = event.target.closest("button[data-view-checker-index]");
    if (viewBtn) {
      const idx = Number(viewBtn.dataset.viewCheckerIndex);
      const row = mappingsCache[idx];
      if (row) showCheckerCommentModal(row);
      return;
    }

    const editBtn = event.target.closest("button[data-edit-index]");
    if (!editBtn) return;
    const index = Number(editBtn.dataset.editIndex);
    const row = mappingsCache[index];
    if (!row) return;
    rowsContainer.innerHTML = "";
    rowsContainer.appendChild(buildRow(row));
    rowsContainer.scrollIntoView({ behavior: "smooth" });
  });
};

const bindDeleteMapping = () => {
  if (!listRowsContainer) return;
  listRowsContainer.addEventListener("click", async (event) => {
    const deleteButton = event.target.closest("button[data-delete-index]");
    if (!deleteButton) return;
    const index = Number(deleteButton.dataset.deleteIndex);
    const row = mappingsCache[index];
    if (!row) return;
    const reason = window.prompt("Enter maker comment for delete request:");
    if (!reason || !reason.trim()) {
      message.textContent = "Maker comment is required for delete request.";
      message.style.color = "#b42318";
      return;
    }
    message.textContent = "Submitting delete request...";
    message.style.color = "#0f4c81";
    try {
      const response = await fetch(
        `${apiBase}/api/store-mappings/requests/${row.mapping_id}/deactivate`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json", ...window.getAuthHeaders() },
          body: JSON.stringify({
            maker_id: currentUser().employeeId,
            reason: reason.trim(),
          }),
        },
      );
      if (!response.ok) {
        let detail = "";
        try {
          const data = await response.json();
          detail = data?.detail || "";
        } catch (error) {
          detail = "";
        }
        throw new Error(detail || "Delete request failed");
      }
      message.textContent = "Delete request submitted for approval.";
      message.style.color = "#0f4c81";
      loadMappingsList();
    } catch (error) {
      message.textContent = error.message || "Unable to submit delete request.";
      message.style.color = "#b42318";
    }
  });
};

const bindAddRow = () => {
  if (!addRowButton) return;
  addRowButton.addEventListener("click", (event) => {
    event.preventDefault();
    window.addMappingRow();
  });
};

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const rows = collectRows();

  if (!rows.length) {
    message.textContent = "Add at least one mapping row before saving.";
    message.style.color = "#b42318";
    return;
  }

  const reason = buildReasonFromRows(rows);
  const mappingsForApi = rows.map(({ comment, ...rest }) => rest);

  message.textContent = "Saving store mapping...";
  message.style.color = "#0f4c81";

  try {
    const response = await fetch(`${apiBase}/api/store-mappings/requests`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...window.getAuthHeaders() },
      body: JSON.stringify({
        mappings: mappingsForApi,
        reason,
        maker_id: sessionStorage.getItem("currentUser")
          ? JSON.parse(sessionStorage.getItem("currentUser")).employeeId
          : "SYSTEM",
      }),
    });

    if (!response.ok) {
      if (response.status === 401 || response.status === 403) {
        message.textContent = "Session expired or user inactive. Please login again.";
      }
      throw new Error("Save failed");
    }

    message.textContent = "Store mapping saved. Ready for reconciliation.";
    loadMappingsList();
  } catch (error) {
    if (!message.textContent || message.textContent.includes("Saving")) {
      message.textContent = "Unable to save mappings.";
    }
    message.style.color = "#b42318";
  }
});

const submitBulkMappings = async (e) => {
  e.preventDefault();
  if (!bulkMappingForm || !bulkMappingFile?.files?.length) return;
  bulkMappingMessage.textContent = "Uploading...";
  bulkMappingMessage.style.color = "#0f4c81";
  try {
    const fd = new FormData();
    fd.append("file", bulkMappingFile.files[0]);
    const response = await fetch(`${apiBase}/api/store-mappings/bulk`, {
      method: "POST",
      headers: window.getAuthHeaders(),
      body: fd,
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data?.detail || "Bulk upload failed");
    }
    const data = await response.json();
    bulkMappingMessage.textContent = `Created: ${data.created}, Skipped: ${data.skipped}${data.errors?.length ? `. Errors: ${JSON.stringify(data.errors.slice(0, 5))}` : ""}`;
    bulkMappingMessage.style.color = "#0f4c81";
    bulkMappingForm.reset();
    loadMappingsList();
  } catch (error) {
    bulkMappingMessage.textContent = error.message || "Bulk upload failed.";
    bulkMappingMessage.style.color = "#b42318";
  }
};

const init = async () => {
  if (!rowsContainer || !form) {
    return;
  }
  bindAddRow();
  bindEditMapping();
  bindDeleteMapping();

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
  if (bulkMappingForm) bulkMappingForm.addEventListener("submit", submitBulkMappings);
  document.querySelector("#bulk-mapping-download-template")?.addEventListener("click", async () => {
    try {
      await window.downloadStaticFile("bulk_mappings_template.xlsx", "bulk_mappings_template.xlsx");
    } catch (error) {
      if (bulkMappingMessage) {
        bulkMappingMessage.textContent = error.message || "Unable to download template.";
        bulkMappingMessage.style.color = "#b42318";
      }
    }
  });
  await Promise.all([loadVendors(), loadStores()]);
  loadRows();
  loadClarifications();
  loadMappingsList();
};

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
