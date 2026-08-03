# VerityAI SaaS Implementation Audit

Date: 2026-08-03

## Current state

- The Windows `verityai_saas` repository contains only `docs/product map.md`; it does not yet contain a Frappe app package, DocTypes, services, APIs, portal assets, or tests.
- A separate clean `verityai_saas` scaffold exists at `/home/frappe/frappe-bench/apps/verityai_saas` on branch `develop` (initial commit only). It has the standard app metadata and empty package structure, but no product implementation. The working repository will be made self-contained rather than treating the bench copy as source of truth.
- The Frappe bench is at `/home/frappe/frappe-bench`, the intended development site is `farm.test`, and `verity_ai` is present in the bench app list. The MariaDB service was not running during this audit, so database-backed installed-app inspection and baseline tests could not yet execute.
- The installed `verity_ai` worktree has two pre-existing local hardening changes in `api/whatsapp.py` and `engine/tools.py`. They concern webhook duplicate handling and manager-authorized sensitive actions. They will be preserved and `verityai_saas` will not modify the engine worktree.

## Missing product surface

- All 13 required SaaS DocTypes and the VerityAI SaaS module.
- Customer account/workspace/member and workspace-scoped authorization model.
- Workspace onboarding that provisions engine tenant/configuration, subscription, wallet, and checklist records.
- Central, tenant-scoped engine integration service.
- Plan, subscription, usage ledger/wallet synchronization, billing events, and scheduled lifecycle jobs.
- Assistant, widget/domain, knowledge, leads, conversations, usage, billing, email, WhatsApp, team, dashboard, and operator APIs.
- Customer-facing portal routes and product UI.
- Email notification delivery logging and basic notification jobs.
- Cross-tenant, secret-exposure, onboarding, usage, billing, suspension, and operator permission tests.
- Installation, migration, build, and implementation documentation.

## Reused `verity_ai` contracts

All engine access will resolve `VerityAI Workspace -> engine_tenant -> AI Tenant` before reading or writing engine records.

- `AI Tenant`: engine tenant, assistant identity, widget presentation, active flag, and `AI Allowed Domain` child rows.
- `AI Configuration`: one per tenant; safe plan/runtime limits and selected WhatsApp configuration. Password fields are write-only. `system_prompt`, provider credentials, ERPNext credentials, cost internals, and raw secrets will never be returned by SaaS APIs.
- `AI Knowledge Source`: SaaS creates/updates tenant-scoped sources; the existing `on_update` hook rebuilds `AI Knowledge Chunk` rows.
- `AI Knowledge Chunk`: tenant-scoped source status/chunk counts only; chunking/search remains in the engine.
- `AI Lead`: tenant-scoped lead list/detail and safe status updates.
- `AI Chat Session`: tenant-scoped conversation list/detail using document names, never `session_id` alone.
- `AI Usage Log`: authoritative server-side usage input for wallet synchronization and dashboards.
- `AI Monitoring Alert`: tenant-scoped customer health and cross-tenant operator summaries.
- `AI Quotation Request` and `AI Action Approval`: existing approval hooks remain authoritative; no direct sensitive execution path will be added.
- Existing widget assets and endpoints: `/assets/verity_ai/js/widget.js`, `verity_ai.api.chat.get_widget_settings`, and `verity_ai.api.chat.send_message`.
- Existing WhatsApp webhook: `verity_ai.api.whatsapp.webhook`; SaaS only configures it and reports setup state.
- Existing security helpers, monitoring dedupe, usage logging, tool loop, quotation flow, knowledge indexing, webhook dedupe, and retention remain engine-owned.

## Implementation order

1. Add a complete Frappe app scaffold with `required_apps = ["frappe", "verity_ai"]`, install hooks, roles, permission hooks, scheduler hooks, and patches.
2. Add the 13 standard DocTypes with safe Desk permissions and controller-level invariants where needed.
3. Implement workspace permissions and the central engine bridge.
4. Implement transactional onboarding and default plan/subscription/wallet/checklist creation.
5. Implement usage, billing, notifications, WhatsApp, and workspace lifecycle services.
6. Add consistently shaped, workspace-authorized APIs.
7. Add a shared customer portal shell and the requested product routes/pages.
8. Add integration/security tests, then run compile/static checks, migrate, both app test suites, and both builds.
9. Record exact validation results and remaining limitations in `docs/implementation_report.md`.

## Risks and unclear points

- The source repository and bench scaffold are separate directories. The source implementation must be synchronized into the bench before runtime validation; this will be done without overwriting the engine's local changes.
- MariaDB/Redis were not running at audit time. Bench validation depends on starting the existing local services; no database changes will be attempted until the implementation is ready.
- Engine DocTypes are programmatically created rather than exported as standard JSON. SaaS DocTypes will use normal exported JSON while linking to the installed engine schemas.
- `AI Tenant.widget_primary_color` and `widget_header_color` are preset selects, not arbitrary CSS color fields. The portal will expose the supported preset values.
- The engine has no safe customer-editable prompt/tone field. Assistant setup will update identity, business nature, greeting, and limits only; it will not expose or mutate `system_prompt`.
- Full WhatsApp credentials must be accepted write-only. Responses will expose presence/status booleans, never stored values.
- There is no payment gateway in the roadmap MVP. Billing is manual and the upgrade action remains a clearly labelled placeholder.
- Engine usage retention can remove source logs. Immutable SaaS usage transactions and billing snapshots are required before cleanup; the scheduled sync reduces but cannot eliminate loss if it is disabled for longer than the engine retention window.

## Planned files and records

- App metadata: `pyproject.toml`, `README.md`, `license.txt`, package initializers, `hooks.py`, `modules.txt`, and `patches.txt`.
- Standard DocTypes: VerityAI Account, Workspace, Workspace Member, Plan, Subscription, Usage Wallet, Usage Transaction, Billing Event, Onboarding Checklist, Notification Setting, Email Delivery Log, WhatsApp Setup, and Integration Status.
- Services: `engine.py`, `workspace.py`, `permissions.py`, `onboarding.py`, `usage.py`, `billing.py`, `notifications.py`, and `whatsapp.py`.
- APIs: shared response helpers plus `workspace.py`, `onboarding.py`, `assistant.py`, `widget.py`, `knowledge.py`, `leads.py`, `conversations.py`, `usage.py`, `billing.py`, `email.py`, `whatsapp.py`, and `admin.py`.
- Portal: shared `/app` shell and routes for onboarding, dashboard, assistant, widget, knowledge, leads, conversations, usage, billing, email, WhatsApp, and team; shared CSS/JavaScript will render product pages without exposing Desk.
- Lifecycle: install/bootstrap helpers, permission query hooks, scheduled usage sync, notifications, and subscription/trial checks.
- Tests covering creation, engine provisioning, tenant isolation, safe updates, secret handling, usage sync, suspension, email logging, WhatsApp write-only secrets, and operator access.

