# VerityAI SaaS Implementation Master Document

## Building `verityai_saas` on Top of the Hardened `verity_ai` Engine

## 1. Purpose

This document directs the full implementation of the new Frappe app:

`verityai_saas`

The app will be built as the customer-facing SaaS layer for Verity AI.

The existing `verity_ai` app must remain the AI engine. It already owns the runtime AI work, including tenant records, public chat, website widget runtime, WhatsApp webhook, model calls, tools, knowledge, lead capture, quotation requests, usage logs, monitoring and retention.

The new `verityai_saas` app must not rebuild those engine features.

Instead, `verityai_saas` must make the engine commercially usable by adding:

Customer signup
Customer accounts
Workspaces
Workspace members
Self-onboarding
Assistant setup UI
Widget setup UI
Allowed domain management
Knowledge management UI
WhatsApp setup UI
Email notification settings
Lead dashboard
Conversation dashboard
Usage dashboard
Plans
Subscriptions
Token wallets or credits
Billing snapshots
Payment readiness
Alerts and health dashboard
Admin/operator dashboard

The goal is to turn the existing AI engine into a sellable SaaS product.

## 2. Product Architecture

The intended product split is:

```text
public static website
= marketing, demo, product education, pricing and conversion

verityai_saas
= signup, onboarding, workspaces, plans, subscriptions, billing, token wallets, customer dashboards, widget setup, WhatsApp/email setup, lead and conversation dashboards

verity_ai
= core AI engine, tenant records, widget runtime, public chat API, WhatsApp webhook, model calls, tools, knowledge, lead capture, quotation requests, usage logs, monitoring and retention
```

## 3. Core Design Principle

`verityai_saas` must make `verity_ai` easy to use, sell, limit, monitor and bill.

It must not duplicate engine logic.

The SaaS app should speak in customer-friendly product language:

Workspace
Assistant
Knowledge
Leads
Conversations
Usage
Widget
WhatsApp
Email
Billing
Team
Settings

Internally, those screens will create, update and read records from `verity_ai`.

## 4. User Experience Goal

The SaaS customer should not feel like they are using Frappe Desk.

The experience should feel like a modern SaaS dashboard.

The primary customer journey should be:

1. Customer signs up.
2. Customer creates a workspace.
3. SaaS creates or links an engine tenant.
4. Customer configures assistant identity.
5. Customer selects business nature.
6. Customer adds an allowed website domain.
7. Customer customizes widget appearance.
8. Customer tests the widget.
9. Customer adds business knowledge.
10. Customer installs the embed script.
11. Assistant captures a lead.
12. Customer sees leads, conversations and usage in the dashboard.
13. Billing and usage limits are enforced by the SaaS layer.

The first important “aha moment” is:

> “I created my assistant, tested it, installed it on my website, and it captured a lead.”

## 5. What `verityai_saas` Must Own

Build these features in `verityai_saas`:

Customer signup
Customer account creation
Workspace creation
Workspace membership
Workspace roles
Plan management
Subscription management
Billing status
Token wallet or usage credits
Usage dashboard
Customer onboarding checklist
Assistant setup dashboard
Widget design/setup UI
Allowed domain management UI
Knowledge upload and management UI
WhatsApp setup wizard
Email notification settings
Lead dashboard
Conversation dashboard
Alerts/health dashboard
Quotation request/approval UI
Admin/operator dashboard for all tenants

## 6. What `verityai_saas` Must Not Duplicate

Do not rebuild these features inside `verityai_saas`:

AI provider call loop
OpenAI/OpenAI-compatible model processing
Public chat processing
Website widget runtime endpoint logic
WhatsApp webhook routing
WhatsApp duplicate handling
Knowledge chunk search core
Lead capture tool logic
Quotation request engine
Quotation approval hook
ERPNext/VerityPack tool safety
Usage log creation from model calls
Tool call audit creation
Monitoring alert dedupe core
Retention cleanup
Secret redaction/sanitization helpers

The SaaS app must wrap and orchestrate the engine.

## 7. App Dependency

`verityai_saas` should depend on `verity_ai`.

In `verityai_saas/hooks.py`:

```python
required_apps = ["frappe", "verity_ai"]
```

The SaaS app should assume that `verity_ai` is installed, migrated and working before `verityai_saas` is installed.

## 8. Recommended App Structure

```text
verityai_saas/
├── verityai_saas/
│   ├── __init__.py
│   ├── hooks.py
│   ├── modules.txt
│   ├── services/
│   │   ├── engine.py
│   │   ├── onboarding.py
│   │   ├── usage.py
│   │   ├── billing.py
│   │   ├── notifications.py
│   │   ├── permissions.py
│   │   └── workspace.py
│   ├── api/
│   │   ├── onboarding.py
│   │   ├── workspace.py
│   │   ├── assistant.py
│   │   ├── widget.py
│   │   ├── knowledge.py
│   │   ├── leads.py
│   │   ├── conversations.py
│   │   ├── usage.py
│   │   ├── billing.py
│   │   ├── whatsapp.py
│   │   ├── email.py
│   │   └── admin.py
│   ├── www/
│   │   ├── app.py
│   │   ├── signup.py
│   │   ├── onboarding.py
│   │   ├── dashboard.py
│   │   ├── assistant.py
│   │   ├── widget.py
│   │   ├── knowledge.py
│   │   ├── leads.py
│   │   ├── conversations.py
│   │   ├── usage.py
│   │   ├── billing.py
│   │   ├── whatsapp.py
│   │   └── email.py
│   ├── templates/
│   │   ├── pages/
│   │   └── includes/
│   ├── public/
│   │   ├── css/
│   │   │   └── portal.css
│   │   └── js/
│   │       ├── portal.js
│   │       ├── onboarding.js
│   │       ├── assistant.js
│   │       ├── widget_setup.js
│   │       ├── knowledge.js
│   │       ├── usage.js
│   │       ├── billing.js
│   │       ├── whatsapp.js
│   │       └── email.js
│   └── tests/
│       ├── test_workspace.py
│       ├── test_engine_link.py
│       ├── test_permissions.py
│       ├── test_usage.py
│       ├── test_billing.py
│       └── test_onboarding.py
```

## 9. Core SaaS DocTypes

## 9.1 VerityAI Account

Represents the customer organization.

Fields:

Account Name
Owner User
Billing Email
Phone
Country
Currency
Status
Created On
Default Workspace
Customer Type: SME, Agency, Enterprise
Notes

Purpose:

A customer may later have multiple workspaces, especially agencies or enterprises.

Relationships:

One Account can have many Workspaces.
One Account can have many Subscriptions.
One Account can have many Payments or Billing Events.

## 9.2 VerityAI Workspace

Represents one business workspace.

Fields:

Workspace Name
Account
Owner User
Engine Tenant
Business Name
Business Nature
Website URL
Country
Currency
Timezone
Status: Draft, Trial, Active, Suspended, Cancelled
Onboarding Status
Setup Progress
Widget Installed
First Lead Captured
Created On

Important field:

`engine_tenant` links to `AI Tenant.name`.

Purpose:

This is the main customer-facing container.

All customer-visible records must scope through:

```text
Workspace -> Engine Tenant -> verity_ai records
```

Rules:

Every SaaS API must resolve the current workspace first.
Every engine query must use the linked `AI Tenant`.
Never query engine records without workspace/tenant scoping.

## 9.3 VerityAI Workspace Member

Represents users invited into a workspace.

Fields:

Workspace
User
Role: Owner, Admin, Sales, Support, Viewer, Billing Manager
Status
Can Manage Assistant
Can Manage Widget
Can Manage Knowledge
Can View Leads
Can Manage Leads
Can View Conversations
Can Manage Billing
Can Manage WhatsApp
Can Manage Email
Can Approve Quotes

Purpose:

Allows customer teams to collaborate without giving them full Frappe Desk access.

Rules:

Customers should use the SaaS portal, not normal Frappe Desk.
Workspace role permissions must be enforced in every SaaS API.

## 9.4 VerityAI Plan

Defines commercial plans and feature limits.

Fields:

Plan Name
Plan Code
Active
Currency
Monthly Price
Annual Price
Trial Days
Max Workspaces
Max Assistants
Max Team Members
Monthly Token Limit
Monthly Web Conversations
Monthly WhatsApp Messages
Monthly Email Sends
Max Knowledge Sources
Max Allowed Domains
Can Remove Branding
Can Use WhatsApp Button
Can Use WhatsApp AI
Can Use Email Notifications
Can Use Custom SMTP
Can Use ERPNext Integration
Can Use Quotation Workflow
Can Use API Access
Can Bring Own AI Provider Key
Support Level

Purpose:

Controls what each workspace can use.

Important:

Plan limits should map to safe engine fields, especially:

`AI Configuration.monthly_token_limit`
`AI Configuration.max_tokens`
`AI Configuration.public_rate_limit_per_minute`
`AI Configuration.max_public_message_chars`
Feature toggles on `AI Configuration`

## 9.5 VerityAI Subscription

Stores active subscription state.

Fields:

Account
Workspace
Plan
Status: Trial, Active, Past Due, Suspended, Cancelled, Expired
Billing Cycle: Monthly, Annual, Manual
Trial Start
Trial End
Current Period Start
Current Period End
Next Billing Date
Amount
Currency
Auto Renew
Grace Period End
Last Payment Reference
Suspension Reason

Purpose:

Controls whether the workspace can use AI and paid features.

Rules:

If subscription is inactive or expired, SaaS should be able to suspend usage.
For MVP, subscription may be manual.
Later, it can be linked to a payment gateway.

## 9.6 VerityAI Usage Wallet

Tracks SaaS-level credits or allowances.

Fields:

Workspace
Subscription
Period Start
Period End
Opening Token Allowance
Top-Up Tokens
Tokens Used
Tokens Remaining
Web Conversations Used
WhatsApp Messages Used
Email Sends Used
Estimated AI Cost
Estimated Revenue
Estimated Gross Margin
Status: Normal, Warning, Exhausted, Suspended
Last Synced From Usage Logs

Purpose:

Provides a customer-friendly usage view and future billing control.

Important:

Do not rely on browser/client-side usage counting.

Usage must be derived from `AI Usage Log`.

## 9.7 VerityAI Usage Transaction

Immutable usage ledger.

Fields:

Workspace
Engine Tenant
AI Usage Log
Transaction Type: Usage, Blocked, Top-Up, Adjustment, Refund
Platform
Input Tokens
Output Tokens
Total Tokens
Estimated Cost
Billable Amount
Created On
Period

Purpose:

Creates SaaS billing-grade records from engine usage logs.

Rules:

Each `AI Usage Log` should only create one SaaS Usage Transaction.
Transactions should be immutable after creation except for administrative correction.

## 9.8 VerityAI Billing Event

Stores billing records and snapshots.

Fields:

Account
Workspace
Subscription
Event Type: Invoice, Payment, Credit, Adjustment, Top-Up, Refund
Amount
Currency
Status
Provider
Provider Reference
Period Start
Period End
Usage Snapshot JSON
Created On
Paid On

Purpose:

Allows billing to work even if engine usage logs are later cleaned by retention.

## 9.9 VerityAI Onboarding Checklist

Stores onboarding progress.

Fields:

Workspace
Step Code
Step Label
Status: Not Started, In Progress, Done, Skipped
Completed On
Completed By

Recommended steps:

Create Workspace
Create Assistant
Set Business Nature
Add Website Domain
Customize Widget
Test Widget
Add Knowledge
Configure Lead Capture
Configure Email Notifications
Configure WhatsApp
Install Widget
Capture First Lead
Choose Plan

Purpose:

Creates visible progress and improves customer onboarding.

## 9.10 VerityAI Notification Setting

Stores email and notification preferences.

Fields:

Workspace
Notification Email
Reply-To Email
Lead Notifications Enabled
Daily Summary Enabled
Human Handoff Alerts Enabled
Quote Request Alerts Enabled
Usage Warning Alerts Enabled
Provider Failure Alerts Enabled
Alert Recipients
Email Branding Name
Email Footer
Status

Purpose:

Supports SaaS email notifications.

Do not store SMTP passwords here unless built as encrypted/password fields.

## 9.11 VerityAI Email Delivery Log

Stores email sending activity.

Fields:

Workspace
Notification Type
Recipient
Subject
Status: Pending, Sent, Failed
Reference Doctype
Reference Name
Error
Sent On

Purpose:

Creates auditability for email notifications.

## 9.12 VerityAI WhatsApp Setup

Customer-facing WhatsApp setup state.

Fields:

Workspace
Mode: Button Only, Lead Alerts, Full AI Automation
Business WhatsApp Number
WhatsApp Button Enabled
Lead Alert Enabled
Full AI Enabled
Setup Status
Meta Phone Number ID Status
Access Token Status
Webhook Status
Signature Verification Status
Last Tested On

Purpose:

Provides a friendly setup layer while actual runtime fields remain in `AI Configuration`.

Rules:

Actual `whatsapp_phone_id`, `whatsapp_access_token`, `meta_verify_token`, `meta_app_secret`, and `verify_meta_signature` should still be written to `AI Configuration`.

## 9.13 VerityAI Integration Status

Optional helper DocType.

Fields:

Workspace
Integration Type: Domain, Widget, WhatsApp, Email, AI Provider, ERPNext
Status: Not Configured, Connected, Failed, Warning
Last Checked
Details
Reference Doctype
Reference Name

Purpose:

Provides a dashboard-friendly health/status layer.

## 10. Engine Integration Service

Create a central service module:

```text
verityai_saas/services/engine.py
```

This file must be the main bridge between `verityai_saas` and `verity_ai`.

Suggested functions:

```python
def get_workspace_engine_tenant(workspace_name):
    pass

def create_engine_tenant(workspace_name):
    pass

def ensure_engine_configuration(workspace_name):
    pass

def set_engine_active(workspace_name, active):
    pass

def update_assistant_identity(workspace_name, values):
    pass

def update_widget_settings(workspace_name, values):
    pass

def replace_allowed_domains(workspace_name, domains):
    pass

def create_knowledge_source(workspace_name, title, content, file=None):
    pass

def get_workspace_usage(workspace_name, from_date=None, to_date=None):
    pass

def get_workspace_conversations(workspace_name, filters=None):
    pass

def get_workspace_leads(workspace_name, filters=None):
    pass

def get_workspace_alerts(workspace_name):
    pass

def apply_plan_limits(workspace_name, plan_name):
    pass

def generate_embed_code(workspace_name):
    pass
```

Rules:

Every function must resolve Workspace -> AI Tenant first.
Never use session ID alone.
Never query engine records globally.
Never expose engine secrets.
Never expose raw system prompt to normal customer users.

## 11. Onboarding Flow Implementation

## Phase 1: Account and Workspace Creation

When a customer signs up:

1. Create User if needed.
2. Create VerityAI Account.
3. Create VerityAI Workspace.
4. Create VerityAI Workspace Member with Owner role.
5. Create linked `AI Tenant`.
6. Create linked `AI Configuration`.
7. Create trial Subscription.
8. Create Usage Wallet.
9. Create Onboarding Checklist.
10. Redirect customer to onboarding dashboard.

## Phase 2: Assistant Setup

Customer configures:

Assistant Name
Business Name
Brand Name
Business Nature
Greeting
Fallback message if supported
Basic behavior/tone if safely exposed

Writes to:

`AI Tenant`
selected safe fields in `AI Configuration`

Do not expose:

Provider API key
System prompt
ERPNext credentials
WhatsApp tokens
Internal cost fields

## Phase 3: Domain and Widget Setup

Customer enters website domain.

SaaS writes to:

`AI Tenant.allowed_domains`

Then shows:

Embed script
Widget preview
Widget install instructions
Domain status
Test widget button

Embed should use existing engine widget:

```html
<script src="https://app.verityai.co.zw/assets/verity_ai/js/widget.js"
        data-tenant-id="TENANT-ID">
</script>
```

The SaaS app must not create a second widget runtime.

## Phase 4: Knowledge Setup

Customer can add:

FAQs
Business profile
Services
Pricing text
Policies
Manual text
Uploaded document text later
Website crawl text later

SaaS creates/updates:

`AI Knowledge Source`

Engine automatically rebuilds:

`AI Knowledge Chunk`

SaaS should show:

Source title
Active status
Last updated
Processing/chunk status
Error state if any

## Phase 5: Lead Capture Setup

Customer selects lead capture configuration.

Initial MVP can use:

Business nature templates from `AI Business Nature` and `AI Business Lead Field`.

Later SaaS can add custom lead field management.

SaaS should show lead fields in friendly language but keep stable engine fieldnames.

## Phase 6: Email Setup

Customer configures:

Lead notification recipients
Daily summary enabled/disabled
Human handoff alerts
Quote request alerts
Usage warning alerts

SaaS owns this via:

`VerityAI Notification Setting`

Engine records that can trigger emails:

`AI Lead`
`AI Chat Session` with Human Handoff
`AI Quotation Request`
`AI Monitoring Alert`
`AI Usage Log`

MVP email features:

New lead notification
Human handoff alert
Usage limit warning
Daily lead summary

## Phase 7: WhatsApp Setup

Start with three modes:

### Button Only

Customer enters WhatsApp number.

Widget can later show click-to-chat.

### Lead Alerts

SaaS/engine sends lead alerts to business owner WhatsApp.

### Full AI Automation

Customer connects Meta WhatsApp Business details.

Writes to `AI Configuration`:

whatsapp_phone_id
whatsapp_access_token
meta_verify_token
meta_app_secret
verify_meta_signature

SaaS shows:

Webhook callback URL
Setup status
Test result
Signature verification status

Important:

Keep actual webhook in `verity_ai`.

## Phase 8: Go Live

Workspace can go live when:

Workspace exists
Engine tenant exists
AI Configuration exists
Allowed domain exists
Subscription/trial active
Plan limits applied
Widget tested or user intentionally skips
Tenant active is set to 1

## 12. Customer Portal Pages

## 12.1 Dashboard

Cards:

Setup Progress
Assistant Status
Widget Installed
Conversations This Month
New Leads
Tokens Used
Tokens Remaining
Current Plan
Workspace Health
Recent Alerts

Primary CTAs:

Continue Setup
Install Widget
Add Knowledge
View Leads
Upgrade Plan

## 12.2 Assistant Page

Allows customer to edit:

Assistant name
Brand name
Business nature
Greeting
Tone/behavior if safely implemented
Lead capture mode
Human handoff message if supported

Writes to:

`AI Tenant`
safe `AI Configuration` fields

## 12.3 Widget Page

Features:

Live preview
Primary color
Header color
Widget title
Greeting
Allowed domains
Embed script
Copy button
Installation guide
Test widget

Writes to:

`AI Tenant`
`AI Allowed Domain`

## 12.4 Knowledge Page

Features:

List knowledge sources
Create manual text source
Edit source
Activate/deactivate source
View chunk status
Rebuild source
Upload file later

Writes to:

`AI Knowledge Source`

Reads:

`AI Knowledge Chunk`

## 12.5 Leads Page

Reads:

`AI Lead`

Features:

Lead list
Search
Filter by status
Filter by source channel
View conversation link
Update status
Export
Email/WhatsApp action later

## 12.6 Conversations Page

Reads:

`AI Chat Session`

Features:

Conversation list
Filter by platform
Status
User identifier
Conversation history viewer
Lead linked
Human handoff flag
Export later

Important:

Must scope through Workspace -> AI Tenant.

## 12.7 Usage Page

Reads:

`AI Usage Log`
`VerityAI Usage Wallet`
`VerityAI Usage Transaction`

Shows:

Tokens used
Tokens remaining
Web conversations
WhatsApp conversations
Estimated usage cost
Current plan
Usage trend
Blocked usage events

## 12.8 Billing Page

Reads:

Subscription
Plan
Billing Events
Wallet

Features:

Current plan
Renewal date
Trial end date
Upgrade/downgrade
Manual payment status
Top-up option later
Invoice/payment history

## 12.9 WhatsApp Page

Features:

Select WhatsApp mode
Configure WhatsApp button
Configure full WhatsApp AI credentials
Show webhook URL
Test connection
Show warnings

Writes to:

`VerityAI WhatsApp Setup`
selected `AI Configuration` fields

## 12.10 Email Page

Features:

Notification recipients
Lead notification toggle
Daily summary toggle
Quote request alert toggle
Human handoff alert toggle
Usage warning toggle

Writes to:

`VerityAI Notification Setting`

## 12.11 Team Page

Features:

Invite member
Change role
Remove member
Set permissions

Writes to:

`VerityAI Workspace Member`

## 12.12 Admin Operator Dashboard

For VerityCore internal users.

Features:

All accounts
All workspaces
All plans
Subscriptions
Usage overview
High usage tenants
Failed WhatsApp setup
Provider failures
Monitoring alerts
Trial conversion status
Suspended accounts

Reads:

SaaS records
`AI Monitoring Alert`
`AI Usage Log`
`AI Tenant`

## 13. Billing and Usage Strategy

## MVP Billing

Start simple.

Manual plans and subscriptions are acceptable.

MVP should support:

Create plans
Assign plan to workspace
Start trial
Activate subscription
Suspend expired subscription
Apply plan token limits to `AI Configuration.monthly_token_limit`
Show usage from `AI Usage Log`

## Later Billing

Add:

Payment gateway
Automatic invoices
Receipts
Recurring billing
Failed payment handling
Grace period
Token top-ups
Usage-based overage

## Usage Enforcement

Current engine supports:

`AI Configuration.monthly_token_limit`

SaaS should set this from active plan.

Later, add pre-call SaaS gate for:

Expired trial
Unpaid subscription
Suspended workspace
Empty token wallet
Channel not allowed by plan
WhatsApp limit reached
Email limit reached

Important:

Usage must be calculated from server-side engine logs, not from browser counters.

## 14. Email Notification Implementation Plan

MVP email triggers:

New lead captured
Human handoff requested
Quotation request created
Usage reaches warning threshold
Usage exhausted
Daily lead summary

Create service:

```text
verityai_saas/services/notifications.py
```

Suggested functions:

```python
def send_lead_notification(ai_lead_name):
    pass

def send_handoff_notification(chat_session_name):
    pass

def send_quote_request_notification(quote_request_name):
    pass

def send_usage_warning(workspace_name):
    pass

def send_daily_summary(workspace_name):
    pass
```

Notification records:

`VerityAI Notification Setting`
`VerityAI Email Delivery Log`

Do not expose or store email secrets publicly.

Use Frappe email sending first.

Custom SMTP can come later.

## 15. WhatsApp Implementation Plan

MVP:

Button-only WhatsApp setup.

Next:

Lead alert notifications.

Later:

Full WhatsApp AI automation.

SaaS should not own the webhook.

It should configure engine fields and display setup status.

The webhook remains:

`verity_ai.api.whatsapp.webhook`

SaaS should show callback URL:

```text
https://app.verityai.co.zw/api/method/verity_ai.api.whatsapp.webhook
```

## 16. Permission Model

Customer users should not be given broad Desk access.

Create SaaS roles:

VerityAI Customer Owner
VerityAI Customer Admin
VerityAI Sales User
VerityAI Support User
VerityAI Billing User
VerityAI Viewer
VerityAI Operator
VerityAI SaaS Administrator

Every API must enforce:

Logged-in user
Workspace membership
Workspace role permission
Workspace -> AI Tenant scope

Never rely only on client-side hiding.

## 17. API Design

All SaaS APIs should return predictable responses:

```json
{
  "success": true,
  "data": {},
  "error": null,
  "code": null
}
```

For errors:

```json
{
  "success": false,
  "data": null,
  "error": "You do not have access to this workspace.",
  "code": "WORKSPACE_FORBIDDEN"
}
```

Important API groups:

Workspace API
Onboarding API
Assistant API
Widget API
Knowledge API
Leads API
Conversations API
Usage API
Billing API
WhatsApp API
Email API
Admin API

## 18. Implementation Phases

## Phase 0: Read and Understand

Before writing code:

1. Read the attached `verity_ai` handover/current-state documentation.
2. Read the full `verity_ai` repo.
3. Confirm `verity_ai` tests pass.
4. Confirm installed app state.
5. Create implementation notes.

## Phase 1: Create App Skeleton

Commands:

```bash
cd ~/frappe-bench
bench new-app verityai_saas
bench --site farm.test install-app verityai_saas
bench --site farm.test migrate
```

Add dependency on `verity_ai`.

Create module:

`VerityAI SaaS`

## Phase 2: Create Core DocTypes

Create:

VerityAI Account
VerityAI Workspace
VerityAI Workspace Member
VerityAI Plan
VerityAI Subscription
VerityAI Usage Wallet
VerityAI Usage Transaction
VerityAI Billing Event
VerityAI Onboarding Checklist
VerityAI Notification Setting
VerityAI Email Delivery Log
VerityAI WhatsApp Setup
VerityAI Integration Status

## Phase 3: Build Engine Service

Create:

`verityai_saas/services/engine.py`

Implement:

Create engine tenant
Ensure AI configuration
Update assistant settings
Update widget settings
Replace allowed domains
Generate embed code
Create knowledge source
Read usage logs
Read leads
Read conversations
Read alerts
Apply plan limits

## Phase 4: Build Workspace Permissions

Create:

`verityai_saas/services/permissions.py`

Implement:

Get current user workspaces
Check workspace access
Check workspace role
Resolve workspace engine tenant
Prevent cross-workspace access

Add tests before building dashboards.

## Phase 5: Build Onboarding Service

Create:

`verityai_saas/services/onboarding.py`

Implement:

Create account
Create workspace
Create workspace member
Create engine tenant
Create AI configuration
Assign trial plan
Create subscription
Create usage wallet
Create checklist
Calculate setup progress

## Phase 6: Build Customer Portal MVP

Pages:

Dashboard
Onboarding
Assistant
Widget
Knowledge
Leads
Conversations
Usage
Billing
WhatsApp
Email
Team

Keep UI simple first.

Do not overdesign before data flow works.

## Phase 7: Build Usage and Plan Mapping

Implement:

Plan limit application
Monthly token limit sync to `AI Configuration`
Usage aggregation from `AI Usage Log`
Wallet sync from usage logs
Usage dashboard
Warnings

## Phase 8: Build Email Notifications

Implement:

Notification settings
Lead notification email
Human handoff email
Usage warning email
Daily summary email
Email delivery log

## Phase 9: Build WhatsApp Setup UI

Implement:

Button-only mode
Business WhatsApp number
Full AI setup fields
Webhook URL display
Connection status
Signature verification status

Writes runtime credentials to `AI Configuration`.

## Phase 10: Build Admin/Operator Dashboard

Implement:

All accounts
All workspaces
Plan/subscription overview
Usage overview
Alerts
High usage workspaces
Failed setups
Trial conversion view

## Phase 11: Billing MVP

Implement:

Manual plan assignment
Manual payment event
Activate/suspend subscription
Trial expiry check
Grace period
Top-up record structure

Payment gateway later.

## Phase 12: Testing and Pilot

Test:

Workspace creation
Engine tenant creation
AI configuration creation
Domain setup
Widget settings
Public chat through widget
Knowledge source creation
Lead capture
Usage logging
Usage dashboard
Email notification
WhatsApp setup
Permissions
Cross-workspace security
Plan limit sync
Subscription suspension

Pilot with:

VerityCore website
1 retail business
1 school/clinic
1 consultancy
1 microfinance/finance lead

## 19. Master Prompt for Codex

Use the following as the execution prompt for Codex.

---

You are working on a new Frappe app called `verityai_saas`.

This app must be built on top of the existing hardened `verity_ai` engine.

Before touching code, read the full `verity_ai` handover/current-state documentation and then read the entire `verity_ai` repository. Understand its DocTypes, APIs, hooks, runtime flows, widget flow, WhatsApp flow, knowledge flow, lead flow, quotation flow, usage logging, monitoring and retention.

Do not modify `verity_ai` unless absolutely required and clearly justified.

Your job is to build the SaaS/customer-facing layer, not to rebuild the AI engine.

`verity_ai` owns the engine:

AI Tenant
AI Configuration
AI Allowed Domain
AI Chat Session
AI Lead
AI Quotation Request
AI Knowledge Source
AI Knowledge Chunk
AI Usage Log
AI Tool Call Log
AI Monitoring Alert
AI Action Approval
Website widget runtime
Public chat endpoint
WhatsApp webhook
AI model calls
Knowledge search
Lead capture tool
Quotation approval flow
ERPNext tool safety
Monitoring
Retention

`verityai_saas` must own:

Customer signup
Customer accounts
Workspaces
Workspace membership
Plans
Subscriptions
Token wallet / usage credits
Billing events
Onboarding checklist
Customer portal
Assistant setup UI
Widget setup UI
Allowed domain UI
Knowledge management UI
WhatsApp setup UI
Email notification settings
Leads dashboard
Conversations dashboard
Usage dashboard
Billing dashboard
Alerts/health dashboard
Quote approval UI
Admin/operator dashboard

Hard rules:

Do not duplicate chat processing.
Do not duplicate WhatsApp webhook routing.
Do not duplicate engine usage logging.
Do not duplicate knowledge search core.
Do not duplicate lead capture tool logic.
Do not duplicate quotation approval hook.
Do not expose engine secrets.
Do not expose system prompts to normal customers.
Do not query engine records without Workspace -> AI Tenant scoping.
Do not rely on `session_id` alone.
Do not give customer users broad Frappe Desk access.
Do not use browser-side token accounting for billing.
Do not bypass `AI Action Approval` for sensitive actions.
Do not bypass `AI Quotation Request` approval flow.
Keep `verity_ai` independently installable.

Start by creating `verityai_saas` with dependency on `verity_ai`.

Then implement in this order:

1. Create app skeleton and module.
2. Create core DocTypes:

   * VerityAI Account
   * VerityAI Workspace
   * VerityAI Workspace Member
   * VerityAI Plan
   * VerityAI Subscription
   * VerityAI Usage Wallet
   * VerityAI Usage Transaction
   * VerityAI Billing Event
   * VerityAI Onboarding Checklist
   * VerityAI Notification Setting
   * VerityAI Email Delivery Log
   * VerityAI WhatsApp Setup
   * VerityAI Integration Status
3. Build `services/engine.py` as the only main bridge to `verity_ai`.
4. Build workspace permission service.
5. Build onboarding service that creates Account, Workspace, Workspace Member, AI Tenant, AI Configuration, Trial Subscription, Usage Wallet and Checklist.
6. Build assistant setup API and UI.
7. Build widget setup API and UI.
8. Build allowed domain management.
9. Build knowledge management on top of `AI Knowledge Source`.
10. Build leads dashboard from `AI Lead`.
11. Build conversations dashboard from `AI Chat Session`.
12. Build usage dashboard from `AI Usage Log`.
13. Build plan/subscription mapping to engine configuration.
14. Build notification settings and email delivery log.
15. Build basic email notifications for leads, handoff and usage warnings.
16. Build WhatsApp setup UI that writes runtime fields to `AI Configuration`.
17. Build billing MVP with manual payments and subscription status.
18. Build admin/operator dashboard.
19. Add tests for workspace scoping, permissions, onboarding, engine tenant creation, usage aggregation and dashboard access.
20. Run:

* `bench --site farm.test migrate`
* `bench --site farm.test run-tests --app verity_ai`
* `bench --site farm.test run-tests --app verityai_saas`
* `bench build --app verity_ai`
* `bench build --app verityai_saas`

At the end, provide a report showing:

Files created
DocTypes created
Services created
APIs created
Pages created
Engine integration points used
Tests added
Tests run
Known limitations
Next recommended work

Final goal:

`verityai_saas` must make the hardened `verity_ai` engine sellable as a self-service SaaS product without duplicating the engine or exposing technical complexity to customers.

---

## 20. Definition of Done for First Build

The first usable build is complete when:

A customer account can be created.
A workspace can be created.
A workspace creates a linked `AI Tenant`.
A workspace creates a linked `AI Configuration`.
A plan can be assigned.
A subscription can be created.
A usage wallet can be created.
Workspace members are permission-scoped.
Customer can configure assistant identity.
Customer can add allowed domain.
Customer can see embed script.
Customer can create knowledge source.
Customer can view leads.
Customer can view conversations.
Customer can view usage.
Customer can configure email notifications.
Customer can configure basic WhatsApp settings.
Admin can view all workspaces.
Usage is read from `AI Usage Log`.
Plan limits update safe engine config fields.
No customer can access another workspace’s engine records.
No engine secrets are exposed.
`verity_ai` tests still pass.
`verityai_saas` tests pass.

## 21. Final Product Direction

The final product should feel like:

> A business signs up, creates its AI assistant, teaches it about the business, installs the widget, connects WhatsApp/email, captures leads, sees usage, and pays monthly.

The technical foundation is:

```text
verity_ai
= hardened AI engine

verityai_saas
= SaaS product layer

public static website
= marketing and conversion
```

The SaaS app must make the AI engine understandable, valuable and commercially controllable.
