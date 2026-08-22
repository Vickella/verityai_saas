(() => {
  const content = document.querySelector("#va-admin-content");
  const notice = document.querySelector("#va-admin-notice");
  let data = null;
  let selectedWorkspace = null;
  let adminView = "overview";
  let workspaceSearch = "";
  let searchTimer = null;
  let paynowTestPayment = new URLSearchParams(window.location.search).get("paynow_test") || "";

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

  const emptyState=(title,description)=>`<div class="va-empty"><span class="va-empty-icon">+</span><div><strong>${esc(title)}</strong><p>${esc(description)}</p></div></div>`;
  const table = (columns, rows, empty={}) => rows.length ? `<div class="va-table-wrap"><table class="va-table"><thead><tr>${columns.map(column=>`<th>${esc(column[0])}</th>`).join("")}</tr></thead><tbody>${rows.map(row=>`<tr>${columns.map(column=>`<td data-label="${esc(column[0])}">${column[1](row)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>` : emptyState(empty.title||"Nothing here yet",empty.description||"Records will appear here when available.");
  const section=(title,description,body,actions="")=>`<section class="va-section"><header class="va-section-heading"><div><h2>${esc(title)}</h2>${description?`<p>${esc(description)}</p>`:""}</div>${actions?`<div class="va-actions">${actions}</div>`:""}</header>${body}</section>`;

  const planChecks = ["can_remove_branding","can_use_whatsapp_button","can_use_whatsapp_ai","can_use_email_notifications","can_use_custom_smtp","can_use_erpnext_integration","can_use_quotation_workflow","can_use_api_access","can_bring_own_ai_provider_key"];
  const planNumbers = ["monthly_price","annual_price","trial_days","max_workspaces","max_assistants","max_team_members","monthly_token_limit","max_tokens","public_rate_limit_per_minute","max_public_message_chars","monthly_web_conversations","monthly_whatsapp_messages","monthly_email_sends","max_knowledge_sources","max_allowed_domains"];
  const label = key => ({monthly_token_limit:"Monthly AI credits",max_tokens:"Maximum AI response credits"}[key] || key.replaceAll("_"," ").replace(/\b\w/g,char=>char.toUpperCase()));
  const applyCreditLanguage = root => {
    const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);
    let node;
    while((node=walker.nextNode())) node.nodeValue=node.nodeValue.replace(/\bTokens\b/g,"AI credits").replace(/\btokens\b/g,"AI credits").replace(/\bToken\b/g,"AI credit");
  };

  function planEditor(plan=null) {
    const item=plan||{}; const create=!plan;
    const numberFields=planNumbers.map(key=>`<div class="va-field"><label>${esc(label(key))}</label><input type="number" min="0" step="${key.includes("price")?"0.01":"1"}" name="${key}" value="${esc(item[key]??0)}"></div>`).join("");
    const checks=planChecks.map(key=>`<label><input type="checkbox" name="${key}" ${item[key]?"checked":""}> ${esc(label(key))}</label>`).join("");
    return `<form class="va-admin-editor" data-plan-form="${esc(item.name||"")}"><details ${create?"":""}><summary><div><span class="va-plan-label">${create?"New plan":esc(item.plan_code)}</span><strong>${create?"Create subscription plan":esc(item.plan_name)}</strong><small>${create?"Define pricing, capacity and entitlements":`${esc(item.currency)} ${number(item.monthly_price)} / month · ${number(item.monthly_token_limit)} tokens`}</small></div><div class="va-actions">${create?"":pill(item.active?"Active":"Archived")}<span class="va-chevron">⌄</span></div></summary><div class="va-admin-editor-body"><div class="va-settings-block"><h3>Identity and pricing</h3><div class="va-fields"><div class="va-field"><label>Plan name</label><input name="plan_name" required value="${esc(item.plan_name||"")}"></div><div class="va-field"><label>Plan code</label><input name="plan_code" ${create?"required":"disabled"} value="${esc(item.plan_code||"")}"></div><div class="va-field"><label>Currency</label><input name="currency" value="${esc(item.currency||"USD")}"></div><div class="va-field"><label>Support level</label><select name="support_level">${["Community","Standard","Priority"].map(value=>`<option ${item.support_level===value?"selected":""}>${value}</option>`).join("")}</select></div></div></div><div class="va-settings-block"><h3>Limits and capacity</h3><div class="va-fields">${numberFields}</div></div><div class="va-settings-block"><h3>Features</h3><div class="va-check-grid"><label><input type="checkbox" name="active" ${create||item.active?"checked":""}> Active</label>${checks}</div></div><div class="va-form-actions"><button class="va-button">${create?"Create plan":"Save changes"}</button>${!create&&item.plan_code!=="TRIAL"&&item.active?`<button type="button" class="va-button danger" data-archive-plan="${esc(item.name)}">Archive plan</button>`:""}</div></div></details></form>`;
  }

  function planManagement() {
    return section("Subscription plans","Create, price, limit and feature-gate plans without exposing Frappe Desk.",`<div class="va-admin-editor-list">${planEditor()}${data.plans.map(planEditor).join("")}</div>`);
  }
  function scheduleEditor(schedule=null) {
    const item=schedule||{}; const existing=Boolean(schedule);
    const workspaceOptions=`<option value="">All workspaces</option>${(data.workspaces||[]).map(row=>`<option value="${esc(row.name)}" ${item.workspace===row.name?"selected":""}>${esc(row.business_name||row.name)}</option>`).join("")}`;
    return `<form class="va-admin-editor" data-report-schedule="${esc(item.name||"")}"><details><summary><div><span class="va-plan-label">${existing?esc(item.frequency):"New schedule"}</span><strong>${existing?esc(item.report_name):"Create report schedule"}</strong><small>${existing?`Next ${esc(item.next_send_on||"pending")} · ${esc(item.recipients)}`:"Automate operator or workspace reporting"}</small></div><span class="va-chevron">⌄</span></summary><div class="va-admin-editor-body"><div class="va-settings-block"><div class="va-fields"><div class="va-field"><label>Report name</label><input name="report_name" required value="${esc(item.report_name||"")}"></div><div class="va-field"><label>Report type</label><select name="report_type"><option ${item.report_type==="Operator Summary"?"selected":""}>Operator Summary</option><option ${item.report_type==="Workspace Analytics"?"selected":""}>Workspace Analytics</option></select></div><div class="va-field"><label>Workspace</label><select name="workspace">${workspaceOptions}</select></div><div class="va-field"><label>Recipients</label><input name="recipients" required value="${esc(item.recipients||"")}"></div><div class="va-field"><label>Frequency</label><select name="frequency">${["Daily","Weekly","Monthly"].map(value=>`<option ${item.frequency===value?"selected":""}>${value}</option>`).join("")}</select></div></div><label class="va-check"><input type="checkbox" name="active" ${!existing||item.active?"checked":""}> Active schedule</label></div><div class="va-form-actions"><button class="va-button">${existing?"Save schedule":"Create schedule"}</button></div></div></details></form>`;
  }

  function scheduleManagement() {
    return section("Scheduled reports","Automate internal summaries and workspace analytics delivery.",`<div class="va-admin-editor-list">${scheduleEditor()}${(data.schedules||[]).map(scheduleEditor).join("")}</div>`,`<a class="va-button secondary" href="/api/method/verityai_saas.api.analytics.operator_export">Export operator summary</a>`);
  }

  function paymentGatewayManagement(eventTable) {
    const gateway=data.paynow||{};
    const configured=Boolean(gateway.configured);
    const live=Boolean(gateway.checkout_enabled);
    const gatewayForm=data.can_configure_platform?`<form id="admin-paynow-form" class="va-payment-gateway-form va-form"><div class="va-settings-block"><div class="va-fields"><div class="va-field"><label>Operating mode</label><select name="environment"><option ${gateway.environment!=="Production"?"selected":""}>Test</option><option ${gateway.environment==="Production"?"selected":""}>Production</option></select></div><div class="va-field"><label>Paynow integration ID</label><input name="integration_id" required maxlength="140" value="${esc(gateway.integration_id||"")}" autocomplete="off" placeholder="e.g. 12345"></div><div class="va-field"><label>Integration key ${configured?'<span class="va-field-state">Configured</span>':""}</label><input name="integration_key" type="password" ${configured?"":"required"} autocomplete="new-password" placeholder="${configured?"Leave blank to keep the current key":"Paste the key from Paynow"}"></div></div></div><div class="va-form-actions"><button class="va-button">${configured?"Save Paynow settings":"Connect Paynow"}</button></div></form>`:`<div class="va-callout warning"><strong>Platform administrator required</strong></div>`;
    const workspaceOptions=(data.workspaces||[]).filter(row=>(row.currency||"USD")==="USD").map(row=>`<option value="${esc(row.name)}">${esc(row.business_name||row.workspace_name||row.name)}</option>`).join("");
    const testForm=configured&&gateway.environment==="Test"&&data.can_configure_platform?`<div class="va-settings-block"><h3>Integration test</h3><form id="admin-paynow-test-form" class="va-form"><div class="va-fields"><div class="va-field"><label>Test workspace</label><select name="workspace" required>${workspaceOptions}</select></div><div class="va-field"><label>Paynow merchant email</label><input name="merchant_email" type="email" required autocomplete="email" placeholder="Merchant account login email"></div></div><div class="va-form-actions"><button class="va-button">Start test transaction</button>${paynowTestPayment?`<button type="button" class="va-button secondary" id="poll-paynow-test">Check test result</button>`:""}</div></form></div>`:"";
    const gatewayCard=`<section class="va-payment-gateway-card"><div class="va-payment-gateway-brand"><div class="va-payment-mark" aria-hidden="true">P</div><div><p class="eyebrow">Payment gateway</p><h2>Paynow</h2><p>Accept secure hosted checkout without handling card numbers inside VerityAI.</p></div><div class="va-payment-connection"><span class="va-status-dot ${configured?"good":""}"></span>${pill(!configured?"Not configured":live?"Production":"Test")}</div></div><div class="va-payment-methods"><div><span class="va-method-icon">CARD</span><strong>Debit & credit cards</strong><small>Visa and Mastercard through Paynow hosted checkout</small></div><div><span class="va-method-icon">MOB</span><strong>Mobile & local methods</strong><small>Available methods are selected securely on Paynow</small></div></div>${gatewayForm}${testForm}<footer><span>Credential source</span><strong>${esc(gateway.source||"Not configured")}</strong></footer></section>`;
    return `<div class="va-payment-admin-layout">${gatewayCard}<aside class="va-payment-readiness"><p class="eyebrow">Gateway status</p><h3>${live?"Production mode enabled":gateway.environment==="Production"?"Credentials required":"Test mode"}</h3><p>${live?"Customer checkout requests will be sent to Paynow. Merchant activation and available payment methods remain controlled by Paynow.":gateway.environment==="Production"?"Save valid Paynow credentials to enable checkout.":"Customer checkout remains disabled until Production mode is selected."}</p></aside></div>${section("Billing ledger","Recent payments, top-ups, refunds and provider updates.",eventTable,`<a class="va-button secondary" href="/api/method/verityai_saas.api.billing.reconciliation_export">Export reconciliation</a>`)}`;
  }

  function platformAIManagement() {
    const ai=data.platform_ai||{};
    const configured=Boolean(ai.api_key_present);
    const form=data.can_configure_platform?`<form id="admin-ai-form" class="va-payment-gateway-form va-form"><div class="va-settings-block"><div class="va-fields"><div class="va-field"><label>Provider</label><select name="provider"><option ${ai.provider!=="OpenAI-Compatible"?"selected":""}>OpenAI</option><option ${ai.provider==="OpenAI-Compatible"?"selected":""}>OpenAI-Compatible</option></select></div><div class="va-field"><label>Model</label><input name="model" required value="${esc(ai.model||"gpt-4.1-mini")}"></div><div class="va-field"><label>API base URL</label><input name="api_base" type="url" value="${esc(ai.api_base||"")}" placeholder="OpenAI uses the default endpoint"></div><div class="va-field"><label>Embedding model</label><input name="embedding_model" required value="${esc(ai.embedding_model||"text-embedding-3-small")}"></div><div class="va-field full"><label>API key ${configured?'<span class="va-field-state">Configured</span>':""}</label><input name="api_key" type="password" ${configured?"":"required"} autocomplete="new-password" placeholder="${configured?"Leave blank to keep the current key":"Enter the provider API key"}"></div></div></div><div class="va-form-actions"><button class="va-button">${configured?"Save AI settings":"Connect AI provider"}</button></div></form>`:`<div class="va-callout warning"><strong>Platform administrator required</strong></div>`;
    return section("AI provider","",form);
  }

  function platformEmailManagement() {
    const email=data.support_email||{};
    const configured=Boolean(email.configured&&email.password_present);
    const form=data.can_configure_platform?`<form id="admin-support-email-form" class="va-payment-gateway-form va-form"><div class="va-settings-block"><div class="va-fields"><div class="va-field"><label>Sender address</label><input value="${esc(email.email_id||"support@veritycore.co.zw")}" readonly></div><div class="va-field"><label>Outgoing server</label><input name="smtp_server" required value="${esc(email.smtp_server||"mail.veritycore.co.zw")}" autocomplete="off"></div><div class="va-field"><label>Port</label><select name="smtp_port"><option value="465" ${Number(email.smtp_port||465)===465?"selected":""}>465 with SSL</option><option value="587" ${Number(email.smtp_port)===587?"selected":""}>587 with TLS</option></select></div><div class="va-field"><label>Mailbox password ${email.password_present?'<span class="va-field-state">Configured</span>':""}</label><input name="password" type="password" ${email.password_present?"":"required"} autocomplete="new-password" placeholder="${email.password_present?"Leave blank to keep the current password":"Enter the mailbox password"}"></div></div></div><div class="va-form-actions"><button class="va-button">${configured?"Save email changes":"Connect support email"}</button></div></form>`:`<div class="va-callout warning"><strong>Platform administrator required</strong></div>`;
    const lifecycle=table([["Message",row=>`<strong>${esc(row.name)}</strong><br><span class="muted">${esc(row.purpose)}</span>`],["Timing",row=>esc(row.timing)],["Audience",row=>esc(row.audience)]],[
      {name:"Password reset",purpose:"Secure account recovery",timing:"On request",audience:"Account user"},
      {name:"Workspace welcome",purpose:"Guided activation",timing:"After workspace creation",audience:"Workspace owner"},
      {name:"Trial reminders",purpose:"Conversion and service continuity",timing:"Seven, three and one day before expiry, then on expiry",audience:"Billing contact"},
      {name:"AI credit reminders",purpose:"Capacity awareness",timing:"At 50%, 75%, 90% and 100% usage",audience:"Workspace contact"},
      {name:"Payment confirmation",purpose:"Transaction assurance",timing:"After confirmed payment",audience:"Billing contact"},
      {name:"Payment reminder",purpose:"Renewal continuity",timing:"Before payment and during grace",audience:"Billing contact"},
    ]);
    return `<div class="va-payment-admin-layout"><section class="va-payment-gateway-card"><div class="va-payment-gateway-brand"><div class="va-payment-mark" aria-hidden="true">@</div><div><p class="eyebrow">Transactional email</p><h2>VerityAI Support</h2><p>Send trusted account, billing and service messages from one verified address.</p></div><div class="va-payment-connection"><span class="va-status-dot ${configured?"good":""}"></span>${pill(configured?"Connected":"Not configured")}</div></div>${form}</section><aside class="va-payment-readiness"><p class="eyebrow">Delivery policy</p><h3>Account messages stay reliable</h3><ul><li class="done">Password reset uses secure single use links</li><li class="done">Mandatory billing notices ignore marketing preferences</li><li class="done">Every workspace message has an audit record</li><li class="${configured?"done":""}">Support mailbox connected</li></ul></aside></div>${section("Automated messages","Professional lifecycle emails delivered at the moments that matter.",lifecycle)}`;
  }

  function creditManagement() {
    const stock=data.credit_stock||{};
    const erp=stock.erpnext||{};
    const money=value=>`${esc(erp.currency||"USD")} ${Number(value||0).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})}`;
    const metrics=`<div class="va-credit-metrics va-credit-metrics-wide"><div><span>Credits in stock</span><strong>${number(stock.balance_credits)}</strong><small>${stock.low_stock?"Replenishment required":"Ready to allocate"}</small></div><div><span>Inventory value</span><strong>${money(stock.balance_value)}</strong><small>Cost of unallocated credits</small></div><div><span>Credits purchased</span><strong>${number(stock.received_credits)}</strong><small>Total provider capacity received</small></div><div><span>Credits allocated</span><strong>${number(stock.allocated_credits)}</strong><small>Subscriptions and top ups</small></div><div><span>Sales revenue</span><strong>${money(stock.revenue)}</strong><small>Completed credit sales</small></div><div><span>Gross profit</span><strong>${money(stock.gross_profit)}</strong><small>${money(stock.revenue)} less ${money(stock.cogs)} cost</small></div></div>`;
    const purchaseForm=`<form id="credit-purchase-form" class="va-form va-credit-entry-form"><div class="va-credit-purchase-grid"><div class="va-fields"><div class="va-field"><label>Receipt type</label><select name="entry_type"><option>Purchase</option><option>Opening Balance</option></select></div><div class="va-field"><label>Currency</label><input name="currency" maxlength="3" value="${esc(erp.currency||"USD")}" required></div><div class="va-field"><label>Amount paid</label><input name="monetary_value" type="number" min="0.01" step="0.01" value="10.00" required></div><div class="va-field"><label>Provider credits per ${esc(erp.currency||"USD")}</label><input name="credits_per_currency_unit" type="number" min="0.000001" step="any" value="${esc(stock.purchase_rate||"")}" placeholder="100000000" required></div><div class="va-field full"><label>Provider reference</label><input name="reference" maxlength="140" placeholder="Invoice or purchase reference"></div></div><aside class="va-credit-calculator" aria-live="polite"><span>Credits to receive</span><strong id="credit-purchase-total">0</strong><div><span>Cost per million</span><b id="credit-cost-million">${money(0)}</b></div><div><span>Projected stock balance</span><b id="credit-projected-balance">${number(stock.balance_credits)}</b></div><div><span>Projected inventory value</span><b id="credit-projected-value">${money(stock.balance_value)}</b></div></aside></div><div class="va-form-actions"><button class="va-button">Add credit stock</button></div></form>`;
    const adjustmentForm=`<details class="va-credit-adjustment"><summary>Manual stock adjustment</summary><form id="credit-stock-entry-form" class="va-form va-credit-entry-form"><div class="va-fields"><div class="va-field"><label>Movement</label><select name="entry_type"><option>Adjustment</option><option>Reversal</option></select></div><div class="va-field"><label>Direction</label><select name="direction"><option>Receipt</option><option>Issue</option></select></div><div class="va-field"><label>AI credits</label><input name="credits" type="number" min="1" step="1" required></div><div class="va-field"><label>Monetary value</label><input name="monetary_value" type="number" min="0" step="0.01" value="0" required></div><div class="va-field"><label>Currency</label><input name="currency" maxlength="3" value="${esc(erp.currency||"USD")}" required></div><div class="va-field"><label>Reference</label><input name="reference" maxlength="140" required></div></div><div class="va-form-actions"><button class="va-button secondary">Post adjustment</button></div></form></details>`;
    const ledger=table([
      ["Date",row=>esc(row.posting_datetime)],
      ["Movement",row=>`<strong>${esc(row.entry_type)}</strong><br><span class="muted">${esc(row.direction)}</span>`],
      ["Credits",row=>number(row.credits)],
      ["Movement value",row=>money(row.direction==="Receipt"?Math.abs(Number(row.inventory_value||0)):row.revenue)],
      ["Cost",row=>money(row.cogs)],
      ["Profit",row=>money(row.gross_profit)],
      ["Stock balance",row=>`<strong>${number(row.balance_credits)}</strong><br><span class="muted">${money(row.balance_value)} inventory</span>`],
      ["ERPNext",row=>`${pill(row.erpnext_status||"Not Applicable")}${row.erpnext_journal_entry?`<br><span class="muted">${esc(row.erpnext_journal_entry)}</span>`:""}`],
      ["Action",row=>["Pending","Failed"].includes(row.erpnext_status)?`<button class="va-button secondary" data-post-credit-entry="${esc(row.name)}">Post</button>`:"—"],
    ],stock.ledger||[],{title:"No credit movements",description:"Record your opening balance or first credit purchase."});
    const economicsRows=stock.cost_basis_available?(stock.plan_economics||[]):[];
    const planEconomics=table([
      ["Plan",row=>`<strong>${esc(row.plan_name)}</strong><br><span class="muted">${esc(row.currency)} ${number(row.monthly_price)} monthly</span>`],
      ["Credits allocated",row=>number(row.monthly_token_limit)],
      ["Estimated cost",row=>money(row.estimated_cogs)],
      ["Estimated gross profit",row=>`<strong>${money(row.estimated_gross_profit)}</strong>`],
      ["Stock after one sale",row=>number(row.credits_after_sale)],
    ],economicsRows,{title:"Add credit stock to calculate margins",description:"Plan economics appear when inventory has an acquisition cost."});
    const accountingForm=`<form id="credit-accounting-form" class="va-form va-credit-accounting-form"><div class="va-check-grid"><label><input type="checkbox" name="enabled" ${erp.enabled?"checked":""}> Enable ERPNext posting</label><label><input type="checkbox" name="auto_post" ${erp.auto_post?"checked":""}> Post completed sales automatically</label></div><div class="va-fields"><div class="va-field full"><label>ERPNext URL</label><input name="url" type="url" value="${esc(erp.url||"")}" placeholder="https://erp.example.com"></div><div class="va-field"><label>API key ${erp.configured?'<span class="va-field-state">Configured</span>':""}</label><input name="api_key" type="password" autocomplete="new-password"></div><div class="va-field"><label>API secret</label><input name="api_secret" type="password" autocomplete="new-password"></div><div class="va-field"><label>Company</label><input name="company" value="${esc(erp.company||"")}"></div><div class="va-field"><label>Currency</label><input name="currency" value="${esc(erp.currency||"USD")}" maxlength="3"></div><div class="va-field"><label>Bank or receivable account</label><input name="receivable_account" value="${esc(erp.receivable_account||"")}"></div><div class="va-field"><label>Sales account</label><input name="sales_account" value="${esc(erp.sales_account||"")}"></div><div class="va-field"><label>AI credit inventory account</label><input name="inventory_account" value="${esc(erp.inventory_account||"")}"></div><div class="va-field"><label>Cost of sales account</label><input name="cogs_account" value="${esc(erp.cogs_account||"")}"></div><div class="va-field"><label>Cost centre</label><input name="cost_center" value="${esc(erp.cost_center||"")}"></div></div><div class="va-form-actions"><button class="va-button">Save accounting setup</button><button type="button" class="va-button secondary" id="test-credit-accounting" ${erp.enabled?"":"disabled"}>Test connection</button>${pill(erp.connection_status||"Not Configured")}</div></form>`;
    return `${metrics}<div class="va-grid two va-credit-command-grid">${section("Add provider credits","Record the amount paid and provider exchange rate. Credits and inventory cost are calculated automatically.",purchaseForm)}${section("Plan unit economics","Monthly allocations use the current weighted acquisition cost.",planEconomics)}</div>${adjustmentForm}${section("Credit stock ledger","Every purchase and completed sale updates credit quantity, monetary value, cost and profit.",ledger)}${section("ERPNext accounting","Map credit sales and cost of sales to a remote ERPNext company.",accountingForm)}`;
  }
  function managementPanel(workspace) {
    if (!workspace) return "";
    const subscription = workspace.subscription || {};
    const planOptions = data.plans.filter(plan=>plan.active).map(plan=>`<option value="${esc(plan.name)}" ${plan.name===subscription.plan?"selected":""}>${esc(plan.plan_name)} — ${esc(plan.currency)} ${number(plan.monthly_price)}/month</option>`).join("");
    const statusOptions = ["Trial","Active","Past Due","Suspended","Cancelled","Expired"].map(status=>`<option ${status===subscription.status?"selected":""}>${status}</option>`).join("");
    const completedPayments = data.recent_events.filter(event=>event.workspace===workspace.name&&event.event_type==="Payment"&&event.status==="Completed");
    const pendingRefunds = data.recent_events.filter(event=>event.workspace===workspace.name&&event.event_type==="Refund"&&event.status==="Pending");
    const refundControls = `${completedPayments.length?`<form id="initiate-refund" class="va-admin-action-card va-form"><h3>Initiate refund</h3><div class="va-field"><label>Completed payment</label><select name="payment">${completedPayments.map(event=>`<option value="${esc(event.name)}">${esc(event.name)} · ${esc(event.currency)} ${number(event.amount)}</option>`).join("")}</select></div><div class="va-field"><label>Amount</label><input name="amount" type="number" min="0.01" step="0.01"></div><div class="va-field"><label>Reason</label><textarea name="reason" required></textarea></div><button class="va-button danger">Create refund request</button></form>`:""}${pendingRefunds.length?`<form id="complete-refund" class="va-admin-action-card va-form"><h3>Complete refund</h3><div class="va-field"><label>Pending refund</label><select name="refund">${pendingRefunds.map(event=>`<option value="${esc(event.name)}">${esc(event.name)} · ${esc(event.currency)} ${number(event.amount)}</option>`).join("")}</select></div><div class="va-field"><label>Provider reference</label><input name="provider_reference" required></div><button class="va-button">Record completed refund</button></form>`:""}`;
    const configurationLink=data.can_configure_platform?`<a class="va-button secondary" href="/verityai/integrations?workspace=${encodeURIComponent(workspace.name)}">Platform configuration</a>`:"";
    return `<div class="va-drawer-backdrop va-admin-drawer-backdrop"><aside class="va-admin-drawer" role="dialog" aria-modal="true"><header class="va-drawer-heading"><div><p class="eyebrow">Manage workspace</p><h2>${esc(workspace.business_name || workspace.workspace_name)}</h2><p>${esc(workspace.name)} · ${esc(workspace.status)}</p></div><button type="button" class="va-icon-button" id="close-management" aria-label="Close">×</button></header><div class="va-admin-drawer-tools">${pill(subscription.status||"No subscription")}${configurationLink}</div><div class="va-admin-action-grid"><form id="assign-plan" class="va-admin-action-card va-form"><h3>Plan & billing</h3><div class="va-field"><label>Plan</label><select name="plan" required>${planOptions}</select></div><div class="va-field"><label>Billing cycle</label><select name="billing_cycle"><option ${subscription.billing_cycle==="Monthly"?"selected":""}>Monthly</option><option ${subscription.billing_cycle==="Annual"?"selected":""}>Annual</option><option ${subscription.billing_cycle==="Manual"?"selected":""}>Manual</option></select></div><div class="va-field"><label>Initial status</label><select name="status">${statusOptions}</select></div><button class="va-button">Apply plan</button></form><form id="set-status" class="va-admin-action-card va-form"><h3>Subscription status</h3><div class="va-field"><label>Status</label><select name="status">${statusOptions}</select></div><div class="va-field"><label>Operational reason</label><textarea name="reason" placeholder="Required context"></textarea></div><button class="va-button">Update status</button></form><form id="record-payment" class="va-admin-action-card va-form"><h3>Manual payment</h3><div class="va-field"><label>Amount</label><input name="amount" type="number" min="0" step="0.01" required></div><div class="va-field"><label>Reference</label><input name="reference" required></div><button class="va-button">Record payment</button></form><form id="record-topup" class="va-admin-action-card va-form"><h3>Token top-up</h3><div class="va-field"><label>Tokens</label><input name="tokens" type="number" min="1" step="1" required></div><div class="va-field"><label>Amount</label><input name="amount" type="number" min="0" step="0.01" value="0"></div><div class="va-field"><label>Reference</label><input name="reference"></div><button class="va-button">Add top-up</button></form>${refundControls}</div></aside></div>`;
  }

  function render() {
    const workspaces = data.workspaces || [];
    const selected = workspaces.find(row=>row.name===selectedWorkspace);
    const query=workspaceSearch.trim().toLowerCase();
    const filtered=workspaces.filter(row=>!query||[row.business_name,row.workspace_name,row.name,row.status,row.subscription?.plan,row.subscription?.status].some(value=>String(value||"").toLowerCase().includes(query)));
    const workspaceTable=table([["Workspace",row=>`<strong>${esc(row.business_name||row.workspace_name)}</strong><br><span class="muted">${esc(row.name)}</span>`],["Status",row=>pill(row.status)],["Subscription",row=>`<strong>${esc(row.subscription?.plan||"No plan")}</strong><br>${pill(row.subscription?.status||"Not configured")}`],["AI credit usage",row=>`<strong>${number(row.usage_percent)}%</strong><br><span class="muted">${number(row.wallet?.tokens_remaining)} remaining</span>`],["Signals",row=>`${number(row.new_leads)} leads · ${number(row.open_alerts)} alerts`],["Action",row=>`<button class="va-button secondary" data-manage="${esc(row.name)}">Manage</button>`]],filtered,{title:"No matching workspaces",description:"Adjust the search or wait for the first customer workspace."});
    const alertTable=table([["Alert",row=>`<strong>${esc(row.summary)}</strong><br><span class="muted">${esc(row.workspace)}</span>`],["Severity",row=>pill(row.severity)],["Status",row=>pill(row.status)],["Last seen",row=>esc(row.last_seen)],["Action",row=>`<div class="va-actions">${row.status==="Open"?`<button class="va-button secondary" data-alert-action="Acknowledged" data-alert="${esc(row.name)}" data-workspace="${esc(row.workspace)}">Acknowledge</button>`:""}<button class="va-button" data-alert-action="Resolved" data-alert="${esc(row.name)}" data-workspace="${esc(row.workspace)}">Resolve</button></div>`]],data.provider_failures,{title:"No provider incidents",description:"All monitored providers are currently clear."});
    const whatsappTable=table([["Workspace",row=>`<strong>${esc(row.workspace)}</strong><br><span class="muted">${esc(row.mode)}</span>`],["Status",row=>pill(row.setup_status)],["Last test",row=>esc(row.last_tested_on||"Never")],["Action",row=>`<button class="va-button secondary" data-retry-whatsapp="${esc(row.workspace)}">Retry test</button>`]],data.failed_whatsapp,{title:"No failed WhatsApp setups",description:"Connected channels requiring attention will appear here."});
    const eventTable=table([["Event",row=>`<strong>${esc(row.event_type)}</strong><br><span class="muted">${esc(row.provider||"Manual")}</span>`],["Workspace",row=>esc(row.workspace)],["Amount",row=>`${esc(row.currency||"")} ${number(row.amount)}`],["Status",row=>`${pill(row.status)} ${row.gateway_status?pill(row.gateway_status):""}`],["Reference",row=>esc(row.gateway_reference||"—")],["Created",row=>esc(row.creation)]],data.recent_events,{title:"No billing events",description:"Payments, top-ups and refunds will appear here."});
    const metrics=data.commercial_metrics||{};
    const attention=`<div class="va-admin-attention"><div><span>Monthly recurring revenue</span><strong>USD ${number(metrics.mrr)}</strong><small>${number(metrics.active_paid)} paying workspaces</small></div><div><span>Trial conversion</span><strong>${number(metrics.trial_conversion_rate)}%</strong><small>Accounts with a completed payment</small></div><div><span>Referral pipeline</span><strong>${number(metrics.referrals_pending)}</strong><small>${number(metrics.referrals_granted)} rewards granted</small></div><div><span>High AI credit usage</span><strong>${number(data.high_usage.length)}</strong><small>Above 80%</small></div></div>`;
    const overview=`${attention}<div class="va-grid two">${section("High AI credit usage","Workspaces approaching their allowance.",table([["Workspace",row=>`<strong>${esc(row.business_name)}</strong><br><span class="muted">${number(row.tokens_remaining)} credits remaining</span>`],["Usage",row=>`${number(row.usage_percent)}%`]],data.high_usage,{title:"Capacity is healthy",description:"No workspace has crossed the 80% threshold."}))}${section("Trials ending soon","Customers requiring a conversion or extension decision.",table([["Workspace",row=>`<strong>${esc(row.business_name)}</strong><br><span class="muted">${esc(row.workspace)}</span>`],["Trial ends",row=>esc(row.trial_end)]],data.trial_expiring,{title:"No urgent trial decisions",description:"No trial expires in the next seven days."}))}</div>${section("Provider incidents","Acknowledge or resolve monitored AI-provider failures.",alertTable)}${section("WhatsApp attention","Failed channel connections requiring operator action.",whatsappTable)}`;
    const views={overview,workspaces:`<div class="va-admin-search"><div><p class="eyebrow">Tenant operations</p><strong>${number(filtered.length)} of ${number(workspaces.length)} workspaces</strong></div><div class="va-field"><label>Search workspaces</label><input id="admin-workspace-search" value="${esc(workspaceSearch)}" placeholder="Business, workspace, status or plan"></div></div>${section("Customer workspaces","Review health, plan, usage and operational signals.",workspaceTable)}`,plans:planManagement(),credits:creditManagement(),reports:scheduleManagement(),ai:platformAIManagement(),billing:paymentGatewayManagement(eventTable),email:platformEmailManagement()};
    content.innerHTML = `<div class="va-grid va-metrics"><div class="va-card va-metric"><span>Customer accounts</span><strong>${number(data.accounts)}</strong><small>Registered organisations</small></div><div class="va-card va-metric"><span>Workspaces</span><strong>${number(workspaces.length)}</strong><small>Customer environments</small></div><div class="va-card va-metric"><span>Active / trial</span><strong>${number(data.active)}</strong><small>Currently available</small></div><div class="va-card va-metric"><span>Suspended</span><strong>${number(data.suspended)}</strong><small>Access restricted</small></div></div><nav class="va-admin-tabs" aria-label="Operator console">${[["overview","Overview"],["workspaces","Workspaces"],["plans","Plans"],["credits","Credit Management"],["reports","Reports"],["ai","AI"],["billing","Billing"],["email","Email"]].map(([key,name])=>`<button type="button" class="${adminView===key?"active":""}" aria-current="${adminView===key?"page":"false"}" data-admin-view="${key}">${name}</button>`).join("")}</nav><div class="va-admin-view">${views[adminView]||views.overview}</div>${managementPanel(selected)}`;
    applyCreditLanguage(content);
    bindActions();
  }

  async function submit(form, method, args, message) {
    const button = form.querySelector("button"); button.disabled = true;
    try { await call(method, {workspace:selectedWorkspace, ...args}); alert(message); await load(selectedWorkspace); }
    catch (error) { alert(error.message, true); button.disabled = false; }
  }

  function bindActions() {
    document.querySelectorAll("[data-admin-view]").forEach(button=>button.addEventListener("click",()=>{adminView=button.dataset.adminView;selectedWorkspace=null;document.body.classList.remove("va-no-scroll");render();}));
    const search=document.querySelector("#admin-workspace-search");
    search?.addEventListener("input",event=>{workspaceSearch=event.target.value;window.clearTimeout(searchTimer);searchTimer=window.setTimeout(()=>{render();const next=document.querySelector("#admin-workspace-search");next?.focus();next?.setSelectionRange(workspaceSearch.length,workspaceSearch.length);},180);});
    document.querySelectorAll("[data-manage]").forEach(button=>button.addEventListener("click",()=>{selectedWorkspace=button.dataset.manage;document.body.classList.add("va-no-scroll");render();}));
    const closeManagement=()=>{selectedWorkspace=null;document.body.classList.remove("va-no-scroll");render();};
    document.querySelector("#close-management")?.addEventListener("click",closeManagement);
    document.querySelector(".va-admin-drawer-backdrop")?.addEventListener("click",event=>{if(event.target===event.currentTarget)closeManagement();});
    document.onkeydown=event=>{if(event.key==="Escape"&&selectedWorkspace)closeManagement();};
    const creditPurchaseForm=document.querySelector("#credit-purchase-form");
    const refreshCreditPurchase=()=>{
      if(!creditPurchaseForm)return;
      const amount=Number(creditPurchaseForm.monetary_value.value||0);
      const rate=Number(creditPurchaseForm.credits_per_currency_unit.value||0);
      const credits=Math.max(Math.floor(amount*rate),0);
      const currency=(creditPurchaseForm.currency.value||"USD").toUpperCase();
      const formatMoney=value=>`${currency} ${Number(value||0).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:6})}`;
      const total=document.querySelector("#credit-purchase-total");
      const cost=document.querySelector("#credit-cost-million");
      const balance=document.querySelector("#credit-projected-balance");
      const value=document.querySelector("#credit-projected-value");
      if(total)total.textContent=number(credits);
      if(cost)cost.textContent=formatMoney(credits?amount/credits*1000000:0);
      if(balance)balance.textContent=number(Number(data.credit_stock?.balance_credits||0)+credits);
      if(value)value.textContent=formatMoney(Number(data.credit_stock?.balance_value||0)+amount);
    };
    creditPurchaseForm?.querySelectorAll("input").forEach(input=>input.addEventListener("input",refreshCreditPurchase));
    refreshCreditPurchase();
    creditPurchaseForm?.addEventListener("submit",async event=>{
      event.preventDefault();const button=creditPurchaseForm.querySelector("button");button.disabled=true;button.textContent="Adding...";
      const values=Object.fromEntries(new FormData(creditPurchaseForm).entries());
      try{const result=await call("verityai_saas.api.admin.record_credit_purchase",{values});data.credit_stock=result.summary;alert(`${number(result.credits)} credits added to stock.`);render();}
      catch(error){alert(error.message,true);button.disabled=false;button.textContent="Add credit stock";}
    });
    const creditEntryForm=document.querySelector("#credit-stock-entry-form");
    creditEntryForm?.addEventListener("submit",async event=>{
      event.preventDefault();const button=creditEntryForm.querySelector("button");button.disabled=true;button.textContent="Posting...";
      const values=Object.fromEntries(new FormData(creditEntryForm).entries());
      try{const result=await call("verityai_saas.api.admin.record_credit_stock_entry",{values});data.credit_stock=result.summary;alert("Credit stock movement posted.");render();}
      catch(error){alert(error.message,true);button.disabled=false;button.textContent="Post movement";}
    });
    const accountingForm=document.querySelector("#credit-accounting-form");
    accountingForm?.addEventListener("submit",async event=>{
      event.preventDefault();const button=accountingForm.querySelector("button");button.disabled=true;button.textContent="Saving...";
      const values=Object.fromEntries(new FormData(accountingForm).entries());values.enabled=accountingForm.enabled.checked?1:0;values.auto_post=accountingForm.auto_post.checked?1:0;
      try{await call("verityai_saas.api.admin.configure_credit_accounting",{values});alert("ERPNext accounting setup saved.");await load(selectedWorkspace);}
      catch(error){alert(error.message,true);button.disabled=false;button.textContent="Save accounting setup";}
    });
    document.querySelector("#test-credit-accounting")?.addEventListener("click",async event=>{
      const button=event.currentTarget;button.disabled=true;button.textContent="Testing...";
      try{const result=await call("verityai_saas.api.admin.test_credit_accounting");alert(`ERPNext connected as ${result.user}.`);await load(selectedWorkspace);}
      catch(error){alert(error.message,true);button.disabled=false;button.textContent="Test connection";}
    });
    document.querySelectorAll("[data-post-credit-entry]").forEach(button=>button.addEventListener("click",async()=>{
      button.disabled=true;button.textContent="Posting...";
      try{await call("verityai_saas.api.admin.post_credit_ledger_entry",{entry:button.dataset.postCreditEntry});alert("Accounting entry posted to ERPNext.");await load(selectedWorkspace);}
      catch(error){alert(error.message,true);button.disabled=false;button.textContent="Post";}
    }));
    const aiForm=document.querySelector("#admin-ai-form");
    aiForm?.addEventListener("submit",async event=>{
      event.preventDefault();const button=aiForm.querySelector("button");button.disabled=true;button.textContent="Saving...";
      const values=Object.fromEntries(new FormData(aiForm).entries());
      try{const status=await call("verityai_saas.api.admin.configure_platform_ai",{values});data.platform_ai=status;alert(`AI provider connected for ${number(status.configurations_updated)} workspaces.`);render();}
      catch(error){alert(error.message,true);button.disabled=false;button.textContent=data.platform_ai?.api_key_present?"Save AI settings":"Connect AI provider";}
    });
    const paynowForm=document.querySelector("#admin-paynow-form");
    paynowForm?.addEventListener("submit",async event=>{
      event.preventDefault();const button=paynowForm.querySelector("button");button.disabled=true;button.textContent="Saving...";
      const values=Object.fromEntries(new FormData(paynowForm).entries());
      try{const status=await call("verityai_saas.api.admin.configure_paynow",{values});data.paynow=status;data.paynow_configured=Boolean(status.checkout_enabled);alert(status.checkout_enabled?"Paynow production mode enabled.":"Paynow settings saved in test mode.");render();}
      catch(error){alert(error.message,true);button.disabled=false;button.textContent=data.paynow_configured?"Save gateway changes":"Connect Paynow";}
    });
    const paynowTestForm=document.querySelector("#admin-paynow-test-form");
    paynowTestForm?.addEventListener("submit",async event=>{
      event.preventDefault();const button=paynowTestForm.querySelector("button");button.disabled=true;button.textContent="Connecting...";
      const values=Object.fromEntries(new FormData(paynowTestForm).entries());
      try{const result=await call("verityai_saas.api.admin.start_paynow_test",values);paynowTestPayment=result.payment;window.location.assign(result.checkout_url);}
      catch(error){alert(error.message,true);button.disabled=false;button.textContent="Start test transaction";}
    });
    document.querySelector("#poll-paynow-test")?.addEventListener("click",async event=>{
      const button=event.currentTarget;button.disabled=true;button.textContent="Checking...";
      try{const result=await call("verityai_saas.api.admin.poll_paynow_test",{payment:paynowTestPayment});alert(result.status==="Completed"?"Paynow integration test completed successfully.":`Paynow test status: ${result.gateway_status||result.status}.`);if(result.status==="Completed"){paynowTestPayment="";history.replaceState({},"",location.pathname);}await load(selectedWorkspace);}
      catch(error){alert(error.message,true);button.disabled=false;button.textContent="Check test result";}
    });
    const supportEmailForm=document.querySelector("#admin-support-email-form");
    supportEmailForm?.addEventListener("submit",async event=>{
      event.preventDefault();const button=supportEmailForm.querySelector("button");button.disabled=true;button.textContent="Verifying mailbox...";
      const values=Object.fromEntries(new FormData(supportEmailForm).entries());
      try{const status=await call("verityai_saas.api.admin.configure_support_email",{values});data.support_email=status;alert("Support email connected. Transactional delivery is ready.");render();}
      catch(error){alert(error.message,true);button.disabled=false;button.textContent=data.support_email?.configured?"Save email changes":"Connect support email";}
    });
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
    topup?.addEventListener("submit",event=>{event.preventDefault();submit(topup,"verityai_saas.api.billing.top_up",{tokens:topup.tokens.value,amount:topup.amount.value,reference:topup.reference.value},"AI credit top-up recorded.");});
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

  const unlockForm=document.querySelector("#va-admin-unlock-form");
  if(unlockForm){
    unlockForm.addEventListener("submit",async event=>{event.preventDefault();const button=unlockForm.querySelector("button");button.disabled=true;button.textContent="Verifying…";try{await call("verityai_saas.api.admin_auth.unlock",{password:unlockForm.password.value});location.reload();}catch(error){unlockForm.password.value="";unlockForm.password.focus();alert(error.message,true);button.disabled=false;button.textContent="Unlock operator console";}});
    return;
  }
  document.querySelector("#va-admin-lock")?.addEventListener("click",async event=>{const button=event.currentTarget;button.disabled=true;try{await call("verityai_saas.api.admin_auth.lock");location.reload();}catch(error){alert(error.message,true);button.disabled=false;}});
  load();
})();
