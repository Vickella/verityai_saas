# VerityAI SaaS

Customer onboarding, workspaces, plans, billing, dashboards, and channel setup for the `verity_ai` engine.

The app requires Frappe and `verity_ai`. It deliberately does not implement chat processing, provider calls, the widget runtime, WhatsApp webhook routing, knowledge search, quotation execution, monitoring dedupe, or engine retention.

## Customer signup

New customers register at `/verityai/signup`. Registration uses Frappe's configured verification email and redirects verified users to a prefilled workspace onboarding form.

## Customer portal

Customer and team users sign in through `/login` and use `/verityai`. Frappe's `/app` route remains reserved for Desk users. Customer roles have no Desk access. Workspace owners and authorized team members can review and approve tenant-scoped quotation requests at `/verityai/quotes`. The read-only `/verityai/health` dashboard summarizes workspace services and tenant-scoped monitoring alerts. Workspace owners and admins manage invitations, roles, explicit permissions, removals, and reactivation at `/verityai/team`. The integrations console at `/verityai/integrations` provides plan-gated, write-only configuration for AI providers, semantic embeddings, ERPNext, custom SMTP, and scoped API credentials.
## Paynow billing

Paid plans use Paynow hosted checkout with signed initiation, callback verification, independent server polling, and idempotent plan activation. Credentials stay in Frappe site configuration. See [Paynow setup](docs/paynow_setup.md).

## Remaining work

The core MVP is implemented. Production-pilot tasks and post-MVP features are tracked in [Remaining work](docs/remaining_work.md).
