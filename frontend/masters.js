const currentUser = () =>
  sessionStorage.getItem("currentUser")
    ? JSON.parse(sessionStorage.getItem("currentUser"))
    : { employeeId: "SYSTEM" };
const apiBase = window.API_BASE || "";
const escapeHtml = window.escapeHtml || ((value) => String(value ?? ""));

const postJson = async (url, payload) => {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...window.getAuthHeaders() },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    if (response.status === 401 || response.status === 403) {
      throw new Error("Session expired or user inactive. Please login again.");
    }
    let detail = "";
    try {
      const data = await response.json();
      detail = data?.detail || "";
    } catch (error) {
      detail = "";
    }
    throw new Error(detail || "Request failed.");
  }
  return response.json();
};

const loadTable = async (url, rowsEl, columns) => {
  const response = await fetch(url, { headers: window.getAuthHeaders() });
  if (!response.ok) {
    rowsEl.innerHTML = "";
    return;
  }
  const items = await response.json();
  rowsEl.innerHTML = items
    .map(
      (item) =>
        `<tr>${columns.map((key) => `<td>${escapeHtml(item[key] ?? "")}</td>`).join("")}</tr>`,
    )
    .join("");
};

const bindForm = (formId, messageId, handler) => {
  const form = document.querySelector(formId);
  const message = document.querySelector(messageId);
  if (!form) return;
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    message.textContent = "Submitting...";
    message.style.color = "#0f4c81";
    try {
      await handler(new FormData(form));
      message.textContent = "Request submitted for approval.";
      form.reset();
    } catch (error) {
      message.textContent = error.message || "Request failed.";
      message.style.color = "#b42318";
    }
  });
};

bindForm("#bank-store-form", "#bank-store-message", async (data) => {
  await postJson(`${apiBase}/api/bank-stores/requests`, {
    bank_store_code: data.get("bankStoreCode"),
    store_name: data.get("storeName") || null,
    sol_id: data.get("solId") || null,
    pickup_type: data.get("pickupType") || "BEAT",
    daily_pickup_limit: data.get("dailyPickupLimit")
      ? Number(data.get("dailyPickupLimit"))
      : null,
    fixed_charge: data.get("monthlyBankCharge") ? Number(data.get("monthlyBankCharge")) : null,
    vendor_charge: data.get("monthlyVendorCharge") ? Number(data.get("monthlyVendorCharge")) : null,
    waiver_percentage: data.get("waiverPercentage") ? Number(data.get("waiverPercentage")) : null,
    effective_from: data.get("effectiveFrom"),
    status: data.get("status"),
    maker_id: currentUser().employeeId,
  });
});

bindForm("#charge-config-form", "#charge-config-message", async (data) => {
  await postJson(`${apiBase}/api/charge-configs/requests`, {
    config_code: data.get("configCode"),
    config_name: data.get("configName"),
    value_number: data.get("valueNumber") ? Number(data.get("valueNumber")) : null,
    value_text: data.get("valueText") || null,
    effective_from: data.get("effectiveFrom"),
    status: data.get("status"),
    maker_id: currentUser().employeeId,
  });
});

bindForm("#pickup-rule-form", "#pickup-rule-message", async (data) => {
  await postJson(`${apiBase}/api/pickup-rules/requests`, {
    pickup_type: data.get("pickupType"),
    free_limit: data.get("freeLimit") ? Number(data.get("freeLimit")) : null,
    effective_from: data.get("effectiveFrom"),
    status: data.get("status"),
    maker_id: currentUser().employeeId,
  });
});

bindForm("#vendor-charge-form", "#vendor-charge-message", async (data) => {
  await postJson(`${apiBase}/api/vendor-charges/requests`, {
    vendor_id: Number(data.get("vendorId")),
    pickup_type: data.get("pickupType"),
    base_charge: Number(data.get("baseCharge")),
    effective_from: data.get("effectiveFrom"),
    status: data.get("status"),
    maker_id: currentUser().employeeId,
  });
});

bindForm("#waiver-form", "#waiver-message", async (data) => {
  await postJson(`${apiBase}/api/waivers/requests`, {
    customer_id: data.get("customerId"),
    waiver_type: data.get("waiverType"),
    waiver_percentage: data.get("waiverPercentage")
      ? Number(data.get("waiverPercentage"))
      : null,
    waiver_cap_amount: data.get("waiverCapAmount")
      ? Number(data.get("waiverCapAmount"))
      : null,
    waiver_from: data.get("waiverFrom"),
    waiver_to: data.get("waiverTo") || null,
    status: "ACTIVE",
    maker_id: currentUser().employeeId,
  });
});

const vendorFormatSelect = document.querySelector("#vendor-format-vendor");
const vendorFormatFilter = document.querySelector("#vendor-format-filter");
const vendorFormatRequestFilter = document.querySelector("#vendor-format-request-filter");
const vendorMappingRows = document.querySelector("#vendor-format-mapping-rows");
const generateMappingButton = document.querySelector("#generate-vendor-mapping");
const mappingTextarea = document.querySelector('textarea[name="headerMapping"]');
const vendorFormatSampleInput = document.querySelector("#vendor-format-sample");
const vendorFormatRows = document.querySelector("#vendor-format-rows");
const vendorFormatForm = document.querySelector("#vendor-format-form");
const vendorFormatListMessage = document.querySelector("#vendor-format-list-message");
const vendorFormatRequestRows = document.querySelector("#vendor-format-request-rows");
const vendorFormatRequestMessage = document.querySelector("#vendor-format-request-message");
let vendorFormatCache = [];
let vendorLookup = {};
let vendorFormatRequestCache = [];
let vendorHeaderOptions = [];

const mappingFields = [
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

const loadActiveVendorsForFormat = async () => {
  if (!vendorFormatSelect) return;
  vendorFormatSelect.innerHTML = '<option value="">Select vendor</option>';
  if (vendorFormatRequestFilter) {
    vendorFormatRequestFilter.innerHTML = '<option value="">Select vendor</option>';
  }
  try {
    const response = await fetch(`${apiBase}/api/vendors`, {
      headers: window.getAuthHeaders(),
    });
    if (!response.ok) {
      throw new Error("Failed to load vendors");
    }
    const vendors = await response.json();
    const activeVendors = vendors.filter((vendor) => vendor.status === "ACTIVE");
    vendorLookup = {};
    activeVendors.forEach((vendor) => {
      vendorLookup[vendor.vendor_id] = vendor;
    });
    activeVendors
      .filter((vendor) => vendor.status === "ACTIVE")
      .forEach((vendor) => {
        const option = document.createElement("option");
        option.value = vendor.vendor_id;
        option.textContent = `${vendor.name} (${vendor.code})`;
        vendorFormatSelect.appendChild(option);
        if (vendorFormatRequestFilter) {
          const requestOption = option.cloneNode(true);
          vendorFormatRequestFilter.appendChild(requestOption);
        }
      });
  } catch (error) {
  }
};

const loadApprovedVendorFilters = async () => {
  if (!vendorFormatFilter) return;
  vendorFormatFilter.innerHTML = '<option value="">Select vendor</option>';
  try {
    const response = await fetch(`${apiBase}/api/vendor-file-formats`, {
      headers: window.getAuthHeaders(),
    });
    if (!response.ok) {
      throw new Error("Failed to load vendor formats");
    }
    const formats = await response.json();
    const seen = new Set();
    formats.forEach((format) => {
      if (!format.vendor_id || seen.has(format.vendor_id)) return;
      seen.add(format.vendor_id);
      const option = document.createElement("option");
      option.value = format.vendor_id;
      option.textContent = format.vendor_name
        ? `${format.vendor_name} (${format.vendor_code || ""})`.trim()
        : String(format.vendor_id);
      vendorFormatFilter.appendChild(option);
    });
  } catch (error) {
  }
};

const formatToInputDate = (value) => {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return String(value).slice(0, 10);
  }
  return parsed.toISOString().slice(0, 10);
};

const setMappingFromJson = (jsonText) => {
  if (!vendorMappingRows) return;
  let parsed = {};
  try {
    parsed = JSON.parse(jsonText || "{}");
  } catch (error) {
    parsed = {};
  }
  const selects = vendorMappingRows.querySelectorAll("select[data-mapping-key]");
  selects.forEach((select) => {
    const key = select.dataset.mappingKey;
    const value = parsed[key] || "";
    if (value && !Array.from(select.options).some((opt) => opt.value === value)) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = value;
      select.appendChild(option);
    }
    select.value = value;
  });
};

const loadVendorFormats = async (vendorId) => {
  if (!vendorFormatRows) return;
  vendorFormatRows.innerHTML = "";
  if (vendorFormatListMessage) {
    vendorFormatListMessage.textContent = "";
  }
  if (!vendorId) {
    if (vendorFormatListMessage) {
      vendorFormatListMessage.textContent = "Select a vendor to view approved formats.";
    }
    return;
  }
  try {
    const response = await fetch(
      `${apiBase}/api/vendor-file-formats?vendor_id=${encodeURIComponent(vendorId)}`,
      { headers: window.getAuthHeaders() },
    );
    if (!response.ok) {
      throw new Error("Failed to load vendor formats");
    }
    vendorFormatCache = await response.json();
    const esc = window.escapeHtml || ((v) => String(v ?? ""));
    vendorFormatRows.innerHTML = vendorFormatCache
      .map(
        (format, index) => `
        <tr>
          <td>${esc(format.format_id ?? "")}</td>
          <td>${esc(format.vendor_name ?? format.vendor_id ?? "")}</td>
          <td>${esc(format.format_name ?? "")}</td>
          <td>${esc(format.status ?? "")}</td>
          <td>${esc(format.effective_from ?? "")}</td>
          <td>
            <button class="secondary-btn" type="button" data-edit-index="${index}">Edit</button>
            <button class="secondary-btn" type="button" data-delete-format-id="${Number(format.format_id) || ""}">Delete</button>
          </td>
        </tr>
      `,
      )
      .join("");
  } catch (error) {
    vendorFormatRows.innerHTML = "";
    if (vendorFormatListMessage) {
      vendorFormatListMessage.textContent = "Unable to load vendor formats.";
    }
  }
};

const renderVendorFormatRequests = (requests) => {
  if (!vendorFormatRequestRows) return;
  const esc = window.escapeHtml || ((v) => String(v ?? ""));
  vendorFormatRequestRows.innerHTML = requests
    .map(
      (request) => `
      <tr>
        <td>${esc(window.formatRequestRef(request.approval_id) ?? "")}</td>
        <td>${esc(request.format_id ?? "")}</td>
        <td>${esc(request.format_name ?? "")}</td>
        <td>${esc(request.status ?? "")}</td>
        <td>${request.created_date ? esc((window.formatDateTime || ((s) => s))(request.created_date)) : ""}</td>
        <td>${esc(request.checker_comment ?? "")}</td>
      </tr>
    `,
    )
    .join("");
};

const filterVendorFormatRequests = (vendorId) => {
  if (!vendorId) return vendorFormatRequestCache;
  return vendorFormatRequestCache.filter(
    (request) => String(request.vendor_id) === String(vendorId),
  );
};

const loadVendorFormatRequests = async () => {
  if (!vendorFormatRequestRows) return;
  vendorFormatRequestRows.innerHTML = "";
  if (vendorFormatRequestMessage) {
    vendorFormatRequestMessage.textContent = "";
  }
  try {
    const response = await fetch(`${apiBase}/api/vendor-file-formats/requests`, {
      headers: window.getAuthHeaders(),
    });
    if (!response.ok) {
      throw new Error("Failed to load request status");
    }
    vendorFormatRequestCache = await response.json();
    if (vendorFormatRequestFilter) {
      vendorFormatRequestFilter.innerHTML = '<option value="">All vendors</option>';
      const seen = new Set();
      vendorFormatRequestCache.forEach((request) => {
        if (!request.vendor_id || seen.has(request.vendor_id)) return;
        seen.add(request.vendor_id);
        const option = document.createElement("option");
        option.value = request.vendor_id;
        option.textContent = request.vendor_name
          ? `${request.vendor_name} (${request.vendor_code || ""})`.trim()
          : String(request.vendor_id);
        vendorFormatRequestFilter.appendChild(option);
      });
    }
    const initialRows = filterVendorFormatRequests(
      vendorFormatRequestFilter ? vendorFormatRequestFilter.value : "",
    );
    renderVendorFormatRequests(initialRows);
    if (vendorFormatRequestMessage && !initialRows.length) {
      vendorFormatRequestMessage.textContent = "No requests found.";
    }
  } catch (error) {
    vendorFormatRequestRows.innerHTML = "";
    if (vendorFormatRequestMessage) {
      vendorFormatRequestMessage.textContent = "Unable to load request status.";
    }
  }
};

bindForm("#vendor-format-form", "#vendor-format-message", async (data) => {
  await postJson(`${apiBase}/api/vendor-file-formats/requests`, {
    vendor_id: Number(data.get("vendorId")),
    format_name: data.get("formatName"),
    header_mapping_json: data.get("headerMapping"),
    effective_from: data.get("effectiveFrom"),
    status: "ACTIVE",
    maker_id: currentUser().employeeId,
  });
});

loadTable(`${apiBase}/api/bank-stores`, document.querySelector("#bank-store-rows"), [
  "bank_store_code",
  "store_name",
  "status",
  "onboarded_date",
  "last_modified_date",
  "effective_from",
]);

loadTable(`${apiBase}/api/charge-configs`, document.querySelector("#charge-config-rows"), [
  "config_code",
  "config_name",
  "value_number",
  "status",
]);

document.querySelectorAll("[data-section]").forEach((button) => {
  button.addEventListener("click", () => {
    const sectionId = button.dataset.section;
    document.querySelectorAll(".master-section").forEach((panel) => {
      panel.classList.toggle("hidden", panel.id !== sectionId);
    });
    const section = document.getElementById(sectionId);
    if (section) {
      section.scrollIntoView({ behavior: "smooth" });
    }
  });
});

const updateMappingSelectOptions = () => {
  if (!vendorMappingRows) return;
  const selects = vendorMappingRows.querySelectorAll("select[data-mapping-key]");
  selects.forEach((select) => {
    const current = select.value;
    select.innerHTML = '<option value="">Select column</option>';
    vendorHeaderOptions.forEach((header) => {
      const option = document.createElement("option");
      option.value = header;
      option.textContent = header;
      select.appendChild(option);
    });
    if (current && !Array.from(select.options).some((opt) => opt.value === current)) {
      const option = document.createElement("option");
      option.value = current;
      option.textContent = current;
      select.appendChild(option);
    }
    select.value = current;
  });
};

const renderMappingBuilder = () => {
  if (!vendorMappingRows) return;
  vendorMappingRows.innerHTML = mappingFields
    .map(
      (field) => `
        <tr>
          <td>${field.label}</td>
          <td>
            <select data-mapping-key="${field.key}">
              <option value="">Select column</option>
            </select>
          </td>
        </tr>
      `,
    )
    .join("");
  updateMappingSelectOptions();
};

const generateMappingJson = () => {
  if (!mappingTextarea || !vendorMappingRows) return;
  const inputs = vendorMappingRows.querySelectorAll("select[data-mapping-key]");
  const payload = {};
  inputs.forEach((input) => {
    const key = input.dataset.mappingKey;
    const value = input.value.trim();
    if (value) {
      payload[key] = value;
    }
  });
  mappingTextarea.value = JSON.stringify(payload, null, 2);
};

if (generateMappingButton) {
  generateMappingButton.addEventListener("click", (event) => {
    event.preventDefault();
    generateMappingJson();
  });
}

if (vendorFormatSampleInput) {
  vendorFormatSampleInput.addEventListener("change", async (event) => {
    const file = event.target.files[0];
    if (!file || !window.XLSX) return;
    try {
      const data = await file.arrayBuffer();
      const workbook = window.XLSX.read(data, { type: "array" });
      const sheetName = workbook.SheetNames[0];
      const sheet = workbook.Sheets[sheetName];
      const rows = window.XLSX.utils.sheet_to_json(sheet, { header: 1 });
      const headerRow = rows[0] || [];
      vendorHeaderOptions = headerRow
        .map((cell) => String(cell || "").trim())
        .filter((cell) => cell);
      updateMappingSelectOptions();
    } catch (error) {
      vendorHeaderOptions = [];
      updateMappingSelectOptions();
    }
  });
}

if (vendorFormatRows && vendorFormatForm) {
  vendorFormatRows.addEventListener("click", async (event) => {
    const deleteBtn = event.target.closest("button[data-delete-format-id]");
    if (deleteBtn) {
      const formatId = Number(deleteBtn.dataset.deleteFormatId);
      if (!formatId || !confirm("Delete this vendor file format? This cannot be undone.")) return;
      try {
        const response = await fetch(`${apiBase}/api/vendor-file-formats/${formatId}`, {
          method: "DELETE",
          headers: window.getAuthHeaders(),
        });
        if (!response.ok) {
          const data = await response.json().catch(() => ({}));
          throw new Error(data?.detail || "Delete failed");
        }
        loadVendorFormats(vendorFormatFilter?.value || "");
        if (vendorFormatListMessage) {
          vendorFormatListMessage.textContent = "Format deleted.";
          vendorFormatListMessage.style.color = "#0f4c81";
        }
      } catch (err) {
        if (vendorFormatListMessage) {
          vendorFormatListMessage.textContent = err.message || "Delete failed.";
          vendorFormatListMessage.style.color = "#b42318";
        }
      }
      return;
    }
    const button = event.target.closest("button[data-edit-index]");
    if (!button) return;
    const index = Number(button.dataset.editIndex);
    const format = vendorFormatCache[index];
    if (!format) return;
    vendorFormatSelect.value = String(format.vendor_id ?? "");
    vendorFormatForm.querySelector('input[name="formatName"]').value =
      format.format_name || "";
    vendorFormatForm.querySelector('input[name="effectiveFrom"]').value =
      formatToInputDate(format.effective_from);
    const mappingText = format.header_mapping_json || "{}";
    mappingTextarea.value = mappingText;
    setMappingFromJson(mappingText);
    vendorFormatForm.scrollIntoView({ behavior: "smooth" });
  });
}

if (vendorFormatFilter) {
  vendorFormatFilter.addEventListener("change", () => {
    loadVendorFormats(vendorFormatFilter.value);
  });
}

if (vendorFormatRequestFilter) {
  vendorFormatRequestFilter.addEventListener("change", () => {
    const rows = filterVendorFormatRequests(vendorFormatRequestFilter.value);
    renderVendorFormatRequests(rows);
    if (vendorFormatRequestMessage) {
      vendorFormatRequestMessage.textContent = rows.length ? "" : "No requests found.";
    }
  });
}

renderMappingBuilder();
loadActiveVendorsForFormat();
loadApprovedVendorFilters();
loadVendorFormats("");
loadVendorFormatRequests();

document.querySelectorAll(".master-section").forEach((panel) => {
  panel.classList.add("hidden");
});
