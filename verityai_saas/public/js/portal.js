(() => {
  const page = document.body.dataset.verityPage || "dashboard";
  const content = document.querySelector("#va-content");
  const picker = document.querySelector("#va-workspace");
  const notice = document.querySelector("#va-notice");
  let workspace = null;

  const esc = (value) => String(value ?? "").replace(/[&<>'"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));
  const number = (value) => new Intl.NumberFormat().format(Number(value || 0));
  const pill = (value) => `<span class="va-pill ${["Active","Connected","Done","Normal","Trial"].includes(value)?"good":["Failed","Suspended","Exhausted"].includes(value)?"bad":""}">${esc(value || "—")}</span>`;
  const field = (label, name, value="", type="text", full=false) => `<div class="va-field ${full?"full":""}"><label>${esc(label)}</label>${type==="textarea"?`<textarea name="${name}">${esc(value)}</textarea>`:`<input type="${type}" name="${name}" value="${esc(value)}">`}</div>`;
  const json = (form) => Object.fromEntries(new FormData(form).entries());

  async function call(method, args={}) {
    const body = new FormData();
    Object.entries(args).forEach(([key,value]) => body.append(key, typeof value === "object" ? JSON.stringify(value) : value ?? ""));
    const response = await fetch(`/api/method/${method}`, {method:"POST", headers:{"X-Frappe-CSRF-Token":window.csrf_token || ""}, body});
    const payload = await response.json();
    const result = payload.message || payload;
    if (!result.success) throw new Error(result.error || "Request failed");
    return result.data;
  }

  function alert(message, error=false) {
    notice.textContent = message; notice.className = `va-notice ${error?"error":""}`; notice.hidden = false;
    window.setTimeout(() => notice.hidden = true, 5000);
  }

  const table = (columns, rows) => rows.length ? `<div class="va-card"><table class="va-table"><thead><tr>${columns.map(c=>`<th>${esc(c[0])}</th>`).join("")}</tr></thead><tbody>${rows.map(row=>`<tr>${columns.map(c=>`<td>${c[1](row)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>` : `<div class="va-card va-empty">Nothing here yet.</div>`;

  async function dashboard() {
    const d = await call("verityai_saas.api.workspace.get", {workspace});
    content.innerHTML = `<div class="va-grid"><div class="va-card va-metric"><span>Setup progress</span><strong>${number(d.workspace.setup_progress)}%</strong><div class="va-progress"><i style="width:${Number(d.workspace.setup_progress||0)}%"></i></div></div><div class="va-card va-metric"><span>Conversations</span><strong>${number(d.conversation_count)}</strong></div><div class="va-card va-metric"><span>New leads</span><strong>${number(d.new_leads)}</strong></div><div class="va-card va-metric"><span>Tokens remaining</span><strong>${number(d.wallet.tokens_remaining)}</strong></div></div><div class="va-grid two"><div class="va-card"><h2>Workspace health</h2><p>${pill(d.workspace.status)} ${pill(d.wallet.status)}</p><p class="muted">${d.recent_alerts.length ? esc(d.recent_alerts[0].summary) : "No recent alerts."}</p></div><div class="va-card"><h2>Current plan</h2><p><strong>${esc(d.subscription?.plan || "No plan")}</strong></p><p class="muted">${esc(d.subscription?.status || "Not configured")}</p></div></div>`;
  }

  async function onboarding() {
    const d = await call("verityai_saas.api.workspace.get", {workspace});
    content.innerHTML = `<div class="va-card"><h2>Set up your assistant</h2><div class="va-progress"><i style="width:${Number(d.workspace.setup_progress||0)}%"></i></div><p class="muted">${number(d.workspace.setup_progress)}% complete</p></div>${table([["Step",r=>esc(r.step_label)],["Status",r=>pill(r.status)]], d.checklist)}`;
  }

  async function assistant() {
    const d = await call("verityai_saas.api.assistant.get", {workspace});
    content.innerHTML = `<form id="assistant-form" class="va-card va-form"><h2>Assistant identity</h2><div class="va-fields">${field("Assistant name","assistant_name",d.assistant_name)}${field("Brand name","brand_name",d.brand_name)}${field("Business nature","business_nature",d.business_nature)}${field("Greeting","widget_greeting",d.widget_greeting,"textarea",true)}</div><button class="va-button">Save assistant</button></form>`;
    bind("assistant-form", async f => call("verityai_saas.api.assistant.update", {workspace, values:json(f)}));
  }

  async function widget() {
    const d = await call("verityai_saas.api.widget.get", {workspace});
    content.innerHTML = `<form id="widget-form" class="va-card va-form"><h2>Widget appearance</h2><div class="va-fields">${field("Widget title","widget_title",d.widget_title)}${field("Greeting","widget_greeting",d.widget_greeting)}${field("Primary preset","widget_primary_color",d.widget_primary_color)}${field("Header preset","widget_header_color",d.widget_header_color)}</div><button class="va-button">Save appearance</button></form><form id="domain-form" class="va-card va-form"><h2>Allowed domains</h2>${field("One domain per line","domains",(d.allowed_domains||[]).join("\n"),"textarea",true)}<button class="va-button">Save domains</button></form><div class="va-card"><h2>Embed code</h2><pre class="va-code">${esc(d.embed_code)}</pre><p class="muted">Add this before your website's closing body tag. It uses the hardened Verity AI widget runtime.</p></div>`;
    bind("widget-form", f => call("verityai_saas.api.widget.update", {workspace, values:json(f)}));
    bind("domain-form", f => call("verityai_saas.api.widget.set_domains", {workspace, domains:f.domains.value.split(/\r?\n/).filter(Boolean)}));
  }

  async function knowledge() {
    const rows = await call("verityai_saas.api.knowledge.list_sources", {workspace});
    content.innerHTML = `<form id="knowledge-form" class="va-card va-form"><h2>Add knowledge</h2><div class="va-fields">${field("Title","title")}${field("Business facts, FAQs, policies or services","content","","textarea",true)}</div><button class="va-button">Add source</button></form>${table([["Source",r=>esc(r.title)],["Status",r=>pill(r.active?"Active":"Inactive")],["Chunks",r=>number(r.chunk_count)],["Updated",r=>esc(r.modified)]], rows)}`;
    bind("knowledge-form", f => call("verityai_saas.api.knowledge.create", {workspace, ...json(f)}), knowledge);
  }

  async function leads() {
    const rows = await call("verityai_saas.api.leads.list_leads", {workspace});
    content.innerHTML = table([["Lead",r=>`<strong>${esc(r.lead_name)}</strong><br><span class="muted">${esc(r.email||r.phone||"")}</span>`],["Channel",r=>esc(r.source_channel)],["Status",r=>pill(r.status)],["Captured",r=>esc(r.creation)]], rows);
  }

  async function conversations() {
    const rows = await call("verityai_saas.api.conversations.list_conversations", {workspace});
    content.innerHTML = table([["Conversation",r=>`<strong>${esc(r.name)}</strong><br><span class="muted">${esc(r.user_identifier||"")}</span>`],["Platform",r=>esc(r.platform)],["Status",r=>pill(r.status)],["Updated",r=>esc(r.modified)]], rows);
  }

  async function quotes() {
    const rows = await call("verityai_saas.api.quotes.list_requests", {workspace});
    const pending = rows.filter(row => row.status === "Pending").length;
    content.innerHTML = `<div class="va-grid two"><div class="va-card va-metric"><span>Pending approval</span><strong>${number(pending)}</strong></div><div class="va-card"><h2>Safe approval flow</h2><p class="muted">Approval submits and sends the existing engine quotation. VerityAI never bypasses the engine approval hook.</p></div></div>${table([["Request",r=>`<strong>${esc(r.name)}</strong><br><span class="muted">${esc(r.erpnext_quotation_id||"Draft quotation")}</span>`],["Customer",r=>`<strong>${esc(r.customer_name)}</strong><br><span class="muted">${esc(r.client_email||r.client_whatsapp_number||"")}</span>`],["Total",r=>number(r.estimated_total)],["Status",r=>pill(r.status)],["Created",r=>esc(r.creation)],["Action",r=>r.status==="Pending"?`<button type="button" class="va-button" data-approve-quote="${esc(r.name)}">Approve &amp; send</button>`:'<span class="muted">Complete</span>']],rows)}`;
    document.querySelectorAll("[data-approve-quote]").forEach(button => button.addEventListener("click", async () => {
      const request = button.dataset.approveQuote;
      if (!window.confirm(`Approve ${request}? This submits the quotation and sends it through the configured engine channel.`)) return;
      const notes = window.prompt("Optional approval note", "") ?? "";
      button.disabled = true;
      try { await call("verityai_saas.api.quotes.approve", {workspace, quotation_request:request, notes}); alert("Quotation approved and processed."); await quotes(); }
      catch (err) { alert(err.message, true); button.disabled = false; }
    }));
  }
  async function usage() {
    const d = await call("verityai_saas.api.usage.get", {workspace});
    content.innerHTML = `<div class="va-grid"><div class="va-card va-metric"><span>Total tokens</span><strong>${number(d.total_tokens)}</strong></div><div class="va-card va-metric"><span>Input tokens</span><strong>${number(d.input_tokens)}</strong></div><div class="va-card va-metric"><span>Output tokens</span><strong>${number(d.output_tokens)}</strong></div><div class="va-card va-metric"><span>Remaining</span><strong>${number(d.wallet?.tokens_remaining)}</strong></div></div><div class="va-grid two"><div class="va-card"><h2>Usage by channel</h2>${Object.entries(d.by_platform||{}).map(([k,v])=>`<p>${esc(k)} <strong>${number(v)}</strong></p>`).join("")||'<p class="muted">No usage yet.</p>'}</div><div class="va-card"><h2>Estimated cost</h2><p class="va-metric"><strong>${number(d.estimated_cost)}</strong></p><p class="muted">Based on server-side engine usage logs.</p></div></div>`;
  }

  async function billing() {
    const d = await call("verityai_saas.api.billing.get", {workspace}); const s=d.subscription?.[0];
    content.innerHTML = `<div class="va-grid two"><div class="va-card"><h2>Current plan</h2><p class="va-metric"><strong>${esc(s?.plan||"No plan")}</strong></p><p>${pill(s?.status)}</p><p class="muted">Trial ends ${esc(s?.trial_end||"—")} · Renewal ${esc(s?.next_billing_date||"—")}</p><button class="va-button" disabled>Upgrade coming soon</button></div><div class="va-card"><h2>Usage</h2><p>Used <strong>${number(d.wallet?.tokens_used)}</strong></p><p>Remaining <strong>${number(d.wallet?.tokens_remaining)}</strong></p></div></div>${table([["Event",r=>esc(r.event_type)],["Amount",r=>`${esc(r.currency||"")} ${number(r.amount)}`],["Status",r=>pill(r.status)],["Date",r=>esc(r.creation)]],d.events)}`;
  }

  async function email() {
    const d = await call("verityai_saas.api.email.get", {workspace});
    content.innerHTML = `<form id="email-form" class="va-card va-form"><h2>Email notifications</h2><div class="va-fields">${field("Notification email","notification_email",d.notification_email,"email")}${field("Additional recipients","alert_recipients",d.alert_recipients)}${field("Branding name","email_branding_name",d.email_branding_name)}${field("Email footer","email_footer",d.email_footer,"textarea",true)}</div><label><input type="checkbox" name="lead_notifications_enabled" ${d.lead_notifications_enabled?"checked":""}> New lead notifications</label><label><input type="checkbox" name="daily_summary_enabled" ${d.daily_summary_enabled?"checked":""}> Daily lead summary</label><label><input type="checkbox" name="usage_warning_alerts_enabled" ${d.usage_warning_alerts_enabled?"checked":""}> Usage warnings</label><button class="va-button">Save settings</button></form>`;
    bind("email-form", f => {const v=json(f);["lead_notifications_enabled","daily_summary_enabled","usage_warning_alerts_enabled"].forEach(k=>v[k]=f[k].checked?1:0);return call("verityai_saas.api.email.update",{workspace,values:v});});
  }

  async function whatsapp() {
    const d = await call("verityai_saas.api.whatsapp.get", {workspace});
    content.innerHTML = `<form id="wa-form" class="va-card va-form"><h2>WhatsApp setup</h2><div class="va-fields"><div class="va-field"><label>Mode</label><select name="mode"><option ${d.mode==="Button Only"?"selected":""}>Button Only</option><option ${d.mode==="Lead Alerts"?"selected":""}>Lead Alerts</option><option ${d.mode==="Full AI Automation"?"selected":""}>Full AI Automation</option></select></div>${field("Business WhatsApp number","business_whatsapp_number",d.business_whatsapp_number)}${field("Meta phone number ID","whatsapp_phone_id")}${field("Access token (write only)","whatsapp_access_token","","password")}${field("Meta verify token (write only)","meta_verify_token","","password")}${field("Meta app secret (write only)","meta_app_secret","","password")}</div><label><input type="checkbox" name="verify_meta_signature" ${d.engine?.signature_verification_enabled?"checked":""}> Verify Meta webhook signatures</label><button class="va-button">Save WhatsApp setup</button></form><div class="va-card"><h2>Callback URL</h2><pre class="va-code">${esc(d.engine?.callback_url)}</pre><p>${pill(d.setup_status)} ${d.engine?.signature_verification_enabled?pill("Signature verified"):pill("Production warning: signature verification off")}</p></div>`;
    bind("wa-form", f => {const v=json(f);v.verify_meta_signature=f.verify_meta_signature.checked?1:0;return call("verityai_saas.api.whatsapp.update",{workspace,values:v});},whatsapp);
  }

  async function team() {
    const rows = await call("verityai_saas.api.workspace.members", {workspace});
    content.innerHTML = `<form id="team-form" class="va-card va-form"><h2>Invite a team member</h2><div class="va-fields">${field("Email","email","","email")}<div class="va-field"><label>Role</label><select name="role"><option>Viewer</option><option>Sales</option><option>Support</option><option>Admin</option><option>Billing Manager</option></select></div></div><button class="va-button">Invite member</button></form>${table([["User",r=>esc(r.user)],["Role",r=>esc(r.workspace_role)],["Status",r=>pill(r.status)]],rows)}`;
    bind("team-form", f => call("verityai_saas.api.workspace.invite",{workspace,...json(f)}),team);
  }

  function bind(id, action, after) { document.querySelector(`#${id}`).addEventListener("submit", async e => {e.preventDefault();const b=e.currentTarget.querySelector("button");b.disabled=true;try{await action(e.currentTarget);alert("Saved successfully.");if(after)await after();}catch(err){alert(err.message,true)}finally{b.disabled=false}}); }

  async function newWorkspace() {
    picker.hidden=true; content.innerHTML=`<form id="new-workspace" class="va-card va-form"><h2>Create your first workspace</h2><p class="muted">We will create your account, assistant, trial plan, usage wallet, and secure engine tenant together.</p><div class="va-fields">${field("Account name","account_name")}${field("Workspace name","workspace_name")}${field("Business name","business_name")}</div><button class="va-button">Create workspace</button></form>`;
    bind("new-workspace", async f=>{const d=await call("verityai_saas.api.onboarding.create",json(f));location.href=d.dashboard_url;});
  }

  const renderers={dashboard,onboarding,assistant,widget,knowledge,leads,conversations,quotes,usage,billing,email,whatsapp,team};
  async function init(){try{const rows=await call("verityai_saas.api.workspace.list_workspaces");if(!rows.length){newWorkspace();return}const params=new URLSearchParams(location.search);workspace=params.get("workspace")||localStorage.getItem("verityai_workspace")||rows[0].name;if(!rows.some(r=>r.name===workspace))workspace=rows[0].name;picker.innerHTML=rows.map(r=>`<option value="${esc(r.name)}" ${r.name===workspace?"selected":""}>${esc(r.business_name||r.workspace_name)}</option>`).join("");picker.addEventListener("change",()=>{workspace=picker.value;localStorage.setItem("verityai_workspace",workspace);renderers[page]();});localStorage.setItem("verityai_workspace",workspace);await (renderers[page]||dashboard)()}catch(err){content.innerHTML=`<div class="va-card va-empty">${esc(err.message)}</div>`;alert(err.message,true)}}
  init();
})();

