# VerityCore AI Big 5 Growth Engine — Implementation Plan

**Status:** Planning and technical design only — no implementation is authorised by this document
**Planning branch:** `feature/big-5-growth-engine`
**Prepared:** 2 September 2026
**Updated:** 3 September 2026

**Current delivery status:** Implementation is in progress on the isolated feature branch; production-facing
capabilities remain disabled.

### Implementation checkpoint

The first control-plane slice now covers the channel and campaign registry, canonical immutable events,
privacy-preserving consent and suppression records, independent feature flags, and an operator Growth view.
Website Doctor, Website Builder, partner access, white-labelling and outbound delivery remain disabled until
their own implementation, security, runtime and acceptance gates pass.

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

The broader growth system has three connected loops:

```text
PRODUCT LOOP
Audit → Redesign → Build → Publish → Powered by Verity → New visitor

PARTNER LOOP
Partner → Client workspaces → Websites/AI/CRM → Recurring client value

CONTENT LOOP
Useful contribution → Profile/content visit → Free tool → User → Case study
```

SEO, referrals, affiliates, templates, integrations, workshops and open-source edge components amplify these loops. They must use shared attribution, consent, approval and reporting infrastructure rather than separate tracking implementations.

### Five-system master architecture

Every proposed capability must belong to one of five cooperating systems. This prevents a marketing idea from
creating its own identity, event, credential, billing or reporting silo.

| System | Owns | Does not own |
|---|---|---|
| Product Engine | Websites, AI experiences, CRM workflows, WhatsApp capabilities, hosting, SEO and customer-facing integrations | Cross-product attribution or partner commercial truth |
| Growth Engine | Acquisition journeys, campaigns, touchpoints, referrals, prospecting, conversion and experiments | Provider credentials or autonomous channel delivery |
| Channel Engine | Channel accounts, conversations, participants, messages, templates, delivery attempts and provider adapters | Lead/opportunity truth or partner permissions |
| Partner Engine | Partner identity, type/tier, agreements, scoped client grants, branding, commissions and payouts | Unrestricted customer data access |
| Governance Engine | Tenant isolation, RBAC, consent, suppression, secrets, audit logs, metering, approvals and attribution rules | Product-specific presentation logic |

The operating rule is:

```text
Build the machine
  -> sell today's proven capabilities while building
  -> progressively automate safe distribution
  -> turn customers, websites and approved partners into measurable distribution
```

The canonical commercial path is shared by every acquisition source:

```text
Visitor -> Prospect -> Lead -> Opportunity -> Customer -> Account/Workspace
```

The source may be Website Doctor, Widget, WhatsApp, a partner, a referral, a campaign or a manual lead, but
all qualified commercial work converges in the existing CRM and carries first-touch, last-touch and conversion
evidence. No initiative may create a parallel prospect or customer database merely for convenience.

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

The roadmap is dependency-led. A downstream feature cannot bypass an unfinished platform or governance gate simply
because its UI can be built quickly.

### Phase 0 — whole-repository readiness audit

Read `verityai_saas`, `verity_ai` and `saas_ai_website` before changing implementation. Produce an existing-versus-new
capability map for Tenant/Account, Customer, Website, Channel, Conversation, Lead, Opportunity, Partner, Referral,
Campaign, Event, Subscription and Usage. Identify duplication, ownership gaps, unsafe secrets and unstable interfaces.

**Gate:** reviewed evidence map, repository ownership decisions and an explicit preserve/refactor/replace decision for
every existing subsystem. No production mutation.

### Phase 1 — shared platform foundation

Establish stable service boundaries for identity, tenant isolation, permissions, secrets, feature flags, immutable
events, attribution, consent, suppression, usage, costs, queues and APIs. Configure limits through plans or operator
settings rather than embedding commercial policy in browser code.

**Gate:** permissions, idempotency, isolation, auditability and disabled-by-default release controls are tested.

### Phase 2 — existing product consolidation

Make Widget, WhatsApp and CRM one coherent commercial flow before adding a second acquisition stack:

```text
Website/WhatsApp conversation -> participant -> lead -> opportunity -> follow-up -> outcome
```

Introduce shared channel, message and delivery contracts only where they remove real duplication. Preserve the proven
WhatsApp webhook and current customer journeys while adding common event names, correlation IDs, attribution and
operator health signals.

**Gate:** Widget and WhatsApp each demonstrate conversation-to-CRM attribution without changing tenant visibility,
delivery reliability or existing entitlements.

### Phase 3 — Website Project platform

Deliver a first-class, workspace-owned Website Project that will eventually aggregate business identity, domain,
template, pages, structured content, brand assets, AI configuration, deployment, analytics, SEO, assistant and CRM
connections. Definitions are versioned, schema validated and free of arbitrary executable code.

**Gate:** ownership, structured definition, version and permission tests pass before an editor or public builder exists.

### Phase 4 — Website Doctor vertical slice

Deliver URL submission, bounded fetch, deterministic checks, PageSpeed adapter, AI summary, report page, lead capture
and event tracking. The audit lifecycle must be reusable by public acquisition, authenticated customers and later
human-reviewed prospect research.

The first stable audit contract accepts a canonical public URL and produces measured performance, technical SEO,
metadata, mobile readiness, accessibility, security headers, content quality, conversion/lead capture, AI readiness,
structured data and page-architecture evidence. Its safe output contains an overall score, category scores, prioritised
problems, severity, recommendations, opportunities, estimated impact, a plain-language explanation and an explicit
redesign next step.

```text
Audit -> consented Prospect/Lead -> Opportunity -> Redesign -> Website Project
```

Deterministic evidence is stored separately from AI interpretation. Reports state what was observed, when it was
measured, what was inferred and which evidence supports each recommendation.

**Gate:** SSRF, redirect, DNS-rebinding and abuse tests pass; reports are useful without hallucinated claims; cost per
audit is measurable.

### Phase 5 — generation, redesign and preview

Convert an audit into a Website Project without modifying the source website. Add a small template catalogue,
schema-validated AI population, structured edits, responsive preview and version history.

**Implemented foundation (September 2026):** the feature-gated customer portal now creates tenant-branded drafts
from three built-in templates or a completed workspace audit, renders a responsive non-interactive preview and saves
edits as immutable validated versions. Platform administrators can upload, activate and deactivate ZIP template
packages through the operator console. Packages are data-only (`template.json` plus an optional README), bounded by
compressed/expanded size and file count, reject traversal, symlinks, encryption, duplicate paths, HTML and executable
content, and retain a private archive checksum. Audit provenance is uniquely linked to the created project. Publishing
remains blocked pending Phase 6. AI-assisted structured population beyond deterministic tenant-safe placeholders is
still outstanding in this phase.

**Gate:** users can generate and revise a complete responsive site without generated scripts, server code or unsafe HTML.

### Phase 6 — publish, hosting and product activation

Deliver immutable builds, validation, Verity subdomains, an isolated deployment worker, logs, health checks and
rollback. Activate the existing Widget, lead capture, CRM and optional WhatsApp journey from the published project.
Add custom-domain proof and SSL only after subdomain publishing is reliable.

**Gate:** audit -> signup -> preview -> publish -> AI conversation -> CRM lead works; repeat deployments are idempotent;
failed releases preserve the last healthy version; rollback is demonstrated in staging.

### Phase 7 — attribution, Powered by Verity and referrals

Add required free-tier badge, signed attribution links, touchpoint resolution, showcase consent and referral-stage
reporting. Reuse the existing delayed reward service; browser events never grant rewards directly.

**Gate:** no self-referral, duplicate conversion, forged link or replayed badge event can grant value.

### Phase 8 — partner platform

Add the common partner hierarchy, verification, agreements, roles, explicit client-workspace grants, scoped portal,
commercial terms, commission ledger, payout reconciliation and support workflow.

**Gate:** cross-partner and ungranted client access tests pass; settled payment events are the only commission source.

### Phase 9 — approved white-label capability

Add versioned Brand Profiles, verified hostnames, validated email identities, preview and approval. Branding permits
allow-listed names, logos, colours, terminology and links—not arbitrary CSS, JavaScript, HTML or headers.

**Gate:** hostname ownership, TLS, partner isolation, brand approval and safe fallback are demonstrated.

### Phase 10 — template and creator marketplace

Add reviewed templates, creators, versions, categories, previews, licences, pricing, installations and attributable
revenue share.

**Gate:** incompatible or unsafe submissions cannot publish; revenue history is immutable and reconcilable.

### Phase 11 — prospect research and human-reviewed outbound

Add CSV/manual prospect import first, duplicate detection, audit reuse, opportunity scoring, draft generation, approval
queue, CRM conversion, suppression checks and outcome tracking. Automate research, never unapproved sending.

**Gate:** every message has source, lawful purpose, tenant, initiator, approval, credential scope, provider outcome and
opt-out evidence; no message sends without explicit human approval.

### Phase 12 — ecosystem and optimization

Add controlled APIs, webhooks, OAuth/API credentials, SDKs, integration registry, developer tooling, SEO monitoring and
evidence-backed experiments only after the underlying workflows are stable.

**Gate:** scoped access, rate limits, replay protection, versioned contracts, operational ownership and measurable
customer value are demonstrated.

### Deferred capability

The Frappe coding agent remains a later, separately approved programme. It must not be a dependency for Website Doctor,
the structured website builder or the core growth platform.

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

## 13. Code-level system structure

The implementation should be split by business capability so public acquisition traffic, customer operations and privileged partner/operator functions do not become one large service.

### SaaS control-plane packages

```text
verityai_saas/
  growth/
    audits.py              # audit orchestration and report lifecycle
    events.py              # canonical growth-event ingestion
    attribution.py         # first/last touch and referral attribution
    campaigns.py           # campaign/channel definitions and budgets
    consent.py             # consent, suppression and retention rules
    prospects.py           # opportunity workflow and human approval
  websites/
    projects.py            # project lifecycle and workspace ownership
    definitions.py         # schema validation and version handling
    templates.py           # template catalogue and compatibility
    builds.py              # build manifest and validation orchestration
    deployments.py         # deployment state machine and rollback
    domains.py             # ownership verification, DNS and SSL state
    showcases.py           # opt-in public showcase workflow
  partnerships/
    partners.py            # partner organisation and lifecycle
    clients.py             # explicit partner-to-workspace relationships
    referrals.py           # attribution connected to existing rewards
    affiliates.py          # commercial affiliate agreements
    commissions.py         # append-only earning and payout ledger
    branding.py            # safe brand profiles and hostname resolution
    templates.py           # creator submissions and revenue attribution
  channels/
    registry.py            # channel definitions and capabilities
    accounts.py            # tenant-owned provider configuration and secret references
    conversations.py       # common conversation and participant identity boundaries
    messages.py            # normalised inbound/outbound message contract
    templates.py           # approved provider/channel message templates
    policies.py            # consent windows, preferences, limits and channel rules
    adapters/              # provider-specific delivery/measurement adapters
    approvals.py           # human review and four-eyes workflows
    delivery.py            # retries, idempotency and delivery results
  infrastructure/
    jobs.py                # queue contracts and job correlation
    secrets.py             # encrypted provider credentials
    audit_log.py           # sensitive administrative action history
    feature_flags.py       # staged rollout and emergency disable controls
    ai_gateway.py          # tenant-aware provider/model/prompt/tool request boundary
```

These are target module boundaries, not a requirement to create every file at once. Each vertical slice should add only the modules it needs.

### AI execution packages

```text
verity_ai/
  ai_core/
    requests.py            # common execution envelope and correlation contract
    providers.py           # provider/model adapters behind stable internal names
    guardrails.py          # purpose, tenant, tool and output constraints
    usage.py               # token, latency, outcome and cost reporting
  growth_tools/
    website_analysis.py    # evidence-based content/conversion analysis
    redesign.py            # structured redesign proposals
    outreach.py            # drafts only; never autonomous delivery
  website_tools/
    generation.py          # populate approved schemas/templates
    editing.py             # validated structured edit operations
    knowledge.py           # approved source reuse
```

Every engine call receives a tenant/workspace context, an entitlement decision, a correlation ID and an explicit tool allow-list. The engine returns proposals/results; SaaS remains authoritative for permissions, lifecycle and publication.

### Canonical relationship and reuse rules

```text
Account
  -> Workspace
      -> Customer / Website Project / Channel Account
      -> Conversation -> Participant -> Message
      -> Lead -> Opportunity -> CRM Activity
      -> Subscription -> Usage Wallet -> Usage Transaction

Partner -> Partner Client Access -> Workspace
Campaign -> Growth Event -> attributed Lead/Account/Subscription
Referral -> attributed conversion -> existing Reward or new Commission Ledger
```

- Existing Account, Workspace, Subscription, Usage, Customer, CRM, conversation and referral records remain authoritative.
- A Channel Account references encrypted provider secrets; it never copies decrypted values into API responses,
  events, logs, campaigns or partner records.
- Website Doctor prospects, widget leads, WhatsApp leads, partner leads and manually sourced leads converge through
  the same deduplication and CRM services.
- AI execution uses one internal request envelope containing tenant, workspace, purpose, provider/model policy,
  prompt/template version, tool allow-list, budget, correlation ID and initiator.
- AI responses return output plus tokens, estimated cost, latency, safety outcome and trace reference. Product modules
  do not call providers directly once the common gateway is available.

### Public website routes

```text
saas_ai_website/
  /website-doctor
  /website-builder/{industry}
  /website-redesign
  /templates/{slug}
  /showcase/{slug}
  /integrations/{slug}
  /resources/{slug}
```

These routes provide discovery and explanation. Mutating requests, durable reports and account-owned state go through authenticated or explicitly public SaaS APIs.

## 14. Growth control-plane records

The earlier product records need the following operating records so growth remains manageable and auditable.

| Record | Core fields | Management purpose |
|---|---|---|
| Growth Channel | code, type, owner, adapter, active, risk class, allowed actions | Central registry for every acquisition/delivery channel. |
| Growth Campaign | channel, objective, audience, start/end, budget/limit, status, owner | Controls campaigns without hard-coded channel logic. |
| Growth Touchpoint | visitor/account/workspace, campaign, source, medium, content, timestamp | Raw attribution evidence. |
| Consent Record | subject, purpose, channel, source, status, captured/withdrawn time | Proves why contact or tracking is permitted. |
| Suppression Record | identity hash, channel, reason, source, expiry | Prevents prohibited or opted-out delivery. |
| Delivery Attempt | campaign, recipient, provider reference, status, error, timestamps | Transparent delivery and retry history. |
| Approval Task | action, payload digest, requester, reviewer, decision, timestamps | Human review for outbound and sensitive partner actions. |
| Partner Organisation | legal/display name, type, status, owner, agreement, billing model | Parent object for agencies, resellers and white-label partners. |
| Partner Membership | partner, user, role, status | Scoped partner access independent of workspace membership. |
| Partner Client Access | partner, workspace, permissions, start/end, granted by | Explicitly controls which clients a partner can manage. |
| Brand Profile | partner, hostname, names/logo/colours/support/legal links, status | Safe white-label configuration with approval and preview. |
| Commercial Agreement | partner, tier, discounts, commission rules, currency, dates | Versioned commercial terms; no historical recalculation. |
| Commission Ledger Entry | partner/affiliate, conversion, amount, status, reversal link | Append-only financial truth for earnings and clawbacks. |
| Payout | beneficiary, included entries, amount, status, provider reference | Reconciled partner/affiliate payout workflow. |
| Template Submission | creator, version, manifest, review state, commercial terms | Controlled creator marketplace input. |
| Integration Listing | provider, capabilities, auth type, review state, docs, owner | Tracks integration lifecycle and distribution ownership. |
| Content Opportunity | channel, source URL, topic, relevance, reach, status, owner | Review queue for comments/content, not an auto-spam engine. |

Sensitive identifiers should be stored only when operationally necessary. Public visitor attribution should use opaque, rotating identifiers rather than email addresses or phone numbers.

## 15. Partner, reseller and white-label management

### Partner types

1. **Referral partner:** introduces a customer and earns the configured one-time reward.
2. **Affiliate:** deliberately markets Verity and can earn commission under an approved agreement.
3. **Agency partner:** manages explicitly assigned client workspaces while Verity remains visible.
4. **Reseller:** owns the customer relationship and receives wholesale pricing/invoicing rules.
5. **White-label partner:** uses an approved branded hostname and presentation layer while Verity operates the platform.
6. **Template/integration partner:** contributes reviewed assets and earns attributable revenue where agreed.

Moving between types is an operator-approved lifecycle change, not a checkbox a partner can grant itself.

### Partner portal

The portal should expose only the partner's scope:

- Client invitations and explicitly assigned workspaces.
- Per-client service status, plan, usage and renewal information allowed by agreement.
- Referral links, conversions and reward/commission state.
- Branded report generation.
- Brand-profile preview and approval state.
- Support requests and operational incidents.
- Statements, invoices and payout history.
- Role management for partner staff.

Partners must never gain access to client conversations, knowledge, leads or credentials merely because they referred or resold the account. Those require explicit client permission grants with expiry and audit history.

### White-label request resolution

```text
Incoming hostname
  → verified hostname mapping
  → active Partner Organisation
  → approved Brand Profile version
  → tenant-neutral themed shell
  → workspace authorisation
  → entitled product feature
```

Brand profiles may configure approved names, logos, colours, email sender identities, support links, legal links and optional powered-by rules. They may not inject JavaScript, arbitrary CSS, HTML, headers or infrastructure configuration.

Custom email domains require DNS verification and provider validation. Custom application domains require ownership verification and TLS before activation. Secret keys remain encrypted server-side and are never copied into partner-visible responses.

### Commercial transparency

- Store the exact agreement version applied to every conversion.
- Calculate commissions from settled payment events, not browser callbacks.
- Delay eligibility through the existing refund/reversal window.
- Record reversals as new ledger entries; do not rewrite history.
- Show pending, eligible, paid and reversed totals separately.
- Require operator approval and reconciliation for payouts.

## 16. Referral and affiliate design

The existing account referral code and delayed credit reward remain the first version. Extend them through an attribution service rather than adding competing referral logic.

```text
Signed link/campaign code
  → anonymous touchpoint
  → account signup
  → workspace creation
  → product activation
  → settled payment
  → eligibility window
  → credit reward or commission ledger
```

Required controls:

- Signed, expiring campaign/referral parameters.
- First-touch and last-touch values stored independently.
- Self-referral checks across account ownership and verified contact identifiers.
- Duplicate-device/IP signals used for review, not automatic identity claims.
- Idempotent conversion processing.
- Refund, chargeback and fraud reversals.
- Operator-visible reason codes for every rejected or reversed reward.
- Configurable caps by campaign, partner, account and period.

Referral credits and affiliate cash commissions are different products and must use separate rule types and ledgers.

## 17. Channel map and governance

| Channel | Delivery mode | System management | Security and transparency |
|---|---|---|---|
| Verity website and landing pages | Owned/public | CMS or reviewed repository content; campaign links | CSP, secure forms, consent, release review and analytics disclosure |
| Website Doctor/free tools | Product-led/public | Audit jobs, quotas, report lifecycle | SSRF protection, rate limits, cost meter, evidence timestamps |
| Website widget | Customer-owned embed | Workspace configuration and versioned loader | Origin allow-list, tenant binding, signed configuration and abuse limits |
| WhatsApp | Customer messaging | Existing workspace setup, Meta webhook and conversation services | Per-tenant credentials, webhook signatures, consent/window enforcement and delivery logs |
| CRM | Owned operational system | Existing lead, opportunity and activity records | Role permissions, assignment history, export controls and audit trail |
| Transactional/marketing email | Provider adapter | Separate purpose, templates, campaigns and suppression | Verified sender, unsubscribe, bounce/complaint handling and rate limits |
| Powered by Verity badge | Distributed product surface | Signed links and badge events | No hidden tracking; minimal identifiers; replay-resistant events |
| Referrals and affiliates | Partner-distributed | Attribution plus reward/commission ledgers | Signed codes, settlement gates, anti-self-referral and visible status |
| Social comments/community | Human-operated | Content Opportunity review queue | No automated posting; record source and owner; platform-policy compliance |
| Direct outbound | Human-approved | Prospect, approval, delivery attempt and CRM activity | Lawful source, suppression check, explicit approval, rate caps and opt-out |
| Workshops and downloadable resources | Human/owned | Content assets, registration campaign and follow-up purpose | Consent-specific follow-up and retention period |
| Showcase/case studies | Public/owned | Opt-in publication workflow | Customer approval, takedown and asset rights record |
| Template marketplace | Creator-distributed | Submission, review, versions and commercial attribution | Static/schema validation, malware checks, no executable server code |
| Integration ecosystem | Provider/developer | Listing, credential scope, health and version lifecycle | OAuth/secret isolation, least privilege, webhook signatures and revocation |
| Open-source edge projects | Developer/community | Separate repositories, releases and disclosure policy | No proprietary secrets/core service code; signed releases and vulnerability process |
| Hosting/domain partnerships | Partner/API | Agreement, provisioning adapter and reconciliation | Scoped credentials, idempotent provisioning, ownership proof and audit logs |

All channels use a canonical naming convention such as `source`, `medium`, `campaign`, `content`, `term` and optional signed `partner/referral` identifiers. Raw events are immutable; corrected attribution is stored as a derived decision with its reason.

### Common channel contract

| Object | Responsibility | Existing reuse / implementation rule |
|---|---|---|
| Channel | Describes a delivery/acquisition capability and its operating risk | Extend the implemented Growth Channel registry; do not store tenant secrets here |
| Channel Account | Binds one workspace to one provider identity/configuration | Adapt existing WhatsApp, email and widget setup records behind a common service; migrate only after parity tests |
| Conversation | Cross-channel interaction lifecycle | Reuse the engine's existing chat session as the initial source; introduce a new record only if the audit proves it necessary |
| Participant | Tenant-scoped external/internal identity | Store only necessary identifiers; encrypt or hash based on operational need |
| Message | Normalised content direction/type/status with provider reference | Preserve provider payloads only under bounded retention and access controls |
| Message Template | Versioned, approved business-initiated content | Provider approval and locale remain explicit |
| Communication Preference | Purpose- and channel-specific permission | Resolve against Consent and Suppression before delivery |
| Delivery Attempt | Append-only provider attempt/result | Carries initiator, purpose, tenant, credential reference, approval and correlation ID |

The common contract is an adapter boundary, not an instruction to rewrite working WhatsApp code. Consolidation begins
with shared interfaces and events, runs parity tests, then moves one channel at a time. Customer messages must continue
working throughout the transition.

## 18. API and event contracts

Exact URLs can follow the repository's existing API conventions, but responsibilities should be stable.

### Public, heavily rate-limited

- Start an audit and poll its safe public status.
- Read an opaque/unlisted public audit report.
- Record a validated badge click.
- Resolve public template/showcase metadata.
- Capture consented lead/resource requests.

### Authenticated workspace

- Convert an audit into a Website Project.
- Create/read/update project definitions and request AI edits.
- Request preview/build/publish/rollback operations.
- Configure domains and verify status.
- Manage showcase consent and Verity badge preferences within entitlement rules.

### Partner-scoped

- Manage partner staff and client invitations.
- Read only explicitly granted client summaries.
- View attribution, commissions, statements and payouts.
- Submit brand profiles, templates and integrations for review.

### Operator-only

- Approve partners, agreements, brand profiles, payouts and marketplace submissions.
- Configure channels, limits, feature flags and kill switches.
- Review outbound drafts and delivery incidents.
- Inspect immutable audit trails and operational health.

### Canonical events

Every asynchronous command emits a correlation ID and state events such as:

```text
audit.requested / completed / failed
project.created / generated / edited
build.requested / validated / failed
deployment.started / healthy / rolled_back / failed
domain.verification_requested / verified / ssl_active
assistant.activated / first_conversation / first_lead
campaign.touchpoint_recorded
referral.signup / activated / settled / rejected
commission.pending / eligible / paid / reversed
partner.client_access_granted / revoked
brand_profile.submitted / approved / rejected
outbound.drafted / approved / sent / replied / opted_out
```

Consumers must be idempotent. Event payloads carry object identifiers and minimal metadata, not copied secrets or entire customer records.

## 19. Infrastructure and operational design

### Runtime separation

- **Web/API processes:** validate requests, authorise and enqueue work; no long crawls or deployments.
- **Audit workers:** isolated outbound network policy, strict fetch budgets and no access to internal networks.
- **AI workers:** tenant-aware requests with spend and tool limits.
- **Build workers:** deterministic rendering from validated manifests; no production credentials.
- **Deployment worker:** narrowly scoped publishing credentials and tenant paths.
- **Scheduled workers:** monitoring, reward eligibility, reports and retention cleanup.

Separate queue classes and concurrency budgets prevent free audits from starving WhatsApp replies, widget chat or billing work.

### Storage

- Relational records for ownership, lifecycle, attribution and financial truth.
- Private object/file storage for source documents and screenshots.
- Immutable/versioned build artifacts for deployment and rollback.
- Public CDN/object storage only for approved published assets.
- Short-lived cache for audit status, rate limits and resolved public metadata.

### Secrets and providers

- One encrypted credential record per provider/account/environment.
- Never expose secret values after saving; show configuration/health state only.
- Rotate and revoke credentials without editing code.
- Separate test and production credentials and endpoints.
- Log who changed credentials without logging the credential value.
- Provider adapters return normalised status/error codes for transparent support.

### Observability

Dashboards and alerts should cover queue age, error rate, external-provider latency, AI spend, audit cost, deployment success, domain/SSL failures, webhook health, delivery failures, abuse throttling and attribution processing lag. Every user-visible failure should have a safe reference ID operators can correlate with logs.

## 20. Parallel promotion of current features

Development of the new platform must not pause go-to-market activity. Run a separate, mostly manual operating track using proven current capabilities.

### Widget campaign

**Promise:** Add a trained AI assistant and lead capture to an existing website.

Deliver immediately:

- Installation walkthrough and short demonstration video.
- Live demo page and a copyable implementation checklist.
- Before/after response and lead-capture examples.
- Agency-facing offer to install the widget for client websites.
- Campaign links into signup/onboarding with source attribution.

Measure visit → demo → signup → widget configured → first conversation → first lead.

### WhatsApp AI campaign

**Promise:** Turn inbound WhatsApp enquiries into immediate, knowledge-grounded replies and captured opportunities.

Deliver immediately:

- Publish the existing complete setup guide through the operator-managed download flow.
- Produce a short proof video showing a real inbound message and AI reply, with all credentials hidden.
- Run live demonstrations for SMEs, agencies and business associations.
- Create troubleshooting and integration content from the proven setup journey.
- Offer guided setup as a conversion service without weakening tenant credential isolation.

Measure guide download → setup started → Meta verified → inbound received → AI reply → lead captured.

### CRM campaign

**Promise:** Keep leads, opportunities, activities and AI conversations in one operating flow.

Deliver immediately:

- Demonstrate Widget/WhatsApp conversation → lead → opportunity → follow-up.
- Publish use-case content for service businesses and agencies.
- Use the current CRM internally for every Website Doctor lead and partner prospect.
- Prepare a simple downloadable lead follow-up checklist linked to Verity signup.

Measure lead captured → assigned → contacted → opportunity → won/lost, segmented by source.

### Weekly operating rhythm

1. Select a small number of relevant social/community opportunities.
2. Publish one useful demonstration, guide, makeover or customer story.
3. Run one partner/customer demo or workshop.
4. Review current-feature activation funnels and support failures.
5. Feed recurring objections into documentation and the product backlog.

Social replies remain human-written or human-approved. The system can identify and rank opportunities, but it should not impersonate people or post automatically.

### Parallel 90-day execution stream

This is an operating backlog, not permission for autonomous posting or messaging. A named human owns every asset,
community interaction, follow-up and result in CRM.

| Window | Product evidence | Distribution work | Required measurement |
|---|---|---|---|
| Days 1-15 | Verify Widget, WhatsApp and CRM demo workspaces; document the complete conversation-to-lead path | Publish one short proof for each product, refresh setup guides, prepare tracked landing links | Demo view, guide download, signup, setup started, first conversation |
| Days 16-30 | Resolve recurring setup friction and add missing lifecycle events without redesigning working flows | Run two guided SME/agency demonstrations; publish one practical troubleshooting article and one lead-follow-up checklist | Setup completion, first AI reply, first lead, demo-to-trial conversion |
| Days 31-45 | Complete channel/CRM attribution parity and operator funnel reporting | Launch one tightly scoped Widget campaign and one WhatsApp campaign; begin relevant human community participation | First/last touch, qualified leads, cost/time per lead, support failures |
| Days 46-60 | Establish Website Project contracts and demonstrate a structured preview internally | Publish a build-in-public update and recruit a small design-partner cohort through existing CRM | Design-partner applications, activation, objections, preview usefulness |
| Days 61-75 | Pilot Website Doctor internally only after security fixtures pass | Create evidence-based before/after material from approved sites; run one partner workshop | Audit completion, useful-report rating, audit-to-meeting, measured audit cost |
| Days 76-90 | Run the first gated acquisition journey and review release evidence | Publish approved customer evidence, formalise early agency/referral conversations, repeat the best-performing proof | Lead-to-opportunity, opportunity-to-paid, source revenue, retention signal |

Weekly review separates facts from assumptions:

1. Product health: delivery failures, setup abandonment, response quality and support load.
2. Funnel: reach -> visit -> demo/guide -> signup -> activation -> lead -> opportunity -> paid.
3. Economics: staff time, provider spend, AI credits, acquisition cost and attributable revenue.
4. Learning: objections, missing proof, lost opportunities and the smallest product correction.
5. Decision: continue, revise or stop each campaign; create no vanity activity without an owner and conversion path.

## 21. Consolidated execution sequence

Four workstreams run together, with production protected by feature flags and approvals.

### Workstream A — current-product growth, starts immediately

- Widget, WhatsApp and CRM proof assets.
- Useful commenting/community participation.
- Workshops and guided demonstrations.
- Current referral programme and tracked campaign links.
- Manual CRM discipline and weekly funnel review.

This workstream does not wait for new feature code.

### Workstream B — shared technical foundation

1. Complete the whole-repository readiness audit and canonical existing-versus-new entity map.
2. Consolidate Widget, WhatsApp and CRM behind stable channel, conversation, lead and event boundaries.
3. Finish attribution decisions, job correlation, cost meters and operator health views on the implemented registry,
   consent, suppression, event and feature-flag foundation.
4. Define the tenant-aware AI gateway and migrate direct provider calls gradually after contract tests.
5. Define partner roles, explicit client grants and append-only commercial ledgers.

### Workstream C — product loop

1. Structured Website Project ownership and definition contracts.
2. Website Doctor vertical slice using the shared audit lifecycle.
3. Redesign, builder, versioning and safe preview.
4. Free Verity-subdomain deployment and rollback.
5. Existing Widget/WhatsApp/CRM activation from the website project.
6. Badge, showcase and referral attribution.
7. Scheduled SEO monitoring and advanced paid tools.

### Workstream D — partner and scale loop

1. Agency/referral partner onboarding and portal.
2. Explicit client-workspace management grants.
3. Commercial agreements, commissions and payout reconciliation.
4. Approved brand profiles and white-label hostnames.
5. Template creator and integration submission workflows.
6. Human-reviewed outbound opportunity workflow.
7. Hosting/domain partnerships and open-source edge ecosystem.

White-labeling should follow a stable multi-client product and deployment flow. It should not delay the Website Doctor or free builder, but its tenant hierarchy, hostname and permission requirements must be accounted for in the foundation.

## 22. Required implementation specification

No initiative enters coding with only a feature name. Its design record must contain every section below, with
"Not applicable" justified explicitly rather than silently omitted.

| Section | Required answer |
|---|---|
| Purpose and business outcome | Which customer problem and measurable commercial result justify the work? |
| User types | Which customer, operator, partner, agency or system actors participate? |
| Core functionality | What genuinely works end to end, beyond screens and placeholders? |
| Existing reuse | Which current records/services remain authoritative, and what duplication is prohibited? |
| Data model | DocTypes/entities, relationships, ownership, lifecycle, retention and immutability rules |
| Workflows | Happy path, state transitions, cancellation, retry, expiry and recovery |
| Permissions | Read/create/change/approve/delete/export authority for every actor and tenant boundary |
| Channels | Website, Widget, WhatsApp, email, API or partner adapters used and their policy constraints |
| Events and attribution | Canonical events, idempotency, correlation, first/last touch and conversion decision rules |
| Security and privacy | Secrets, isolation, consent, suppression, abuse, validation, logging and data minimisation |
| Billing and usage | Who pays, which entitlement applies, what is metered and how cost is reconciled |
| Administration | Configuration, approval, health, incident handling, kill switch and audit visibility |
| Partner management | Agreement, scope, client grants, commission and branding implications where relevant |
| Analytics | Operational health, funnel, customer value, unit economics and source revenue |
| Failure handling | Safe user error, operator reference, retry ownership, escalation and rollback |
| API contracts | Public/authenticated/partner/operator interfaces, versions, limits and webhook behavior |
| UX | Complete customer, partner and operator journeys across desktop/mobile and accessibility states |
| Acceptance criteria | Executable proof required before the feature can leave its disabled rollout stage |

Every specification ends with dependencies, migration/rollback steps, test fixtures, responsible owner and explicit
non-goals. This prevents impressive screens from being mistaken for commercially operable product capability.

## 23. Development gates and Definition of Done

Before each new product phase begins:

- Product owner approves the first release slice and free limits.
- Architecture review approves record ownership and repository boundaries.
- Security review approves crawler, generated-content and deployment threat models.
- Commercial review approves partner/referral/affiliate distinctions.
- Operations approves hosting, support and incident ownership.

For every implemented slice, Done means:

- Server-side permissions and entitlements are enforced.
- Tenant-isolation and abuse tests pass.
- Events, cost meters and safe failure references exist.
- Operator management and kill switch exist where operational risk requires them.
- Documentation and support runbook are updated.
- Staging end-to-end acceptance passes.
- Rollback or disable procedure is demonstrated.
- No regression in Widget, WhatsApp, CRM, billing or current portal journeys.

## 24. Branch and implementation policy

This branch contains the growth control plane and the completed Phase 3 Website Project foundation. Phase 4 now has
an internal Website Doctor evidence slice plus an unlisted, evidence-based report and explicit-consent CRM hand-off:
opaque audit access, bounded and IP-pinned retrieval, deterministic checks, an optional PageSpeed adapter, safe report
rendering, tenant-scoped lead deduplication, suppression checks, cost/error telemetry and operator visibility. Public
Website Doctor remains disabled by default until the server suite and staging acceptance gates pass. Website publishing, partner, white-label and
outbound capabilities also remain disabled. Each next slice requires its implementation specification and phase gate
before code is added.

`main` remains untouched. Matching feature branches should be created in `verity_ai` and `saas_ai_website` only for work
those repositories actually own. Changes merge in small vertical slices behind disabled-by-default feature flags; the
existing production journeys remain untouched until each rollout gate passes.
