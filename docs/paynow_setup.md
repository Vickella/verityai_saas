# Paynow setup

VerityAI uses Paynow's hosted web checkout. Card and mobile-money details remain on Paynow; VerityAI stores only transaction references, signed status data, and audit records.

## 1. Create the Paynow integration

In Paynow, create a **3rd Party Shopping Cart or Link** integration and keep it in test mode until the callback and return flow have been verified. Copy the Integration ID and Integration Key.

Paynow's current protocol documentation:

- [Initiate a transaction](https://developers.paynow.co.zw/docs/paynow/initiate_transaction/)
- [Generating and validating hashes](https://developers.paynow.co.zw/docs/paynow/generating_hash/)
- [Status updates](https://developers.paynow.co.zw/docs/paynow/status_update/)
- [Polling transaction status](https://developers.paynow.co.zw/docs/paynow/polling_status/)

## 2. Configure the Frappe site

Store credentials in site configuration, never in repository files or browser JavaScript:

```bash
cd /home/frappe/frappe-bench
bench --site farm.test set-config paynow_integration_id "YOUR_INTEGRATION_ID"
bench --site farm.test set-config paynow_integration_key "YOUR_INTEGRATION_KEY"
bench --site farm.test set-config host_name "https://your-public-domain.example"
bench --site farm.test clear-cache
```

`host_name` must be a public HTTPS origin that Paynow can reach. The app generates its result callback and customer return URL from this value.

## 3. Create paid plans

Create active `VerityAI Plan` records with:

- a unique plan code other than `TRIAL`;
- currency `USD`;
- a positive monthly price and, optionally, annual price;
- token and feature limits.

The customer billing page lists these plans and redirects authorized billing users to Paynow checkout.

## 4. Verify in Paynow test mode

1. Start checkout from `/verityai/billing`.
2. Complete or fake the payment in Paynow test mode.
3. Confirm a `VerityAI Billing Event` is marked `Completed` and contains a Paynow reference.
4. Confirm the subscription plan, period, wallet allowance, engine token limit, and tenant active state were updated.
5. Confirm cancelled or tampered transactions do not activate the plan.

Only request that Paynow set the integration live after these checks pass on the public HTTPS site.

## Security behavior

- Every outbound message is signed with SHA-512 using the site-only integration key.
- Initiation responses and callbacks must have valid signatures.
- Checkout and poll URLs must use HTTPS and an approved Paynow hostname.
- Server-side HTTP redirects are disabled.
- A callback never activates a plan directly; the server independently polls Paynow and verifies that signed response first.
- The local reference and amount must match the immutable billing event.
- Repeated successful callbacks are idempotent.
- Customers cannot create or complete manual billing events.