# VerityAI SaaS Implementation Report

Date: 2026-08-04

## Implemented

The repository now contains a complete Frappe app scaffold for the customer-facing SaaS layer around `verity_ai`. It provides Frappe-backed customer signup, then provisions customer accounts and workspaces after verified login, links every workspace to one engine tenant, creates engine configuration, assigns a trial plan, creates a subscription and usage wallet, tracks onboarding, exposes workspace-authorized APIs, supplies a product-styled portal, provides tenant-safe quotation approvals through the existing engine hook, and adds Paynow hosted checkout with signed server-side confirmation.

The implementation does not duplicate the engine's model loop, public chat API, widget runtime, WhatsApp webhook, knowledge indexing/search, lead capture, quotation execution, action approval, usage logging, monitoring dedupe, redaction helpers, or retention.

## DocTypes created

DocTypes are installed programmatically by `verityai_saas.setup_doctypes.install`, matching the existing engine's programmatic schema approach:

1. VerityAI Account
2. VerityAI Workspace
3. VerityAI Workspace Member
4. VerityAI Plan
5. VerityAI Subscription
6. VerityAI Usage Wallet
7. VerityAI Usage Transaction
8. VerityAI Billing Event
9. VerityAI Onboarding Checklist
10. VerityAI Notification Setting
11. VerityAI Email Delivery Log
12. VerityAI WhatsApp Setup
13. VerityAI Integration Status

The installer also creates portal-only customer roles, operator/admin roles, the module definition, and a default `TRIAL` plan. The main relationship is `VerityAI Workspace.engine_tenant -> AI Tenant.name`.

## Services created

- `services/permissions.py`: login, operator detection, workspace membership/role/permission checks, and Frappe query conditions.
- `services/engine.py`: the sole main bridge to tenant, configuration, domains, widget embed code, knowledge, leads, conversations, usage, alerts, quotation requests, approvals, and plan limits.
- `services/onboarding.py`: transactional account/workspace/member/tenant/configuration/subscription/wallet/checklist provisioning.
- `services/workspace.py`: workspace dashboard plus invitation, reactivation, role/permission updates, protected-owner rules, removal, and plan-limited team management.
- `services/user_roles.py`: portal-role assignment and synchronization across all active workspace memberships.
- `services/health.py`: tenant-scoped health state, service status, alert counts, and filterable safe alert history.
- `services/usage.py`: idempotent engine usage-log to SaaS transaction synchronization and wallet totals.
- `services/billing.py`: validated plan assignment, billing periods, immutable operator audit events/manual payments/top-ups, wallet updates, suspension, and trial/subscription expiry.
- `services/paynow.py`: SHA-512 signed checkout initiation, strict Paynow URL validation, callback verification, independent polling, amount/reference checks, and idempotent plan activation.
- `services/notifications.py`: Frappe email delivery, new-lead/handoff/quotation/provider hooks, usage warnings, daily summaries, and delivery logs.
- `services/whatsapp.py`: button/alert/full-AI setup and write-only engine credential updates.

## APIs created

All public SaaS methods return the required `{success, data, error, code}` envelope and enforce workspace access before customer-scoped work.

- Customer signup through Frappe's built-in verification and rate controls
- Workspace and complete team lifecycle management
- Onboarding
- Assistant
- Widget and allowed domains
- Knowledge
- Leads
- Conversations
- Health and monitoring alerts
- Usage
- Billing and Paynow hosted checkout
- Email
- WhatsApp
- Quotation requests and approval
- Interactive admin/operator operations console with bulk workspace rollups, plan/status controls, manual payments, and top-ups

Engine secrets and `AI Configuration.system_prompt` are absent from response field lists. WhatsApp token/secret responses contain presence booleans only.

## Pages created

The SaaS website provides a guest signup page at `/verityai/signup`. After verification and login, the shared customer portal shell provides:

- `/verityai` and `/verityai/dashboard`
- `/verityai/health`
- `/verityai/onboarding`
- `/verityai/assistant`
- `/verityai/widget`
- `/verityai/knowledge`
- `/verityai/leads`
- `/verityai/conversations`
- `/verityai/quotes`
- `/verityai/usage`
- `/verityai/billing`
- `/verityai/email`
- `/verityai/whatsapp`
- `/verityai/team` for invitations, role changes, explicit permissions, removal, and reactivation
- `/verityai/admin` for operators, with high-usage/trial/setup alerts and auditable billing controls

The portal uses product language and shared responsive CSS/JavaScript. The widget page displays embed code for `/assets/verity_ai/js/widget.js`; no SaaS widget runtime was created.

## Engine integration points

- `AI Tenant` for assistant identity, widget settings, domains, and active/suspended state.
- `AI Configuration` for safe limits and write-only WhatsApp setup.
- `AI Knowledge Source` and the existing engine save hook for chunk rebuilding.
- `AI Knowledge Chunk` for scoped chunk counts only.
- `AI Lead`, `AI Chat Session`, `AI Usage Log`, and `AI Monitoring Alert` for scoped dashboards.
- Existing `verity_ai.api.chat` endpoints and widget assets for customer websites.
- Existing `verity_ai.api.whatsapp.webhook` as the displayed Meta callback.
- `AI Quotation Request` for tenant-scoped review; setting a pending request to `Approved` delegates submission and delivery to the existing engine `on_update` hook.

## Tests added

`verityai_saas/tests/test_saas.py` covers:

- account, workspace, member, tenant, configuration, subscription, wallet, and checklist creation;
- owner access and cross-workspace denial;
- safe assistant/widget updates;
- domain normalization and scoping;
- tenant-scoped knowledge, leads, conversations, and usage;
- idempotent usage transaction creation;
- plan limit mapping and suspension;
- email delivery logging;
- write-only WhatsApp secrets;
- customer denial and administrator access for operator functions.

`verityai_saas/tests/test_quotes.py` covers safe-field responses, tenant isolation, permission denial, and delegation through the authoritative engine document hook.

`verityai_saas/tests/test_health.py` covers tenant-safe alert aggregation, status/severity filters, derived workspace health, and unauthorized access denial.

`verityai_saas/tests/test_signup.py` covers guest page access, input validation, Frappe signup delegation, and the sanitized post-login onboarding redirect.

`verityai_saas/tests/test_team.py` covers plan limits, role synchronization, explicit permissions, owner protection, removal/reactivation, and unauthorized API denial.

`verityai_saas/tests/test_notifications.py` covers complete notification settings, email validation and recipient normalization, permission denial, quotation/provider event filtering, and duplicate-delivery prevention.

`verityai_saas/tests/test_paynow.py` covers the documented Paynow hash vector, signed checkout initiation, tamper rejection, independent callback polling, idempotent activation, refund suspension, monthly wallet rollover, operator-only manual billing, and immutable top-up ledger updates.

`verityai_saas/tests/test_admin_billing.py` covers bulk operator rollups, customer denial, plan/status engine synchronization, immutable operator audit events, strict manual-payment validation, top-ups, and operator page access.

## Validation results

Validated on the local WSL Frappe site `farm.test` on 2026-08-04:

- Both Python app trees compile successfully.
- `portal.js`, `admin.js`, and the engine widget pass `node --check`.
- Both repositories pass `git diff --check` (Git reports only expected Windows line-ending notices).
- `bench --site farm.test migrate` completed, applying engine patch `v0_0_22` and SaaS patch `v0_4`. The pre-existing Frappe S3 backup `lib.GEN_EMAIL` warnings remained non-fatal and are unrelated to these apps.
- Complete `verityai_saas` suite: **82/82 passed**.
- Complete `verity_ai` suite: **40/40 passed**.
- Production assets for `verity_ai` and `verityai_saas` built successfully with Frappe's installed esbuild runner.

Coverage includes entitlement and quota enforcement, account/workspace capacity, plan CRUD, Paynow signing/callback/polling/idempotency, invoices/receipts/refunds/reminders/grace recovery, CRM assignment/notes/handoffs/exports/funnels, safe ingestion/crawling, analytics/reports, custom SMTP, scoped API credentials, BYO provider and ERPNext secret handling, widget branding, engine entitlement hooks, semantic retrieval, webhook replay, rate limits, approval controls, monitoring, and retention.

## Implemented safeguards and boundaries

- All tenant operations resolve through a workspace-to-engine-tenant link and enforce membership or operator scope.
- Mutations are POST-only; public customer API tokens are high-entropy, SHA-256 hashed, scoped, revocable, rate-limited, and never shown after creation.
- Provider, ERPNext, WhatsApp, SMTP, and Paynow secrets are encrypted or held in site configuration and never returned by status APIs.
- Public URL and SMTP host validation rejects credentials, private/local/reserved destinations, unsafe ports, and redirect-based SSRF; network connections revalidate destinations.
- Knowledge ingestion is queued and bounded. Semantic embeddings and hybrid retrieval remain engine-owned, with lexical fallback when a provider fails.
- Recurring/tokenized Paynow payments are intentionally not enabled without merchant approval and a dedicated security review.
- The customer portal remains at `/verityai`; `/app` remains reserved for Frappe Desk.

## Live validation still required

Credentialed and infrastructure-dependent checks are tracked in `docs/remaining_work.md`: Paynow test/live transactions, real SMTP/Meta/widget/provider/ERPNext/API exercises, OCR system-package installation, production migration/backup/restore, authenticated browser smoke tests, production-sized load testing, disaster recovery, and independent security review.