const storeForm = document.querySelector("#store-form");
const storeMessage = document.querySelector("#store-message");
const bulkStoreForm = document.querySelector("#bulk-store-form");
const bulkStoreFile = document.querySelector("#bulk-store-file");
const bulkStoreMessage = document.querySelector("#bulk-store-message");
const storeRows = document.querySelector("#store-rows");
const storeSearchInput = document.querySelector("#store-search");
const storeStatusFilter = document.querySelector("#store-status-filter");
const storeVendorFilter = document.querySelector("#store-vendor-filter");
const storeDownloadBtn = document.querySelector("#store-download-btn");
const clarificationRows = document.querySelector("#clarification-rows");
const clarificationMessage = document.querySelector("#clarification-message");
const apiBase = window.API_BASE || "";
let storeCache = [];
let vendorStoreCodesByVendorId = new Map();
const escapeHtml = window.escapeHtml || ((value) => String(value ?? ""));

const STORE_EYE_ICON =
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

const buildStoreStatusCell = (entity) => {
  const status = (entity.status || "").toUpperCase();
  const approval = (entity.approval_status || "").toUpperCase();
  const action = (entity.approval_action || "").toUpperCase();
  if (status === "ACTIVE") {
    if (approval === "PENDING" && action === "DEACTIVATE") {
      return { label: "Deactivation Pending", cls: "status-pending" };
    }
    if (approval === "PENDING" && action === "UPDATE") {
      return { label: "Update Pending", cls: "status-pending" };
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

const deactivateStoreModal = document.querySelector("#deactivate-store-modal");
const deactivateStoreForm = document.querySelector("#deactivate-store-form");
const deactivateStoreIdInput = document.querySelector("#deactivate-store-id");
const deactivateStoreNameInput = document.querySelector("#deactivate-store-name");
const deactivateStoreMakerCommentInput = document.querySelector("#deactivate-store-maker-comment");
const deactivateStoreMessage = document.querySelector("#deactivate-store-message");
const editingStoreIdInput = document.querySelector("#editing-store-id");
const storeSubmitBtn = document.querySelector("#store-submit-btn");
const storeCancelEditBtn = document.querySelector("#store-cancel-edit-btn");
const storePickupTypeSelect = document.querySelector("#store-pickup-type");
const storeBeatPricing = document.querySelector("#store-beat-pricing");
const storeCallPricing = document.querySelector("#store-call-pricing");

const getEditingStoreId = () => (editingStoreIdInput?.value || "").trim();

const syncStorePickupPricingVisibility = () => {
  if (!storePickupTypeSelect || !storeBeatPricing || !storeCallPricing) return;
  const isCall = storePickupTypeSelect.value === "CALL";
  storeBeatPricing.hidden = isCall;
  storeCallPricing.hidden = !isCall;
};

const setStoreEditMode = (storeId) => {
  if (editingStoreIdInput) editingStoreIdInput.value = storeId ? String(storeId) : "";
  if (storeSubmitBtn) storeSubmitBtn.textContent = storeId ? "Submit change for approval" : "Add Store";
  if (storeCancelEditBtn) storeCancelEditBtn.hidden = !storeId;
};

const fillStoreFormFromStore = (store) => {
  if (!storeForm) return;
  const ef = store.effective_from ? new Date(store.effective_from).toISOString().slice(0, 10) : "";
  storeForm.querySelector('[name="bankStoreCode"]').value = store.bank_store_code ?? "";
  storeForm.querySelector('[name="storeName"]').value = store.store_name ?? "";
  storeForm.querySelector('[name="customerId"]').value = store.customer_id ?? "";
  storeForm.querySelector('[name="customerName"]').value = store.customer_name ?? "";
  storeForm.querySelector('[name="accountNo"]').value = store.account_no ?? "";
  const pt = store.pickup_type || "BEAT";
  storeForm.querySelector('[name="pickupType"]').value = pt;
  syncStorePickupPricingVisibility();
  const setNumInput = (name, val) => {
    const el = storeForm.querySelector(`[name="${name}"]`);
    if (!el) return;
    el.value = val != null && val !== "" && !Number.isNaN(Number(val)) ? String(val) : "";
  };
  if (pt === "CALL") {
    setNumInput("dailyPickupLimit", null);
    setNumInput("monthlyBankCharge", null);
    setNumInput("monthlyVendorCharge", null);
    setNumInput("callIncludedPickups", store.call_included_pickups);
    setNumInput("callMonthlyBankCharge", store.call_monthly_bank_charge);
    setNumInput("callAdditionalBankPerPickup", store.call_additional_bank_per_pickup);
    setNumInput("callVendorPayPerPickup", store.call_vendor_pay_per_pickup);
  } else {
    setNumInput("callIncludedPickups", null);
    setNumInput("callMonthlyBankCharge", null);
    setNumInput("callAdditionalBankPerPickup", null);
    setNumInput("callVendorPayPerPickup", null);
    setNumInput("dailyPickupLimit", store.daily_pickup_limit);
    setNumInput("monthlyBankCharge", store.fixed_charge);
    setNumInput("monthlyVendorCharge", store.vendor_charge);
  }
  const wv = store.waiver_percentage;
  storeForm.querySelector('[name="waiverPercentage"]').value =
    wv != null && wv !== "" && !Number.isNaN(Number(wv)) ? String(wv) : "";
  const wc = store.waiver_cap_amount;
  storeForm.querySelector('[name="waiverCapAmount"]').value =
    wc != null && wc !== "" && !Number.isNaN(Number(wc)) ? String(wc) : "";
  const wcf = store.waiver_cap_from ? new Date(store.waiver_cap_from).toISOString().slice(0, 10) : "";
  const wct = store.waiver_cap_to ? new Date(store.waiver_cap_to).toISOString().slice(0, 10) : "";
  storeForm.querySelector('[name="waiverCapFrom"]').value = wcf;
  storeForm.querySelector('[name="waiverCapTo"]').value = wct;
  storeForm.querySelector('[name="effectiveFrom"]').value = ef;
  storeForm.querySelector('[name="makerComment"]').value = "";
};

const cancelStoreEdit = () => {
  setStoreEditMode(null);
  storeForm?.reset();
  syncStorePickupPricingVisibility();
  if (storeMessage) {
    storeMessage.textContent = "";
  }
};

const beginEditStore = (store) => {
  fillStoreFormFromStore(store);
  setStoreEditMode(String(store.store_id));
  storeForm?.scrollIntoView({ behavior: "smooth", block: "start" });
};

const showDeactivateStoreModal = (storeId, storeLabel) => {
  if (!deactivateStoreModal) return;
  if (deactivateStoreIdInput) deactivateStoreIdInput.value = storeId;
  if (deactivateStoreNameInput) deactivateStoreNameInput.value = storeLabel || "";
  if (deactivateStoreMakerCommentInput) deactivateStoreMakerCommentInput.value = "";
  if (deactivateStoreMessage) deactivateStoreMessage.textContent = "";
  deactivateStoreModal.hidden = false;
  deactivateStoreModal.classList.add("approval-modal-visible");
};

const hideDeactivateStoreModal = () => {
  if (!deactivateStoreModal) return;
  deactivateStoreModal.hidden = true;
  deactivateStoreModal.classList.remove("approval-modal-visible");
};

const requestDeactivateStore = async (storeId, makerComment) => {
  try {
    const response = await fetch(`${apiBase}/api/bank-stores/requests/${storeId}/deactivate`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...window.getAuthHeaders() },
      body: JSON.stringify({
        store_id: Number(storeId),
        maker_id: currentUser().employeeId,
        reason: makerComment || undefined,
      }),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data?.detail || "Failed to submit request");
    }
    if (storeMessage) {
      storeMessage.textContent = "Deactivation request submitted for checker approval.";
      storeMessage.style.color = "#0f4c81";
    }
    hideDeactivateStoreModal();
    loadStores();
  } catch (error) {
    if (deactivateStoreMessage) {
      deactivateStoreMessage.textContent = error.message || "Unable to submit request.";
      deactivateStoreMessage.style.color = "#b42318";
    }
  }
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

const getFilteredStores = () => {
  let list = storeCache;
  const statusFilter = storeStatusFilter?.value || "";
  if (statusFilter) {
    list = list.filter((s) => s.status === statusFilter);
  }
  const vendorId = (storeVendorFilter?.value || "").trim();
  if (vendorId) {
    const mappedCodes = vendorStoreCodesByVendorId.get(vendorId) || new Set();
    list = list.filter((s) => mappedCodes.has(String(s.bank_store_code ?? "")));
  }
  const q = (storeSearchInput?.value || "").trim().toLowerCase();
  if (q) {
    list = list.filter(
      (s) =>
        (s.bank_store_code || "").toLowerCase().includes(q) ||
        (s.store_name || "").toLowerCase().includes(q)
    );
  }
  return list;
};

const fmtYmd = (v) => {
  if (!v) return "";
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return "";
  return d.toISOString().slice(0, 10);
};

const fmtYmdHmIst = (v) => {
  if (!v) return "";
  return (window.formatDateTime || ((s) => String(s)))(v);
};

const renderStores = (stores) => {
  if (!storeRows) return;
  storeRows.innerHTML = "";
  const isChecker = (currentUser().role || "").toUpperCase() === "CHECKER";
  stores.forEach((store) => {
    const statusInfo = buildStoreStatusCell(store);
    const isRejected =
      (store.status || "").toUpperCase() === "INACTIVE" &&
      (store.approval_status || "").toUpperCase() === "REJECTED";
    const row = document.createElement("tr");
    const effectiveFrom = store.effective_from
      ? new Date(store.effective_from).toISOString().slice(0, 10)
      : "";
    const storeLabel = [store.bank_store_code, store.store_name].filter(Boolean).join(" - ") || store.store_id;
    const editBtn =
      !isChecker && store.status === "ACTIVE"
        ? `<button type="button" class="secondary-btn action-icon-btn" data-edit-store="${store.store_id}" title="Edit store" aria-label="Edit store"><span aria-hidden="true">✏</span></button>`
        : "";
    const inactiveBtn =
      !isChecker && store.status === "ACTIVE"
        ? `<button type="button" class="secondary-btn action-icon-btn action-icon-btn-danger" data-deactivate-store="${store.store_id}" title="Make Inactive" aria-label="Make Inactive"><span aria-hidden="true">✕</span></button>`
        : "";
    const eyeBtn = isRejected
      ? `<button type="button" class="secondary-btn action-icon-btn" data-view-checker="${store.store_id}" title="View checker comment" aria-label="View checker comment">${STORE_EYE_ICON}</button>`
      : "";
    const pickupTypeLabel = { BEAT: "Beat", CALL: "Call" }[store.pickup_type] || store.pickup_type || "Beat";
    const isCall = store.pickup_type === "CALL";
    const fmtNum = (v) =>
      v != null && v !== "" && !Number.isNaN(Number(v)) ? Number(v).toLocaleString("en-IN") : "";
    row.innerHTML = `
      <td>${escapeHtml(store.bank_store_code ?? "")}</td>
      <td>${escapeHtml(store.store_name ?? "")}</td>
      <td>${escapeHtml(pickupTypeLabel)}</td>
      <td>${escapeHtml(store.customer_id ?? "")}</td>
      <td>${escapeHtml(store.customer_name ?? "")}</td>
      <td>${escapeHtml(store.account_no ?? "")}</td>
      <td>${isCall ? "" : fmtNum(store.daily_pickup_limit)}</td>
      <td>${isCall ? "" : fmtNum(store.fixed_charge)}</td>
      <td>${isCall ? "" : fmtNum(store.vendor_charge)}</td>
      <td>${isCall ? fmtNum(store.call_included_pickups) : ""}</td>
      <td>${isCall ? fmtNum(store.call_monthly_bank_charge) : ""}</td>
      <td>${isCall ? fmtNum(store.call_additional_bank_per_pickup) : ""}</td>
      <td>${isCall ? fmtNum(store.call_vendor_pay_per_pickup) : ""}</td>
      <td>${store.waiver_percentage != null && store.waiver_percentage !== "" ? `${store.waiver_percentage}%` : ""}</td>
      <td>${fmtNum(store.waiver_cap_amount)}</td>
      <td>${store.waiver_cap_from ? new Date(store.waiver_cap_from).toISOString().slice(0, 10) : ""}</td>
      <td>${store.waiver_cap_to ? new Date(store.waiver_cap_to).toISOString().slice(0, 10) : ""}</td>
      <td>${fmtYmd(store.onboarded_date)}</td>
      <td>${fmtYmdHmIst(store.last_modified_date)}</td>
      <td>${effectiveFrom}</td>
      <td><span class="status-pill ${statusInfo.cls}">${escapeHtml(statusInfo.label)}</span></td>
      <td class="inline-actions">${eyeBtn}${editBtn}${inactiveBtn}</td>
    `;
    row.querySelector("[data-edit-store]")?.addEventListener("click", () => beginEditStore(store));
    const btn = row.querySelector("[data-deactivate-store]");
    if (btn) {
      btn.addEventListener("click", () => showDeactivateStoreModal(store.store_id, storeLabel));
    }
    row.querySelector("[data-view-checker]")?.addEventListener("click", () =>
      showCheckerCommentModal(store)
    );
    storeRows.appendChild(row);
  });
};

const loadStores = async () => {
  if (!storeRows) return;

  try {
    const response = await fetch(`${apiBase}/api/bank-stores?include_inactive=1`, {
      headers: window.getAuthHeaders(),
    });
    if (!response.ok) {
      throw new Error("Failed to load stores");
    }
    storeCache = await response.json();
    renderStores(getFilteredStores());
  } catch (error) {
    if (storeMessage) {
      storeMessage.textContent = "Unable to load stores.";
      storeMessage.style.color = "#b42318";
    }
  }
};

const loadVendorFilterOptions = async () => {
  if (!storeVendorFilter) return;
  try {
    const response = await fetch(`${apiBase}/api/vendors`, {
      headers: window.getAuthHeaders(),
    });
    if (!response.ok) {
      throw new Error("Failed to load vendors");
    }
    const vendors = await response.json();
    const previousValue = storeVendorFilter.value;
    storeVendorFilter.innerHTML = '<option value="">All vendors</option>';
    vendors
      .slice()
      .sort((a, b) => (a.vendor_name || "").localeCompare(b.vendor_name || ""))
      .forEach((v) => {
        const opt = document.createElement("option");
        opt.value = String(v.vendor_id);
        const code = v.vendor_code ? ` (${v.vendor_code})` : "";
        opt.textContent = `${v.vendor_name || v.vendor_code || v.vendor_id}${code}`;
        storeVendorFilter.appendChild(opt);
      });
    if (previousValue && storeVendorFilter.querySelector(`option[value="${previousValue}"]`)) {
      storeVendorFilter.value = previousValue;
    }
  } catch (error) {
    console.warn("vendor filter load failed", error);
  }
};

const loadVendorMappingsIndex = async () => {
  try {
    const response = await fetch(`${apiBase}/api/store-mappings`, {
      headers: window.getAuthHeaders(),
    });
    if (!response.ok) {
      throw new Error("Failed to load store mappings");
    }
    const mappings = await response.json();
    const index = new Map();
    mappings.forEach((m) => {
      if (!m || m.status !== "ACTIVE") return;
      const vid = String(m.vendor_id ?? "");
      const code = String(m.bank_store_code ?? "");
      if (!vid || !code) return;
      if (!index.has(vid)) index.set(vid, new Set());
      index.get(vid).add(code);
    });
    vendorStoreCodesByVendorId = index;
  } catch (error) {
    vendorStoreCodesByVendorId = new Map();
    console.warn("vendor mapping index load failed", error);
  }
};

const downloadStoresList = () => {
  if (typeof XLSX === "undefined") {
    if (storeMessage) {
      storeMessage.textContent = "Excel export library failed to load.";
      storeMessage.style.color = "#b42318";
    }
    return;
  }
  const stores = getFilteredStores();
  const payload = stores.map((s) => {
    const eff = s.effective_from ? new Date(s.effective_from).toISOString().slice(0, 10) : "";
    const pt = s.pickup_type || "BEAT";
    const isCall = pt === "CALL";
    return {
      "Bank Store Code": s.bank_store_code ?? "",
      "Store Name": s.store_name ?? "",
      "Pickup Type": pt,
      "Customer ID": s.customer_id ?? "",
      "Customer Name": s.customer_name ?? "",
      "Account No": s.account_no ?? "",
      "Daily limit": isCall ? "" : s.daily_pickup_limit ?? "",
      "Monthly bank charge": isCall ? "" : s.fixed_charge ?? "",
      "Monthly vendor charge": isCall ? "" : s.vendor_charge ?? "",
      "CALL included/mo": isCall ? s.call_included_pickups ?? "" : "",
      "CALL bank package": isCall ? s.call_monthly_bank_charge ?? "" : "",
      "CALL bank extra/pu": isCall ? s.call_additional_bank_per_pickup ?? "" : "",
      "CALL vendor/pu": isCall ? s.call_vendor_pay_per_pickup ?? "" : "",
      "Waiver %": s.waiver_percentage ?? "",
      "Waiver cap (₹)": s.waiver_cap_amount ?? "",
      "Waiver cap from": s.waiver_cap_from ? new Date(s.waiver_cap_from).toISOString().slice(0, 10) : "",
      "Waiver cap to": s.waiver_cap_to ? new Date(s.waiver_cap_to).toISOString().slice(0, 10) : "",
      Onboarded: fmtYmd(s.onboarded_date),
      "Last modified (IST)": fmtYmdHmIst(s.last_modified_date),
      "Effective From": eff,
      Status: s.status ?? "",
    };
  });
  const worksheet = XLSX.utils.json_to_sheet(payload);
  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, worksheet, "Stores");
  XLSX.writeFile(workbook, `store_list_${new Date().toISOString().slice(0, 10)}.xlsx`);
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
    const filtered = items.filter((item) => item.entity_type === "BANK_STORE_MASTER");
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

const submitStore = async (event) => {
  event.preventDefault();
  if (!storeForm) return;

  const formData = new FormData(storeForm);
  const bankStoreCode = formData.get("bankStoreCode").trim();
  const storeName = formData.get("storeName").trim();
  const pickupType = formData.get("pickupType") || "BEAT";
  const customerId = formData.get("customerId").trim();
  const customerName = formData.get("customerName").trim();
  const accountNo = formData.get("accountNo").trim();
  const dailyPickupLimit = formData.get("dailyPickupLimit");
  const monthlyBankCharge = formData.get("monthlyBankCharge");
  const monthlyVendorCharge = formData.get("monthlyVendorCharge");
  const callIncludedPickups = formData.get("callIncludedPickups");
  const callMonthlyBankCharge = formData.get("callMonthlyBankCharge");
  const callAdditionalBankPerPickup = formData.get("callAdditionalBankPerPickup");
  const callVendorPayPerPickup = formData.get("callVendorPayPerPickup");
  const waiverPercentage = formData.get("waiverPercentage");
  const waiverCapAmount = formData.get("waiverCapAmount");
  const waiverCapFrom = formData.get("waiverCapFrom");
  const waiverCapTo = formData.get("waiverCapTo");
  const effectiveFrom = formData.get("effectiveFrom");
  const makerComment = formData.get("makerComment").trim();

  if (!bankStoreCode || !effectiveFrom || !makerComment) {
    storeMessage.textContent = "Please enter bank store code, date, and comment.";
    storeMessage.style.color = "#b42318";
    return;
  }

  storeMessage.textContent = "Saving store...";
  storeMessage.style.color = "#0f4c81";

  const makerId = sessionStorage.getItem("currentUser")
    ? JSON.parse(sessionStorage.getItem("currentUser")).employeeId
    : "SYSTEM";
  const editingId = getEditingStoreId();

  try {
    const isCall = pickupType === "CALL";
    const basePayload = {
      bank_store_code: bankStoreCode,
      store_name: storeName || null,
      pickup_type: pickupType,
      customer_id: customerId || null,
      customer_name: customerName || null,
      account_no: accountNo || null,
      daily_pickup_limit:
        !isCall && dailyPickupLimit !== "" && dailyPickupLimit != null ? Number(dailyPickupLimit) : null,
      fixed_charge:
        !isCall && monthlyBankCharge !== "" && monthlyBankCharge != null ? Number(monthlyBankCharge) : null,
      vendor_charge:
        !isCall && monthlyVendorCharge !== "" && monthlyVendorCharge != null ? Number(monthlyVendorCharge) : null,
      call_included_pickups:
        isCall && callIncludedPickups !== "" && callIncludedPickups != null
          ? Number(callIncludedPickups)
          : null,
      call_monthly_bank_charge:
        isCall && callMonthlyBankCharge !== "" && callMonthlyBankCharge != null
          ? Number(callMonthlyBankCharge)
          : null,
      call_additional_bank_per_pickup:
        isCall && callAdditionalBankPerPickup !== "" && callAdditionalBankPerPickup != null
          ? Number(callAdditionalBankPerPickup)
          : null,
      call_vendor_pay_per_pickup:
        isCall && callVendorPayPerPickup !== "" && callVendorPayPerPickup != null
          ? Number(callVendorPayPerPickup)
          : null,
      waiver_percentage: waiverPercentage !== "" && waiverPercentage != null ? Number(waiverPercentage) : null,
      waiver_cap_amount:
        waiverCapAmount !== "" && waiverCapAmount != null ? Number(waiverCapAmount) : null,
      waiver_cap_from: waiverCapFrom ? String(waiverCapFrom).slice(0, 10) : null,
      waiver_cap_to: waiverCapTo ? String(waiverCapTo).slice(0, 10) : null,
      effective_from: effectiveFrom,
      reason: makerComment,
      maker_id: makerId,
    };

    const response = editingId
      ? await fetch(`${apiBase}/api/bank-stores/requests/${editingId}/update`, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...window.getAuthHeaders() },
          body: JSON.stringify({
            store_id: Number(editingId),
            ...basePayload,
          }),
        })
      : await fetch(`${apiBase}/api/bank-stores/requests`, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...window.getAuthHeaders() },
          body: JSON.stringify({
            ...basePayload,
            status: "INACTIVE",
          }),
        });

    if (!response.ok) {
      if (response.status === 403) {
        storeMessage.textContent =
          "You do not have permission to add or edit stores. Checkers can only review and approve requests.";
        storeMessage.style.color = "#b42318";
        return;
      }
      if (response.status === 401) {
        storeMessage.textContent = "Session expired. Please login again.";
        storeMessage.style.color = "#b42318";
        return;
      }
      let detail = "";
      try {
        const payload = await response.json();
        detail = payload?.detail || "";
      } catch (error) {
        detail = "";
      }
      storeMessage.textContent = detail || "Unable to save store.";
      storeMessage.style.color = "#b42318";
      return;
    }

    storeMessage.textContent = editingId
      ? "Store change submitted for checker approval."
      : "Store request submitted for approval.";
    setStoreEditMode(null);
    storeForm.reset();
    loadStores();
  } catch (error) {
    if (!storeMessage.textContent) {
      storeMessage.textContent = "Unable to save store.";
    }
    storeMessage.style.color = "#b42318";
  }
};

const submitBulkStores = async (e) => {
  e.preventDefault();
  if (!bulkStoreForm || !bulkStoreFile?.files?.length) return;
  bulkStoreMessage.textContent = "Uploading...";
  bulkStoreMessage.style.color = "#0f4c81";
  try {
    const fd = new FormData();
    fd.append("file", bulkStoreFile.files[0]);
    const response = await fetch(`${apiBase}/api/bank-stores/bulk`, {
      method: "POST",
      headers: window.getAuthHeaders(),
      body: fd,
    });
    if (!response.ok) {
      if (response.status === 403) {
        throw new Error(
          "You do not have permission to add stores. Checkers can only review and approve requests.",
        );
      }
      const data = await response.json().catch(() => ({}));
      throw new Error(data?.detail || "Bulk upload failed");
    }
    const data = await response.json();
    bulkStoreMessage.textContent = `Created: ${data.created}, Skipped: ${data.skipped}${data.errors?.length ? `. Errors: ${JSON.stringify(data.errors.slice(0, 5))}` : ""}`;
    bulkStoreMessage.style.color = "#0f4c81";
    bulkStoreForm.reset();
    loadStores();
  } catch (error) {
    bulkStoreMessage.textContent = error.message || "Bulk upload failed.";
    bulkStoreMessage.style.color = "#b42318";
  }
};

const init = () => {
  if (!storeForm) return;
  syncStorePickupPricingVisibility();
  storePickupTypeSelect?.addEventListener("change", syncStorePickupPricingVisibility);
  storeForm.addEventListener("submit", submitStore);
  if (bulkStoreForm) bulkStoreForm.addEventListener("submit", submitBulkStores);
  document.querySelector("#bulk-store-download-template")?.addEventListener("click", async () => {
    try {
      await window.downloadStaticFile("bulk_stores_template.xlsx", "bulk_stores_template.xlsx");
    } catch (error) {
      if (bulkStoreMessage) {
        bulkStoreMessage.textContent = error.message || "Unable to download template.";
        bulkStoreMessage.style.color = "#b42318";
      }
    }
  });
  loadStores();
  loadClarifications();
  Promise.all([loadVendorFilterOptions(), loadVendorMappingsIndex()]).then(() => {
    if (storeVendorFilter?.value) {
      renderStores(getFilteredStores());
    }
  });

  storeSearchInput?.addEventListener("input", () => {
    renderStores(getFilteredStores());
  });
  storeStatusFilter?.addEventListener("change", () => {
    renderStores(getFilteredStores());
  });
  storeVendorFilter?.addEventListener("change", () => {
    renderStores(getFilteredStores());
  });
  storeDownloadBtn?.addEventListener("click", downloadStoresList);
  storeCancelEditBtn?.addEventListener("click", cancelStoreEdit);

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

  if (deactivateStoreForm) {
    deactivateStoreForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const storeId = deactivateStoreIdInput?.value;
      const comment = deactivateStoreMakerCommentInput?.value?.trim();
      if (!storeId || !comment) {
        if (deactivateStoreMessage) {
          deactivateStoreMessage.textContent = "Maker comment is required.";
          deactivateStoreMessage.style.color = "#b42318";
        }
        return;
      }
      if (deactivateStoreMessage) {
        deactivateStoreMessage.textContent = "Submitting...";
        deactivateStoreMessage.style.color = "#0f4c81";
      }
      await requestDeactivateStore(storeId, comment);
    });
  }
  if (deactivateStoreModal) {
    deactivateStoreModal.querySelector(".approval-modal-backdrop")?.addEventListener("click", hideDeactivateStoreModal);
    deactivateStoreModal.querySelector(".approval-modal-close")?.addEventListener("click", hideDeactivateStoreModal);
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && deactivateStoreModal.classList.contains("approval-modal-visible")) {
        hideDeactivateStoreModal();
      }
    });
  }
};

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
