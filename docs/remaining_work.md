# Remaining live validation

All planned application code is implemented. The items below require merchant credentials, public infrastructure, third-party accounts, production data, or independent review and therefore remain for live validation.

## Payment rollout

- Configure Paynow test credentials and a public HTTPS `host_name`.
- Exercise successful checkout, delayed callback, cancellation, dispute, operator refund, reconciliation export, invoice, receipt, reminder, and grace-period recovery in Paynow test mode.
- Request Paynow live mode and run a low-value production transaction.
- Enable recurring/tokenized Paynow billing only after Paynow merchant approval and a dedicated payment-security review; the current hosted-checkout flow intentionally does not store card or payment tokens.

## Channel and integration validation

- Send through the default Frappe outgoing account and a real workspace custom-SMTP account; confirm SPF, DKIM, DMARC, reply-to, retry, and inbox placement.
- Validate Meta WhatsApp webhook verification, signatures, replay handling, connection test, and a real inbound/outbound AI conversation.
- Install the public widget on an allowed HTTPS domain and confirm branding behavior for plans with and without removal rights.
- Validate a customer-supplied AI provider and embedding model, including queued semantic indexing and provider-failure fallback.
- Validate ERPNext quotation creation, approval, submission, and delivery against the target ERPNext site.
- Exercise scoped API tokens from an external client using the `X-VerityAI-API-Key` header, then revoke and rotate them.

## Production operations and assurance

- Install declared OCR system packages (`tesseract-ocr`, `poppler-utils`) and verify scanned PDF/image extraction with representative documents.
- Run production migration, asset build, backup and restore; configure workers, scheduler, Redis, MariaDB backups, TLS, monitoring, and log retention.
- Run authenticated browser smoke tests for signup verification, onboarding, Paynow return, team management, integrations, and operator controls on the deployed site.
- Run production-sized load/concurrency tests and a disaster-recovery exercise.
- Complete an independent security review before allowing customer-supplied provider credentials or any future recurring-payment flow in production.