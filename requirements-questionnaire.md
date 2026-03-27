# Audit Log Analyzer — Requirements Questionnaire

Fill in your answers inside the code fences after each question.

---

## Priority Decision Points

These 8 questions have the highest architectural impact. Answer these first.

**P1. Should threat detection be real-time (sub-minute), near-real-time (1–15 min), or batch (hourly/daily)?**
```
Given a lot of the things we'll look for are trend based, I think near real time is fine.
```

**P2. Where do logs currently live? (e.g., streaming to S3/Azure/GCS/Splunk/Datadog, REST API polling, manual CSV/JSON exports)**
```
I would like to have the option for a user to specify which data store they are using and provide us appropriate authentication to that source. I do NOT want to support REST or GraphQL polling. Given the amount of data, it will be impossible to get an accurate picture within the rate limits of GitHub.
```

**P3. Where will the tool be deployed? (on-prem, inside the customer's own cloud account, or SaaS)**
```
I plan to open source this project so I would like it fairly portable. Docker/k8s/etc.
```

**P4. What storage backend should processed events land in? (e.g., PostgreSQL, Elasticsearch, ClickHouse, DuckDB, BigQuery, Snowflake, S3+Athena)**
```
I'm good with whatever tools work best as long as they are proper open source projects.
```

**P5. Are `git.*` events (push/fetch/clone — streaming-only) required? Are `api.request` events (opt-in, streaming-only, very high volume) required?**
```
We should support any event that is streamed.
```

**P6. Must the tool support multiple GHEC enterprises from day one, or is single-enterprise sufficient for v1?**
```
I think one instance of the analyzer per one GHEC enterprise is appropriate for now. We might add multiple support later since it's just looking at another blob or bucket.
```

**P7. Is a behavioral baseline / "normal behavior" model required, or are explicit rules sufficient for v1? Is ML acceptable, or must all rules be fully explainable?**
```
rules, ML, and AI are acceptable. I'd like for it to be an option to turn on any combination of them. I.e. if a user just wants to try it out, they can just use the base rules. If they like it, they can look more into the ML/AL components 
```

**P8. Which compliance frameworks must the tool's outputs explicitly support? (e.g., SOC 2 Type II, ISO 27001, PCI DSS, HIPAA, FedRAMP, NIST 800-53, CIS Controls)**
```
None right now
```

---

## A. Data Ingestion & Sources

**A1. Which streaming destination(s) are in use and must be supported in v1?**
```
Let's start with S3 and Azure Blob.
```

> **Implementation note (v0.1.0):** S3 and Azure Blob polling was chosen for v1 to maximize reliability and simplify initial deployment. Webhook-based push ingestion is planned for a future release.

**A2. Is audit log streaming already configured, or does setting it up fall within scope of this project?**
```
It will need to be set up before this project will work. We should direct the users to GitHub documentation to set that piece up.
```

**A3. What is the expected daily and monthly event volume? (order of magnitude is fine)**
```
Anywhere from hundreds or thousands of events for smaller customers to millions of events for the largest enterprises
```

**A4. How far back does historical data need to go? Is backfill required, or only from a specific start date?**
```
The data we have available is highly dependent on when audit log streaming was enabled. We should analyze any available data in the storage bucket/blob
```

**A5. What is the deduplication strategy given at-least-once delivery from streaming? Is `_document_id` the primary dedup key?**
```
I believe github manages dedupes so the blob should only have 1 event for each activity
```

**A6. For REST API polling: what polling interval is acceptable given GitHub's rate limits?**
```
None. We do not want to support polling.
```

**A7. For object storage (S3/GCS/Blob) ingestion: does the tool need to track its own read cursor, or is there an existing notification mechanism (e.g., SQS, Event Grid)?**
```
Assume all we have is read access to the bucket/blob.
```

**A8. Are there network or firewall constraints on where the ingestion component can run?**
```
Assume all we have is read access to the bucket or blob
```

**A9. What GitHub credentials are available for ingestion? (fine-grained PAT, GitHub App, OAuth App — and what scopes)**
```
We should not talk to GitHub directly. Our task is to provide reporting and metrics on audit log events
```

---

## B. Scope & Event Coverage

**B1. Which event namespaces are in scope for v1? List must-haves and nice-to-haves if possible.**
```
all audit log events are in scope
```

**B2. For security use cases — are the following required in v1?**
- `secret_scanning_push_protection` (push protection bypass)
- `protected_branch` (branch protection changes, rejected refs)
- `business.recovery_code_*` / `org.recovery_code_*` (SSO bypass attempts)
- `public_key.verification_failure` (SSH key failures)
- `personal_access_token` (PAT lifecycle events)
```
all audit log events are in scope
```

**B3. For compliance use cases — are the following required in v1?**
- `repo` (visibility changes, branch protection)
- `org` (policy changes, member management)
- `business` (enterprise-level settings)
- `audit_log_streaming` (changes to the streaming config itself)
```
all audit log events are in scope
```

**B4. Should `copilot` events (seat assignments, policy changes) be in scope? (relevant for cost tracking and compliance)**
```
all audit log events are in scope
```

**B5. Should `packages` and `migration` events be in scope? (both are potential data-exfiltration vectors)**
```
all audit log events are in scope
```

**B6. How should unknown or future event namespaces be handled? (drop silently / store raw / flag for review)**
```
The audit log is well defined so I don't anticipate any events that are not documented.
```

---

## C. Reporting & Metrics

**C1. What specific business metrics are required? List what you need.**
Candidates: MAU/WAU by org, license seat utilization, repo creation/deletion rate, Actions run volume + success/failure rate, Copilot seat utilization, codespace hours, PAT counts by expiry tier, webhook/app counts.
```
those sound like a great place to start
```

**C2. What time granularities are needed for reports? (daily, weekly, monthly, rolling 30/60/90 days, fiscal-calendar-aligned)**
```
those sound like a great place to start
```

**C3. What output formats are required? (web dashboard, PDF, CSV, JSON, Slack message, email digest)**
```
web dashboards, csv/json table exports
```

**C4. Do different personas need role-scoped views? (e.g., security sees threats, finance sees cost metrics, compliance sees policy history)**
```
Eventually but not right now. We aren't going to show individual metrics or anything so it shouldn't be a big deal right now
```

**C5. Is a self-service query interface needed, or are all reports pre-defined?**
```
query interface needed. Should be based on a standard pattern sql/kql/etc., and have a visual query builder
```

**C6. Are scheduled/automated report deliveries required (e.g., weekly email to a distribution list), or always pull-on-demand?**
```
Eventually but not for the mvp/v1
```

**C7. Is drill-down required — click a metric and see the raw events that contributed to it?**
```
yes
```

---

## D. Bad Actor / Threat Detection

**D1. What threat scenarios are explicitly in scope for v1? Check all that apply and add others.**
Candidates:
- Insider data exfiltration (mass cloning, repo visibility changes to public)
- Account compromise (recovery code use, credential stuffing indicators)
- Privilege escalation (unauthorized team/role changes, collaborator additions)
- Secret leakage (push protection bypass with `publicly_leaked` or `multi_repo` flags)
- Supply-chain attack (unauthorized webhook or GitHub App installs)
- Branch protection bypass (`protected_branch.policy_override`)
- PAT abuse (high-volume API calls from a single token)
- Impossible travel (same token from geographically distant IPs in a short window)
- Off-hours or geo-anomalous access
```
those all sound good
```

**D2. What is the acceptable false positive rate? (High-sensitivity rules that generate noise erode trust quickly.)**
```
sub 1% false positive rate. If we have something that might have a higher rate, we need to mark it as a medium or low confidence report and provide some guidance about why there could be variablility in the data.
```

**D3. What are the alert notification and escalation paths when a threat is detected?**
Candidates: Slack, PagerDuty, email (SMTP), Microsoft Teams, OpsGenie, SIEM ticket, Jira issue, ServiceNow incident.
```
No alerts for mvp/v1
```

**D4. Is there a severity classification system? (e.g., Critical / High / Medium / Low / Info) What defines each level?**
```
We need to build one as part of this project. This should be tuneable in the app so analysts and admins can change which event types fall into what classification
```

**D5. Should detections have a lifecycle (open → investigating → resolved / false positive), or are they fire-and-forget?**
```
lifecycle
```

**D6. How should `actor_is_bot` events be treated? (separate detection rules, suppressed from human-threat models, or flagged when bot behavior is anomalous)**
```
a life cycle
```

**D7. Are known-bad actor lists (e.g., recently terminated employees, flagged accounts) an input to detection?**
```
Assume we have no information aside from the audit log stream
```

**D8. Should off-hours or geo-anomalous access be detected? If yes, what is the source of "normal hours" and "expected geography" per user?**
```
Yes. Normal should be based on calculated usage data.
```

**D9. Should "impossible travel" be detected? If yes, are IP-to-geo lookups acceptable (e.g., MaxMind GeoIP)?**
```
yes.
```

**D10. Should analysts be able to suppress / tune alerts for specific actors, orgs, or repos without modifying code?**
```
yes
```

---

## E. Architecture & Deployment

**E1. What is the target deployment form factor? (CLI tool, background daemon/service, web application, or a combination)**
```
Web app
```

**E2. Is there a preferred technology stack or language? Any platform constraints?**
Candidates: Python, Go, TypeScript/Node, Java, Rust. Constraints: must run on Kubernetes, approved container base images, specific Linux distro, etc.
```
python. we should probably distribute it in several deployments patterns. raw install, docker container, helm chart.
```

**E3. What are the availability and reliability requirements? (e.g., 99.9% uptime, specific RTO/RPO if ingestion pipeline goes down)**
```
We should allow our architecture to scale vertically and horizontally, however, we won't be hosting it for anyone so the actual requirements and patterns are up to the user
```

**E4. Is horizontal scalability required from day one, or is single-node sufficient for v1?**
```
We should allow our architecture to scale vertically and horizontally, however, we won't be hosting it for anyone so the actual requirements and patterns are up to the user
```

**E5. What are the container and orchestration requirements? (Docker-only, Kubernetes-required, Helm chart, Terraform/CDK module)**
```
we should probably distribute it in several deployments patterns. raw install, docker container, helm chart.
```

**E6. Is there an existing internal platform (data platform, observability stack, CI/CD system) this should integrate with or deploy alongside?**
```
the runtime should be generally agnostic but we should provide it with github as the favored tool since this is to review github audit logs 
```

---

## F. Storage & Data Retention

**F1. What are the retention requirements for each data tier?**
- Raw (unprocessed) events: 
- Processed / normalized events: 
- Detected findings / alerts: 
```
I would guess at least a year but we should make those values tunable in the admin portal
```

**F2. Are usernames, actor IDs, email addresses, and IP addresses considered PII under applicable law (GDPR, CCPA, etc.)? What are the obligations around storage, masking, and deletion?**
```
This isn't a hosted service so users will run their own instance. They are responsible for their own data
```

**F3. Is right-to-erasure (GDPR Article 17) required — i.e., the ability to scrub a specific user's data from the store?**
```
This isn't a hosted service so users will run their own instance. They are responsible for their own data
```

**F4. Is encryption at rest required? Customer-managed keys (BYOK/CMK) or provider-managed keys?**
```
This isn't a hosted service so users will run their own instance. They are responsible for their own data
```

**F5. Should raw compressed files from S3/GCS/Blob be retained after ingestion, archived to cold storage, or deleted?**
```
retained
```

---

## G. Security & Access Control

**G1. Who is allowed to access this tool and its reports? Is RBAC required, or is it a single-team tool?**
```
I would think a number of different users will consume this info. we definitely need RBAC, preferablly based on something dynamic like github teams.
```

**G2. Should there be distinct access tiers? (e.g., read-only analyst, report admin, rule author, system admin)**
```
yes. different access tiers and data subdivision. I.e. an owner of a group of 50 repos should be able to see info about their repos specifically but nothing else.
```

**G3. How will the tool authenticate its own users? (SSO/SAML, OAuth, local accounts, or network-level access control only)**
```
I think we should support GitHub auth and SSO/SAML. We shouldn't manage our own accounts.
```

**G4. Should the tool produce its own audit trail — logging who queried what and who acknowledged which alert?**
```
yes
```

**G5. How will credentials (GitHub tokens, cloud storage keys, database passwords) be managed?**
Candidates: HashiCorp Vault, AWS Secrets Manager, Azure Key Vault, Kubernetes Secrets, environment variables.
```
env variables.
```

**G6. Is org-scoped data isolation required — e.g., an analyst for Org A can only query Org A data?**
```
yes
```

---

## H. Compliance & Legal

**H1. Which compliance frameworks must the tool's outputs explicitly support?**
Candidates: SOC 2 Type II, ISO 27001, PCI DSS, HIPAA, FedRAMP, NIST 800-53, CIS Controls, DORA, FFIEC, CMMC.
```
Given the amount of overlap, i think we should have our own internal tracking numbers for activities, then cross reference those to regulatory frameworks
```

**H2. Are specific control mappings required? (e.g., "this report satisfies SOC 2 CC6.6 — Logical Access")**
```
yes Given the amount of overlap, i think we should have our own internal tracking numbers for activities, then cross reference those to regulatory frameworks
```

**H3. Are there data residency requirements? Must data remain within a specific country or region?**
```
This isn't a hosted service so users will run their own instance. They are responsible for their own data
```

**H4. Are there industry-specific regulations that place additional requirements on audit log handling?**
```
i don't think so
```

**H5. Will findings and reports be shared with external auditors? Are there specific format or chain-of-custody requirements?**
```
possibly. users will run their own instance. They are responsible for their own data
```

---

## I. Integrations

**I1. Is SIEM integration required in v1? If yes, which platforms and what integration mechanism?**
Platforms: Splunk, Datadog, Elastic/SIEM, Microsoft Sentinel, IBM QRadar.
Mechanisms: push via syslog/CEF/LEEF, push via REST webhook, or pull (SIEM queries this tool).
```
no
```

**I2. Is ticketing system integration required? Should findings auto-create tickets, or is that manual?**
Candidates: Jira, ServiceNow, GitHub Issues, Linear.
```
yes, auto create option and manual trigger
```

**I3. What notification channels are required?**
Candidates: Slack (workspace/channel), PagerDuty (with severity routing), email, Microsoft Teams, OpsGenie.
```
slack and email for now
```

**I4. Is IdP integration needed to enrich actor events with user metadata (department, title, employment status)?**
Candidates: Okta, Azure AD/Entra, Google Workspace.
```
yes
```

**I5. Is there an existing BI or data warehouse platform that should be the report delivery target instead of building a custom dashboard?**
Candidates: Tableau, Looker, Power BI, Grafana, Metabase.
```
We should build our own dashboards for the primary views, but provide summarized exports or read only db connections for more advanced users
```

**I6. Should the tool call GitHub's REST API for enrichment — e.g., look up current repo visibility or team membership to provide context alongside events?**
```
yes, during investigations. we shouldn't ping the api for every event
```

**I7. Is HR system integration needed to flag events from recently terminated employees?**
```
no
```

---

## J. Extensibility & Future

**J1. Should detection rules be externalized as configuration files (YAML, JSON, Rego/OPA) so analysts can write/modify rules without deploying new code?**
```
They should be configurations but they should be managed inside the app. a WYSIWYG editor on top of config files backed by a git repo are probably the best.
```

**J2. Is a plugin or extension system required for custom ingestion adapters, report types, or detectors?**
```
defer to v2
```

**J3. Is multi-tenancy required — serving multiple independent enterprise customers with strict data isolation from a single deployment?**
```
no
```

**J4. Should this tool expose its own REST or GraphQL API so other systems can query findings and reports programmatically?**
```
yes
```

**J5. Is ML/AI-based anomaly detection on the roadmap, even if rules-based detection is sufficient for v1? (Storage and data model choices should not foreclose this option.)**
```
on the roadmap but deferred to later version
```

**J6. Will the tool need to support multiple GHEC enterprise instances simultaneously (e.g., separate enterprises per subsidiary or region)?**
```
no. 1 instance for 1 enterprise
```

**J7. Who owns the long-term maintenance of detection rules? (Internal security team, a vendor, or open-source community — this affects rule authoring UX.)**
```
probably some of all 3
```
