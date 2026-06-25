const vendorForm = document.querySelector("#vendor-upload-form");
const vendorMessage = document.querySelector("#vendor-message");
const vendorSelect = document.querySelector("#vendor-name");
const previewHead = document.querySelector("#vendor-preview-head");
const previewBody = document.querySelector("#vendor-preview-body");
const previewMessage = document.querySelector("#vendor-preview-message");
const fileInput = vendorForm?.querySelector('input[type="file"]');
const historyRows = document.querySelector("#vendor-history-rows");
const historyMessage = document.querySelector("#vendor-history-message");
const historyFilter = document.querySelector("#vendor-history-filter");
const validateButton = document.querySelector("#vendor-validate");
const validateMessage = document.querySelector("#vendor-validate-message");
const progressContainer = document.querySelector("#vendor-upload-progress");
const progressLabel = document.querySelector("#vendor-progress-label");
const progressFill = document.querySelector("#vendor-progress-fill");
const progressPercent = document.querySelector("#vendor-progress-percent");
let vendorLookup = {};
const apiBase = window.API_BASE || "";
const escapeHtml = window.escapeHtml || ((value) => String(value ?? ""));

const showProgress = (label) => {
  if (progressContainer && progressLabel) {
    progressLabel.textContent = label || "Uploading...";
    progressContainer.hidden = false;
  }
  if (progressFill) progressFill.style.width = "0%";
  if (progressPercent) progressPercent.textContent = "0%";
};

const updateProgress = (pct) => {
  const val = Math.min(100, Math.round(pct));
  if (progressFill) progressFill.style.width = `${val}%`;
  if (progressPercent) progressPercent.textContent = `${val}%`;
};

const hideProgress = () => {
  if (progressContainer) progressContainer.hidden = true;
  if (progressFill) progressFill.style.width = "0%";
  if (progressPercent) progressPercent.textContent = "0%";
};

const fetchWithProgress = (url, options) => {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const formData = options.body;
    const headers = options.headers || {};

    xhr.upload.addEventListener("progress", (e) => {
      if (e.lengthComputable) {
        const pct = (e.loaded / e.total) * 100;
        updateProgress(pct);
      }
    });

    xhr.addEventListener("load", () => {
      hideProgress();
      resolve({
        ok: xhr.status >= 200 && xhr.status < 300,
        status: xhr.status,
        json: () => Promise.resolve(JSON.parse(xhr.responseText || "{}")),
        text: () => Promise.resolve(xhr.responseText || ""),
      });
    });

    xhr.addEventListener("error", () => {
      hideProgress();
      reject(new Error("Network error"));
    });

    xhr.addEventListener("abort", () => {
      hideProgress();
      reject(new Error("Request aborted"));
    });

    xhr.open(options.method || "POST", url);
    Object.entries(headers).forEach(([k, v]) => xhr.setRequestHeader(k, v));
    xhr.send(formData);
  });
};

const loadVendors = async () => {
  if (!vendorSelect) return;
  vendorSelect.innerHTML = '<option value="">Select vendor</option>';

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
      if (!vendor.vendor_id || !vendor.name) return;
      vendorLookup[vendor.vendor_id] = vendor;
      const option = document.createElement("option");
      option.value = vendor.name;
      option.textContent = `${vendor.name} (${vendor.code || ""})`.trim();
      vendorSelect.appendChild(option);
    });
    if (historyFilter) {
      historyFilter.innerHTML = '<option value="">All vendors</option>';
      activeVendors.forEach((vendor) => {
        if (!vendor.vendor_id || !vendor.name) return;
        const option = document.createElement("option");
        option.value = vendor.vendor_id;
        option.textContent = `${vendor.name} (${vendor.code || ""})`.trim();
        historyFilter.appendChild(option);
      });
    }
  } catch (error) {
    vendorMessage.textContent = "Unable to load vendors. Please onboard first.";
    vendorMessage.style.color = "#b42318";
  }
};

const clearPreview = () => {
  if (previewHead) previewHead.innerHTML = "";
  if (previewBody) previewBody.innerHTML = "";
};

const renderPreview = (rows) => {
  if (!previewHead || !previewBody) return;
  clearPreview();

  if (!rows.length) {
    previewMessage.textContent = "No data found in file.";
    previewMessage.style.color = "#b42318";
    return;
  }

  const headerRow = rows[0] || [];
  const headTr = document.createElement("tr");
  headerRow.forEach((cell) => {
    const th = document.createElement("th");
    th.textContent = cell ?? "";
    headTr.appendChild(th);
  });
  previewHead.appendChild(headTr);

  rows.slice(1).forEach((row) => {
    const tr = document.createElement("tr");
    headerRow.forEach((_, index) => {
      const td = document.createElement("td");
      td.textContent = row[index] ?? "";
      tr.appendChild(td);
    });
    previewBody.appendChild(tr);
  });
};

const renderPreviewFromHeaders = (headers, rows) => {
  if (!previewHead || !previewBody) return;
  clearPreview();

  if (!headers.length) {
    previewMessage.textContent = "No data available for preview.";
    previewMessage.style.color = "#b42318";
    return;
  }

  const headTr = document.createElement("tr");
  headers.forEach((cell) => {
    const th = document.createElement("th");
    th.textContent = cell ?? "";
    headTr.appendChild(th);
  });
  previewHead.appendChild(headTr);

  rows.forEach((row) => {
    const tr = document.createElement("tr");
    headers.forEach((_, index) => {
      const td = document.createElement("td");
      td.textContent = row[index] ?? "";
      tr.appendChild(td);
    });
    previewBody.appendChild(tr);
  });
};

const handleFilePreview = async (file) => {
  if (!previewMessage) return;
  if (!window.XLSX) {
    previewMessage.textContent = "Preview library not loaded.";
    previewMessage.style.color = "#b42318";
    return;
  }
  if (!file) {
    previewMessage.textContent = "Select a file to preview.";
    previewMessage.style.color = "#b42318";
    clearPreview();
    return;
  }

  previewMessage.textContent = "Loading preview...";
  previewMessage.style.color = "#0f4c81";

  try {
    const data = await file.arrayBuffer();
    const workbook = window.XLSX.read(data, { type: "array" });
    const sheetName = workbook.SheetNames[0];
    const sheet = workbook.Sheets[sheetName];
    const rows = window.XLSX.utils.sheet_to_json(sheet, { header: 1 });
    renderPreview(rows);
    previewMessage.textContent = "";
  } catch (error) {
    previewMessage.textContent = "Unable to preview file.";
    previewMessage.style.color = "#b42318";
    clearPreview();
  }
};

/* ----- Skip-unmapped-codes modal ----- */
const skipModal = document.querySelector("#vendor-skip-modal");
const skipList = document.querySelector("#vendor-skip-list");
const skipCount = document.querySelector("#vendor-skip-count");
let pendingUpload = null; // { vendorName, misDate, file }

const showSkipModal = (missing) => {
  if (!skipModal || !skipList || !skipCount) return;
  skipCount.textContent = String(missing.length);
  skipList.innerHTML = missing
    .map((code) => `<li>${escapeHtml(code)}</li>`)
    .join("");
  skipModal.hidden = false;
  skipModal.classList.add("approval-modal-visible");
};

const hideSkipModal = () => {
  if (!skipModal) return;
  skipModal.hidden = true;
  skipModal.classList.remove("approval-modal-visible");
  pendingUpload = null;
};

const performUpload = async (vendorName, misDate, file, skipUnmapped) => {
  vendorMessage.textContent = "Uploading Vendor MIS...";
  vendorMessage.style.color = "#0f4c81";
  showProgress("Uploading Vendor MIS...");

  const payload = new FormData();
  payload.append("vendorName", vendorName);
  payload.append("misDate", misDate);
  payload.append("file", file);
  if (skipUnmapped) payload.append("skipUnmapped", "true");

  let response;
  try {
    response = await fetchWithProgress(`${apiBase}/api/uploads/vendor`, {
      method: "POST",
      body: payload,
      headers: window.getAuthHeaders(),
    });
  } catch (error) {
    hideProgress();
    vendorMessage.textContent = "Upload failed. Please retry.";
    vendorMessage.style.color = "#b42318";
    return;
  }

  if (!response.ok) {
    if (response.status === 401 || response.status === 403) {
      vendorMessage.textContent = "Session expired or user inactive. Please login again.";
      vendorMessage.style.color = "#b42318";
      return;
    }
    let detail = "";
    try {
      const body = await response.json();
      detail = body?.detail || "";
    } catch (_) {
      detail = "";
    }
    vendorMessage.textContent = detail || "Upload failed. Please retry.";
    vendorMessage.style.color = "#b42318";
    return;
  }

  let result = {};
  try {
    result = await response.json();
  } catch (_) {
    result = {};
  }
  const status = result.status || "UNKNOWN";
  const invalid = result.invalid_rows ?? 0;
  const total = result.total_rows ?? "";
  const skipped = result.missing_store_codes?.length || 0;

  if (status === "FAILED") {
    let msg = `Upload failed. Invalid rows: ${invalid}${total !== "" ? ` of ${total}` : ""}.`;
    if (skipped > 0) {
      msg += ` Unmapped codes: ${result.missing_store_codes.join(", ")}.`;
    } else {
      msg += " Check vendor store mapping and required fields.";
    }
    vendorMessage.textContent = msg;
    vendorMessage.style.color = "#b42318";
  } else if (skipped > 0) {
    vendorMessage.textContent =
      `Vendor MIS uploaded with ${skipped} skipped code(s). Invalid rows: ${invalid}` +
      `${total !== "" ? ` of ${total}` : ""}.`;
    vendorMessage.style.color = "#0f4c81";
  } else {
    vendorMessage.textContent =
      `Vendor MIS uploaded (${status}). Invalid rows: ${invalid}${total !== "" ? ` of ${total}` : ""}.`;
    vendorMessage.style.color = "#0f4c81";
  }
  loadVendorHistory();
};

vendorForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const formData = new FormData(vendorForm);
  const vendorName = (formData.get("vendorName") || "").trim();
  const misDate = formData.get("misDate");
  const file = vendorForm.querySelector('input[type="file"]').files[0];

  if (!vendorName || !misDate || !file) {
    vendorMessage.textContent = "Please enter vendor name, date, and file.";
    vendorMessage.style.color = "#b42318";
    return;
  }

  vendorMessage.textContent = "Checking vendor store mappings...";
  vendorMessage.style.color = "#0f4c81";

  // Pre-flight validation: if any vendor store codes are unmapped,
  // pop the skip-confirm modal instead of uploading silently.
  let missing = [];
  try {
    const checkPayload = new FormData();
    checkPayload.append("vendorName", vendorName);
    checkPayload.append("misDate", misDate);
    checkPayload.append("file", file);
    const validateResp = await fetch(`${apiBase}/api/uploads/vendor/validate`, {
      method: "POST",
      body: checkPayload,
      headers: window.getAuthHeaders(),
    });
    if (validateResp.ok) {
      const validateBody = await validateResp.json();
      missing = validateBody?.unmapped_codes || [];
    }
  } catch (_) {
    /* fall through */
  }

  if (missing.length) {
    pendingUpload = { vendorName, misDate, file };
    showSkipModal(missing);
    vendorMessage.textContent = "";
    return;
  }

  await performUpload(vendorName, misDate, file, false);
});

if (skipModal) {
  const cancel = (msg) => {
    hideSkipModal();
    vendorMessage.textContent = msg || "Upload cancelled. Add the missing mappings and retry.";
    vendorMessage.style.color = "#b42318";
  };
  skipModal.querySelector(".approval-modal-close")?.addEventListener("click", () => cancel());
  skipModal.querySelector(".approval-modal-backdrop")?.addEventListener("click", () => cancel());
  skipModal.querySelector("[data-skip-cancel]")?.addEventListener("click", () => cancel());
  skipModal.querySelector("[data-skip-confirm]")?.addEventListener("click", async () => {
    if (!pendingUpload) {
      hideSkipModal();
      return;
    }
    const { vendorName, misDate, file } = pendingUpload;
    hideSkipModal();
    await performUpload(vendorName, misDate, file, true);
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && skipModal.classList.contains("approval-modal-visible")) {
      cancel();
    }
  });
}

const runValidation = async () => {
  const vendorName = vendorSelect.value?.trim();
  const misDate = vendorForm.querySelector('input[name="misDate"]').value;
  const file = vendorForm.querySelector('input[type="file"]').files[0];
  if (!vendorName || !misDate || !file) {
    validateMessage.textContent = "Please select vendor, date, and file to validate.";
    validateMessage.style.color = "#b42318";
    return;
  }
  validateMessage.textContent = "Validating file...";
  validateMessage.style.color = "#0f4c81";
  showProgress("Validating file...");
  try {
    const payload = new FormData();
    payload.append("vendorName", vendorName);
    payload.append("misDate", misDate);
    payload.append("file", file);
    const response = await fetchWithProgress(`${apiBase}/api/uploads/vendor/validate`, {
      method: "POST",
      body: payload,
      headers: window.getAuthHeaders(),
    });
    if (!response.ok) {
      let detail = "";
      try {
        const data = await response.json();
        detail = data?.detail || "";
      } catch (error) {
        detail = "";
      }
      validateMessage.textContent = detail || "Validation failed.";
      validateMessage.style.color = "#b42318";
      return;
    }
    const result = await response.json();
    if (result.unmapped_codes && result.unmapped_codes.length) {
      validateMessage.textContent = `Unmapped store codes: ${result.unmapped_codes.join(", ")}`;
      validateMessage.style.color = "#b42318";
      return;
    }
    if (result.out_of_range_codes && result.out_of_range_codes.length) {
      validateMessage.textContent = `Mapping date not effective for: ${result.out_of_range_codes.join(", ")}`;
      validateMessage.style.color = "#b42318";
      return;
    }
    validateMessage.textContent = `Validation passed. Invalid rows: ${result.invalid_rows ?? 0} of ${result.total_rows ?? ""}.`;
    validateMessage.style.color = "#0f4c81";
  } catch (error) {
    hideProgress();
    validateMessage.textContent = "Validation failed.";
    validateMessage.style.color = "#b42318";
  }
};

if (validateButton) {
  validateButton.addEventListener("click", (event) => {
    event.preventDefault();
    runValidation();
  });
}

const loadVendorHistory = async () => {
  if (!historyRows) return;
  historyRows.innerHTML = "";
  if (historyMessage) {
    historyMessage.textContent = "Loading previous uploads...";
    historyMessage.style.color = "#0f4c81";
  }
  const vendorId = historyFilter?.value || "";
  const url = vendorId
    ? `${apiBase}/api/uploads/vendor/batches?vendor_id=${encodeURIComponent(vendorId)}`
    : `${apiBase}/api/uploads/vendor/batches`;
  try {
    const response = await fetch(url, { headers: window.getAuthHeaders() });
    if (!response.ok) {
      throw new Error("Unable to load uploads");
    }
    const batches = await response.json();
    if (!batches.length) {
      if (historyMessage) {
        historyMessage.textContent = "No uploads found.";
        historyMessage.style.color = "#667085";
      }
      return;
    }
    const cachedUser = sessionStorage.getItem("currentUser");
    const role = cachedUser ? (JSON.parse(cachedUser).role || "").toUpperCase() : "";
    const isChecker = role === "CHECKER";
    historyRows.innerHTML = batches
      .map(
        (batch) => `
        <tr>
          <td>${escapeHtml(batch.batch_id ?? "")}</td>
          <td>${escapeHtml(batch.vendor_name ?? "")}</td>
          <td>${escapeHtml(batch.mis_date ?? "")}</td>
          <td>${escapeHtml(batch.file_name ?? "")}</td>
          <td>${escapeHtml(batch.uploaded_by ?? "")}</td>
          <td>${escapeHtml(batch.uploaded_at ? (window.formatDateTime || ((s) => s))(batch.uploaded_at) : "")}</td>
          <td>${escapeHtml(batch.status ?? "")}</td>
          <td>
            <button class="secondary-btn action-icon-btn" type="button" data-preview-batch="${batch.batch_id}" title="Preview" aria-label="Preview">
              <span aria-hidden="true">👁</span>
            </button>
            <button class="secondary-btn action-icon-btn" type="button" data-download-batch="${batch.batch_id}" title="Download" aria-label="Download">
              <span aria-hidden="true">⬇</span>
            </button>
            ${
              isChecker
                ? ""
                : `<button class="secondary-btn action-icon-btn" type="button" data-delete-batch="${batch.batch_id}" title="Delete" aria-label="Delete">
              <span aria-hidden="true">✕</span>
            </button>`
            }
          </td>
        </tr>
      `,
      )
      .join("");
    if (historyMessage) {
      historyMessage.textContent = "";
    }
  } catch (error) {
    if (historyMessage) {
      historyMessage.textContent = "Unable to load previous uploads.";
      historyMessage.style.color = "#b42318";
    }
  }
};

if (historyFilter) {
  historyFilter.addEventListener("change", () => {
    loadVendorHistory();
  });
}

if (historyRows) {
  historyRows.addEventListener("click", async (event) => {
    const previewButton = event.target.closest("button[data-preview-batch]");
    const downloadButton = event.target.closest("button[data-download-batch]");
    const deleteButton = event.target.closest("button[data-delete-batch]");
    if (previewButton) {
      const batchId = previewButton.dataset.previewBatch;
      previewMessage.textContent = "Loading preview...";
      previewMessage.style.color = "#0f4c81";
      try {
        const response = await fetch(`${apiBase}/api/uploads/vendor/${batchId}/preview`, {
          headers: window.getAuthHeaders(),
        });
        if (!response.ok) {
          throw new Error("Preview failed");
        }
        const payload = await response.json();
        renderPreviewFromHeaders(payload.headers || [], payload.rows || []);
        previewMessage.textContent = `Preview loaded for batch ${batchId}.`;
      } catch (error) {
        previewMessage.textContent = "Unable to preview this batch.";
        previewMessage.style.color = "#b42318";
      }
    }
    if (downloadButton) {
      const batchId = downloadButton.dataset.downloadBatch;
      try {
        const response = await fetch(`${apiBase}/api/uploads/vendor/${batchId}/download`, {
          headers: window.getAuthHeaders(),
        });
        if (!response.ok) {
          throw new Error("Download failed");
        }
        const blob = await response.blob();
        if (window.saveBlob) {
          window.saveBlob(blob, `vendor_upload_${batchId}.xlsx`);
        } else {
          const url = window.URL.createObjectURL(blob);
          const anchor = document.createElement("a");
          anchor.href = url;
          anchor.download = `vendor_upload_${batchId}.xlsx`;
          document.body.appendChild(anchor);
          anchor.click();
          anchor.remove();
          window.URL.revokeObjectURL(url);
        }
      } catch (error) {
        vendorMessage.textContent = "Unable to download file.";
        vendorMessage.style.color = "#b42318";
      }
    }
    if (deleteButton) {
      const batchId = deleteButton.dataset.deleteBatch;
      const confirmed = window.confirm(
        `Delete batch ${batchId}? This will remove stored data for this upload.`,
      );
      if (!confirmed) return;
      try {
        const response = await fetch(`${apiBase}/api/uploads/vendor/${batchId}`, {
          method: "DELETE",
          headers: window.getAuthHeaders(),
        });
        if (!response.ok) {
          let detail = "";
          try {
            const data = await response.json();
            detail = data?.detail || "";
          } catch (error) {
            detail = "";
          }
          throw new Error(detail || "Delete failed");
        }
        vendorMessage.textContent = `Deleted batch ${batchId}.`;
        vendorMessage.style.color = "#0f4c81";
        loadVendorHistory();
      } catch (error) {
        vendorMessage.textContent = error.message || "Unable to delete batch.";
        vendorMessage.style.color = "#b42318";
      }
    }
  });
}

if (fileInput) {
  fileInput.addEventListener("change", (event) => {
    const file = event.target.files[0];
    handleFilePreview(file);
  });
}

loadVendors();
loadVendorHistory();
