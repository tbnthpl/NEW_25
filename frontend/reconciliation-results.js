const loadButton = document.querySelector("#load-results");
const resultsMessage = document.querySelector("#results-message");
const tableWrapper = document.querySelector("#results-table-wrapper");
const misDateInput = document.querySelector("#results-mis-date");
const downloadButton = document.querySelector("#download-results");
const apiBase = window.API_BASE || "";

let latestResults = [];

const downloadXlsx = (rows, misDate) => {
  if (!rows.length) return;
  const payload = rows.map((row) => ({
    "Bank Store Code": row.bank_store_code || "",
    "Store Name": row.store_name || "",
    "Vendor Name": row.vendor_names || "",
    "Vendor Pickup Date": row.pickup_date || "",
    "Vendor Amount": row.pickup_amount ?? "",
    "Finacle Date": row.remittance_date || "",
    "Finacle Amount": row.remittance_amount ?? "",
    Status: row.status || "",
    Reason: row.reason || "",
    "Edit Status": row.correction_status || "",
  }));
  const worksheet = XLSX.utils.json_to_sheet(payload);
  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, worksheet, "Reconciliation");
  const filename = `reconciliation_results_${misDate || "report"}.xlsx`;
  XLSX.writeFile(workbook, filename);
};

const renderResults = (results) => {
  if (!results.length) {
    tableWrapper.innerHTML = "";
    latestResults = [];
    downloadButton.disabled = true;
    downloadButton.hidden = true;
    return;
  }

  latestResults = results;
  downloadButton.disabled = false;
  downloadButton.hidden = false;
  const esc = window.escapeHtml || ((v) => String(v ?? ""));
  const rows = results
    .map(
      (row) => `
      <tr>
        <td>${esc(row.bank_store_code || "")}</td>
        <td>${esc(row.store_name || "")}</td>
        <td>${esc(row.vendor_names || "")}</td>
        <td>${esc(row.pickup_date || "")}</td>
        <td>${esc(row.pickup_amount ?? "")}</td>
        <td>${esc(row.remittance_date || "")}</td>
        <td>${esc(row.remittance_amount ?? "")}</td>
        <td><span class="status ${row.status === "MATCHED" ? "match" : "mismatch"}">${esc(row.status)}</span></td>
        <td>${esc(row.reason || "")}</td>
        <td>${esc(row.correction_status || "")}</td>
      </tr>
    `,
    )
    .join("");

  tableWrapper.innerHTML = `
    <table>
      <thead>
        <tr>
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
        </tr>
      </thead>
      <tbody>
        ${rows}
      </tbody>
    </table>
  `;
};

loadButton.addEventListener("click", async () => {
  const misDate = misDateInput?.value;
  if (!misDate) {
    resultsMessage.textContent = "Please select MIS date.";
    resultsMessage.style.color = "#b42318";
    return;
  }
  resultsMessage.textContent = "Loading reconciliation results...";
  resultsMessage.style.color = "#0f4c81";

  try {
    const response = await fetch(
      `${apiBase}/api/reconciliation/results?misDate=${encodeURIComponent(misDate)}`,
      { headers: window.getAuthHeaders() },
    );
    if (!response.ok) {
      let detail = "";
      try {
        const data = await response.json();
        detail = data?.detail || "";
      } catch (error) {
        detail = "";
      }
      throw new Error(detail || "Unable to load results.");
    }
    const results = await response.json();
    renderResults(results);
    resultsMessage.textContent = results.length
      ? "Reconciliation results loaded."
      : "No results found for this date.";
  } catch (error) {
    resultsMessage.textContent = error.message || "Unable to load results.";
    resultsMessage.style.color = "#b42318";
  }
});

downloadButton.addEventListener("click", () => {
  const misDate = misDateInput?.value;
  downloadXlsx(latestResults, misDate);
});

const urlParams = new URLSearchParams(window.location.search);
const misDateFromUrl = urlParams.get("misDate");
if (misDateFromUrl && misDateInput) {
  misDateInput.value = misDateFromUrl;
  loadButton.click();
}
