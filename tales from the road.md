# Tales from the Road

---

## Best Buy — In-Person Visit

**Customer:** Best Buy
**Visit Type:** In-person technical deep-dive
**Customer Attendees:** Vinoth Rajagopalan, Brian Plantenberg, Vijay Krishna
**GitHub Attendees:** Jenna (NCE)

### Key Outcomes

* We dug into a Safe Settings issue the team has been chasing — it runs fine in Actions but silently skips repo creation without throwing any errors. Best guess is a missing `force_create` flag in the config. They're going to test that and we'll regroup; longer term, they'd like to move it to a webhook-hosted setup anyway for better performance.
* Got to give the team an early heads-up on the upcoming Copilot billing changes (official announcement May 1, changes take effect June 1). The short version: PRUs are going away in favor of AI credits with a pooled model, and — importantly — GitHub Apps will be able to hold Copilot allocations. That directly unblocks the org-level bot access they've been asking about for a while.
* Spent some time showing off Agent HQ and the multi-agent orchestrator pattern I've been building out. The team was genuinely excited about it, especially given they already have an internal MCP registry stood up. Left them with the blog post and all the agent files to dig into on their own.
* Introduced the new GitHub code quality product (preview now, GA late summer) as a potential path off SonarQube. Showed how the Copilot auto-fix integration works, how you can gate merges on quality results through rule sets, and the campaigns feature. Their SonarQube adoption is pretty low right now and Groovy support is a gap — worth watching as the product matures.

### Business Impact

* Best Buy has already blown past their finance-approved Copilot budget, so the pooled credit model is well-timed. GitHub App Copilot access also unblocks the agentic automation work their teams are actively building toward.
* This team is deeply invested in the platform — they've built their own MCP registry, they're experimenting with multi-agent workflows, and they're thinking seriously about consolidating tooling. The Agent HQ demo landed right where they are, which is a good sign for the relationship.
* SonarQube is on the table as a displacement target. They're already questioning whether to move to SonarQube Cloud vs. keeping self-hosted, so the timing of showing the GitHub code quality product was good. There's a real expansion story here once it hits GA.

### Next Actions

* Jenna to check back on the Safe Settings `force_create` fix and help dig into logs if it doesn't pan out. (Jenna, April 30)
* Vinoth/Vijay to read through the multi-agent blog post and see how the orchestrator pattern fits into what they're already doing. (Vinoth/Vijay, May 15)
* Jenna to share the official token-based billing announcement and comparison dashboards as soon as they're out. (Jenna, May 1)
* QT team to pick some pilot repos and kick the tires on GitHub code quality; Jenna to loop in Tom Horton (practices lead) for a deeper walkthrough on language coverage and what's still on the roadmap. (Jenna + Vinoth/Pete, May 15)

---

## Target — In-Person Visit

**Customer:** Target
**Visit Type:** In-person technical review
**Customer Attendees:** Matt (Engineering), Eric (Engineering), Chris (Engineering Lead), Sammy (PM, Coding Companion)
**GitHub Attendees:** Jenna (NCE)

### Key Outcomes

* Had a great conversation about their custom SCIM setup — they built it themselves because their IDP doesn't support it natively, which is a pretty unique situation. Shared some best practices around rate limiting, ETag conditional requests, and moving toward an event-driven model using the GitHub Enterprise App so they're not constantly polling.
* Copilot adoption is going well and usage is strong, but the team has a couple of blockers holding them back from enabling CLI and Cloud Agent — mainly TPRM and security reviews. They've also built an internal tool called "Dayton" that wraps the Copilot CLI with enterprise guardrails and context management, and there's interest in exploring deeper integration with the Copilot SDK.
* Had a meaty discussion about moving from per-repo branch protection rules to org-level repo rule sets with custom compliance properties for SOX/PCI. The big win here is shifting from detective to preventive controls — catching issues before they happen instead of auditing after. Q3 is the earliest realistic target, and they'll need SOX IT sign-off before they start.

### Business Impact

* Target is building toward a genuinely mature governance posture — audit-log-driven compliance, org-level rule sets, the whole picture. That kind of investment signals a long-term bet on GitHub as their platform, which is great for the relationship.
* Getting Dayton and Copilot better integrated — plus clearing the TPRM hurdles for CLI and Cloud Agent — could meaningfully expand agentic workflow adoption across their engineering teams. There's real seat utilization upside here once those blockers come down.

### Next Actions

* Jenna to look up whether there's an existing feature request for a better error message when suspended users hit the login loop, and get Target added to it if so. (Jenna, April 23)
* Jenna to reach out to the OctoShift team about options for migrating really large repos (the one they're dealing with is pushing 100GB of metadata) and report back with what's possible. (Jenna, April 30)
* Chris/Sammy to get a session on the calendar with the Dayton team and GitHub to talk through how Copilot CLI integration, the SDK, and guardrails could work together. (Chris/Sammy, May 15)
* Chris/Engineering to put together an implementation plan for org-level repo rule sets and get it in front of the SOX IT team before committing to a Q3 migration. (Chris, May 31)
