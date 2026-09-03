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
    adapters/              # provider-specific delivery/measurement adapters
    approvals.py           # human review and four-eyes workflows
    delivery.py            # retries, idempotency and delivery results
  infrastructure/
    jobs.py                # queue contracts and job correlation
    secrets.py             # encrypted provider credentials
    audit_log.py           # sensitive administrative action history
    feature_flags.py       # staged rollout and emergency disable controls
```

These are target module boundaries, not a requirement to create every file at once. Each vertical slice should add only the modules it needs.

### AI execution packages

```text
verity_ai/
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

1. Approve entity definitions, permissions and event taxonomy.
2. Add channel/campaign registry, attribution, consent and suppression contracts.
3. Add feature flags, job correlation, cost meters and operator health views.
4. Define partner roles, explicit client grants and append-only commercial ledgers.

### Workstream C — product loop

1. Website Doctor vertical slice.
2. Structured Website Project and redesign preview.
3. Builder, versioning and safe preview.
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

## 22. Development gates and Definition of Done

Before coding begins:

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

## 23. Branch and implementation policy

This branch currently contains planning documentation only. No code, schema, patch, migration or production configuration should be added until the plan and Stage 0 decisions are approved.

`main` remains untouched. When implementation is authorised, matching feature branches should be created in `verity_ai` and `saas_ai_website` only for work those repositories actually own. Changes should merge in small vertical slices behind disabled-by-default feature flags; the existing production journeys remain untouched until each rollout gate passes.
