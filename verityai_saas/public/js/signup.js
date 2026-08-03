(() => {
  const form = document.querySelector("#signup-form");
  const notice = document.querySelector("#signup-notice");
  const login = document.querySelector("#signup-login");

  form.addEventListener("submit", async event => {
    event.preventDefault();
    const button = form.querySelector("button");
    button.disabled = true;
    notice.hidden = true;
    try {
      const response = await fetch("/api/method/verityai_saas.api.signup.register", {
        method: "POST",
        headers: {"X-Frappe-CSRF-Token": window.csrf_token || ""},
        body: new FormData(form),
      });
      const payload = await response.json();
      const result = payload.message || payload;
      if (!result.success) throw new Error(result.error || "Registration failed");
      notice.textContent = result.data.message;
      notice.className = "va-notice";
      notice.hidden = false;
      login.href = result.data.login_url;
      if (result.data.registered) form.hidden = true;
    } catch (error) {
      notice.textContent = error.message;
      notice.className = "va-notice error";
      notice.hidden = false;
      button.disabled = false;
    }
  });
})();
