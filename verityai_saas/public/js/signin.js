(() => {
	const form = document.querySelector("#signin-form");
	const notice = document.querySelector("#signin-notice");
	const params = new URLSearchParams(window.location.search);
	const requested = params.get("redirect-to") || "/verityai";
	const nextUrl = requested.startsWith("/verityai") && !requested.startsWith("//") ? requested : "/verityai";

	form?.addEventListener("submit", async event => {
		event.preventDefault();
		const button = form.querySelector('button[type="submit"]');
		button.disabled = true;
		notice.hidden = true;
		try {
			const data = new FormData(form);
			const body = new URLSearchParams({usr: String(data.get("usr") || "").trim(), pwd: String(data.get("pwd") || "")});
			const response = await fetch("/api/method/login", {
				method: "POST",
				headers: {"Content-Type": "application/x-www-form-urlencoded", "X-Frappe-CSRF-Token": window.csrf_token || ""},
				credentials: "same-origin",
				body,
			});
			const payload = await response.json().catch(() => ({}));
			if (!response.ok || payload.exc || payload.exception) throw new Error("The email address or password is incorrect.");
			window.location.replace(nextUrl);
		} catch (error) {
			notice.textContent = error.message || "Sign in failed. Please try again.";
			notice.className = "va-notice error";
			notice.hidden = false;
			button.disabled = false;
		}
	});
})();
