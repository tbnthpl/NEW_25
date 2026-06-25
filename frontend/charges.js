const apiBase = window.API_BASE || "";
const currentUser = () =>
  sessionStorage.getItem("currentUser")
    ? JSON.parse(sessionStorage.getItem("currentUser"))
    : { employeeId: "SYSTEM" };

const chargeDateFromVendor = document.querySelector("#charge-date-from-vendor");
const chargeDateToVendor = document.querySelector("#charge-date-to-vendor");
const chargeDateFromCustomer = document.querySelector("#charge-date-from-customer");
const chargeDateToCustomer = document.querySelector("#charge-date-to-customer");
const computeVendorBtn = document.querySelector("#compute-vendor-btn");
const computeCustomerBtn = document.querySelector("#compute-customer-btn");
const chargeVendorMessage = document.querySelector("#charge-vendor-message");
const chargeCustomerMessage = document.querySelector("#charge-customer-message");
const vendorRows = document.querySelector("#vendor-charge-rows");
const customerRows = document.querySelector("#customer-charge-rows");
const vendorChargeMessage = document.querySelector("#vendor-charge-message");
const customerChargeMessage = document.querySelector("#customer-charge-message");
const chargeClarificationRows = document.querySelector("#charge-clarification-rows");
const chargeClarificationMessage = document.querySelector("#charge-clarification-message");
const escapeHtml = window.escapeHtml || ((value) => String(value ?? ""));

// Holds the exact rows currently shown in the Vendor Charges grid so the
// download produces the same data (and total) as the on-screen preview.
let vendorExportAOA = null;

/** Approval entity types for configuration submitted from this Charges page. */
const CHARGE_RELATED_CLARIFICATION_TYPES = new Set([
  "CHARGE_CONFIG",
  "VENDOR_CHARGE",
  "PICKUP_RULE",
  "WAIVER",
]);

const postJson = async (url, payload) => {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...window.getAuthHeaders() },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || response.statusText || "Request failed");
  }
  return response.json();
};

const setMessage = (el, text, isError = false) => {
  if (!el) return;
  el.textContent = text;
  el.style.color = isError ? "#b42318" : "#0f4c81";
};

const formatCurrency = (n) => {
  if (n == null || n === "") return "";
  const num = Number(n);
  return Number.isNaN(num) ? "" : num.toLocaleString("en-IN", { maximumFractionDigits: 2 });
};

const formatChargeDate = (iso) => (iso ? (window.formatDateTime || ((s) => String(s)))(iso) : "");

const formatClarificationHistory = (raw) => {
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
  } catch {
    return "";
  }
};

const loadChargeClarifications = async () => {
  if (!chargeClarificationRows) return;
  chargeClarificationRows.innerHTML = "";
  if (chargeClarificationMessage) {
    chargeClarificationMessage.textContent = "Loading clarifications...";
    chargeClarificationMessage.style.color = "#0f4c81";
  }

  try {
    const response = await fetch(`${apiBase}/api/approvals/clarifications`, {
      headers: window.getAuthHeaders(),
    });
    if (!response.ok) {
      throw new Error("Failed to load clarifications");
    }
    const items = await response.json();
    const filtered = items.filter((item) => CHARGE_RELATED_CLARIFICATION_TYPES.has(item.entity_type));
    if (!filtered.length) {
      if (chargeClarificationMessage) {
        chargeClarificationMessage.textContent = "No charge-related clarification requests.";
      }
      return;
    }

    filtered.forEach((item) => {
      const row = document.createElement("tr");
      const history = formatClarificationHistory(item.comments_history);
      row.innerHTML = `
        <td>${escapeHtml(window.formatRequestRef(item.approval_id))}</td>
        <td>${escapeHtml(window.formatEntityType ? window.formatEntityType(item.entity_type) : item.entity_type)}</td>
        <td>${escapeHtml(item.status)}</td>
        <td>${escapeHtml(item.reason ?? "")}</td>
        <td>${escapeHtml(item.checker_comment ?? "")}</td>
        <td>${history}</td>
        <td><input type="text" class="maker-reply" placeholder="Reply to checker" /></td>
        <td><button type="button" class="secondary-btn" data-resubmit="${item.approval_id}">Resubmit</button></td>
      `;
      row.querySelector("[data-resubmit]").addEventListener("click", async () => {
        const reply = row.querySelector(".maker-reply").value.trim();
        if (!reply) {
          if (chargeClarificationMessage) {
            chargeClarificationMessage.textContent = "Reply comment required.";
            chargeClarificationMessage.style.color = "#b42318";
          }
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
          if (chargeClarificationMessage) {
            chargeClarificationMessage.textContent = "Resubmitted to checker.";
            chargeClarificationMessage.style.color = "#0f4c81";
          }
          loadChargeClarifications();
        } catch {
          if (chargeClarificationMessage) {
            chargeClarificationMessage.textContent = "Unable to resubmit.";
            chargeClarificationMessage.style.color = "#b42318";
          }
        }
      });
      chargeClarificationRows.appendChild(row);
    });

    if (chargeClarificationMessage) {
      chargeClarificationMessage.textContent = "";
    }
  } catch {
    if (chargeClarificationMessage) {
      chargeClarificationMessage.textContent = "Unable to load clarifications.";
      chargeClarificationMessage.style.color = "#b42318";
    }
  }
};

const dateToMonthKey = (val) => (val && val.length >= 7 ? val.slice(0, 7).replace(/-/g, "") : null);

const monthKeyToDateRange = (monthKey) => {
  if (!monthKey || monthKey.length !== 6) return { from: "", to: "" };
  const y = parseInt(monthKey.slice(0, 4), 10);
  const m = parseInt(monthKey.slice(4, 6), 10);
  const lastDay = new Date(y, m, 0).getDate();
  return {
    from: `${y}-${String(m).padStart(2, "0")}-01`,
    to: `${y}-${String(m).padStart(2, "0")}-${String(lastDay).padStart(2, "0")}`,
  };
};

const getMonthsInRange = (monthFrom, monthTo) => {
  if (!monthFrom || !monthTo) return monthFrom ? [monthFrom] : [];
  const [from, to] = monthFrom <= monthTo ? [monthFrom, monthTo] : [monthTo, monthFrom];
  const months = [];
  const [yFrom, mFrom] = [parseInt(from.slice(0, 4), 10), parseInt(from.slice(4, 6), 10)];
  const [yTo, mTo] = [parseInt(to.slice(0, 4), 10), parseInt(to.slice(4, 6), 10)];
  for (let y = yFrom; y <= yTo; y++) {
    const mStart = y === yFrom ? mFrom : 1;
    const mEnd = y === yTo ? mTo : 12;
    for (let m = mStart; m <= mEnd; m++) {
      months.push(`${y}${String(m).padStart(2, "0")}`);
    }
  }
  return months;
};

const initDate = (el) => {
  if (!el || el.value) return;
  const now = new Date();
  el.value = now.toISOString().slice(0, 10);
};

const chargeViewVendor = document.querySelector("#charge-view-vendor");
const chargeViewStoreVendor = document.querySelector("#charge-view-store-vendor");
const vendorChargeThead = document.querySelector("#vendor-charge-thead");

const VENDOR_AGGREGATE_HEADER = `
  <tr>
    <th>Vendor</th>
    <th>From Date</th>
    <th>To Date</th>
    <th>Beat stores</th>
    <th>Call pickups</th>
    <th>Total remittance (₹)</th>
    <th>Base (₹)</th>
    <th>Enhancement (₹)</th>
    <th>Tax (₹)</th>
    <th>Total (₹)</th>
    <th>Computed By</th>
    <th>Charge calc date</th>
  </tr>
`;

const VENDOR_BY_STORE_HEADER = `
  <tr>
    <th>Vendor</th>
    <th>Store code</th>
    <th>Store name</th>
    <th>Period from</th>
    <th>Period to</th>
    <th>Pickup type</th>
    <th title="CALL: pickups from vendor MIS (drives the charge). BEAT: matched pickups from final Daily Reconciliation (informational; flat monthly fee is unchanged).">Pickups</th>
    <th>Total remittance (₹)</th>
    <th title="₹/month for BEAT stores, ₹/pickup for CALL stores.">Rate (₹)</th>
    <th>Charge (₹)</th>
    <th>Charge calc date</th>
  </tr>
`;

const setVendorChargeHeader = (mode) => {
  if (!vendorChargeThead) return;
  vendorChargeThead.innerHTML = mode === "by-store" ? VENDOR_BY_STORE_HEADER : VENDOR_AGGREGATE_HEADER;
};

const loadVendorCharges = async (monthFrom, monthTo, vendorId = null) => {
  if (!vendorRows) return;
  setVendorChargeHeader("aggregate");
  vendorRows.innerHTML = "";
  vendorExportAOA = null;
  setMessage(vendorChargeMessage, "");
  try {
    let url = `${apiBase}/api/charges/vendor/summary`;
    const params = [];
    if (vendorId) params.push(`vendor_id=${encodeURIComponent(vendorId)}`);
    if (monthFrom && monthTo) {
      const [from, to] = monthFrom <= monthTo ? [monthFrom, monthTo] : [monthTo, monthFrom];
      params.push(`month_from=${encodeURIComponent(from)}`, `month_to=${encodeURIComponent(to)}`);
    } else if (monthFrom) {
      params.push(`month_key=${encodeURIComponent(monthFrom)}`);
    }
    if (params.length) url += `?${params.join("&")}`;
    const response = await fetch(url, { headers: window.getAuthHeaders() });
    if (!response.ok) throw new Error("Failed to load vendor charges");
    const data = await response.json();
    if (!data.length) {
      setMessage(vendorChargeMessage, "No vendor charges found. Select dates and compute.");
      return;
    }
    const userFrom = chargeDateFromVendor?.value?.trim() || null;
    const userTo = chargeDateToVendor?.value?.trim() || null;
    const byVendor = {};
    for (const r of data) {
      const { from, to } = monthKeyToDateRange(r.month_key);
      let displayFrom = from;
      let displayTo = to;
      if (userFrom && userFrom >= from && userFrom <= to) displayFrom = userFrom;
      if (userTo && userTo >= from && userTo <= to) displayTo = userTo;
      const key = r.vendor_id;
      if (!byVendor[key]) {
        byVendor[key] = {
          vendor_name: r.vendor_name || r.vendor_code || r.vendor_id,
          displayFrom,
          displayTo,
          beat_pickups: r.beat_pickups ?? 0,
          call_pickups: r.call_pickups ?? 0,
          total_remittance: r.total_remittance ?? 0,
          base_charge_amount: r.base_charge_amount ?? 0,
          enhancement_charge: r.enhancement_charge ?? 0,
          tax_amount: r.tax_amount ?? 0,
          total_with_tax: r.total_with_tax ?? 0,
          computed_by: r.computed_by || "",
          computed_at: r.computed_at || null,
        };
      } else {
        const agg = byVendor[key];
        agg.displayFrom = agg.displayFrom < displayFrom ? agg.displayFrom : displayFrom;
        agg.displayTo = agg.displayTo > displayTo ? agg.displayTo : displayTo;
        agg.beat_pickups += r.beat_pickups ?? 0;
        agg.call_pickups += r.call_pickups ?? 0;
        agg.total_remittance += r.total_remittance ?? 0;
        agg.base_charge_amount += r.base_charge_amount ?? 0;
        agg.enhancement_charge += r.enhancement_charge ?? 0;
        agg.tax_amount += r.tax_amount ?? 0;
        agg.total_with_tax += r.total_with_tax ?? 0;
        if (r.computed_at && (!agg.computed_at || r.computed_at > agg.computed_at)) {
          agg.computed_at = r.computed_at;
        }
      }
    }
    const combined = Object.values(byVendor);
    const grandTotal = combined.reduce((sum, agg) => sum + (Number(agg.total_with_tax) || 0), 0);
    const grandRemittance = combined.reduce((sum, agg) => sum + (Number(agg.total_remittance) || 0), 0);
    vendorRows.innerHTML =
      combined
        .map(
          (agg) => `
      <tr>
        <td>${escapeHtml(agg.vendor_name)}</td>
        <td>${escapeHtml(agg.displayFrom)}</td>
        <td>${escapeHtml(agg.displayTo)}</td>
        <td>${agg.beat_pickups}</td>
        <td>${agg.call_pickups}</td>
        <td>${formatCurrency(agg.total_remittance)}</td>
        <td>${formatCurrency(agg.base_charge_amount)}</td>
        <td>${formatCurrency(agg.enhancement_charge)}</td>
        <td>${formatCurrency(agg.tax_amount)}</td>
        <td>${formatCurrency(agg.total_with_tax)}</td>
        <td>${escapeHtml(agg.computed_by)}</td>
        <td>${escapeHtml(formatChargeDate(agg.computed_at))}</td>
      </tr>
    `,
        )
        .join("") +
      `
      <tr class="charge-total-row">
        <td colspan="9" style="text-align:right;font-weight:600;">Total vendor charge (₹)</td>
        <td style="font-weight:600;">${formatCurrency(grandTotal)}</td>
        <td></td>
        <td></td>
      </tr>
    `;
    const aggHeader = [
      "Vendor", "From Date", "To Date", "Beat stores", "Call pickups", "Total remittance (₹)",
      "Base (₹)", "Enhancement (₹)", "Tax (₹)", "Total (₹)", "Computed By", "Charge calc date",
    ];
    vendorExportAOA = [
      aggHeader,
      ...combined.map((agg) => [
        agg.vendor_name, agg.displayFrom, agg.displayTo, agg.beat_pickups, agg.call_pickups,
        agg.total_remittance, agg.base_charge_amount, agg.enhancement_charge, agg.tax_amount, agg.total_with_tax,
        agg.computed_by, formatChargeDate(agg.computed_at),
      ]),
      ["Total vendor charge (₹)", "", "", "", "", grandRemittance, "", "", "", grandTotal, "", ""],
    ];
  } catch (error) {
    setMessage(vendorChargeMessage, error.message || "Unable to load vendor charges.", true);
  }
};

const loadVendorChargesByStore = async (monthFrom, monthTo, vendorId, storeId) => {
  if (!vendorRows) return;
  setVendorChargeHeader("by-store");
  vendorRows.innerHTML = "";
  vendorExportAOA = null;
  setMessage(vendorChargeMessage, "");
  try {
    let url = `${apiBase}/api/charges/vendor/by-store`;
    const params = [];
    if (vendorId) params.push(`vendor_id=${encodeURIComponent(vendorId)}`);
    if (storeId) params.push(`store_id=${encodeURIComponent(storeId)}`);
    if (monthFrom && monthTo) {
      const [from, to] = monthFrom <= monthTo ? [monthFrom, monthTo] : [monthTo, monthFrom];
      params.push(`month_from=${encodeURIComponent(from)}`, `month_to=${encodeURIComponent(to)}`);
    } else if (monthFrom) {
      params.push(`month_key=${encodeURIComponent(monthFrom)}`);
    }
    if (params.length) url += `?${params.join("&")}`;
    const response = await fetch(url, { headers: window.getAuthHeaders() });
    if (!response.ok) {
      const errBody = await response.json().catch(() => ({}));
      throw new Error(errBody.detail || "Failed to load per-store vendor charges");
    }
    const data = await response.json();
    if (!data.length) {
      setMessage(
        vendorChargeMessage,
        storeId
          ? "No vendor charges for the selected store in this date range."
          : "No vendor charges found. Select dates and click Go.",
      );
      return;
    }
    const userFrom = chargeDateFromVendor?.value?.trim() || null;
    const userTo = chargeDateToVendor?.value?.trim() || null;
    // When a single vendor is selected, group the rows by store (then month) so the
    // per-store split reads cleanly before the total.
    const rows = vendorId
      ? [...data].sort(
          (a, b) =>
            String(a.bank_store_code || "").localeCompare(String(b.bank_store_code || "")) ||
            String(a.month_key || "").localeCompare(String(b.month_key || "")),
        )
      : data;
    let totalCharge = 0;
    let totalRemittance = 0;
    const aoaRows = [];
    const bodyHtml = rows
      .map((r) => {
        totalCharge += Number(r.charge_amount) || 0;
        totalRemittance += Number(r.total_remittance) || 0;
        const { from, to } = monthKeyToDateRange(r.month_key);
        let displayFrom = from;
        let displayTo = to;
        if (userFrom && userFrom >= from && userFrom <= to) displayFrom = userFrom;
        if (userTo && userTo >= from && userTo <= to) displayTo = userTo;
        const vendorLabel = `${r.vendor_name || r.vendor_code || r.vendor_id}`;
        const pickupsCell = r.pickups == null ? "-" : String(r.pickups);
        const rateCell = r.rate == null ? "-" : formatCurrency(r.rate);
        aoaRows.push([
          vendorLabel,
          r.bank_store_code || "",
          r.store_name || "",
          displayFrom,
          displayTo,
          r.pickup_type || "",
          r.pickups == null ? "" : r.pickups,
          Number(r.total_remittance) || 0,
          r.rate == null ? "" : Number(r.rate),
          Number(r.charge_amount) || 0,
          formatChargeDate(r.computed_at),
        ]);
        return `
      <tr>
        <td>${escapeHtml(vendorLabel)}</td>
        <td>${escapeHtml(r.bank_store_code || "")}</td>
        <td>${escapeHtml(r.store_name || "")}</td>
        <td>${escapeHtml(displayFrom)}</td>
        <td>${escapeHtml(displayTo)}</td>
        <td>${escapeHtml(r.pickup_type || "")}</td>
        <td>${pickupsCell}</td>
        <td>${formatCurrency(r.total_remittance)}</td>
        <td>${rateCell}</td>
        <td>${formatCurrency(r.charge_amount)}</td>
        <td>${escapeHtml(formatChargeDate(r.computed_at))}</td>
      </tr>
    `;
      })
      .join("");
    // Grand total of the vendor's charges across the listed stores/months.
    const totalLabel = vendorId ? "Total vendor charge (₹)" : "Total (₹)";
    const totalRow = `
      <tr class="charge-total-row">
        <td colspan="9" style="text-align:right;font-weight:600;">${totalLabel}</td>
        <td style="font-weight:600;">${formatCurrency(totalCharge)}</td>
        <td></td>
      </tr>
    `;
    vendorRows.innerHTML = bodyHtml + totalRow;
    const byStoreHeader = [
      "Vendor", "Store code", "Store name", "Period from", "Period to",
      "Pickup type", "Pickups", "Total remittance (₹)", "Rate (₹)", "Charge (₹)", "Charge calc date",
    ];
    vendorExportAOA = [
      byStoreHeader,
      ...aoaRows,
      [totalLabel, "", "", "", "", "", "", totalRemittance, "", totalCharge, ""],
    ];
  } catch (error) {
    setMessage(vendorChargeMessage, error.message || "Unable to load per-store vendor charges.", true);
  }
};

const renderVendorChargesForCurrentFilters = (monthFrom, monthTo) => {
  const vendorId = chargeViewVendor?.value || null;
  const storeId = chargeViewStoreVendor?.value || null;
  // A specific vendor (with or without a store) gets the per-store split + total.
  // Only "All vendors + All stores" shows the per-vendor aggregate list.
  if (vendorId || storeId) {
    loadVendorChargesByStore(monthFrom, monthTo, vendorId, storeId);
  } else {
    loadVendorCharges(monthFrom, monthTo, vendorId);
  }
};

const loadCustomerCharges = async (monthFrom, monthTo, storeId = null) => {
  if (!customerRows) return;
  customerRows.innerHTML = "";
  setMessage(customerChargeMessage, "");
  try {
    let url = `${apiBase}/api/charges/customer/summary`;
    const params = [];
    if (storeId) params.push(`store_id=${encodeURIComponent(storeId)}`);
    if (monthFrom && monthTo) {
      const [from, to] = monthFrom <= monthTo ? [monthFrom, monthTo] : [monthTo, monthFrom];
      params.push(`month_from=${encodeURIComponent(from)}`, `month_to=${encodeURIComponent(to)}`);
    } else if (monthFrom) {
      params.push(`month_key=${encodeURIComponent(monthFrom)}`);
    }
    if (params.length) url += `?${params.join("&")}`;
    const response = await fetch(url, { headers: window.getAuthHeaders() });
    if (!response.ok) throw new Error("Failed to load store charges");
    const data = await response.json();
    if (!data.length) {
      setMessage(customerChargeMessage, "No store charges found. Select dates and compute.");
      return;
    }
    const byStore = {};
    for (const r of data) {
      const { from, to } = monthKeyToDateRange(r.month_key);
      let displayFrom = from;
      let displayTo = to;
      if (r.charge_period_from && r.charge_period_to) {
        displayFrom = String(r.charge_period_from).slice(0, 10);
        displayTo = String(r.charge_period_to).slice(0, 10);
      }
      const key = r.store_id;
      if (!byStore[key]) {
        byStore[key] = {
          store_id: r.store_id ?? "",
          bank_store_code: r.bank_store_code || "",
          store_name: r.store_name || "",
          vendor_name: r.vendor_name || "",
          displayFrom,
          displayTo,
          days_over_limit: r.days_over_limit ?? 0,
          total_remittance: r.total_remittance ?? 0,
          base_charge_amount: r.base_charge_amount ?? 0,
          enhancement_charge: r.enhancement_charge ?? 0,
          waiver_amount: r.store_waiver_applied ?? r.waiver_amount ?? 0,
          net_charge_amount: r.net_charge_amount ?? 0,
          total_with_tax: r.total_with_tax ?? 0,
          computed_by: r.computed_by || "",
          computed_at: r.computed_at || null,
        };
      } else {
        const agg = byStore[key];
        agg.displayFrom = agg.displayFrom < displayFrom ? agg.displayFrom : displayFrom;
        agg.displayTo = agg.displayTo > displayTo ? agg.displayTo : displayTo;
        if (!agg.vendor_name && r.vendor_name) agg.vendor_name = r.vendor_name;
        agg.days_over_limit += Number(r.days_over_limit ?? 0);
        agg.total_remittance += r.total_remittance ?? 0;
        agg.base_charge_amount += r.base_charge_amount ?? 0;
        agg.enhancement_charge += r.enhancement_charge ?? 0;
        agg.waiver_amount += r.waiver_amount ?? 0;
        agg.net_charge_amount += r.net_charge_amount ?? 0;
        agg.total_with_tax += r.total_with_tax ?? 0;
        if (r.computed_at && (!agg.computed_at || r.computed_at > agg.computed_at)) {
          agg.computed_at = r.computed_at;
        }
      }
    }
    const combined = Object.values(byStore);
    customerRows.innerHTML = combined
      .map(
        (agg) => `
      <tr>
        <td>${escapeHtml(agg.store_id)}</td>
        <td>${escapeHtml(agg.bank_store_code)}</td>
        <td>${escapeHtml(agg.store_name)}</td>
        <td>${escapeHtml(agg.vendor_name)}</td>
        <td>${escapeHtml(agg.displayFrom)}</td>
        <td>${escapeHtml(agg.displayTo)}</td>
        <td>${agg.days_over_limit != null ? Number(agg.days_over_limit) : ""}</td>
        <td>${formatCurrency(agg.total_remittance)}</td>
        <td>${formatCurrency(agg.base_charge_amount)}</td>
        <td>${formatCurrency(agg.enhancement_charge)}</td>
        <td>${formatCurrency(agg.waiver_amount)}</td>
        <td>${formatCurrency(agg.net_charge_amount)}</td>
        <td>${formatCurrency(agg.total_with_tax)}</td>
        <td>${escapeHtml(agg.computed_by)}</td>
        <td>${escapeHtml(formatChargeDate(agg.computed_at))}</td>
      </tr>
    `,
      )
      .join("");
  } catch (error) {
    setMessage(customerChargeMessage, error.message || "Unable to load store charges.", true);
  }
};

const computeMonthsBatch = async (type, months, vendorIds, fromVal, toVal, overwrite) => {
  let totalComputed = 0;
  const skipped409Months = [];
  const customerDiag = { noReconFinal: 0, hadReconNoCharges: 0, staleDbSummaries: null };
  for (const monthKey of months) {
    const payload = { month_key: monthKey };
    if (vendorIds) payload.vendor_ids = vendorIds;
    if (type === "customer" && fromVal) {
      payload.from_date = fromVal;
      payload.to_date = toVal || fromVal;
    }
    if (overwrite) payload.overwrite = true;
    const response = await fetch(`${apiBase}/api/charges/${type}/compute`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...window.getAuthHeaders() },
      body: JSON.stringify(payload),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      if (response.status === 409) {
        skipped409Months.push(monthKey);
        continue;
      }
      throw new Error(data.detail || response.statusText || "Compute failed");
    }
    totalComputed += data.computed ?? 0;
    if (type === "customer") {
      const reconRows = data.reconciliation_final_rows ?? 0;
      const comp = data.computed ?? 0;
      const stored = data.customer_summaries_in_db_for_month ?? 0;
      if (comp === 0 && reconRows === 0) customerDiag.noReconFinal += 1;
      if (comp === 0 && reconRows > 0) customerDiag.hadReconNoCharges += 1;
      if (comp === 0 && reconRows === 0 && stored > 0) {
        customerDiag.staleDbSummaries = Math.max(customerDiag.staleDbSummaries ?? 0, stored);
      }
    }
  }
  return { totalComputed, skipped409Months, customerDiag };
};

const computeCharges = async (type) => {
  const fromEl = type === "vendor" ? chargeDateFromVendor : chargeDateFromCustomer;
  const toEl = type === "vendor" ? chargeDateToVendor : chargeDateToCustomer;
  const msgEl = type === "vendor" ? chargeVendorMessage : chargeCustomerMessage;
  const fromVal = fromEl?.value?.trim();
  const toVal = toEl?.value?.trim();
  const monthFrom = dateToMonthKey(fromVal);
  const monthTo = dateToMonthKey(toVal) || monthFrom;
  if (!monthFrom || monthFrom.length !== 6) {
    setMessage(msgEl, "Select From Date to compute charges", true);
    return;
  }
  const months = getMonthsInRange(monthFrom, monthTo);
  const vendorIds = type === "vendor" && chargeViewVendor?.value ? [Number(chargeViewVendor.value)] : null;

  // Checkers/Auditors have view-only access: load saved charges without
  // recomputing (compute is restricted to Makers/Admins on the backend).
  const role = (currentUser().role || "").toUpperCase();
  if (role !== "MAKER" && role !== "ADMIN") {
    setMessage(msgEl, "");
    if (type === "vendor") {
      renderVendorChargesForCurrentFilters(monthFrom, monthTo);
    } else {
      const storeId = document.querySelector("#charge-view-store")?.value || null;
      loadCustomerCharges(monthFrom, monthTo, storeId);
    }
    return;
  }

  setMessage(msgEl, `Computing ${type} charges for ${months.length} month(s)...`);
  try {
    const result = await computeMonthsBatch(type, months, vendorIds, fromVal, toVal, false);

    // If some months already have saved charges, ask before overwriting them.
    if (result.skipped409Months.length) {
      const proceed = window.confirm(
        "Click OK to overwrite and recompute this months now or Cancel to keep the saved data.",
      );
      if (proceed) {
        const redo = await computeMonthsBatch(type, result.skipped409Months, vendorIds, fromVal, toVal, true);
        result.totalComputed += redo.totalComputed;
        result.skipped409Months = redo.skipped409Months;
        if (type === "customer") {
          result.customerDiag.noReconFinal += redo.customerDiag.noReconFinal;
          result.customerDiag.hadReconNoCharges += redo.customerDiag.hadReconNoCharges;
          if (redo.customerDiag.staleDbSummaries) {
            result.customerDiag.staleDbSummaries = Math.max(
              result.customerDiag.staleDbSummaries ?? 0,
              redo.customerDiag.staleDbSummaries,
            );
          }
        }
      }
    }

    const skipped = result.skipped409Months.length;
    let doneMsg = `${type} charges computed: ${result.totalComputed} records across ${months.length} month(s).`;
    if (type === "customer" && skipped > 0) {
      doneMsg += ` ${skipped} month(s) were already computed and were kept as saved-grid shows saved full-month totals, not only the From/To dates you selected this time.`;
    }
    if (type === "vendor" && skipped > 0) {
      doneMsg += ` ${skipped} month(s) had vendor charge rows already saved and were kept.`;
    }
    if (type === "customer" && result.totalComputed === 0) {
      if (result.customerDiag.noReconFinal > 0) {
        doneMsg +=
          " No final Daily Reconciliation rows in range-run Reconciliation for each MIS date, resolve exceptions, then Save as final. Dates must fall in the selected month and From/To range.";
        if (result.customerDiag.staleDbSummaries) {
          doneMsg += ` The grid may still show ${result.customerDiag.staleDbSummaries} older saved row(s) for this month from a previous compute-not updated this time.`;
        }
      } else if (result.customerDiag.hadReconNoCharges > 0) {
        doneMsg +=
          " Final reconciliation rows were read but no charge lines were produced-check stores are active with daily limit / monthly charge where needed, and bank store codes match reconciliation.";
      }
    }
    setMessage(msgEl, doneMsg);
    if (type === "vendor") {
      renderVendorChargesForCurrentFilters(monthFrom, monthTo);
    } else {
      const storeId = document.querySelector("#charge-view-store")?.value || null;
      loadCustomerCharges(monthFrom, monthTo, storeId);
    }
  } catch (error) {
    setMessage(msgEl, error.message || "Compute failed", true);
  }
};

const loadVendors = async (selectIds) => {
  const ids = Array.isArray(selectIds) ? selectIds : [selectIds];
  const selects = ids.map((id) => document.querySelector(id)).filter(Boolean);
  if (!selects.length) return;
  try {
    const response = await fetch(`${apiBase}/api/vendors`, { headers: window.getAuthHeaders() });
    if (!response.ok) return;
    const vendors = await response.json();
    const active = vendors.filter((v) => v.status === "ACTIVE");
    selects.forEach((sel) => {
      const isChargeView = sel.id === "charge-view-vendor";
      sel.innerHTML = isChargeView
        ? '<option value="">All vendors</option>'
        : '<option value="">Select vendor</option>';
      active.forEach((v) => {
        const opt = document.createElement("option");
        opt.value = v.vendor_id;
        opt.textContent = `${v.name || ""} (${v.code || ""})`.trim() || v.vendor_id;
        sel.appendChild(opt);
      });
    });
  } catch (e) {}
};

const populateStoreSelect = (selectEl, stores) => {
  if (!selectEl) return;
  selectEl.innerHTML = '<option value="">All stores</option>';
  stores.forEach((s) => {
    const opt = document.createElement("option");
    opt.value = s.store_id;
    opt.textContent = `${s.bank_store_code || ""} ${s.store_name ? `(${s.store_name})` : ""}`.trim() || s.store_id;
    selectEl.appendChild(opt);
  });
};

const loadStoresForChargeView = async () => {
  const customerStoreSel = document.querySelector("#charge-view-store");
  const vendorStoreSel = document.querySelector("#charge-view-store-vendor");
  if (!customerStoreSel && !vendorStoreSel) return;
  try {
    const response = await fetch(`${apiBase}/api/bank-stores`, { headers: window.getAuthHeaders() });
    if (!response.ok) return;
    const stores = await response.json();
    const active = stores.filter((s) => (s.status || "ACTIVE").toUpperCase() === "ACTIVE");
    populateStoreSelect(customerStoreSel, active);
    populateStoreSelect(vendorStoreSel, active);
  } catch (e) {}
};

/** Matches backend charge codes used in customer charge computation for daily excess above store limit. */
const CUSTOMER_EXCESS_THRESHOLD_CODE = "ENHANCEMENT_THRESHOLD_AMOUNT";
const CUSTOMER_EXCESS_CHARGE_CODE = "ENHANCEMENT_CHARGE_AMOUNT";

const formatConfigDate = (iso) => {
  if (!iso || typeof iso !== "string") return "-";
  return iso.length >= 10 ? iso.slice(0, 10) : iso;
};

const loadCustomerExcessChargeDisplay = async () => {
  const tbody = document.querySelector("#customer-excess-active-rows");
  const footnote = document.querySelector("#customer-excess-active-footnote");
  const inpStep = document.querySelector("#customer-excess-step-amount");
  const inpPer = document.querySelector("#customer-excess-charge-per-step");
  if (!tbody) return;

  const setFootnote = (text) => {
    if (!footnote) return;
    if (text) {
      footnote.textContent = text;
      footnote.hidden = false;
    } else {
      footnote.textContent = "";
      footnote.hidden = true;
    }
  };

  const fmtAmt = (v) =>
    v != null && v !== "" && !Number.isNaN(Number(v)) ? Number(v).toLocaleString("en-IN") : "-";

  const statusLabel = (row) => {
    if (!row?.row_status) return "-";
    if (row.row_status === "ACTIVE") return "Active";
    if (row.row_status === "PENDING") return "Pending approval";
    return "-";
  };

  try {
    const res = await fetch(`${apiBase}/api/charge-configs/customer-excess-display`, {
      headers: window.getAuthHeaders(),
    });
    if (!res.ok) {
      tbody.innerHTML =
        '<tr><td colspan="5">Unable to load configuration. Check session and try again.</td></tr>';
      setFootnote("");
      return;
    }
    const data = await res.json();
    const t = data.threshold;
    const c = data.charge_per_step;
    const tv = t?.value_number;
    const cv = c?.value_number;

    tbody.innerHTML = "";
    const appendRow = (setting, amount, effFrom, effTo, row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${setting}</td>
        <td>${fmtAmt(amount)}</td>
        <td>${formatConfigDate(effFrom)}</td>
        <td>${effTo ? formatConfigDate(effTo) : "-"}</td>
        <td>${statusLabel(row)}</td>
      `;
      tbody.appendChild(tr);
    };

    appendRow("Excess amount per step", tv, t?.effective_from, t?.effective_to, t);
    appendRow("Charge per step", cv, c?.effective_from, c?.effective_to, c);

    const hasPending = t?.row_status === "PENDING" || c?.row_status === "PENDING";
    if (!c) {
      setFootnote("");
    } else if (hasPending) {
      setFootnote(
        "Pending approval: not used in customer charge runs until the checker approves. Both ENHANCEMENT_THRESHOLD_AMOUNT and ENHANCEMENT_CHARGE_AMOUNT must be active for saved values to apply.",
      );
    } else {
      setFootnote("");
    }

    const prefillStep = tv != null && tv !== "" && !Number.isNaN(Number(tv));
    const prefillCharge = cv != null && cv !== "" && !Number.isNaN(Number(cv));
    if (inpStep && prefillStep) inpStep.value = String(Number(tv));
    if (inpPer && prefillCharge) inpPer.value = String(Number(cv));
  } catch {
    tbody.innerHTML =
      '<tr><td colspan="5">Unable to load active configuration.</td></tr>';
    setFootnote("");
  }
};

// Filters (vendor / store) no longer auto-fetch. Charges are loaded only when
// the user clicks the Go (Compute) button, using the current filter selection.

const bindForm = (formId, messageId, handler) => {
  const form = document.querySelector(formId);
  const message = document.querySelector(messageId);
  if (!form) return;
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (message) message.textContent = "Submitting...";
    try {
      await handler(new FormData(form));
      if (message) message.textContent = "Request submitted for approval.";
      form.reset();
    } catch (error) {
      if (message) {
        message.textContent = error.message || "Request failed.";
        message.style.color = "#b42318";
      }
    }
  });
};

const switchTab = (tab) => {
  document.querySelectorAll(".charge-tab").forEach((b) => b.classList.remove("active"));
  document.querySelectorAll(".charge-panel").forEach((p) => {
    const isVisible = p.id === `${tab}-panel`;
    p.classList.toggle("hidden", !isVisible);
  });
  document.querySelector(`.charge-tab[data-tab='${tab}']`)?.classList.add("active");
  window.location.hash = tab;
  if (tab === "vendor") {
    if (vendorRows && !vendorRows.innerHTML.trim()) {
      setMessage(vendorChargeMessage, "");
    }
  } else if (tab === "customer") {
    if (customerRows && !customerRows.innerHTML.trim()) {
      setMessage(customerChargeMessage, "");
    }
    loadCustomerExcessChargeDisplay();
  }
};

document.querySelectorAll(".charge-tab").forEach((btn) => {
  btn.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    switchTab(btn.dataset.tab);
    return false;
  });
});

// On load: show only the selected tab (no auto-load of charges; user must click Compute)
const hash = window.location.hash.replace("#", "");
const initialTab = hash === "customer" ? "customer" : "vendor";
switchTab(initialTab);

if (computeVendorBtn) computeVendorBtn.addEventListener("click", () => computeCharges("vendor"));
if (computeCustomerBtn) computeCustomerBtn.addEventListener("click", () => computeCharges("customer"));

const downloadChargeReport = async (type) => {
  const fromEl = type === "vendor" ? chargeDateFromVendor : chargeDateFromCustomer;
  const toEl = type === "vendor" ? chargeDateToVendor : chargeDateToCustomer;
  const msgEl = type === "vendor" ? chargeVendorMessage : chargeCustomerMessage;
  const fromVal = fromEl?.value?.trim();
  const toVal = toEl?.value?.trim();
  let fromDate = fromVal;
  let toDate = toVal;
  if (!fromDate || !toDate) {
    const monthFrom = dateToMonthKey(fromVal) || dateToMonthKey(toVal);
    if (!monthFrom) {
      setMessage(msgEl, "Select From Date and To Date to download report", true);
      return;
    }
    const monthTo = dateToMonthKey(toVal) || monthFrom;
    const range = monthKeyToDateRange(monthFrom <= monthTo ? monthFrom : monthTo);
    fromDate = fromDate || range.from;
    toDate = toDate || monthKeyToDateRange(monthFrom <= monthTo ? monthTo : monthFrom).to;
  }
  try {
    const endpoint = type === "vendor" ? "vendor-charges" : "customer-charges";
    const url = `${apiBase}/api/reports/${endpoint}?from_date=${encodeURIComponent(fromDate)}&to_date=${encodeURIComponent(toDate)}`;
    const response = await fetch(url, { headers: window.getAuthHeaders() });
    if (!response.ok) throw new Error("Download failed");
    const blob = await response.blob();
    const filename = `${endpoint.replace("-", "_")}_${fromDate}_to_${toDate}.xlsx`;
    window.saveBlob(blob, filename);
    setMessage(msgEl, `Report downloaded for ${fromDate} to ${toDate}.`);
  } catch (error) {
    setMessage(msgEl, error.message || "Download failed", true);
  }
};

const downloadVendorPreview = () => {
  if (!vendorExportAOA || vendorExportAOA.length <= 1) {
    setMessage(chargeVendorMessage, "Nothing to download yet-click Go to load the charges first.", true);
    return;
  }
  if (typeof XLSX === "undefined") {
    setMessage(chargeVendorMessage, "Excel library not loaded. Refresh the page and try again.", true);
    return;
  }
  const ws = XLSX.utils.aoa_to_sheet(vendorExportAOA);
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, "Vendor Charges");
  const fromVal = chargeDateFromVendor?.value?.trim() || "";
  const toVal = chargeDateToVendor?.value?.trim() || "";
  const stamp = fromVal && toVal ? `${fromVal}_to_${toVal}` : new Date().toISOString().slice(0, 10);
  XLSX.writeFile(wb, `vendor_charges_${stamp}.xlsx`);
  setMessage(chargeVendorMessage, "Downloaded the previewed vendor charges.");
};

const downloadVendorBtn = document.querySelector("#download-vendor-charges");
const downloadCustomerBtn = document.querySelector("#download-customer-charges");
if (downloadVendorBtn) downloadVendorBtn.addEventListener("click", () => downloadVendorPreview());
if (downloadCustomerBtn) downloadCustomerBtn.addEventListener("click", () => downloadChargeReport("customer"));

bindForm("#charge-config-form", "#charge-config-message", async (data) => {
  await postJson(`${apiBase}/api/charge-configs/requests`, {
    config_code: data.get("configCode"),
    config_name: data.get("configName"),
    value_number: data.get("valueNumber") ? Number(data.get("valueNumber")) : null,
    value_text: data.get("valueText") || null,
    effective_from: data.get("effectiveFrom"),
    status: "ACTIVE",
    maker_id: currentUser().employeeId,
  });
});

const customerExcessForm = document.querySelector("#customer-excess-charge-form");
const customerExcessMsg = document.querySelector("#customer-excess-charge-message");
if (customerExcessForm) {
  customerExcessForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (customerExcessMsg) {
      customerExcessMsg.textContent = "Submitting...";
      customerExcessMsg.style.color = "#0f4c81";
    }
    const fd = new FormData(customerExcessForm);
    const eff = fd.get("effectiveFrom");
    const step = fd.get("excessStepAmount");
    const per = fd.get("chargePerStep");
    try {
      await postJson(`${apiBase}/api/charge-configs/requests/customer-excess-pair`, {
        excess_step_amount: Number(step),
        charge_per_step: Number(per),
        effective_from: eff,
        maker_id: currentUser().employeeId,
      });
      if (customerExcessMsg) {
        customerExcessMsg.textContent =
          "Two requests submitted for checker approval (excess step + charge per step).";
        customerExcessMsg.style.color = "#0f4c81";
      }
      await loadCustomerExcessChargeDisplay();
    } catch (err) {
      if (customerExcessMsg) {
        let msg = err?.message || "Request failed.";
        if (msg === "Failed to fetch") {
          msg =
            "Could not reach the server (network or API crash). Check the API console. If you see ORA-00001 on charge config, run migration: drop_charge_config_code_unique.sql";
        }
        customerExcessMsg.textContent = msg;
        customerExcessMsg.style.color = "#b42318";
      }
    }
  });
}

initDate(chargeDateFromVendor);
initDate(chargeDateToVendor);
initDate(chargeDateFromCustomer);
initDate(chargeDateToCustomer);
initDate(document.querySelector("#customer-excess-effective-from"));
loadVendors(["#charge-view-vendor"]);
loadStoresForChargeView();
loadChargeClarifications();
