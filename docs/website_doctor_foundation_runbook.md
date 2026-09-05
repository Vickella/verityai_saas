# Website Doctor foundation runbook

## Scope

This release is the internal evidence foundation for Website Doctor. It accepts one public page, retrieves it through
the pinned-IP safety boundary, stores immutable measured evidence, calculates deterministic scores, optionally adds
PageSpeed measurements and exposes operational status in the Growth operator console.

It does not publish a public marketing page, capture leads, invoke AI summaries, crawl an entire site or generate a
redesign. Those remain later Phase 4/5 gates.

## Deploy

```bash
cd ~/frappe-bench
bench --site saasai.veritypack.cloud migrate
bench --site saasai.veritypack.cloud clear-cache
bench restart
```

The migration creates `VerityAI Website Audit` and `VerityAI Website Audit Evidence`. The public release control stays
off after migration.

## Optional PageSpeed configuration

The deterministic audit works without PageSpeed. To enable the official PageSpeed Insights v5 adapter, store its key
in site configuration rather than source code:

```bash
bench --site saasai.veritypack.cloud set-config verityai_pagespeed_api_key YOUR_KEY
bench --site saasai.veritypack.cloud set-config verityai_pagespeed_cost_usd 0
bench restart
```

Set `verityai_pagespeed_cost_usd` to the internally allocated cost per provider call if applicable. The operator table
reports this value without exposing the key or provider payload.

## Internal acceptance

1. Open **Operator console -> Growth -> Release controls**, enable **Internal Website Doctor**, and save.
2. Open **Website Doctor operations**.
3. Enter a normal public HTTPS website and select **Run internal audit**.
4. Confirm the audit moves from **Requested** to **Running**, then **Completed**.
5. Confirm an overall score, fetch time, provider time and provider cost appear.
6. Confirm failed targets show only a safe reference, not an internal exception or submitted URL path.
7. Run the test module:

```bash
bench --site saasai.veritypack.cloud run-tests \
  --app verityai_saas \
  --module verityai_saas.tests.test_website_audits
```

## Security acceptance

The automated suite must demonstrate rejection of loopback/private/mixed DNS answers, embedded credentials, unsafe
ports, oversized or compressed responses, non-HTML content, redirect loops, HTTPS downgrade redirects and redirects
that resolve to a non-public address. Every network connection uses an IP returned by the validated resolution; the
HTTP client does not perform a second hostname lookup.

The fetch body and raw PageSpeed response are never stored. Audit query strings and fragments are removed before the
request is persisted. Public status requires the one-time opaque token returned when the audit is created; only its
SHA-256 digest is stored.

## Disable and rollback

Turn off **Public Website Doctor** under Growth release controls to stop new anonymous and customer requests. Turn off
**Internal Website Doctor** to stop new operator pilots. Existing queued work can be stopped by pausing the `long` queue
workers while preserving audit evidence for investigation.

Application rollback does not require deleting audit tables. Revert the application commit, run `migrate`, clear cache
and restart. Existing audit and evidence records remain inert and can be retained or removed later under an approved
data-retention operation.
