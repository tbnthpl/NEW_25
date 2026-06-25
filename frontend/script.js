const form = document.querySelector("#login-form");
const message = document.querySelector("#form-message");
const passwordInput = document.querySelector("#password-input");
const togglePassword = document.querySelector("#toggle-password");
const API_BASE = window.API_BASE || "";

const handleLoginSuccess = (user) => {
  sessionStorage.setItem(
    "currentUser",
    JSON.stringify({
      employeeId: user.employeeId,
      name: user.name,
      role: user.role,
    }),
  );
  if (user && user.token) {
    sessionStorage.setItem("authToken", user.token);
  } else {
    sessionStorage.removeItem("authToken");
  }

  message.textContent = `Welcome, ${user.name}. Redirecting to dashboard...`;
  message.style.color = "#0f4c81";
  window.location.href = "dashboard.html";
};

togglePassword.addEventListener("click", () => {
  const isPassword = passwordInput.type === "password";
  passwordInput.type = isPassword ? "text" : "password";
  togglePassword.textContent = isPassword ? "Hide" : "Show";
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const formData = new FormData(form);
  const employeeId = formData.get("employeeId").trim();
  const password = formData.get("password").trim();

  if (!employeeId || !password) {
    message.textContent = "Please enter both Employee ID and password.";
    message.style.color = "#b42318";
    return;
  }

  message.textContent = "Signing in...";
  message.style.color = "#0f4c81";

  try {
    const response = await fetch(`${API_BASE}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ employeeId, password }),
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      const detail = data.detail || "Login failed";
      if (response.status === 401) {
        message.textContent = detail === "Invalid credentials"
          ? "Invalid credentials. Check Employee ID and password, or ensure you have application access."
          : detail;
      } else {
        message.textContent = detail;
      }
      message.style.color = "#b42318";
      return;
    }

    handleLoginSuccess(data);
  } catch (error) {
    message.textContent =
      "Auth service unavailable. Please try again or contact admin.";
    message.style.color = "#b42318";
  }
});
