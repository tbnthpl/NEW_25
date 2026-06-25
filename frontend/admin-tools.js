const cleanupForm = document.querySelector("#admin-cleanup-form");
const cleanupMessage = document.querySelector("#admin-cleanup-message");
const cleanupResult = document.querySelector("#admin-cleanup-result");
const resetAllForm = document.querySelector("#admin-reset-all-form");
const resetMessage = document.querySelector("#admin-reset-message");
const userAddForm = document.querySelector("#user-add-form");
const userAddMessage = document.querySelector("#user-add-message");
const userListRows = document.querySelector("#user-list-rows");
const userListMessage = document.querySelector("#user-list-message");
const finacleMappingForm = document.querySelector("#finacle-mapping-form");
const finacleMappingFields = document.querySelector("#finacle-mapping-fields");
const finacleMappingMessage = document.querySelector("#finacle-mapping-message");
const finacleMappingReset = document.querySelector("#finacle-mapping-reset");
const apiBase = window.API_BASE || "";

const FINACLE_MAPPING_LABELS = {
  store_code_column: "Store Code",
  remittance_amount_column: "Remittance Amount",
  remittance_date_column: "Remittance Date",
  account_no_column: "Account No",
  customer_id_column: "Customer ID",
  customer_name_column: "Customer Name",
  sol_id_column: "SOL ID",
  location_column: "Location",
  tran_id_column: "Transaction ID",
  tran_type_column: "Transaction Type",
};

const FINACLE_DEFAULT_MAPPING = {
  store_code_column: "STORE_CODE",
  remittance_amount_column: "COLLN_AMT",
  remittance_date_column: "TRAN_DATE",
  account_no_column: "FORACID",
  customer_id_column: "CUST_ID",
  customer_name_column: "ACCT_NAME",
  sol_id_column: "SOL_ID",
  location_column: "LOCATION",
  tran_id_column: "TRAN_ID",
  tran_type_column: "TRAN_TYPE",
};

if (resetAllForm) {
  resetAllForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    resetMessage.textContent = "";
    const reason = resetAllForm.querySelector('textarea[name="reason"]')?.value?.trim();
    const confirmText = resetAllForm.querySelector('input[name="confirm"]')?.value?.trim();
    if (!reason) {
      resetMessage.textContent = "Reason is required.";
      resetMessage.style.color = "#b42318";
      return;
    }
    if (confirmText !== "RESET ALL") {
      resetMessage.textContent = 'Type "RESET ALL" (exactly) to proceed.';
      resetMessage.style.color = "#b42318";
      return;
    }
    resetMessage.textContent = "Resetting application...";
    resetMessage.style.color = "#0f4c81";
    try {
      const response = await fetch(`${apiBase}/api/admin/reset-all`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...window.getAuthHeaders() },
        body: JSON.stringify({ reason, confirm_text: confirmText }),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        resetMessage.textContent = data?.detail || "Reset failed.";
        resetMessage.style.color = "#b42318";
        return;
      }
      const data = await response.json();
      resetMessage.textContent = data?.message || "Reset complete. Refreshing...";
      resetMessage.style.color = "#0f4c81";
      resetAllForm.reset();
      setTimeout(() => window.location.reload(), 1500);
    } catch (error) {
      resetMessage.textContent = "Reset failed.";
      resetMessage.style.color = "#b42318";
    }
  });
}

if (cleanupForm) {
  cleanupForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    cleanupMessage.textContent = "";
    cleanupResult.textContent = "";

      const formData = new FormData(cleanupForm);
    const targets = formData.getAll("targets");
    const reason = formData.get("reason")?.trim();
    const confirmText = formData.get("confirm")?.trim();

    if (!targets.length) {
      cleanupMessage.textContent = "Select at least one data area.";
      cleanupMessage.style.color = "#b42318";
      return;
    }
    if (!reason) {
      cleanupMessage.textContent = "Reason is required.";
      cleanupMessage.style.color = "#b42318";
      return;
    }
    if (confirmText !== "CONFIRM") {
      cleanupMessage.textContent = 'Type "CONFIRM" to proceed.';
      cleanupMessage.style.color = "#b42318";
      return;
    }

    cleanupMessage.textContent = "Clearing data...";
    cleanupMessage.style.color = "#0f4c81";

    try {
      const response = await fetch(`${apiBase}/api/admin/cleanup`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...window.getAuthHeaders() },
        body: JSON.stringify({
          targets,
          reason,
          confirm_text: confirmText,
        }),
      });
      if (!response.ok) {
        let detail = "";
        try {
          const data = await response.json();
          detail = data?.detail || "";
        } catch (error) {
          detail = "";
        }
        cleanupMessage.textContent = detail || "Cleanup failed.";
        cleanupMessage.style.color = "#b42318";
        return;
      }
      const data = await response.json();
      cleanupMessage.textContent = "Cleanup completed.";
      cleanupMessage.style.color = "#0f4c81";
      cleanupResult.textContent = JSON.stringify(data.deleted || {}, null, 2);
      cleanupForm.reset();
    } catch (error) {
      cleanupMessage.textContent = "Cleanup failed.";
      cleanupMessage.style.color = "#b42318";
    }
  });
}

const loadUsers = async () => {
  if (!userListRows) return;
  userListRows.innerHTML = "";
  userListMessage.textContent = "";
  try {
    const response = await fetch(`${apiBase}/api/users`, {
      headers: window.getAuthHeaders(),
    });
    if (!response.ok) throw new Error("Failed to load users");
    const users = await response.json();
    if (!users.length) {
      userListMessage.textContent = "No users with access. Add users above.";
      return;
    }
    const currentUser = JSON.parse(sessionStorage.getItem("currentUser") || "{}");
    const currentId = currentUser.employeeId;
    const esc = window.escapeHtml || ((v) => String(v ?? ""));
    userListRows.innerHTML = users
      .map(
        (u) => {
          const isSelf = u.employee_id === currentId;
          const userIdAttr = Number(u.user_id) || 0;
          return `
      <tr>
        <td>${esc(u.employee_id || "")}</td>
        <td>${esc(u.full_name || "")}</td>
        <td>${esc(u.role_code || "")}</td>
        <td>${esc(u.status || "")}</td>
        <td>${u.last_login_date ? esc((window.formatDate || ((s) => String(s).slice(0, 10)))(u.last_login_date)) : "-"}</td>
        <td class="button-row">
          ${u.status === "ACTIVE" ? (isSelf ? "<span class=\"form-message\">(you)</span>" : `<button class="secondary-btn user-deactivate" data-user-id="${userIdAttr}">Deactivate</button>`) : `<button class="secondary-btn user-activate" data-user-id="${userIdAttr}">Activate</button>`}
          <select class="user-role-select" data-user-id="${userIdAttr}" ${u.status !== "ACTIVE" ? "disabled" : ""} style="min-width: 100px;">
            <option value="MAKER" ${u.role_code === "MAKER" ? "selected" : ""}>MAKER</option>
            <option value="CHECKER" ${u.role_code === "CHECKER" ? "selected" : ""}>CHECKER</option>
            <option value="ADMIN" ${u.role_code === "ADMIN" ? "selected" : ""}>ADMIN</option>
            <option value="AUDITOR" ${u.role_code === "AUDITOR" ? "selected" : ""}>AUDITOR</option>
          </select>
        </td>
      </tr>
    `;
        },
      )
      .join("");
    userListRows.querySelectorAll(".user-deactivate").forEach((btn) => {
      btn.addEventListener("click", () => deactivateUser(Number(btn.dataset.userId)));
    });
    userListRows.querySelectorAll(".user-activate").forEach((btn) => {
      btn.addEventListener("click", () => activateUser(Number(btn.dataset.userId)));
    });
    userListRows.querySelectorAll(".user-role-select").forEach((sel) => {
      sel.addEventListener("change", () => updateRole(Number(sel.dataset.userId), sel.value));
    });
  } catch (error) {
    userListMessage.textContent = error.message || "Unable to load users.";
    userListMessage.style.color = "#b42318";
  }
};

const deactivateUser = async (userId) => {
  try {
    const response = await fetch(`${apiBase}/api/users/${userId}/deactivate`, {
      method: "PATCH",
      headers: window.getAuthHeaders(),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail || "Deactivate failed");
    }
    loadUsers();
  } catch (error) {
    userListMessage.textContent = error.message || "Deactivate failed.";
    userListMessage.style.color = "#b42318";
  }
};

const activateUser = async (userId) => {
  try {
    const response = await fetch(`${apiBase}/api/users/${userId}/activate`, {
      method: "PATCH",
      headers: window.getAuthHeaders(),
    });
    if (!response.ok) throw new Error("Activate failed");
    loadUsers();
  } catch (error) {
    userListMessage.textContent = error.message || "Activate failed.";
    userListMessage.style.color = "#b42318";
  }
};

const updateRole = async (userId, roleCode) => {
  try {
    const response = await fetch(`${apiBase}/api/users/${userId}/role`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...window.getAuthHeaders() },
      body: JSON.stringify({ role_code: roleCode }),
    });
    if (!response.ok) throw new Error("Update role failed");
    loadUsers();
  } catch (error) {
    userListMessage.textContent = error.message || "Update role failed.";
    userListMessage.style.color = "#b42318";
  }
};

if (userAddForm) {
  userAddForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(userAddForm);
    userAddMessage.textContent = "Adding user...";
    userAddMessage.style.color = "#0f4c81";
    try {
      const response = await fetch(`${apiBase}/api/users`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...window.getAuthHeaders() },
        body: JSON.stringify({
          employee_id: fd.get("employeeId")?.trim(),
          full_name: fd.get("fullName")?.trim(),
          role_code: fd.get("roleCode")?.trim(),
        }),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || "Add user failed");
      }
      userAddMessage.textContent = "User added. They can now log in with Bank AD.";
      userAddForm.reset();
      loadUsers();
    } catch (error) {
      userAddMessage.textContent = error.message || "Add user failed.";
      userAddMessage.style.color = "#b42318";
    }
  });
}

loadUsers();

// Finacle column mapping (admin only)
const loadFinacleMapping = async () => {
  if (!finacleMappingFields) return;
  finacleMappingMessage.textContent = "";
  try {
    const response = await fetch(`${apiBase}/api/finacle-format`, {
      headers: window.getAuthHeaders(),
    });
    if (!response.ok) throw new Error("Failed to load mapping");
    const data = await response.json();
    const mapping = data.mapping || {};
    const esc = window.escapeHtml || ((s) => String(s ?? ""));
    finacleMappingFields.innerHTML = Object.keys(FINACLE_MAPPING_LABELS)
      .map(
        (key) => `
      <label class="field">
        <span class="label">${esc(FINACLE_MAPPING_LABELS[key])}</span>
        <input type="text" name="${esc(key)}" value="${esc(mapping[key] || "")}" placeholder="e.g. STORE_CODE" />
      </label>
    `
      )
      .join("");
  } catch (error) {
    finacleMappingMessage.textContent = error.message || "Unable to load mapping.";
    finacleMappingMessage.style.color = "#b42318";
  }
};

if (finacleMappingForm) {
  finacleMappingForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    finacleMappingMessage.textContent = "";
    const mapping = {};
    Object.keys(FINACLE_MAPPING_LABELS).forEach((key) => {
      const val = finacleMappingForm.querySelector(`[name="${key}"]`)?.value?.trim();
      mapping[key] = val || FINACLE_DEFAULT_MAPPING[key] || "";
    });
    const empty = Object.entries(mapping).filter(([, v]) => !v);
    if (empty.length) {
      finacleMappingMessage.textContent = "All fields are required.";
      finacleMappingMessage.style.color = "#b42318";
      return;
    }
    finacleMappingMessage.textContent = "Saving...";
    finacleMappingMessage.style.color = "#0f4c81";
    try {
      const response = await fetch(`${apiBase}/api/finacle-format`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...window.getAuthHeaders() },
        body: JSON.stringify({ mapping }),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || "Save failed");
      }
      finacleMappingMessage.textContent = "Mapping saved.";
      finacleMappingMessage.style.color = "#0f4c81";
    } catch (error) {
      finacleMappingMessage.textContent = error.message || "Save failed.";
      finacleMappingMessage.style.color = "#b42318";
    }
  });
}

if (finacleMappingReset) {
  finacleMappingReset.addEventListener("click", async () => {
    if (!confirm("Reset to default column names?")) return;
    finacleMappingMessage.textContent = "";
    try {
      const response = await fetch(`${apiBase}/api/finacle-format/reset`, {
        method: "POST",
        headers: window.getAuthHeaders(),
      });
      if (!response.ok) throw new Error("Reset failed");
      finacleMappingMessage.textContent = "Reset to defaults.";
      finacleMappingMessage.style.color = "#0f4c81";
      loadFinacleMapping();
    } catch (error) {
      finacleMappingMessage.textContent = error.message || "Reset failed.";
      finacleMappingMessage.style.color = "#b42318";
    }
  });
}

if (finacleMappingFields) loadFinacleMapping();
