const reportMessage = document.querySelector("#report-message");
const vendorReportForm = document.querySelector("#vendor-report-form");
const vendorSelect = document.querySelector("#vendor-report-select");
const vendorStoreSelect = document.querySelector("#vendor-report-store-select");
const vendorFromInput = document.querySelector("#vendor-report-from");
const vendorToInput = document.querySelector("#vendor-report-to");
const vendorPreviewButton = document.querySelector("#vendor-report-preview");
const vendorPreviewTable = document.querySelector("#vendor-report-preview-table");
const vendorChargesPreviewButton = document.querySelector("#vendor-charges-preview");
const vendorChargesPreviewTable = document.querySelector("#vendor-charges-preview-table");
const customerReportForm = document.querySelector("#customer-report-form");
const customerSelect = document.querySelector("#customer-report-select");
const customerFromInput = document.querySelector("#customer-report-from");
const customerToInput = document.querySelector("#customer-report-to");
const customerPreviewButton = document.querySelector("#customer-report-preview");
const customerPreviewTable = document.querySelector("#customer-report-preview-table");
const customerChargesPreviewButton = document.querySelector("#customer-charges-preview");
const customerChargesPreviewTable = document.querySelector("#customer-charges-preview-table");
const reconReportForm = document.querySelector("#recon-report-form");
const reconFromInput = document.querySelector("#recon-report-from");
const reconToInput = document.querySelector("#recon-report-to");
const reconPreviewButton = document.querySelector("#recon-report-preview");
const reconPreviewTable = document.querySelector("#recon-report-preview-table");
const apiBase = window.API_BASE || "";

const triggerDownload = async (reportKey) => {
  if (reportKey === "vendor-charges" && (!vendorFromInput?.value || !vendorToInput?.value)) {
    reportMessage.textContent = "Select From Date and To Date for vendor charges report.";
    reportMessage.style.color = "#b42318";
    return;
  }
  if (reportKey === "customer-charges" && (!customerFromInput?.value || !customerToInput?.value)) {
    reportMessage.textContent = "Select From Date and To Date for store charges report.";
    reportMessage.style.color = "#b42318";
    return;
  }

  reportMessage.textContent = "Preparing report...";
  reportMessage.style.color = "#0f4c81";

  let url = `${apiBase}/api/reports/${reportKey}`;
  if (reportKey === "vendor-charges" && vendorFromInput?.value && vendorToInput?.value) {
    url += `?from_date=${encodeURIComponent(vendorFromInput.value)}&to_date=${encodeURIComponent(vendorToInput.value)}`;
  } else if (reportKey === "customer-charges" && customerFromInput?.value && customerToInput?.value) {
    url += `?from_date=${encodeURIComponent(customerFromInput.value)}&to_date=${encodeURIComponent(customerToInput.value)}`;
  }

  try {
    const response = await fetch(url, {
      headers: window.getAuthHeaders(),
    });
    if (!response.ok) {
      let detail = "";
      try {
        const errData = await response.json();
        const d = errData?.detail;
        detail = Array.isArray(d) ? d.map((e) => e?.msg || JSON.stringify(e)).join("; ") : (d || "");
      } catch (_) {
        detail = (await response.text().catch(() => "")) || response.statusText;
      }
      throw new Error(detail || `Report failed (${response.status})`);
    }
    const blob = await response.blob();
    const disposition = response.headers.get("Content-Disposition") || "";
    const match = disposition.match(/filename="([^"]+)"/);
    const filename = match ? match[1] : `${reportKey}.xlsx`;
    window.saveBlob(blob, filename);
    reportMessage.textContent = "Report downloaded.";
  } catch (error) {
    reportMessage.textContent = error.message || "Unable to download report.";
    reportMessage.style.color = "#b42318";
  }
};

document.querySelectorAll("[data-report]").forEach((button) => {
  button.addEventListener("click", () => {
    triggerDownload(button.dataset.report);
  });
});

const loadVendors = async () => {
  if (!vendorSelect) return;
  vendorSelect.innerHTML = "";
  try {
    const response = await fetch(`${apiBase}/api/vendors`, {
      headers: window.getAuthHeaders(),
    });
    if (!response.ok) {
      throw new Error("Failed to load vendors");
    }
    const vendors = await response.json();
    vendors.forEach((vendor) => {
      const option = document.createElement("option");
      option.value = vendor.vendor_id;
      option.textContent = `${vendor.name} (${vendor.code})`;
      vendorSelect.appendChild(option);
    });
  } catch (error) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "Unable to load vendors";
    vendorSelect.appendChild(option);
  }
};

const loadStoresForVendorReport = async () => {
  if (!vendorStoreSelect) return;
  vendorStoreSelect.innerHTML = '<option value="">All stores</option>';
  try {
    const response = await fetch(`${apiBase}/api/bank-stores`, {
      headers: window.getAuthHeaders(),
    });
    if (!response.ok) throw new Error("Failed to load stores");
    const stores = await response.json();
    const active = stores.filter(
      (s) => (s.status || "ACTIVE").toUpperCase() === "ACTIVE",
    );
    active.forEach((s) => {
      const option = document.createElement("option");
      option.value = s.store_id;
      const code = s.bank_store_code || "";
      const name = s.store_name || "";
      option.textContent = name ? `${code} (${name})` : code || String(s.store_id);
      vendorStoreSelect.appendChild(option);
    });
  } catch (error) {
    vendorStoreSelect.innerHTML = '<option value="">All stores</option>';
  }
};

const loadCustomers = async () => {
  if (!customerSelect) return;
  customerSelect.innerHTML = "";
  try {
    const response = await fetch(`${apiBase}/api/reports/customers`, {
      headers: window.getAuthHeaders(),
    });
    if (!response.ok) {
      throw new Error("Failed to load customers");
    }
    const customers = await response.json();
    customers.forEach((customer) => {
      const option = document.createElement("option");
      option.value = customer.customer_id;
      option.textContent = customer.customer_name
        ? `${customer.customer_name} (${customer.customer_id})`
        : customer.customer_id;
      customerSelect.appendChild(option);
    });
  } catch (error) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "Unable to load customers";
    customerSelect.appendChild(option);
  }
};

const buildVendorPickupsUrl = (path) => {
  const vendorId = vendorSelect?.value;
  const fromDate = vendorFromInput?.value;
  const toDate = vendorToInput?.value;
  const storeId = vendorStoreSelect?.value || "";
  const params = [
    `vendor_id=${encodeURIComponent(vendorId)}`,
    `from_date=${encodeURIComponent(fromDate)}`,
    `to_date=${encodeURIComponent(toDate)}`,
  ];
  if (storeId) params.push(`store_id=${encodeURIComponent(storeId)}`);
  return `${apiBase}${path}?${params.join("&")}`;
};

const downloadVendorReport = async (event) => {
  event.preventDefault();
  const vendorId = vendorSelect?.value;
  const fromDate = vendorFromInput?.value;
  const toDate = vendorToInput?.value;
  if (!vendorId || !fromDate || !toDate) {
    reportMessage.textContent = "Select vendor and date range.";
    reportMessage.style.color = "#b42318";
    return;
  }

  reportMessage.textContent = "Preparing vendor report...";
  reportMessage.style.color = "#0f4c81";
  try {
    const response = await fetch(buildVendorPickupsUrl("/api/reports/vendor-pickups"), {
      headers: window.getAuthHeaders(),
    });
    if (!response.ok) {
      throw new Error("Report failed");
    }
    const blob = await response.blob();
    const storeId = vendorStoreSelect?.value || "";
    const suffix = storeId ? `_store${storeId}` : "";
    window.saveBlob(blob, `vendor-pickups_${vendorId}${suffix}_${fromDate}_${toDate}.xlsx`);
    reportMessage.textContent = "Vendor report downloaded.";
  } catch (error) {
    reportMessage.textContent = "Unable to download vendor report.";
    reportMessage.style.color = "#b42318";
  }
};

const renderPreviewTable = (container, rows) => {
  if (!container) return;
  if (!rows.length) {
    container.innerHTML = "<p class=\"form-message\">No data found.</p>";
    return;
  }
  const esc = window.escapeHtml || ((v) => String(v ?? ""));
  const headers = Object.keys(rows[0]);
  const bodyRows = rows
    .map(
      (row) =>
        `<tr>${headers.map((key) => `<td>${esc(row[key] ?? "")}</td>`).join("")}</tr>`,
    )
    .join("");
  container.innerHTML = `
    <table>
      <thead>
        <tr>${headers.map((key) => `<th>${esc(key)}</th>`).join("")}</tr>
      </thead>
      <tbody>
        ${bodyRows}
      </tbody>
    </table>
  `;
};

const previewVendorReport = async () => {
  const vendorId = vendorSelect?.value;
  const fromDate = vendorFromInput?.value;
  const toDate = vendorToInput?.value;
  if (!vendorId || !fromDate || !toDate) {
    reportMessage.textContent = "Select vendor and date range.";
    reportMessage.style.color = "#b42318";
    return;
  }
  reportMessage.textContent = "Loading vendor preview...";
  reportMessage.style.color = "#0f4c81";
  try {
    const response = await fetch(buildVendorPickupsUrl("/api/reports/vendor-pickups/preview"), {
      headers: window.getAuthHeaders(),
    });
    if (!response.ok) {
      throw new Error("Preview failed");
    }
    const rows = await response.json();
    renderPreviewTable(vendorPreviewTable, rows);
    reportMessage.textContent = "Vendor preview loaded.";
  } catch (error) {
    reportMessage.textContent = "Unable to load vendor preview.";
    reportMessage.style.color = "#b42318";
  }
};

const downloadCustomerReport = async (event) => {
  event.preventDefault();
  const customerId = customerSelect?.value;
  const fromDate = customerFromInput?.value;
  const toDate = customerToInput?.value;
  if (!customerId || !fromDate || !toDate) {
    reportMessage.textContent = "Select customer and date range.";
    reportMessage.style.color = "#b42318";
    return;
  }

  reportMessage.textContent = "Preparing customer report...";
  reportMessage.style.color = "#0f4c81";
  try {
    const response = await fetch(
      `${apiBase}/api/reports/customer-pickups?customer_id=${encodeURIComponent(
        customerId,
      )}&from_date=${encodeURIComponent(fromDate)}&to_date=${encodeURIComponent(toDate)}`,
      { headers: window.getAuthHeaders() },
    );
    if (!response.ok) {
      throw new Error("Report failed");
    }
    const blob = await response.blob();
    window.saveBlob(blob, `customer-pickups_${customerId}_${fromDate}_${toDate}.xlsx`);
    reportMessage.textContent = "Customer report downloaded.";
  } catch (error) {
    reportMessage.textContent = "Unable to download customer report.";
    reportMessage.style.color = "#b42318";
  }
};

const previewCustomerReport = async () => {
  const customerId = customerSelect?.value;
  const fromDate = customerFromInput?.value;
  const toDate = customerToInput?.value;
  if (!customerId || !fromDate || !toDate) {
    reportMessage.textContent = "Select customer and date range.";
    reportMessage.style.color = "#b42318";
    return;
  }
  reportMessage.textContent = "Loading customer preview...";
  reportMessage.style.color = "#0f4c81";
  try {
    const response = await fetch(
      `${apiBase}/api/reports/customer-pickups/preview?customer_id=${encodeURIComponent(
        customerId,
      )}&from_date=${encodeURIComponent(fromDate)}&to_date=${encodeURIComponent(toDate)}`,
      { headers: window.getAuthHeaders() },
    );
    if (!response.ok) {
      throw new Error("Preview failed");
    }
    const rows = await response.json();
    renderPreviewTable(customerPreviewTable, rows);
    reportMessage.textContent = "Customer preview loaded.";
  } catch (error) {
    reportMessage.textContent = "Unable to load customer preview.";
    reportMessage.style.color = "#b42318";
  }
};

const previewReconReport = async () => {
  const fromDate = reconFromInput?.value;
  const toDate = reconToInput?.value;
  if (!fromDate || !toDate) {
    reportMessage.textContent = "Select date range.";
    reportMessage.style.color = "#b42318";
    return;
  }
  reportMessage.textContent = "Loading reconciliation preview...";
  reportMessage.style.color = "#0f4c81";
  try {
    const response = await fetch(
      `${apiBase}/api/reports/reconciliation-final/preview?from_date=${encodeURIComponent(
        fromDate,
      )}&to_date=${encodeURIComponent(toDate)}`,
      { headers: window.getAuthHeaders() },
    );
    if (!response.ok) {
      throw new Error("Preview failed");
    }
    const rows = await response.json();
    renderPreviewTable(reconPreviewTable, rows);
    reportMessage.textContent = "Reconciliation preview loaded.";
  } catch (error) {
    reportMessage.textContent = "Unable to load reconciliation preview.";
    reportMessage.style.color = "#b42318";
  }
};

const downloadReconReport = async (event) => {
  event.preventDefault();
  const fromDate = reconFromInput?.value;
  const toDate = reconToInput?.value;
  if (!fromDate || !toDate) {
    reportMessage.textContent = "Select date range.";
    reportMessage.style.color = "#b42318";
    return;
  }

  reportMessage.textContent = "Preparing reconciliation report...";
  reportMessage.style.color = "#0f4c81";
  try {
    const response = await fetch(
      `${apiBase}/api/reports/reconciliation-final?from_date=${encodeURIComponent(
        fromDate,
      )}&to_date=${encodeURIComponent(toDate)}`,
      { headers: window.getAuthHeaders() },
    );
    if (!response.ok) {
      throw new Error("Report failed");
    }
    const blob = await response.blob();
    window.saveBlob(blob, `reconciliation_final_${fromDate}_${toDate}.xlsx`);
    reportMessage.textContent = "Reconciliation report downloaded.";
  } catch (error) {
    reportMessage.textContent = "Unable to download reconciliation report.";
    reportMessage.style.color = "#b42318";
  }
};

document.querySelectorAll(".report-toggle").forEach((button) => {
  button.addEventListener("click", () => {
    const targetId = button.dataset.target;
    const section = document.getElementById(targetId);
    if (!section) return;
    document.querySelectorAll(".report-group").forEach((group) => {
      group.classList.add("hidden");
    });
    section.classList.remove("hidden");
  });
});

const loadVendorAbsenceVendors = async () => {
  const sel = document.querySelector("#vendor-absence-select");
  if (!sel) return;
  sel.innerHTML = '<option value="">All vendors</option>';
  try {
    const response = await fetch(`${apiBase}/api/vendors`, {
      headers: window.getAuthHeaders(),
    });
    if (!response.ok) throw new Error("Failed to load vendors");
    const vendors = await response.json();
    vendors.forEach((vendor) => {
      const option = document.createElement("option");
      option.value = vendor.vendor_id;
      option.textContent = `${vendor.name} (${vendor.code})`;
      sel.appendChild(option);
    });
  } catch (_) {}
};

const detectVendorAbsence = async () => {
  const fromDate = document.querySelector("#vendor-absence-from")?.value;
  const toDate = document.querySelector("#vendor-absence-to")?.value;
  if (!fromDate || !toDate) {
    reportMessage.textContent = "Select From Date and To Date.";
    reportMessage.style.color = "#b42318";
    return;
  }
  reportMessage.textContent = "Detecting and recording vendor absences...";
  reportMessage.style.color = "#0f4c81";
  try {
    const url = `${apiBase}/api/reports/vendor-absence/detect?from_date=${encodeURIComponent(fromDate)}&to_date=${encodeURIComponent(toDate)}`;
    const response = await fetch(url, { method: "POST", headers: window.getAuthHeaders() });
    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      const detail = errData?.detail;
      throw new Error(typeof detail === "string" ? detail : "Detect failed");
    }
    const data = await response.json();
    reportMessage.textContent = `Recorded ${data.recorded || 0} absence(s) for monitoring. Use "Use stored records" to view.`;
  } catch (error) {
    reportMessage.textContent = error.message || "Unable to detect vendor absences.";
    reportMessage.style.color = "#b42318";
  }
};

const previewVendorAbsence = async () => {
  const fromDate = document.querySelector("#vendor-absence-from")?.value;
  const toDate = document.querySelector("#vendor-absence-to")?.value;
  const vendorId = document.querySelector("#vendor-absence-select")?.value || "";
  const useStored = document.querySelector("#vendor-absence-use-stored")?.checked || false;
  if (!fromDate || !toDate) {
    reportMessage.textContent = "Select From Date and To Date.";
    reportMessage.style.color = "#b42318";
    return;
  }
  reportMessage.textContent = "Loading vendor absence preview...";
  reportMessage.style.color = "#0f4c81";
  try {
    let url = `${apiBase}/api/reports/vendor-absence?from_date=${encodeURIComponent(fromDate)}&to_date=${encodeURIComponent(toDate)}`;
    if (vendorId) url += `&vendor_id=${encodeURIComponent(vendorId)}`;
    if (useStored) url += "&use_stored=1";
    const response = await fetch(url, { headers: window.getAuthHeaders() });
    if (!response.ok) throw new Error("Preview failed");
    const data = await response.json();
    const rows = data.items || [];
    const displayRows = rows.map((r) => ({
      "Vendor ID": r.vendor_id,
      "Vendor Name": r.vendor_name,
      "Vendor Code": r.vendor_code,
      "Bank Store Code": r.bank_store_code,
      "Store Name": r.store_name,
      "Vendor Store Code": r.vendor_store_code,
      "Absence Date": r.absence_date,
    }));
    renderPreviewTable(document.querySelector("#vendor-absence-preview-table"), displayRows);
    reportMessage.textContent = rows.length ? `${rows.length} absence(s) found.` : "No vendor absences for selected dates.";
  } catch (error) {
    reportMessage.textContent = error.message || "Unable to load vendor absence preview.";
    reportMessage.style.color = "#b42318";
  }
};

const downloadVendorAbsence = async () => {
  const fromDate = document.querySelector("#vendor-absence-from")?.value;
  const toDate = document.querySelector("#vendor-absence-to")?.value;
  const vendorId = document.querySelector("#vendor-absence-select")?.value || "";
  const useStored = document.querySelector("#vendor-absence-use-stored")?.checked || false;
  if (!fromDate || !toDate) {
    reportMessage.textContent = "Select From Date and To Date.";
    reportMessage.style.color = "#b42318";
    return;
  }
  reportMessage.textContent = "Preparing vendor absence report...";
  reportMessage.style.color = "#0f4c81";
  try {
    let url = `${apiBase}/api/reports/vendor-absence/download?from_date=${encodeURIComponent(fromDate)}&to_date=${encodeURIComponent(toDate)}`;
    if (vendorId) url += `&vendor_id=${encodeURIComponent(vendorId)}`;
    if (useStored) url += "&use_stored=1";
    const response = await fetch(url, { headers: window.getAuthHeaders() });
    if (!response.ok) throw new Error("Download failed");
    const blob = await response.blob();
    window.saveBlob(blob, `vendor-absence_${fromDate}_${toDate}.xlsx`);
    reportMessage.textContent = "Vendor absence report downloaded.";
  } catch (error) {
    reportMessage.textContent = error.message || "Unable to download vendor absence report.";
    reportMessage.style.color = "#b42318";
  }
};

if (vendorReportForm) {
  vendorReportForm.addEventListener("submit", downloadVendorReport);
  loadVendors();
  loadStoresForVendorReport();
  loadVendorAbsenceVendors();
}

document.querySelector("#vendor-absence-detect")?.addEventListener("click", detectVendorAbsence);
document.querySelector("#vendor-absence-preview")?.addEventListener("click", previewVendorAbsence);
document.querySelector("#vendor-absence-download")?.addEventListener("click", downloadVendorAbsence);

if (customerReportForm) {
  customerReportForm.addEventListener("submit", downloadCustomerReport);
  loadCustomers();
}

if (reconReportForm) {
  reconReportForm.addEventListener("submit", downloadReconReport);
}

if (vendorPreviewButton) {
  vendorPreviewButton.addEventListener("click", previewVendorReport);
}

const previewVendorCharges = async () => {
  const fromDate = vendorFromInput?.value;
  const toDate = vendorToInput?.value;
  if (!fromDate || !toDate) {
    reportMessage.textContent = "Select From Date and To Date.";
    reportMessage.style.color = "#b42318";
    return;
  }
  reportMessage.textContent = "Loading vendor charges preview...";
  reportMessage.style.color = "#0f4c81";
  try {
    const response = await fetch(
      `${apiBase}/api/reports/vendor-charges/preview?from_date=${encodeURIComponent(fromDate)}&to_date=${encodeURIComponent(toDate)}`,
      { headers: window.getAuthHeaders() },
    );
    if (!response.ok) throw new Error("Preview failed");
    const rows = await response.json();
    renderPreviewTable(vendorChargesPreviewTable, rows);
    reportMessage.textContent = rows.length ? "Vendor charges loaded." : "No vendor charges found for selected dates.";
  } catch (error) {
    reportMessage.textContent = "Unable to load vendor charges preview.";
    reportMessage.style.color = "#b42318";
  }
};

if (vendorChargesPreviewButton) {
  vendorChargesPreviewButton.addEventListener("click", previewVendorCharges);
}

if (customerPreviewButton) {
  customerPreviewButton.addEventListener("click", previewCustomerReport);
}

const previewCustomerCharges = async () => {
  const fromDate = customerFromInput?.value;
  const toDate = customerToInput?.value;
  if (!fromDate || !toDate) {
    reportMessage.textContent = "Select From Date and To Date.";
    reportMessage.style.color = "#b42318";
    return;
  }
  reportMessage.textContent = "Loading customer charges preview...";
  reportMessage.style.color = "#0f4c81";
  try {
    const response = await fetch(
      `${apiBase}/api/reports/customer-charges/preview?from_date=${encodeURIComponent(fromDate)}&to_date=${encodeURIComponent(toDate)}`,
      { headers: window.getAuthHeaders() },
    );
    if (!response.ok) throw new Error("Preview failed");
    const rows = await response.json();
    renderPreviewTable(customerChargesPreviewTable, rows);
    reportMessage.textContent = rows.length ? "Store charges loaded." : "No store charges found for selected dates.";
  } catch (error) {
    reportMessage.textContent = "Unable to load store charges preview.";
    reportMessage.style.color = "#b42318";
  }
};

if (customerChargesPreviewButton) {
  customerChargesPreviewButton.addEventListener("click", previewCustomerCharges);
}

if (reconPreviewButton) {
  reconPreviewButton.addEventListener("click", previewReconReport);
}
