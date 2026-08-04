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

Passed:

- Windows Python compilation: 74 Python files compiled without syntax errors.
- Frappe bench-environment import validation: all service and API modules imported successfully.
- Frappe bench-environment `compileall`: passed.
- `node --check` for `portal.js` and `signup.js`: passed.
- Trailing whitespace scan: passed.
- `bench --site farm.test install-app verityai_saas`: installed; the first attempt exposed and led to a fix for the cyclic Account/Workspace Link creation order.
- `bench --site farm.test migrate`: passed. The pre-existing Frappe S3 backup `lib.GEN_EMAIL` warnings remained non-fatal.
- `bench --site farm.test run-tests --app verity_ai`: passed, 35 tests.
- `bench --site farm.test run-tests --app verityai_saas`: passed, 46 tests, including operator billing controls, Paynow security/activation, notification management, guest signup, team lifecycle and plan limits, website routes, portal roles, health/alert scoping, quotation scoping, and approval delegation.
- Sequential SaaS and engine regression runs passed without fixture leakage: 46/46 and 35/35.
- `bench build --app verity_ai`: passed.
- `bench build --app verityai_saas`: passed.

MariaDB plus the bench Redis cache and queue were started for validation. The complete mandated migration, regression, SaaS test, and build sequence now passes.

## Known limitations

- Signup relies on Frappe's system signup settings and outgoing email. Workspace and tenant resources are deliberately created only after the verified user signs in.
- Paynow hosted checkout is implemented, but live merchant credentials and a public HTTPS callback must be verified in Paynow test mode before launch. Recurring tokenized payments, automatic invoices, and receipts remain future work.
- Wallet state is synchronized from engine logs, while hard pre-call enforcement currently uses the engine's `monthly_token_limit`. A separate optional prepaid/subscription gate in `verity_ai` would require an explicit engine extension point.
- Plan fields for workspace/assistant counts, channel-specific monthly volumes, and feature entitlements are not yet enforced consistently across every API; these are the highest-priority remaining code milestone.
- Full WhatsApp setup stores engine credentials safely and reports configuration presence, but does not perform a live Meta Graph connection test.
- File extraction, OCR, website crawling, and semantic/vector search are not duplicated here; manual knowledge text uses the existing engine hook and chunker.
- Quote execution remains engine-owned. The customer page approves only tenant-scoped pending requests and deliberately triggers the existing engine hook; a live pilot must verify ERPNext quotation submission and the configured delivery channel.
- Monitoring alert lifecycle and deduplication remain engine-owned; the customer health dashboard is intentionally read-only.
- The customer portal uses the validated `/verityai` route because `/app` is reserved by Frappe Desk. Website users receive portal-only roles with `desk_access = 0`.

## Manual setup and next commands

1. Keep the source tree synchronized or linked at `/home/frappe/frappe-bench/apps/verityai_saas`.
2. Configure AI provider credentials through an operator-only engine workflow; they are intentionally absent from customer pages.
3. Configure Paynow using `docs/paynow_setup.md`, then verify test-mode checkout on the public HTTPS host.
4. Verify a real allowed-domain/widget exchange, outbound email, and Meta webhook credentials before production launch.
5. Re-run migration and both suites after future schema or engine integration changes.
6. Track prioritized remaining work in docs/remaining_work.md.
