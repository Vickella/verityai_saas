(() => {
  "use strict";
  const loading = document.querySelector("#doctor-loading");
  const loadingCopy = document.querySelector("#doctor-loading-copy");
  const errorState = document.querySelector("#doctor-error");
  const errorCopy = document.querySelector("#doctor-error-copy");
  const report = document.querySelector("#doctor-report");
  const contactForm = document.querySelector("#doctor-contact-form");
  const contactNotice = document.querySelector("#doctor-contact-notice");
  const secret = new URLSearchParams(location.hash.slice(1));
  const audit = secret.get("audit") || "";
  const token = secret.get("token") || "";
  let attempts = 0;
  let stopped = false;

  const setText = (selector, value) => { document.querySelector(selector).textContent = String(value ?? ""); };
  const formatDate = value => value ? new Intl.DateTimeFormat(undefined, {dateStyle:"medium", timeStyle:"short"}).format(new Date(value)) : "Not available";
  const showError = message => {
    stopped = true;
    loading.hidden = true;
    report.hidden = true;
    errorCopy.textContent = message || "Check that you used the complete private report link.";
    errorState.hidden = false;
  };
  const api = async (method, options = {}) => {
    const response = await fetch(`/api/method/${method}${options.query ? `?${options.query}` : ""}`, {
      method: options.body ? "POST" : "GET",
      body: options.body,
      headers: options.body ? {"X-Frappe-CSRF-Token": window.csrf_token || ""} : {},
      credentials: "same-origin",
      referrerPolicy: "no-referrer",
    });
    const payload = await response.json();
    const result = payload.message || payload;
    if (!response.ok || !result.success) throw new Error(result.error || "The report service is unavailable.");
    return result.data;
  };
  const element = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const renderCategories = categories => {
    const root = document.querySelector("#doctor-categories");
    root.replaceChildren();
    Object.entries(categories || {}).sort(([left], [right]) => left.localeCompare(right)).forEach(([name, score]) => {
      const card = element("article", "doctor-category");
      card.append(element("span", "", name), element("strong", "", `${Math.round(Number(score || 0))}/100`));
      const track = element("div", "doctor-progress");
      const bar = element("i");
      bar.style.width = `${Math.max(0, Math.min(100, Number(score || 0)))}%`;
      track.append(bar); card.append(track); root.append(card);
    });
  };
  const renderFindings = findings => {
    const root = document.querySelector("#doctor-findings");
    root.replaceChildren();
    const rank = {Fail:0, Warning:1, Unavailable:2, Pass:3};
    [...(findings || [])].sort((a,b) => (rank[a.status] ?? 4) - (rank[b.status] ?? 4)).forEach(item => {
      const card = element("article", `doctor-finding status-${String(item.status || "").toLowerCase()}`);
      const heading = element("div", "doctor-finding-heading");
      heading.append(element("span", "doctor-badge", item.status || "Observed"), element("small", "", item.category || "Website"));
      card.append(heading, element("h3", "", item.summary || "Observation unavailable."));
      if (item.recommendation) card.append(element("p", "", item.recommendation));
      const source = element("small", "doctor-source", `Evidence source: ${item.source || "Audit"}`);
      card.append(source); root.append(card);
    });
  };
  const renderReport = data => {
    stopped = true;
    setText("#doctor-host", data.target_host);
    setText("#doctor-score", Math.round(Number(data.overall_score || 0)));
    setText("#doctor-observed", formatDate(data.observed_at));
    setText("#doctor-pages", data.pages_checked || 1);
    renderCategories(data.category_scores);
    renderFindings(data.findings);
    loading.hidden = true; errorState.hidden = true; report.hidden = false;
  };
  const poll = async () => {
    if (stopped) return;
    if (!audit || !token) return showError("This private report link is incomplete.");
    try {
      const body = new FormData(); body.set("audit", audit); body.set("token", token);
      const data = await api("verityai_saas.api.audits.status", {body});
      if (data.status === "Completed") return renderReport(data);
      if (data.status === "Failed") return showError(`${data.error_message || "The audit could not be completed."}${data.error_reference ? ` Reference: ${data.error_reference}` : ""}`);
      attempts += 1;
      loadingCopy.textContent = data.status === "Running" ? `Measuring ${data.target_host}. This page will update automatically.` : "Your audit is queued and will start shortly.";
      if (attempts >= 60) return showError("This audit is taking longer than expected. Keep this private link and try it again shortly.");
      window.setTimeout(poll, Math.min(4000 + attempts * 250, 10000));
    } catch (error) { showError(error.message); }
  };
  contactForm?.addEventListener("submit", async event => {
    event.preventDefault();
    const button = contactForm.querySelector("button");
    button.disabled = true; contactNotice.hidden = true;
    try {
      const values = Object.fromEntries(new FormData(contactForm).entries());
      const body = new FormData(); body.set("audit", audit); body.set("token", token); body.set("values", JSON.stringify(values));
      await api("verityai_saas.api.audits.capture_lead", {body});
      contactNotice.textContent = "Thank you. A VerityAI specialist can now follow up about this report.";
      contactNotice.className = "doctor-notice success"; contactNotice.hidden = false; contactForm.querySelectorAll("input,button").forEach(node => node.disabled = true);
    } catch (error) {
      contactNotice.textContent = error.message; contactNotice.className = "doctor-notice error"; contactNotice.hidden = false; button.disabled = false;
    }
  });
  poll();
})();
