const initForm = document.querySelector("#remittance-init-form");
const initMessage = document.querySelector("#remittance-init-message");
const actionForm = document.querySelector("#remittance-action-form");
const actionMessage = document.querySelector("#remittance-action-message");
const remittanceRows = document.querySelector("#remittance-rows");
const API_BASE = window.API_BASE || "";
const escapeHtml = window.escapeHtml || ((value) => String(value ?? ""));

const currentUser = () =>
  sessionStorage.getItem("currentUser")
    ? JSON.parse(sessionStorage.getItem("currentUser"))
    : { employeeId: "SYSTEM" };

initForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  initMessage.textContent = "Submitting...";
  initMessage.style.color = "#0f4c81";

  const data = new FormData(initForm);
  const ids = data
    .get("canonicalIds")
    .split(",")
    .map((id) => Number(id.trim()))
    .filter((id) => !Number.isNaN(id));

  try {
    const response = await fetch(`${API_BASE}/api/remittances/initialize`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...window.getAuthHeaders() },
      body: JSON.stringify({ canonical_ids: ids, maker_id: currentUser().employeeId }),
    });
    if (!response.ok) throw new Error();
    initMessage.textContent = "Remittances initialized.";
    initForm.reset();
  } catch (error) {
    initMessage.textContent = "Request failed.";
    initMessage.style.color = "#b42318";
  }
});

actionForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  actionMessage.textContent = "Submitting...";
  actionMessage.style.color = "#0f4c81";

  const data = new FormData(actionForm);
  const remittanceId = Number(data.get("remittanceId"));
  const action = data.get("action");
  const reason = data.get("reason");

  try {
    let response;
    if (action === "VALIDATE") {
      response = await fetch(`${API_BASE}/api/remittances/validate`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...window.getAuthHeaders() },
        body: JSON.stringify({ remittance_id: remittanceId, maker_id: currentUser().employeeId }),
      });
    } else if (action === "CLOSE") {
      response = await fetch(`${API_BASE}/api/remittances/close`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...window.getAuthHeaders() },
        body: JSON.stringify({ remittance_id: remittanceId, maker_id: currentUser().employeeId }),
      });
    } else {
      response = await fetch(`${API_BASE}/api/remittances/requests`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...window.getAuthHeaders() },
        body: JSON.stringify({
          remittance_id: remittanceId,
          action,
          maker_id: currentUser().employeeId,
          rejection_reason: reason || null,
        }),
      });
    }

    if (!response.ok) throw new Error();
    actionMessage.textContent = "Action submitted.";
    actionForm.reset();
  } catch (error) {
    actionMessage.textContent = "Action failed.";
    actionMessage.style.color = "#b42318";
  }
});

const loadRemittances = async () => {
  const response = await fetch(`${API_BASE}/api/remittances?status_filter=UPLOADED`, {
    headers: window.getAuthHeaders(),
  });
  if (!response.ok) {
    remittanceRows.innerHTML = "";
    return;
  }
  const items = await response.json();
  remittanceRows.innerHTML = items
    .map(
      (item) =>
        `<tr>
          <td>${escapeHtml(item.remittance_id)}</td>
          <td>${escapeHtml(item.canonical_id)}</td>
          <td>${escapeHtml(item.source)}</td>
          <td>${escapeHtml(item.status)}</td>
        </tr>`,
    )
    .join("");
};

loadRemittances();
