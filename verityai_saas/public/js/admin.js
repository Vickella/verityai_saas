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
    Object.entries(args).forEach(([key,value]) => body.append(key, typeof value === "object" ? JSON.stringify(value) : value ?? ""));
    const response = await fetch(`/api/method/${method}`, {method:"POST", headers:{"X-Frappe-CSRF-Token":window.csrf_token || ""}, body});
    let payload;
    try { payload=await response.json(); }
    catch(error) { throw new Error(`Server returned an unreadable response (HTTP ${response.status}).`); }
    const result = payload.message || payload;
    if (!response.ok || !result.success) {
      const type=payload.exc_type || result.code || "";
      const expired=type.includes("CSRF") || response.status===401;
      throw new Error(result.error || (expired?"Your session expired. Refresh the page and sign in again.":`Server request failed${response.status?` (HTTP ${response.status})`:""}.`));
    }
    return result.data;
  }

  function alert(message, error=false) {
    notice.textContent = message;
    notice.className = `va-notice ${error?"error":""}`;
    notice.hidden = false;
    window.setTimeout(() => notice.hidden = true, 6000);
  }

  const table = (columns, rows, empty="Nothing here yet.") => rows.length ? `<div class="va-card va-table-wrap"><table class="va-table"><thead><tr>${columns.map(column=>`<th>${esc(column[0])}</th>`).join("")}</tr></thead><tbody>${rows.map(row=>`<tr>${columns.map(column=>`<td>${column[1](row)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>` : `<div class="va-card va-empty">${esc(empty)}</div>`;

  const planChecks = ["can_remove_branding","can_use_whatsapp_button","can_use_whatsapp_ai","can_use_email_notifications","can_use_custom_smtp","can_use_erpnext_integration","can_use_quotation_workflow","can_use_api_access","can_bring_own_ai_provider_key"];
  const planNumbers = ["monthly_price","annual_price","trial_days","max_workspaces","max_assistants","max_team_members","monthly_token_limit","max_tokens","public_rate_limit_per_minute","max_public_message_chars","monthly_web_conversations","monthly_whatsapp_messages","monthly_email_sends","max_knowledge_sources","max_allowed_domains"];
  const label = key => key.replaceAll("_"," ").replace(/\b\w/g,char=>char.toUpperCase());

  function planEditor(plan=null) {
    const item=plan||{}; const create=!plan;
    const numberFields=planNumbers.map(key=>`<div class="va-field"><label>${esc(label(key))}</label><input type="number" min="0" step="${key.includes("price")?"0.01":"1"}" name="${key}" value="${esc(item[key]??0)}"></div>`).join("");
    const checks=planChecks.map(key=>`<label><input type="checkbox" name="${key}" ${item[key]?"checked":""}> ${esc(label(key))}</label>`).join("");
    return `<form class="va-card va-form" data-plan-form="${esc(item.name||"")}"><h3>${create?"Create plan":esc(item.plan_name)}</h3><div class="va-fields"><div class="va-field"><label>Plan name</label><input name="plan_name" required value="${esc(item.plan_name||"")}"></div><div class="va-field"><label>Plan code</label><input name="plan_code" ${create?"required":"disabled"} value="${esc(item.plan_code||"")}"></div><div class="va-field"><label>Currency</label><input name="currency" value="${esc(item.currency||"USD")}"></div><div class="va-field"><label>Support level</label><select name="support_level">${["Community","Standard","Priority"].map(value=>`<option ${item.support_level===value?"selected":""}>${value}</option>`).join("")}</select></div>${numberFields}</div><div class="va-checks"><label><input type="checkbox" name="active" ${create||item.active?"checked":""}> Active</label>${checks}</div><div class="va-actions"><button class="va-button">${create?"Create plan":"Save plan"}</button>${!create&&item.plan_code!=="TRIAL"&&item.active?`<button type="button" class="va-button danger" data-archive-plan="${esc(item.name)}">Archive</button>`:""}</div></form>`;
  }

  function planManagement() {
    return `<section><div><p class="eyebrow">Commercial controls</p><h2>Plans</h2><p class="muted">Create, price, limit, feature-gate, or archive plans without Frappe Desk.</p></div><div class="va-grid two">${planEditor()}${data.plans.map(planEditor).join("")}</div></section>`;
  }
  function scheduleEditor(schedule=null) {
    const item=schedule||{}; const existing=Boolean(schedule);
    const workspaceOptions=`<option value="">All workspaces</option>${(data.workspaces||[]).map(row=>`<option value="${esc(row.name)}" ${item.workspace===row.name?"selected":""}>${esc(row.business_name||row.name)}</option>`).join("")}`;
    return `<form class="va-card va-form" data-report-schedule="${esc(item.name||"")}"><h3>${existing?esc(item.report_name):"Create report schedule"}</h3><div class="va-fields"><div class="va-field"><label>Report name</label><input name="report_name" required value="${esc(item.report_name||"")}"></div><div class="va-field"><label>Report type</label><select name="report_type"><option ${item.report_type==="Operator Summary"?"selected":""}>Operator Summary</option><option ${item.report_type==="Workspace Analytics"?"selected":""}>Workspace Analytics</option></select></div><div class="va-field"><label>Workspace</label><select name="workspace">${workspaceOptions}</select></div><div class="va-field"><label>Recipients</label><input name="recipients" required value="${esc(item.recipients||"")}"></div><div class="va-field"><label>Frequency</label><select name="frequency">${["Daily","Weekly","Monthly"].map(value=>`<option ${item.frequency===value?"selected":""}>${value}</option>`).join("")}</select></div></div><label><input type="checkbox" name="active" ${!existing||item.active?"checked":""}> Active</label><p class="muted">Next: ${esc(item.next_send_on||"after creation")} ${item.last_status?`· Last ${esc(item.last_status)}`:""}</p><button class="va-button">${existing?"Save schedule":"Create schedule"}</button></form>`;
  }

  function scheduleManagement() {
    return `<section><div class="va-actions"><div><p class="eyebrow">Reporting</p><h2>Scheduled reports</h2></div><a class="va-button secondary" href="/api/method/verityai_saas.api.analytics.operator_export">Download operator summary</a></div><div class="va-grid two">${scheduleEditor()}${(data.schedules||[]).map(scheduleEditor).join("")}</div></section>`;
  }
  function managementPanel(workspace) {
    if (!workspace) return "";
    const subscription = workspace.subscription || {};
    const planOptions = data.plans.filter(plan=>plan.active).map(plan=>`<option value="${esc(plan.name)}" ${plan.name===subscription.plan?"selected":""}>${esc(plan.plan_name)} — ${esc(plan.currency)} ${number(plan.monthly_price)}/month</option>`).join("");
    const statusOptions = ["Trial","Active","Past Due","Suspended","Cancelled","Expired"].map(status=>`<option ${status===subscription.status?"selected":""}>${status}</option>`).join("");
    const completedPayments = data.recent_events.filter(event=>event.workspace===workspace.name&&event.event_type==="Payment"&&event.status==="Completed");
    const pendingRefunds = data.recent_events.filter(event=>event.workspace===workspace.name&&event.event_type==="Refund"&&event.status==="Pending");
    const refundControls = `${completedPayments.length?`<form id="initiate-refund" class="va-card va-form"><h3>Initiate refund</h3><div class="va-field"><label>Completed payment</label><select name="payment">${completedPayments.map(event=>`<option value="${esc(event.name)}">${esc(event.name)} · ${esc(event.currency)} ${number(event.amount)}</option>`).join("")}</select></div><div class="va-field"><label>Amount</label><input name="amount" type="number" min="0.01" step="0.01"></div><div class="va-field"><label>Reason</label><textarea name="reason" required></textarea></div><button class="va-button danger">Create refund request</button></form>`:""}${pendingRefunds.length?`<form id="complete-refund" class="va-card va-form"><h3>Complete refund</h3><div class="va-field"><label>Pending refund</label><select name="refund">${pendingRefunds.map(event=>`<option value="${esc(event.name)}">${esc(event.name)} · ${esc(event.currency)} ${number(event.amount)}</option>`).join("")}</select></div><div class="va-field"><label>Provider reference</label><input name="provider_reference" required></div><button class="va-button">Record completed refund</button></form>`:""}`;
    const configurationLink=data.can_configure_platform?`<a class="va-button secondary" href="/verityai/integrations?workspace=${encodeURIComponent(workspace.name)}">Platform configuration</a>`:"";
    return `<section class="va-card va-form va-operator-panel"><div class="va-actions"><div><p class="eyebrow">Manage workspace</p><h2>${esc(workspace.business_name || workspace.workspace_name)}</h2><p class="muted">${esc(workspace.name)}</p></div>${configurationLink}<button type="button" class="va-button secondary" id="close-management">Close</button></div><div class="va-grid two"><form id="assign-plan" class="va-card va-form"><h3>Plan and billing period</h3><div class="va-field"><label>Plan</label><select name="plan" required>${planOptions}</select></div><div class="va-field"><label>Billing cycle</label><select name="billing_cycle"><option ${subscription.billing_cycle==="Monthly"?"selected":""}>Monthly</option><option ${subscription.billing_cycle==="Annual"?"selected":""}>Annual</option><option ${subscription.billing_cycle==="Manual"?"selected":""}>Manual</option></select></div><div class="va-field"><label>Initial status</label><select name="status">${statusOptions}</select></div><button class="va-button">Apply plan</button></form><form id="set-status" class="va-card va-form"><h3>Subscription status</h3><div class="va-field"><label>Status</label><select name="status">${statusOptions}</select></div><div class="va-field"><label>Reason</label><textarea name="reason" placeholder="Required operational context"></textarea></div><button class="va-button">Update status</button></form><form id="record-payment" class="va-card va-form"><h3>Record manual payment</h3><div class="va-field"><label>Amount</label><input name="amount" type="number" min="0" step="0.01" required></div><div class="va-field"><label>Reference</label><input name="reference" required></div><button class="va-button">Record completed payment</button></form><form id="record-topup" class="va-card va-form"><h3>Add token top-up</h3><div class="va-field"><label>Tokens</label><input name="tokens" type="number" min="1" step="1" required></div><div class="va-field"><label>Amount</label><input name="amount" type="number" min="0" step="0.01" value="0"></div><div class="va-field"><label>Reference</label><input name="reference"></div><button class="va-button">Add top-up</button></form>${refundControls}</div></section>`;
  }

  function render() {
    const workspaces = data.workspaces || [];
    const selected = workspaces.find(row=>row.name===selectedWorkspace);
    content.innerHTML = `<div class="va-grid"><div class="va-card va-metric"><span>Accounts</span><strong>${number(data.accounts)}</strong></div><div class="va-card va-metric"><span>Workspaces</span><strong>${number(workspaces.length)}</strong></div><div class="va-card va-metric"><span>Active / trial</span><strong>${number(data.active)}</strong></div><div class="va-card va-metric"><span>Suspended</span><strong>${number(data.suspended)}</strong></div></div><div class="va-grid two"><div class="va-card"><h2>Operational attention</h2><p>High usage <strong>${number(data.high_usage.length)}</strong></p><p>Trials ending / overdue <strong>${number(data.trial_expiring.length)}</strong></p><p>Failed WhatsApp setups <strong>${number(data.failed_whatsapp.length)}</strong></p><p>Provider alerts <strong>${number(data.provider_failures.length)}</strong></p></div><div class="va-card"><h2>Payments</h2><p>Paynow ${data.paynow_configured?pill("Connected"):pill("Not configured")}</p><p class="muted">Manual controls are operator-only and every transaction is stored in the billing ledger.</p><a class="va-button secondary" href="/api/method/verityai_saas.api.billing.reconciliation_export">Download reconciliation CSV</a></div></div>${planManagement()}${scheduleManagement()}${table([["Workspace",row=>`<strong>${esc(row.business_name||row.workspace_name)}</strong><br><span class="muted">${esc(row.name)}</span>`],["Workspace",row=>pill(row.status)],["Plan",row=>`<strong>${esc(row.subscription?.plan||"No plan")}</strong><br>${pill(row.subscription?.status)}`],["Usage",row=>`${number(row.wallet?.tokens_used)} used<br><span class="muted">${number(row.wallet?.tokens_remaining)} remaining — ${number(row.usage_percent)}%</span>`],["Signals",row=>`${number(row.new_leads)} new leads<br>${number(row.open_alerts)} alerts`],["Action",row=>`<button class="va-button secondary" data-manage="${esc(row.name)}">Manage</button>`]],workspaces,"No workspaces have been created.")}${managementPanel(selected)}<div class="va-grid two">${table([["High usage",row=>`<strong>${esc(row.business_name)}</strong><br><span class="muted">${number(row.tokens_remaining)} remaining</span>`],["Used",row=>`${number(row.usage_percent)}%`]],data.high_usage,"No high-usage workspaces.")}${table([["Trial",row=>`<strong>${esc(row.business_name)}</strong><br><span class="muted">${esc(row.workspace)}</span>`],["Ends",row=>esc(row.trial_end)]],data.trial_expiring,"No trials expire in the next seven days.")}</div>${table([["Alert",row=>`<strong>${esc(row.summary)}</strong><br><span class="muted">${esc(row.workspace)}</span>`],["Severity",row=>pill(row.severity)],["Status",row=>pill(row.status)],["Last seen",row=>esc(row.last_seen)],["Action",row=>`<div class="va-actions">${row.status==="Open"?`<button class="va-button secondary" data-alert-action="Acknowledged" data-alert="${esc(row.name)}" data-workspace="${esc(row.workspace)}">Acknowledge</button>`:""}<button class="va-button" data-alert-action="Resolved" data-alert="${esc(row.name)}" data-workspace="${esc(row.workspace)}">Resolve</button></div>`]],data.provider_failures,"No open provider alerts.")}${table([["WhatsApp setup",row=>`<strong>${esc(row.workspace)}</strong><br><span class="muted">${esc(row.mode)}</span>`],["Status",row=>pill(row.setup_status)],["Last test",row=>esc(row.last_tested_on||"Never")],["Action",row=>`<button class="va-button secondary" data-retry-whatsapp="${esc(row.workspace)}">Retry connection test</button>`]],data.failed_whatsapp,"No failed WhatsApp setups.")}${table([["Event",row=>`<strong>${esc(row.event_type)}</strong><br><span class="muted">${esc(row.provider||"Manual")}</span>`],["Workspace",row=>esc(row.workspace)],["Amount",row=>`${esc(row.currency||"")} ${number(row.amount)}`],["Status",row=>`${pill(row.status)} ${row.gateway_status?pill(row.gateway_status):""}`],["Reference",row=>esc(row.gateway_reference||"—")],["Created",row=>esc(row.creation)]],data.recent_events,"No billing events yet.")}`;
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
    document.querySelectorAll("[data-report-schedule]").forEach(form=>form.addEventListener("submit",async event=>{
      event.preventDefault();const button=form.querySelector("button");button.disabled=true;const values=Object.fromEntries(new FormData(form).entries());values.active=form.active.checked?1:0;
      try{const schedule=form.dataset.reportSchedule;await call(schedule?"verityai_saas.api.analytics.update_schedule":"verityai_saas.api.analytics.create_schedule",schedule?{schedule,values}:{values});alert(schedule?"Report schedule updated.":"Report schedule created.");await load(selectedWorkspace);}catch(error){alert(error.message,true);button.disabled=false;}
    }));    document.querySelectorAll("[data-plan-form]").forEach(form=>form.addEventListener("submit",async event=>{
      event.preventDefault(); const button=form.querySelector("button"); button.disabled=true;
      const values=Object.fromEntries(new FormData(form).entries()); ["active",...planChecks].forEach(key=>values[key]=form[key]?.checked?1:0);
      try{const existing=form.dataset.planForm;await call(existing?"verityai_saas.api.admin.update_plan":"verityai_saas.api.admin.create_plan",existing?{plan:existing,values}:{values});alert(existing?"Plan updated.":"Plan created.");await load(selectedWorkspace);}
      catch(error){alert(error.message,true);button.disabled=false;}
    }));
    document.querySelectorAll("[data-archive-plan]").forEach(button=>button.addEventListener("click",async()=>{
      if(!window.confirm("Archive this plan? Existing subscriptions remain linked, but it cannot be newly assigned."))return;
      button.disabled=true;try{await call("verityai_saas.api.admin.archive_plan",{plan:button.dataset.archivePlan});alert("Plan archived.");await load(selectedWorkspace);}catch(error){alert(error.message,true);button.disabled=false;}
    }));
    document.querySelectorAll("[data-alert-action]").forEach(button=>button.addEventListener("click",async()=>{
      const note=window.prompt(`${button.dataset.alertAction} alert note`,""); if(note===null)return;
      button.disabled=true;
      try{await call("verityai_saas.api.health.update_alert",{workspace:button.dataset.workspace,alert:button.dataset.alert,status:button.dataset.alertAction,note});alert(`Alert ${button.dataset.alertAction.toLowerCase()}.`);await load(selectedWorkspace);}
      catch(error){alert(error.message,true);button.disabled=false;}
    }));
    document.querySelectorAll("[data-retry-whatsapp]").forEach(button=>button.addEventListener("click",async()=>{
      button.disabled=true;
      try{await call("verityai_saas.api.whatsapp.test_connection",{workspace:button.dataset.retryWhatsapp});alert("Meta connection restored.");await load(selectedWorkspace);}
      catch(error){alert(error.message,true);button.disabled=false;}
    }));
    const plan = document.querySelector("#assign-plan");
    plan?.addEventListener("submit",event=>{event.preventDefault();submit(plan,"verityai_saas.api.billing.assign_plan",{plan:plan.plan.value,billing_cycle:plan.billing_cycle.value,status:plan.status.value},"Plan updated.");});
    const status = document.querySelector("#set-status");
    status?.addEventListener("submit",event=>{event.preventDefault();submit(status,"verityai_saas.api.billing.set_status",{status:status.status.value,reason:status.reason.value},"Subscription status updated.");});
    const payment = document.querySelector("#record-payment");
    payment?.addEventListener("submit",event=>{event.preventDefault();submit(payment,"verityai_saas.api.billing.manual_event",{event_type:"Payment",amount:payment.amount.value,status:"Completed",reference:payment.reference.value},"Payment recorded.");});
    const topup = document.querySelector("#record-topup");
    topup?.addEventListener("submit",event=>{event.preventDefault();submit(topup,"verityai_saas.api.billing.top_up",{tokens:topup.tokens.value,amount:topup.amount.value,reference:topup.reference.value},"Token top-up recorded.");});
    const initiateRefund = document.querySelector("#initiate-refund");
    initiateRefund?.addEventListener("submit",event=>{event.preventDefault();if(!window.confirm("Create this refund request? Complete the refund with the payment provider, then record its reference here."))return;submit(initiateRefund,"verityai_saas.api.billing.initiate_refund",{payment:initiateRefund.payment.value,amount:initiateRefund.amount.value,reason:initiateRefund.reason.value},"Refund request created.");});
    const completeRefund = document.querySelector("#complete-refund");
    completeRefund?.addEventListener("submit",event=>{event.preventDefault();submit(completeRefund,"verityai_saas.api.billing.complete_refund",{refund:completeRefund.refund.value,provider_reference:completeRefund.provider_reference.value},"Refund completed and confirmation generated.");});
  }

  async function load(keepSelected=null) {
    try {
      const dashboard=await call("verityai_saas.api.admin.dashboard");
      let schedules=[];
      try { schedules=await call("verityai_saas.api.analytics.schedules"); }
      catch(error) { alert(`Dashboard loaded, but scheduled reports are unavailable: ${error.message}`,true); }
      data={...dashboard,schedules}; selectedWorkspace = keepSelected; render();
    }
	catch (error) { content.innerHTML = `<div class="va-notice error">${esc(error.message)}</div>`; }
  }

  load();
})();
