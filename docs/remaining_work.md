# Remaining work

The core SaaS MVP phases in the product map are implemented. Remaining work is ordered by launch risk and customer value.

## P0 — Production pilot readiness

1. **Paynow merchant rollout**
   - Configure real test credentials and a public HTTPS `host_name`.
   - Complete Paynow test-mode checkout, callback, cancellation, dispute, and refund exercises.
   - Request live mode and run a low-value production transaction.

2. **Live channel validation**
   - Configure and verify Frappe outgoing email and reply-to behavior.
   - Validate the Meta WhatsApp webhook, access token, app secret, signature verification, and a real inbound/outbound conversation.
   - Verify the public widget on an allowed production domain.
   - Verify ERPNext quotation creation, submission, and delivery through the engine-owned approval hook.

3. **Deployment operations**
   - Run a complete production-site migration and backup.
   - Configure workers, scheduler, Redis, MariaDB backups, TLS, error monitoring, and log retention.
   - Run the customer/operator smoke test and both automated app suites after deployment.

## P1 — Commercial enforcement and operational control

1. **Central entitlement gate**
   - Enforce subscription state, empty wallet, and channel eligibility before every engine call.
   - Enforce `monthly_web_conversations`, `monthly_whatsapp_messages`, and `monthly_email_sends`.
   - Enforce plan feature flags for email, WhatsApp modes, quotation workflow, API access, custom SMTP, ERPNext, and bring-your-own-provider keys.
   - Keep these checks server-side through an explicit `verity_ai` extension point.

2. **Workspace and plan limits**
   - Enforce `max_workspaces` during additional workspace creation.
   - Enforce `max_assistants` if multiple assistants are introduced.
   - Add customer-facing additional-workspace creation and account-profile management.
   - Add operator plan create/edit/archive controls outside Frappe Desk.

3. **Channel health operations**
   - Add a live Meta Graph connection test and webhook health check for WhatsApp.
   - Add operator actions to acknowledge and resolve monitoring alerts.
   - Add retry actions for failed email delivery and failed channel setup.

## P2 — Billing and customer workflow depth

1. **Billing automation**
   - Generate invoices and receipts.
   - Add payment reminders, grace-period notifications, retry/recovery flows, and customer-downloadable documents.
   - Add Paynow recurring/tokenized payments only after merchant approval and a dedicated security review.
   - Add operator-driven refund initiation and reconciliation exports.

2. **Lead and conversation operations**
   - Add portal filters, search, pagination, status updates, assignment, notes, and CSV export.
   - Add human-handoff ownership and resolution workflows.
   - Add conversion/funnel reporting.

3. **Knowledge ingestion**
   - Add safe file upload, extraction, OCR, website crawling, URL refresh, and ingestion status.
   - Add semantic/vector search only through the engine-owned knowledge architecture.

4. **Analytics and reporting**
   - Add time-series usage, cost, lead, conversation, and channel charts.
   - Add scheduled operator reports and tenant-level exports.

## P3 — Scale and assurance

- Replace remaining high-volume synchronous operations with queued jobs where appropriate.
- Add browser end-to-end coverage for signup, onboarding, Paynow return, team management, and operator controls.
- Add load, concurrency, webhook replay, rate-limit, dependency-failure, and disaster-recovery tests.
- Complete an external security review before enabling recurring payments or customer-supplied provider credentials.