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
	  const data = new FormData(form);
	  if (data.get("password") !== data.get("confirm_password")) {
		throw new Error("Passwords do not match");
	  }
      const response = await fetch("/api/method/verityai_saas.api.signup.register", {
        method: "POST",
        headers: {"X-Frappe-CSRF-Token": window.csrf_token || ""},
        body: data,
      });
      const payload = await response.json();
      const result = payload.message || payload;
      if (!result.success) throw new Error(result.error || "Registration failed");
      notice.textContent = result.data.message;
      notice.className = "va-notice";
      notice.hidden = false;
      login.href = result.data.login_url;
      if (result.data.authenticated && result.data.next_url) {
        window.location.assign(result.data.next_url);
        return;
      }
      if (result.data.registered) form.hidden = true;
    } catch (error) {
      notice.textContent = error.message;
      notice.className = "va-notice error";
      notice.hidden = false;
      button.disabled = false;
    }
  });
})();
