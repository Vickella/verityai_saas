(() => {
  const content = document.querySelector("#va-admin-content");
  const notice = document.querySelector("#va-admin-notice");
  let data = null;
  let selectedWorkspace = null;

  const esc = value => String(value ?? "").replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
  const number = value => new Intl.NumberFormat().format(Number(value || 0));
  const pill = value => `<span class="va-pill ${["Active","Trial","Completed","Normal","Connected"].includes(value)?"good":["Suspended","Cancelled","Expired","Failed","Exhausted","Critical"].includes(value)?"bad":""}">${esc(value || "—")}</span>`;

  async function call(method, args={}) {
    const body = new FormData();
    Object.entries(args).forEach(([key,value]) => body.append(key, value ?? ""));
    const response = await fetch(`/api/method/${method}`, {method:"POST", headers:{"X-Frappe-CSRF-Token":window.csrf_token || ""}, body});
    const payload = await response.json();
    const result = payload.message || payload;
    if (!result.success) throw new Error(result.error || "Request failed");
    return result.data;
  }

  function alert(message, error=false) {
    notice.textContent = message;
    notice.className = `va-notice ${error?"error":""}`;
    notice.hidden = false;
    window.setTimeout(() => notice.hidden = true, 6000);
  }

  const table = (columns, rows, empty="Nothing here yet.") => rows.length ? `<div class="va-card va-table-wrap"><table class="va-table"><thead><tr>${columns.map(column=>`<th>${esc(column[0])}</th>`).join("")}</tr></thead><tbody>${rows.map(row=>`<tr>${columns.map(column=>`<td>${column[1](row)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>` : `<div class="va-card va-empty">${esc(empty)}</div>`;

  function managementPanel(workspace) {
    if (!workspace) return "";
    const subscription = workspace.subscription || {};
    const planOptions = data.plans.map(plan=>`<option value="${esc(plan.name)}" ${plan.name===subscription.plan?"selected":""}>${esc(plan.plan_name)} · ${esc(plan.currency)} ${number(plan.monthly_price)}/month</option>`).join("");
    const statusOptions = ["Trial","Active","Past Due","Suspended","Cancelled","Expired"].map(status=>`<option ${status===subscription.status?"selected":""}>${status}</option>`).join("");
    return `<section class="va-card va-form va-operator-panel"><div class="va-actions"><div><p class="eyebrow">Manage workspace</p><h2>${esc(workspace.business_name || workspace.workspace_name)}</h2><p class="muted">${esc(workspace.name)}</p></div><button type="button" class="va-button secondary" id="close-management">Close</button></div><div class="va-grid two"><form id="assign-plan" class="va-card va-form"><h3>Plan and billing period</h3><div class="va-field"><label>Plan</label><select name="plan" required>${planOptions}</select></div><div class="va-field"><label>Billing cycle</label><select name="billing_cycle"><option ${subscription.billing_cycle==="Monthly"?"selected":""}>Monthly</option><option ${subscription.billing_cycle==="Annual"?"selected":""}>Annual</option><option ${subscription.billing_cycle==="Manual"?"selected":""}>Manual</option></select></div><div class="va-field"><label>Initial status</label><select name="status">${statusOptions}</select></div><button class="va-button">Apply plan</button></form><form id="set-status" class="va-card va-form"><h3>Subscription status</h3><div class="va-field"><label>Status</label><select name="status">${statusOptions}</select></div><div class="va-field"><label>Reason</label><textarea name="reason" placeholder="Required operational context"></textarea></div><button class="va-button">Update status</button></form><form id="record-payment" class="va-card va-form"><h3>Record manual payment</h3><div class="va-field"><label>Amount</label><input name="amount" type="number" min="0" step="0.01" required></div><div class="va-field"><label>Reference</label><input name="reference" required></div><button class="va-button">Record completed payment</button></form><form id="record-topup" class="va-card va-form"><h3>Add token top-up</h3><div class="va-field"><label>Tokens</label><input name="tokens" type="number" min="1" step="1" required></div><div class="va-field"><label>Amount</label><input name="amount" type="number" min="0" step="0.01" value="0"></div><div class="va-field"><label>Reference</label><input name="reference"></div><button class="va-button">Add top-up</button></form></div></section>`;
  }

  function render() {
    const workspaces = data.workspaces || [];
    const selected = workspaces.find(row=>row.name===selectedWorkspace);
    content.innerHTML = `<div class="va-grid"><div class="va-card va-metric"><span>Accounts</span><strong>${number(data.accounts)}</strong></div><div class="va-card va-metric"><span>Workspaces</span><strong>${number(workspaces.length)}</strong></div><div class="va-card va-metric"><span>Active / trial</span><strong>${number(data.active)}</strong></div><div class="va-card va-metric"><span>Suspended</span><strong>${number(data.suspended)}</strong></div></div><div class="va-grid two"><div class="va-card"><h2>Operational attention</h2><p>High usage <strong>${number(data.high_usage.length)}</strong></p><p>Trials ending / overdue <strong>${number(data.trial_expiring.length)}</strong></p><p>Failed WhatsApp setups <strong>${number(data.failed_whatsapp.length)}</strong></p><p>Provider alerts <strong>${number(data.provider_failures.length)}</strong></p></div><div class="va-card"><h2>Payments</h2><p>Paynow ${data.paynow_configured?pill("Connected"):pill("Not configured")}</p><p class="muted">Manual controls are operator-only and every transaction is stored in the billing ledger.</p></div></div>${table([["Workspace",row=>`<strong>${esc(row.business_name||row.workspace_name)}</strong><br><span class="muted">${esc(row.name)}</span>`],["Workspace",row=>pill(row.status)],["Plan",row=>`<strong>${esc(row.subscription?.plan||"No plan")}</strong><br>${pill(row.subscription?.status)}`],["Usage",row=>`${number(row.wallet?.tokens_used)} used<br><span class="muted">${number(row.wallet?.tokens_remaining)} remaining · ${number(row.usage_percent)}%</span>`],["Signals",row=>`${number(row.new_leads)} new leads<br>${number(row.open_alerts)} alerts`],["Action",row=>`<button class="va-button secondary" data-manage="${esc(row.name)}">Manage</button>`]],workspaces,"No workspaces have been created.")}${managementPanel(selected)}<div class="va-grid two">${table([["High usage",row=>`<strong>${esc(row.business_name)}</strong><br><span class="muted">${number(row.tokens_remaining)} remaining</span>`],["Used",row=>`${number(row.usage_percent)}%`]],data.high_usage,"No high-usage workspaces.")}${table([["Trial",row=>`<strong>${esc(row.business_name)}</strong><br><span class="muted">${esc(row.workspace)}</span>`],["Ends",row=>esc(row.trial_end)]],data.trial_expiring,"No trials expire in the next seven days.")}</div>${table([["Event",row=>`<strong>${esc(row.event_type)}</strong><br><span class="muted">${esc(row.provider||"Manual")}</span>`],["Workspace",row=>esc(row.workspace)],["Amount",row=>`${esc(row.currency||"")} ${number(row.amount)}`],["Status",row=>`${pill(row.status)} ${row.gateway_status?pill(row.gateway_status):""}`],["Reference",row=>esc(row.gateway_reference||"—")],["Created",row=>esc(row.creation)]],data.recent_events,"No billing events yet.")}`;
    bindActions();
  }

  async function submit(form, method, args, message) {
    const button = form.querySelector("button"); button.disabled = true;
    try { await call(method, {workspace:selectedWorkspace, ...args}); alert(message); await load(selectedWorkspace); }
    catch (error) { alert(error.message, true); button.disabled = false; }
  }

  function bindActions() {
    document.querySelectorAll("[data-manage]").forEach(button=>button.addEventListener("click",()=>{selectedWorkspace=button.dataset.manage;render();document.querySelector(".va-operator-panel")?.scrollIntoView({behavior:"smooth"});}));
    document.querySelector("#close-management")?.addEventListener("click",()=>{selectedWorkspace=null;render();});
    const plan = document.querySelector("#assign-plan");
    plan?.addEventListener("submit",event=>{event.preventDefault();submit(plan,"verityai_saas.api.billing.assign_plan",{plan:plan.plan.value,billing_cycle:plan.billing_cycle.value,status:plan.status.value},"Plan updated.");});
    const status = document.querySelector("#set-status");
    status?.addEventListener("submit",event=>{event.preventDefault();submit(status,"verityai_saas.api.billing.set_status",{status:status.status.value,reason:status.reason.value},"Subscription status updated.");});
    const payment = document.querySelector("#record-payment");
    payment?.addEventListener("submit",event=>{event.preventDefault();submit(payment,"verityai_saas.api.billing.manual_event",{event_type:"Payment",amount:payment.amount.value,status:"Completed",reference:payment.reference.value},"Payment recorded.");});
    const topup = document.querySelector("#record-topup");
    topup?.addEventListener("submit",event=>{event.preventDefault();submit(topup,"verityai_saas.api.billing.top_up",{tokens:topup.tokens.value,amount:topup.amount.value,reference:topup.reference.value},"Token top-up recorded.");});
  }

  async function load(keepSelected=null) {
    try { data = await call("verityai_saas.api.admin.dashboard"); selectedWorkspace = keepSelected; render(); }
    catch (error) { content.innerHTML = `<div class="va-notice error">${esc(error.message)}</div>`; }
  }

  load();
})();