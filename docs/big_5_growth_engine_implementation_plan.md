# VerityCore AI Big 5 Growth Engine — Implementation Plan

**Status:** Planning only — no implementation is authorised by this document  
**Planning branch:** `feature/big-5-growth-engine`  
**Prepared:** 2 September 2026

## 1. Executive decision

Build the Big 5 as one connected acquisition and expansion system, not five independent products:

```text
Discover → Audit → Redesign → Build → Publish → Engage → Refer → Discover
```

The recommended first complete release is:

```text
Website Doctor
  → useful free report
  → AI redesign starter project
  → structured website builder
  → Verity subdomain publishing
  → Powered by Verity distribution
  → Verity AI lead capture
```

SEO and human-reviewed outbound feed prospects into this journey. Paid upgrades begin when a customer receives recurring business value: custom domains, increased limits, monitoring, automation, advanced AI and business integrations.

## 2. What already exists and should be reused

The current repositories already provide important foundations:

| Capability | Current owner | Reuse decision |
|---|---|---|
| Accounts, workspaces and tenant ownership | `verityai_saas` | Use as the ownership boundary for every private project, audit and deployment. |
| Plans, subscriptions and feature entitlements | `verityai_saas` | Extend with website, audit, SEO and outbound limits. Do not create a second billing system. |
| Usage wallets and AI credit ledger | `verityai_saas` | Charge metered AI actions through the existing credit system. |
| Referral codes, delayed rewards and abuse controls | `verityai_saas` | Extend attribution stages instead of replacing the referral system. |
| CRM, leads and activities | `verityai_saas` | Convert audit leads and approved outbound prospects into the current CRM. |
| Workspace analytics and reporting | `verityai_saas` | Add growth events and funnel aggregations. |
| Knowledge ingestion | SaaS + `verity_ai` | Reuse uploaded business material for both website content and assistant knowledge, with explicit user consent. |
| Tenant-aware AI execution and tools | `verity_ai` | Add narrowly scoped website-analysis and structured-editing tools here. |
| Web widget, WhatsApp and lead capture | SaaS + `verity_ai` | Offer as the engagement layer on published websites. |
| Public marketing website | `saas_ai_website` | Host acquisition pages and direct visitors into the SaaS public tool flow. |

## 3. What is genuinely new

The following product systems are not currently implemented as complete capabilities:

- Public Website Doctor and durable audit reports.
- Safe, bounded website crawling and PageSpeed collection.
- Structured Website Project, page, section, theme and asset definitions.
- Versioned templates and deterministic site rendering.
- AI redesign and structured AI editing.
- Preview, build, publish, deployment, rollback and hosting lifecycle.
- Verity-managed subdomains and custom-domain verification/SSL lifecycle.
- Powered by Verity badge impression/click attribution.
- Public showcase and case-study publishing.
- Unified Growth Event funnel attribution.
- Scheduled SEO monitoring and controlled automated recommendations/fixes.
- Human-reviewed growth-prospect analysis and outbound workflow.

## 4. Product and repository boundaries

### `verityai_saas` — control plane

Owns users, workspaces, projects, subscriptions, entitlements, audit records, templates, builds, deployments, domains, referrals, showcases, prospects, approval workflow, analytics and operator controls.

### `verity_ai` — execution engine

Owns AI analysis, content generation, structured edit proposals, knowledge retrieval and tool execution. It must not receive unrestricted shell, DNS, reverse-proxy or production deployment access.

### `saas_ai_website` — discovery surface

Owns indexed marketing and education pages. Website Doctor results and authenticated builder state remain in SaaS so there is one source of truth.

### Deployment worker — isolated execution boundary

Begin as a narrowly scoped background worker invoked by SaaS. It accepts validated build manifests, writes only to assigned tenant paths and reports status/logs back. If deployment volume or isolation requirements grow, extract it into a separate service later.

## 5. Core records

Names below are conceptual and must be confirmed against Frappe naming conventions before schema implementation.

| Record | Purpose | Important rules |
|---|---|---|
| Website Audit | Requested URL, snapshots, scores, issues and recommendations | Public audits use opaque IDs; private data must never appear in public reports. |
| Website Project | Workspace-owned website and its lifecycle | Every query and mutation enforces workspace membership. |
| Website Definition | Versioned structured pages, sections, content, theme and settings | JSON schema validated; no unrestricted executable code. |
| Website Template | Versioned renderer-compatible template definition | Publishing stays pinned to a tested version until explicitly upgraded. |
| Website Asset | Images, logos and documents | Validate type/size; separate public assets from private source documents. |
| Website Build | Immutable render artifact and validation results | Contains schema, accessibility, link and security checks. |
| Website Deployment | Environment, version, status, logs and rollback target | Idempotent operations with complete audit history. |
| Website Domain | Hostname, ownership proof, DNS and SSL state | No activation before ownership verification. |
| Website Showcase | Opt-in public listing linked to a published project | Separate approval and unpublish controls. |
| Growth Event | First-party acquisition/activation/referral/revenue event | Minimal metadata, retention policy and consent-aware visitor identity. |
| Growth Prospect | Imported or operator-created outreach opportunity | Human approval and suppression state required before contact. |

The existing referral records remain authoritative for financial/credit rewards. Growth Event records add attribution; they do not grant rewards directly.

## 6. Free and paid boundaries

The boundary is recurring value and operational cost, not merely feature visibility.

| Growth engine | Free experience | Paid expansion |
|---|---|---|
| Website Doctor | One useful basic audit with core scores, priority issues and actions | Multi-page audits, saved history, scheduled monitoring, competitor comparison and advanced recommendations |
| Website Builder | One website, limited pages/templates/AI edits, Verity subdomain, basic hosting and required badge | Custom domain, remove branding, more sites/pages/AI, premium templates, analytics, backups and advanced integrations |
| Powered by Verity | Badge, referral link and normal referral rewards | Higher usage/limits may vary by plan; the distribution mechanism itself stays free |
| SEO & AI Discovery | Basic score, selected free tools and useful public guides | Scheduled audits, keyword/competitor monitoring, automated fixes and reporting |
| AI-assisted outbound | Small operator-controlled demonstration allowance | Higher analysis volume, bulk import, automation, team workflow and CRM sequences |

Suggested initial free safeguards, configurable by operators rather than hard-coded:

- Anonymous audit rate limits by IP, domain and time window.
- Email/account gate for saved reports and redesign generation.
- One free website project per account.
- A small page allowance and monthly AI-edit allowance.
- Verity subdomain only; Powered by Verity badge required.
- Fixed storage, bandwidth and deployment quotas.
- Five prospect analyses as a product demonstration, with no autonomous sending.

Exact limits should be configured through plan entitlements after cost measurement; they should not be embedded in UI code.

## 7. Delivery plan and approval gates

### Stage 0 — foundation and product contracts

Plan and approve:

- Definition JSON schema and supported section catalogue.
- Entitlement names, cost meters and operator-configurable limits.
- Ownership model, public/private visibility and retention rules.
- Growth event taxonomy and attribution rules.
- Feature flags and kill switches.
- Queue names, retry policy and idempotency keys.
- Environment separation for local, staging and production.

**Gate:** architecture/security review and approved schemas. No public release.

### Stage 1 — Website Doctor vertical slice

Deliver URL submission, bounded fetch, deterministic checks, PageSpeed adapter, AI summary, report page, lead capture and event tracking.

The deterministic evidence must be stored separately from AI interpretation. A report must clearly show what was observed, when it was measured and which recommendation was inferred.

**Gate:** SSRF and abuse tests pass; reports are useful without hallucinated claims; cost per audit is measurable.

### Stage 2 — structured Website Builder

Deliver Website Project, onboarding inputs, a small template catalogue, schema-validated AI population, preview and version history. Start with common small-business sites rather than a general-purpose visual editor.

**Gate:** users can create and revise a complete responsive site without generated executable code.

### Stage 3 — free publish and hosting

Deliver immutable builds, validation, Verity subdomains, safe deployment worker, logs, health checks, rollback and operator controls. Add custom-domain proof and SSL only after subdomain publishing is reliable.

**Gate:** repeated deploys are idempotent; failed releases do not replace the last healthy version; rollback is demonstrated in staging.

### Stage 4 — Doctor-to-redesign conversion and Verity AI

Turn an audit into a new Website Project without modifying the source website. Map approved uploads into both site content and the existing knowledge pipeline. Add widget/lead capture activation to the published site.

**Gate:** one complete journey works: audit → signup → preview → publish → AI conversation → CRM lead.

### Stage 5 — Powered by Verity, referrals and showcase

Add required free-tier badge, signed attribution links, badge events, opt-in showcase, sharing assets and referral-stage reporting. Reuse the existing delayed reward service for credit grants.

**Gate:** no self-referral, duplicate conversion or badge-event replay can grant credits.

### Stage 6 — SEO and discovery

Publish useful industry, template, integration and showcase pages with canonical metadata, structured data, sitemaps and real examples. Add paid scheduled monitoring only after one-time audit quality is established.

**Gate:** every indexed page has distinct user value and a measurable product action; no mass-produced thin pages.

### Stage 7 — human-reviewed outbound

Add CSV/manual prospect import first, duplicate detection, audit reuse, opportunity scoring, draft generation, review queue, CRM conversion, suppression lists and outcome tracking. Discovery automation comes after compliance and unit economics are proven.

**Gate:** no message can be sent without explicit human approval; source, legal basis, opt-out and audit history are recorded.

### Deferred capability

The Frappe coding agent remains a later, separately approved programme. It must not be a dependency for the Website Doctor or structured website builder.

## 8. Critical security controls

### Website analysis

- Permit only HTTP/HTTPS and normalise URLs before use.
- Resolve DNS and block loopback, link-local, private, metadata and internal network ranges before every fetch and redirect.
- Defend against DNS rebinding; restrict ports, redirects, response size and crawl depth.
- Use strict timeouts, a declared crawler identity and per-domain concurrency limits.
- Never execute fetched JavaScript inside the application network boundary.

### Generated sites

- Validate all definitions against an allow-listed schema.
- Sanitize rich text and URLs; enforce CSP and safe outbound links.
- Prohibit arbitrary scripts, server code, shell commands and path selection in the first release.
- Scan uploads and keep original private documents inaccessible from public deployments.

### Deployment and domains

- Use per-tenant paths and credentials with least privilege.
- Reject traversal, symlinks and shell interpolation.
- Require domain ownership proof before routing or certificate issuance.
- Log every deploy, domain change, approval and rollback.

### Growth and privacy

- Minimise visitor identifiers and define retention/deletion rules.
- Use signed attribution parameters and server-side conversion checks.
- Maintain suppression and opt-out records for outbound activity.

## 9. Test strategy

Implementation is not considered complete until the relevant gate is demonstrated.

1. **Unit tests:** scoring, schema validation, entitlement limits, URL handling, state transitions, attribution and reward eligibility.
2. **Security tests:** SSRF payloads, redirects, rebinding, oversized responses, malicious HTML/assets, XSS, traversal, tenant leakage and permission bypass.
3. **Contract tests:** SaaS-to-engine AI tools, PageSpeed adapter, deployment worker and DNS/SSL adapters with recorded fixtures.
4. **Integration tests:** anonymous audit, account conversion, project creation, credits, publish, rollback, domain verification, widget activation and CRM lead capture.
5. **Render tests:** responsive breakpoints, accessibility, broken links, metadata, sitemap and representative browser snapshots.
6. **Billing tests:** free limits, upgrades/downgrades, renewals, exhausted allowances and paid feature enforcement on both UI and server.
7. **Abuse tests:** repeated audits, duplicate referrals, fake badge events, repeated deploys, prospect duplicates and suppression enforcement.
8. **Staging acceptance:** complete end-to-end journeys with production-like queues, DNS and isolated hosting.
9. **Pilot:** operator-only, then selected tenants, then a percentage rollout behind feature flags.

## 10. Metrics and unit economics

Track the connected funnel rather than vanity totals:

- Audit start/completion and useful-report rate.
- Audit-to-account and account-to-redesign conversion.
- Time to first preview and first publish.
- Published-site activation, AI activation and first lead.
- Badge impressions, verified clicks and attributed signups.
- Free-to-paid conversion by trigger: domain, limits, monitoring or integrations.
- Cost per audit, redesign, AI edit, build, deployment and hosted free site.
- Retention, project activity and monitored-site renewal.
- Prospect approval, outreach response and conversion rates.

Every metered operation needs a cost event before free limits are expanded.

## 11. Recommended release slices

Avoid launching disconnected infrastructure. Use these demonstrable slices:

1. **Acquisition proof:** safe audit + useful report + captured lead.
2. **Magic moment:** audit + AI redesign preview.
3. **Activation proof:** account + edit + free subdomain publish.
4. **Business-value proof:** published site + Verity AI + captured CRM lead.
5. **Distribution proof:** badge/showcase/referral attribution.
6. **Recurring-revenue proof:** custom domain or monitoring upgrade.
7. **Scale proof:** SEO acquisition and approved outbound feed the same funnel.

## 12. Decisions required before implementation

- Final free project, page, storage, bandwidth and AI-edit allowances.
- Initial templates and industries.
- Verity subdomain format and reserved-name policy.
- Hosting topology and deployment-worker boundary.
- Custom-domain/SSL provider and operational ownership.
- Whether anonymous full reports are public, unlisted or email-gated.
- Data retention for fetched website content, screenshots and visitor attribution.
- Badge incentive and rules for removal on paid tiers.
- Initial outbound jurisdictions, approved sources and compliance process.

## 13. Branch and implementation policy

This branch currently contains planning documentation only. No code, schema, patch, migration or production configuration should be added until the plan and Stage 0 decisions are approved.

When implementation is authorised, matching feature branches should be created in `verity_ai` and `saas_ai_website` only for work those repositories actually own. Changes should merge in small vertical slices behind disabled-by-default feature flags; the existing production journeys remain untouched until each rollout gate passes.
