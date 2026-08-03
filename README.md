# VerityAI SaaS

Customer onboarding, workspaces, plans, billing, dashboards, and channel setup for the `verity_ai` engine.

The app requires Frappe and `verity_ai`. It deliberately does not implement chat processing, provider calls, the widget runtime, WhatsApp webhook routing, knowledge search, quotation execution, monitoring dedupe, or engine retention.

## Customer portal

Customer and team users sign in through `/login` and use `/verityai`. Frappe's `/app` route remains reserved for Desk users. Customer roles have no Desk access.
