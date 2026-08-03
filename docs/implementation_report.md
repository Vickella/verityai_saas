# VerityAI SaaS Implementation Report

Date: 2026-08-03

## Implemented

The repository now contains a complete Frappe app scaffold for the customer-facing SaaS layer around `verity_ai`. It provisions customer accounts and workspaces, links every workspace to one engine tenant, creates engine configuration, assigns a trial plan, creates a subscription and usage wallet, tracks onboarding, exposes workspace-authorized APIs, and supplies a product-styled portal.

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
- `services/engine.py`: the sole main bridge to tenant, configuration, domains, widget embed code, knowledge, leads, conversations, usage, alerts, and plan limits.
- `services/onboarding.py`: transactional account/workspace/member/tenant/configuration/subscription/wallet/checklist provisioning.
- `services/workspace.py`: workspace dashboard and team summaries.
- `services/usage.py`: idempotent engine usage-log to SaaS transaction synchronization and wallet totals.
- `services/billing.py`: plan assignment, manual billing events with usage snapshots, suspension, and trial/subscription expiry.
- `services/notifications.py`: Frappe email delivery, new-lead/handoff hooks, usage warnings, daily summaries, and delivery logs.
- `services/whatsapp.py`: button/alert/full-AI setup and write-only engine credential updates.

## APIs created

All public SaaS methods return the required `{success, data, error, code}` envelope and enforce workspace access before customer-scoped work.

- Workspace and team
- Onboarding
- Assistant
- Widget and allowed domains
- Knowledge
- Leads
- Conversations
- Usage
- Billing
- Email
- WhatsApp
- Admin/operator dashboard

Engine secrets and `AI Configuration.system_prompt` are absent from response field lists. WhatsApp token/secret responses contain presence booleans only.

## Pages created

The shared SaaS portal shell provides:

- `/app` and `/app/dashboard`
- `/app/onboarding`
- `/app/assistant`
- `/app/widget`
- `/app/knowledge`
- `/app/leads`
- `/app/conversations`
- `/app/usage`
- `/app/billing`
- `/app/email`
- `/app/whatsapp`
- `/app/team`
- `/app/admin` for operators

The portal uses product language and shared responsive CSS/JavaScript. The widget page displays embed code for `/assets/verity_ai/js/widget.js`; no SaaS widget runtime was created.

## Engine integration points

- `AI Tenant` for assistant identity, widget settings, domains, and active/suspended state.
- `AI Configuration` for safe limits and write-only WhatsApp setup.
- `AI Knowledge Source` and the existing engine save hook for chunk rebuilding.
- `AI Knowledge Chunk` for scoped chunk counts only.
- `AI Lead`, `AI Chat Session`, `AI Usage Log`, and `AI Monitoring Alert` for scoped dashboards.
- Existing `verity_ai.api.chat` endpoints and widget assets for customer websites.
- Existing `verity_ai.api.whatsapp.webhook` as the displayed Meta callback.
- Existing engine approval hooks remain untouched.

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

## Validation results

Passed:

- Windows Python compilation: 51 Python files compiled without syntax errors.
- Frappe bench-environment import validation: all service and API modules imported successfully.
- Frappe bench-environment `compileall`: passed.
- `node --check verityai_saas/public/js/portal.js`: passed.
- Trailing whitespace scan: passed.
- `bench build --app verity_ai`: passed. Redis asset-cache update warnings were emitted because Redis is stopped.
- `bench build --app verityai_saas`: passed. The same Redis warnings were emitted.

Blocked by local service state:

- `bench --site farm.test migrate`
- `bench --site farm.test run-tests --app verity_ai`
- `bench --site farm.test run-tests --app verityai_saas`

MariaDB is stopped and the current WSL user cannot start it without a sudo password. Bench database access fails with PyMySQL error 2003 (`Can't connect to MySQL server on 127.0.0.1`). Redis is also stopped. The commands were attempted but could not reach migration or test execution. No pass result is claimed for them.

## Known limitations

- The payment gateway, recurring invoices, automatic receipts, and paid upgrade checkout remain future work; billing is manual and stores immutable usage snapshots.
- Wallet state is synchronized from engine logs, while hard pre-call enforcement currently uses the engine's `monthly_token_limit`. A separate optional prepaid/subscription gate in `verity_ai` would require an explicit engine extension point.
- Full WhatsApp setup stores engine credentials safely and reports configuration presence, but does not perform a live Meta Graph connection test.
- File extraction, OCR, website crawling, and semantic/vector search are not duplicated here; manual knowledge text uses the existing engine hook and chunker.
- Quote approval and AI action approval remain engine-owned. A customer-friendly approval page can be added later without bypassing those hooks.
- `/app` is also Frappe's conventional Desk prefix. Route precedence must be verified after migration on the target Frappe version; if Desk takes precedence, deploy the same portal under a non-reserved route and redirect customer roles there.
- Runtime install/migration behavior and database-backed tests still require the local MariaDB/Redis services.

## Manual setup and next commands

1. Start MariaDB and Redis in WSL with an account that has service privileges.
2. Ensure the source tree is synchronized or linked at `/home/frappe/frappe-bench/apps/verityai_saas`.
3. If the app is not yet installed in the site database, run `bench --site farm.test install-app verityai_saas`.
4. Run:

```bash
cd /home/frappe/frappe-bench
bench --site farm.test migrate
bench --site farm.test run-tests --app verity_ai
bench --site farm.test run-tests --app verityai_saas
bench build --app verity_ai
bench build --app verityai_saas
```

5. Configure the AI provider credentials through an operator-only engine workflow; they are intentionally not exposed to customer pages.
6. Verify `/app` route precedence, a real allowed domain/widget exchange, email delivery, and Meta webhook credentials before production launch.

