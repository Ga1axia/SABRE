# SABRE

**Self-improving Agent Business Recursive Engine**
Product Requirements Document · v2.0 · 17 August 2026

| | |
|---|---|
| Owner | Taihei Eastwood |
| Target host | macOS 12+, 8 GB RAM, clean install |
| Distribution | Public GitHub repository, one-command install |
| Time to first run | < 45 minutes from `curl` to first agent turn |

---

## 1. What SABRE is

SABRE is an installable autonomous company. One agent identifies revenue opportunities, spins up ventures to pursue them, assembles specialist teams to execute, spends real money inside pre-authorized limits, measures results in dollars, and writes what it learns back into itself as reusable skills. It reports to one human through Slack.

It ships as a repository. You clone it, run one installer, answer a wizard, and it runs.

The design bias is **autonomy**. SABRE is not an assistant awaiting instructions. It operates continuously inside envelopes and consults its operator when it hits a boundary, needs a capability it structurally lacks, or wants strategic direction — not for permission to work.

Three things are withheld from it, and only three:

1. **Raw values of high-consequence credentials.** It uses them; it never reads them.
2. **Accounts it does not own.** It operates only identities created for it.
3. **Its own containment.** It cannot alter the policy engine, the spending ceilings, the account registry, or the kill switch.

---

## 2. Goals and non-goals

### 2.1 Goals

| ID | Goal | Measure |
|---|---|---|
| G1 | Installs and runs from a clean machine | `curl` → first agent turn in under 45 min |
| G2 | Operates unattended for ≥ 7 days | Days between blocking operator requests |
| G3 | Generates revenue exceeding operating cost | Rolling 30-day net: revenue − spend − inference |
| G4 | Improves measurably over time | Cost-to-first-dollar per venture, trending down |
| G5 | Never touches the operator's personal identity | Zero incidents, structurally enforced |
| G6 | Never exceeds authorized spend | Zero ceiling breaches, enforced at network level |
| G7 | Fully auditable after the fact | Every dollar traceable to a decision chain |

### 2.2 Non-goals

- Multiple human users, roles, or org permissions.
- Multi-machine or clustered deployment.
- Local model inference.
- Managing businesses that already exist. SABRE creates its own.
- A public-facing or multi-tenant dashboard.

---

## 3. Design principles

1. **Autonomy is the default.** Every restriction in this document justifies itself by naming a specific irreversible harm.
2. **Bound the envelope, not the action.** Approve budgets, scopes, and windows. Never approve individual actions — it does not scale, it makes the operator the bottleneck, and within days it degrades into reflexive approval, which is worse than no gate.
3. **Enforce structurally, not by instruction.** A rule in a prompt is a suggestion. A rule enforced by a separate OS user, a network proxy, an exhausted virtual card, or a credential that does not exist in the agent's address space is a fact. Anything that matters is enforced structurally.
4. **Defense in depth for money.** Three independent layers, each sufficient alone: a network-level card ceiling, a policy engine, and the agent's own instructions. The outermost layer must not depend on the software that might be failing.
5. **Money is the fitness function.** Self-improvement without a measured quantity is decoration.
6. **Revenue is observed, never asserted.** The agent cannot write the number it optimizes.
7. **Assume the agent's reasoning can be compromised.** Prompt injection from fetched content is expected. Design so that a fully-persuaded SABRE still cannot reach anything critical.
8. **One source of truth.** One database. Dashboard, Slack, gate, and agent read the same rows.
9. **Fail closed on irreversibility, fail open on everything else.** A failed policy check blocks. A failed logger alerts but never blocks work.

---

## 4. Installation and setup

### 4.1 The sequence

```bash
curl -fsSL https://raw.githubusercontent.com/<org>/sabre/main/install.sh | bash
sabre setup          # interactive wizard
sabre doctor         # preflight verification
sabre up             # start all services
```

Install is unattended. Setup is interactive by necessity — Slack app creation, OS user creation, and credential entry require a human and cannot be automated away. The wizard's job is to make that unavoidable part short, ordered, and impossible to get wrong.

### 4.2 What `install.sh` does

1. Verifies macOS 12+, ≥ 8 GB RAM, and available disk.
2. Installs Xcode Command Line Tools if absent.
3. Installs `uv` and Python 3.11 into an isolated prefix.
4. Installs the Hermes agent runtime.
5. Clones the SABRE repo to `/opt/sabre` (source of truth for `core/`).
6. Installs the `sabre` CLI onto PATH.
7. Prints the next command. Does not start anything, does not create users, does not touch the network beyond package fetches.

Idempotent. Re-running upgrades in place and never overwrites config.

### 4.3 What `sabre setup` walks through

The wizard is a numbered sequence with resumable state in `~/.sabre/setup.json`. Each step verifies before advancing.

| Step | What happens | Requires |
|---|---|---|
| 1 | Create OS users `sabre` and `sabre-gate`, set home dirs and permissions | sudo, once |
| 2 | Generate and initialize `sabre.db` from schema | — |
| 3 | Choose inference provider, enter key, run a live test completion | Provider account |
| 4 | Generate Slack app manifest, open browser to Slack, wait for tokens | Slack workspace |
| 5 | Create channels, invite the bot, verify a round trip on each | — |
| 6 | Enter operator Slack member ID for the allowlist | — |
| 7 | Set envelope ceilings (interactive, with recommended defaults) | Budget decision |
| 8 | Register the funding instrument and issue the first virtual card | Card provider |
| 9 | Install credential proxy, migrate Tier-2 secrets into it | — |
| 10 | Provision SABRE's dedicated browser profile | — |
| 11 | Convert selected persona bundles into runtime skills | — |
| 12 | Write and load launchd services | sudo, once |
| 13 | Install the kill switch, owned by the operator, mode 444 | sudo |

Steps 8 and 9 are skippable at setup time and resumable later with `sabre setup --step 8`; the system runs in a no-spend mode until they complete.

### 4.4 What `sabre doctor` verifies

Preflight is a hard gate on `sabre up`. Failures are listed with the exact remediation command.

- Every service's dependencies present and correct version.
- Database schema at expected migration.
- Inference provider reachable, model responds, cost accounting returns figures.
- Slack gateway connects; every required channel exists and the bot is a member.
- **Isolation proof:** as user `sabre`, attempt to read the operator's home directory, the operator's browser profile, and the gate's credential store. All three must fail. This check is not advisory — `sabre up` refuses without it.
- **Ceiling proof:** submit a synthetic intent exceeding the per-transaction ceiling; confirm it is refused.
- Kill switch present, correct ownership, correct mode.
- Virtual card provider reachable; issued card's authorized limit matches configured envelope.
- Disk, memory headroom, and sleep settings.

### 4.5 CLI surface

```
sabre setup [--step N] [--resume]
sabre doctor [--json] [--fix]
sabre up | down | restart [service]
sabre status                     # one-screen summary
sabre kill | unkill              # kill switch
sabre logs [--follow] [--venture X]
sabre envelope show | set <key> <value>
sabre accounts list | add | retire
sabre secrets list | add | rotate        # names only, never values
sabre venture list | show <slug> | kill <slug>
sabre personas sync | list | enable <id>
sabre backup | restore <snapshot>
sabre upgrade
```

---

## 5. System architecture

### 5.1 Trust boundaries

Three macOS users on one machine. This split is what converts the document's guarantees from intentions into facts.

| User | Runs | Can read |
|---|---|---|
| `taihei` | Dashboard client, kill switch, Slack | Everything |
| `sabre` | Agent runtime, its browser, venture code | Its own home only |
| `sabre-gate` | Policy engine, credential proxy, webhooks, dashboard server | Tier-2 secrets, database (write) |

`sabre` cannot escalate, cannot read `~taihei`, cannot signal `sabre-gate` processes, cannot modify `/opt/sabre/core`.

### 5.2 Services

| Service | User | Purpose |
|---|---|---|
| `sabre-agent` | `sabre` | Hermes gateway: Slack ↔ agent, tool execution |
| `sabre-gate` | `sabre-gate` | Policy engine; executes all consequential effects |
| `sabre-proxy` | `sabre-gate` | Credential injection at the network boundary |
| `sabre-web` | `sabre-gate` | Local console, `127.0.0.1:8787`, never internet-exposed |
| `sabre-push` | `sabre-gate` | Publishes read-only snapshots to the hosted mirror |
| `sabre-hooks` | `sabre-gate` | Payment and provider webhook ingest |
| `sabre-watch` | `taihei` | Heartbeat monitor, kill switch, alerting |

All under launchd with `KeepAlive`, surviving reboot.

### 5.3 Inference

Remote by API. Local models are out of scope: 8 GB cannot host a model competent at multi-step tool use alongside the gateway, browser, and automation stack.

| Role | Tier | Rationale |
|---|---|---|
| SABRE core — planning, strategy, decomposition | Frontier | Judgment is where quality pays |
| Persona subagents — bounded execution | Mid / cheap | Executing a well-specified subtask with a clear output contract needs less |
| Adversarial review | Different provider from core | A second model catches what the first rationalizes |
| Digests, summarization, classification | Cheapest | Mechanical |

All provider traffic routes through a gateway supporting virtual keys with hard budget caps, so inference spend is bounded in the request path rather than discovered on an invoice.

### 5.4 Runtime discipline

```yaml
delegation:
  max_concurrent_children: 2
  max_iterations: 40
loop_caps:
  max_web_search: 15
  max_subagents: 8
compression:
  enabled: true
  threshold: 0.5
  target: 0.2
  protect_last: 20
session:
  recycle_on: [venture_boundary, 4h_elapsed]
```

`max_concurrent_children: 2` is a memory constraint, not a philosophy. Three subagents plus a headless browser will swap on 8 GB, and the symptom presents as mysterious tool timeouts rather than as memory pressure.

---

## 6. The autonomy model

### 6.1 Envelopes

An envelope is a pre-authorized region of action. Inside it SABRE acts with no human involvement. Envelopes live in `core/envelopes.yaml` and are enforced by the policy engine.

```yaml
envelopes:
  spend:
    per_transaction_max: 50
    daily_max: 150
    monthly_max: 1200
    per_venture_max: 400
    allowed_categories: [hosting, domains, saas, ads, api_credits, contractor_micro]
    blocked_categories: [equity, legal_retainer, crypto, gambling, prepaid_cards, payroll]
  inference:
    daily_usd: 25
    per_venture_usd: 120
  publish:
    domains_allowed: ["*.<company-domain>", "*.vercel.app"]
  outreach:
    email_per_day: 40
    email_per_recipient_domain_per_day: 3
    dm_per_platform_per_day: 15
    new_account_creation_per_week: 2
  code:
    venture_repos: unrestricted
    core_repo: proposal_only
  portfolio:
    max_concurrent_ventures: 3
  auto_raise:
    rule: "spend.daily_max +20% per consecutive week of positive net contribution"
    cap_multiple: 3.0
```

`auto_raise` matters: it lets SABRE earn autonomy by performing, which points its incentives where they should be.

### 6.2 Three-layer enforcement

Every layer is independently sufficient. The outermost does not depend on SABRE's code being correct.

**Layer 1 — network.** Each venture receives a virtual card with a pre-authorized limit equal to its envelope. When the card is exhausted, the venture is financially dead regardless of what any software believes. A retry storm, a race condition, or a successful prompt injection cannot spend past it. The funding account carries a hard monthly ceiling below the sum of all envelopes.

**Layer 2 — policy engine.** The gate evaluates every intent against category rules, cumulative ceilings, rate windows, and the account registry before executing. Runs as a different OS user than the agent.

**Layer 3 — instruction.** The agent's own understanding of its limits. Useful for good behavior, never relied upon for safety.

### 6.3 Action classes

Classification is performed by the policy engine, never by the agent.

**Green — autonomous, silent, logged.**
Reading and researching anything. Writing, running, and deploying code. Publishing to owned domains. Creating content. Posting to owned accounts within rate limits. Spending inside all ceilings and allowed categories. Outreach within rate limits. Creating ventures. Killing its own ventures. Writing and revising skills. Editing company knowledge. Registering domains under the per-transaction ceiling.

**Amber — autonomous, announced, held.**
Executes automatically after a hold window during which the operator may veto. Default hold 30 minutes.
Single spends above 50% of the per-transaction ceiling. First contact with a named company. Publishing content that names the operator. Creating an account on a platform not yet used. Any intent whose provenance chain includes untrusted fetched content and whose effect touches money or identity.

**Red — blocks until approved.**
Any spend exceeding a ceiling or in a blocked category. Payments to a natural person. Anything contractual. Any action against an account absent from the registry. Any modification to `core/`, envelopes, the account registry, or the gate. Requests to widen an envelope. **Anything the classifier cannot classify.** Unknown resolves to Red, always.

### 6.4 Adversarial review

Before any Amber or Red intent, and before any venture launch, a reality-check persona running on a *different provider* from SABRE core reviews the plan and writes a dissent to the intent record. The dissent is advisory but always visible in the approval message. A single model reviewing its own plan finds what it already believes.

### 6.5 Envelope negotiation

SABRE argues for larger envelopes in `#directives`: what it wants, the evidence, the intended use, the expected return. Envelope changes are Red by construction. The agent can never widen its own bounds.

---

## 7. Identity and account isolation

### 7.1 Requirement

SABRE acts only on identities created for it, and must be structurally incapable of reaching the operator's personal accounts.

### 7.2 Enforcement layers

1. **OS separation.** `sabre` cannot read the operator's home directory, browser profile, Keychain, or SSH keys.
2. **Dedicated browser.** SABRE gets its own browser profile and cookie jar under its own home, launched with an explicit isolated user-data directory. It is never handed a debugging endpoint attached to a browser the operator uses.
3. **Account registry.** `core/accounts.yaml` is an allowlist. Absent means Red.
4. **Egress policy.** The credential proxy logs every outbound host and can deny by pattern.
5. **Continuous verification.** `sabre doctor` re-proves isolation on every start.

```yaml
accounts:
  - id: x_main
    platform: x.com
    handle: "@<handle>"
    owner: sabre
    credential: proxy://x_main
    rate: {posts_per_day: 8, dms_per_day: 15}
  - id: reddit_main
    platform: reddit.com
    owner: sabre
    credential: proxy://reddit_main
    rate: {comments_per_day: 10, posts_per_day: 2}
  - id: github_sabre
    platform: github.com
    owner: sabre
    credential: env://GITHUB_PAT          # Tier 1
    scope: "repos under <org>/ventures-* only"
  - id: stripe_main
    platform: stripe.com
    owner: sabre-gate
    credential: proxy://stripe_live        # Tier 2
denied_hosts:
  - mail.google.com
  - "*.chase.com"
  - "*/user/<operator_handle>"
```

### 7.3 Disclosure

SABRE-operated accounts must not impersonate a specific real human, and must identify as agent-operated in whatever form each platform supports. Undisclosed synthetic personas get accounts terminated and domains blacklisted, and the resulting exposure lands on the operator. The constraint is therefore structural, checked by the gate on account creation.

---

## 8. Secrets

### 8.1 Premise

The agent has shell access. Any file it can read, it can exfiltrate. Protection therefore requires that a value never exist in the agent's address space.

### 8.2 Two tiers

**Tier 1 — agent-held.** Low blast radius, cheap to rotate, revocable in seconds. Lives in the agent's environment. Its own scoped code-host token, dev keys, its own hosting token.

**Tier 2 — proxy-held.** Anything that moves money, controls an identity at scale, or is expensive to revoke. The value lives only inside the credential proxy under `sabre-gate`. SABRE receives an opaque token, places it in the request header, and the proxy swaps it at the network boundary.

### 8.3 Known limits — do not over-trust the proxy

- It protects registered credentials. It does not inspect arbitrary files. Never mount real credentials into the agent's sandbox.
- Exfiltration to an allowlisted host remains possible in a request body. The proxy logs it; it does not prevent it. Layer 1 card ceilings exist partly for this reason.
- Signature-based auth schemes (SigV4, service-account OAuth) cannot be swapped by header replacement. Credentials of that kind must not be present on this machine.
- The proxy holds real values in process memory.

### 8.4 Dashboard's role

The dashboard is the management surface, never the store. It shows credential name, tier, last use, usage count, error rate, and a rotate action. Tier-2 values are never rendered and are not retrievable through any endpoint. Adding a Tier-2 secret happens through `sabre secrets add`, which writes directly into the proxy store and never through a web form the agent could reach.

---

## 9. Slack

Channels are speech acts, not topics. Each has a direction, a required response type, and a system prompt injected per turn.

| Channel | Direction | Response | Cadence |
|---|---|---|---|
| `#directives` | ⇄ | Operator answers | SABRE's initiative |
| `#requests` | → operator, blocking | Operator acts | As needed |
| `#approvals` | → operator | ✅ / ❌ / timeout | Amber and Red only |
| `#status` | → operator | None | Daily 08:00, weekly Mon |
| `#logs` | runtime → operator | None | Continuous, filtered |
| `#ventures` | → operator | None | Thread per venture |
| `#postmortems` | → operator | Optional | Per venture close |
| `#revenue` | webhook → operator | None | Per payment event |

### 9.1 `#directives`

> You are asking for direction, not permission. Use this when a decision would change what you pursue for weeks, when two paths look comparably good and the operator's preference breaks the tie, or when you want a larger envelope. Recommendation first, then reasoning, then the question. One question per message. If no answer arrives within 24 hours, act on your own recommendation and note that you did.

The final clause is essential. Without it, silence becomes a stop and autonomy evaporates the first weekend.

### 9.2 `#requests`

> Only for things you structurally cannot do: a signature, a phone call, an identity verification, a payment method you have no access to, an account only the operator can open. State what you need, why you cannot do it, what is blocked until it happens, and what you are doing meanwhile. Never ask permission here — that is `#approvals`. Never use this for something you could do with more effort.

### 9.3 `#approvals`

Machine-formatted, one message per gated intent: intent ID, class, amount, category, venture, one-line rationale, adversarial dissent, and for Amber the auto-execute deadline. Reactions are the interface — ✅ approve, ❌ veto, 🕐 extend 24h. No prose. If this channel fires more than about three times a day, the envelopes are wrong, not the operator.

### 9.4 `#status`

Daily 08:00: active ventures with one-line state, revenue and spend for the day, envelope headroom, outstanding blocking requests, intent for today. Weekly Monday: net position, cost-to-first-dollar by venture, skills promoted and retired, envelope asks.

### 9.5 `#logs`

Written by the runtime, never by the agent. A hook on the tool-call stream writes every call to the event table and mirrors a filtered subset here: tool, target, duration, outcome, truncated arguments. The agent has no logging tool and cannot suppress an entry.

### 9.6 `#revenue`

Written only by the webhook service. The one channel whose numbers are trustworthy by construction.

---

## 10. Agent composition

### 10.1 Core

One primary agent with persistent identity across sessions, backed by company knowledge and its skill library. Responsible for opportunity generation, portfolio management, team assembly, delegation, synthesis, and self-improvement. It does not perform specialist work itself.

### 10.2 Persona teams

Specialist personas are converted once from the persona catalog into runtime skills under `core/personas/`.

**Loading is on demand and never wholesale.** A catalog of 160+ personas resident in context is context poison. SABRE assembles 3–5 per task.

| Stage | Team shape |
|---|---|
| Validation | market researcher, reality checker, pricing strategist |
| Build | backend architect, frontend developer, devops |
| Launch | growth, content, SEO |
| Sell | outbound strategist, copywriter, community builder |
| Operate | analytics, support, retention |

### 10.3 Delegation contract

Every delegation must specify goal, full context (the subagent has no history), output contract, tool subset, and acceptance criteria. A lint check rejects delegations lacking acceptance criteria — this is the most common failure mode in delegated agent work and it is cheap to prevent.

### 10.4 Catalog maintenance

`sabre personas sync` runs weekly, diffs upstream, and reports additions and changes to `#status`. Custom personas may be added to `core/personas/` through the proposal flow.

---

## 11. Work model

### 11.1 Board

Work is a file-backed board under `work/board/`, one markdown file per task with YAML frontmatter. File-backed rather than database-only because the agent reads and edits it natively, it diffs in git, and it survives every other component.

```yaml
---
id: T-0142
venture: geo-audit
status: in-progress          # backlog|ready|in-progress|review|done|abandoned
priority: high
goal: "Ship pricing page A/B test"
acceptance: "Two variants live, traffic split, 200 sessions per arm"
team: [growth-hacker, frontend-developer]
opened: 2026-08-17
---
```

The board is mirrored into the database on every write for the dashboard's benefit. Files are authoritative.

### 11.2 Claim semantics

Subagents claim tasks atomically before working. A claimed task carries an owner and a lease; expired leases return to `ready`. This prevents two parallel subagents from duplicating work or racing on the same artifact.

---

## 12. Memory and knowledge

### 12.1 `COMPANY.md`

Read at session start, freely editable by SABRE.

```
# Identity          — what this company is, what it will and won't do
# Current position  — generated section, not hand-edited
# Playbook          — what has worked
# Anti-playbook     — what has failed, and the tell that predicted it
# Decisions         — append-only, dated, with reasoning
# Open questions
```

The **anti-playbook** is load-bearing. Agents accumulate successes and forget failures, which produces confident repetition of expensive mistakes.

### 12.2 Lessons ledger

Structured counterpart to the anti-playbook. On any failure or discovered optimization, SABRE writes a lesson record: context, what was expected, what happened, the generalizable rule, and confidence. Lessons enter `candidate` state and are promoted only on the terms in §14.3.

### 12.3 Skills

Procedural memory — how to stand up a landing page, run an outreach sequence, configure payments for a new venture. Created from experience, promoted on evidence, retired on evidence.

### 12.4 Ledger

The structured record. Knowledge files hold judgment; the ledger holds facts. Where they disagree, the ledger wins and the knowledge file is corrected.

### 12.5 Self-modification

SABRE may propose changes to its own harness. It may not merge them.

Branch → patch to `core/` → PR → gate runs the test suite → posted to `#approvals` as Red → on approval, gate merges and restarts affected services → on failed health check, automatic rollback to previous commit.

Venture code under `work/ventures/` is entirely unrestricted.

The distinction: full freedom over *what the company does*, constrained freedom over *what SABRE is*. Without it, one bad self-edit ends the company, and a sufficiently motivated agent edits away its own limits.

---

## 13. Observability

### 13.1 Event tap

A runtime hook writes every tool call: timestamp, trace, session, venture, actor, tool, redacted arguments, outcome, duration, tokens, cost. Non-blocking; a logger failure alerts rather than blocks.

### 13.2 Redaction

Applied at write time and again before any Slack mirroring. Matches known secret shapes and all registered proxy token names.

### 13.3 Trace

Every action carries a trace linking directive → plan → task → delegation → tool calls → intent → transaction. The dashboard renders a complete trace for any dollar spent. G7 depends on this.

### 13.4 Cost attribution

Inference cost is attributed per venture per delegation. A venture that earned $200 while burning $340 of inference is a losing venture and the system must be able to see that without manual arithmetic.

---

## 14. The self-improvement loop

### 14.1 Fitness function

Primary: **net contribution per venture** = revenue − direct spend − attributed inference cost.

Secondary: cost-to-first-dollar, time-to-first-dollar, venture survival rate, skill reuse rate.

### 14.2 The cycle

1. Venture runs; all effects logged and costed.
2. Venture reaches terminal state.
3. SABRE writes a postmortem: what was believed, what was done, what happened, the earliest signal that predicted the outcome.
4. Reusable procedure extracted as a candidate skill; generalizable rule extracted as a candidate lesson.
5. Applied on the next venture of that shape.
6. Outcome measured. Promoted, revised, or retired.

### 14.3 Promotion criteria

A candidate is promoted only after use in ≥ 2 ventures with non-negative net contribution in both. A candidate used in two ventures with negative contribution is retired automatically and its inverse written to the anti-playbook. Without this the library fills with confidently-written procedures that have never worked.

### 14.4 Venture kill criteria

Every venture is created with explicit kill criteria enforced by the gate regardless of the agent's opinion. Defaults:

- No revenue after $150 direct spend.
- No revenue after 21 days.
- Negative net contribution three consecutive weeks after first revenue.
- Any legal, ToS, or platform-ban event — immediate, with Red gate to revive.

Agents are systematically poor at killing their own projects. This must not be a judgment call.

### 14.5 Metric integrity

Because SABRE optimizes net contribution and has broad latitude, the metric must be unfakeable:

- Revenue rows are insertable only by the webhook service. No agent tool writes revenue.
- Spend rows are written by the gate at execution time.
- Inference cost comes from provider usage figures, not agent estimates.
- Refunds and chargebacks reverse revenue automatically.

---

## 15. The revenue engine

### 15.1 Opportunity generation

A daily scan produces scored candidate ventures. Sources: community pain-point mining, competitor gap analysis, search-demand signals, pricing anomalies, adjacencies to ventures already earning, and re-examination of anti-playbook failures whose cause has since changed.

Scoring: estimated time-to-first-dollar, estimated spend-to-first-dollar, strength of market evidence, and **reuse of existing promoted skills**. Skill reuse is weighted deliberately — it is what makes the engine compound rather than restart from zero each time.

### 15.2 Portfolio discipline

Maximum three concurrent ventures, envelope-controlled. A new venture starts only when a slot frees, which forces killing before starting.

### 15.3 Expansion on live ventures

For any earning venture, SABRE continuously tests pricing, tiers and upsells, new acquisition channels, conversion, and retention. Each test is a task with a stated hypothesis and a measurement window. Results enter the ledger; wins enter the playbook.

### 15.4 Outreach discipline

Rate ceilings are enforced by the gate through recorded usage windows, not by prompt. Additional hard rules: no purchased lists, honest sender identity, working unsubscribe on every sequence, per-recipient-domain caps to protect deliverability, immediate stop on complaint. A burned sending domain costs more than any campaign earns.

---

## 16. Data model

One SQLite database, owned by `sabre-gate`, WAL mode. The agent reads directly and writes only through the gate's local API.

```sql
CREATE TABLE ventures (
  id            TEXT PRIMARY KEY,
  slug          TEXT UNIQUE NOT NULL,
  name          TEXT NOT NULL,
  thesis        TEXT NOT NULL,
  icp           TEXT,
  status        TEXT NOT NULL,     -- ideating|building|launched|earning|stalled|killed
  kill_criteria TEXT NOT NULL,     -- JSON
  card_id       TEXT,              -- virtual card backing this venture
  created_at    TEXT NOT NULL,
  closed_at     TEXT,
  close_reason  TEXT
);

CREATE TABLE tasks (
  id          TEXT PRIMARY KEY,
  venture_id  TEXT REFERENCES ventures(id),
  parent_id   TEXT REFERENCES tasks(id),
  goal        TEXT NOT NULL,
  acceptance  TEXT NOT NULL,
  team        TEXT,
  status      TEXT NOT NULL,
  claimed_by  TEXT,
  lease_until TEXT,
  created_at  TEXT NOT NULL,
  closed_at   TEXT,
  result      TEXT
);

CREATE TABLE intents (
  id              TEXT PRIMARY KEY,
  venture_id      TEXT REFERENCES ventures(id),
  task_id         TEXT REFERENCES tasks(id),
  kind            TEXT NOT NULL,    -- spend|publish|deploy|outreach|account|core_change
  classification  TEXT NOT NULL,    -- green|amber|red
  payload         TEXT NOT NULL,
  idempotency_key TEXT UNIQUE NOT NULL,
  rationale       TEXT NOT NULL,
  dissent         TEXT,             -- adversarial review output
  provenance      TEXT,             -- JSON: trust chain of inputs
  state           TEXT NOT NULL,    -- proposed|held|approved|vetoed|executed|failed|expired
  hold_until      TEXT,
  slack_ts        TEXT,
  created_at      TEXT NOT NULL,
  decided_at      TEXT,
  executed_at     TEXT,
  error           TEXT
);

CREATE TABLE transactions (
  id           TEXT PRIMARY KEY,
  venture_id   TEXT REFERENCES ventures(id),
  intent_id    TEXT REFERENCES intents(id),
  direction    TEXT NOT NULL,       -- debit|credit
  amount_cents INTEGER NOT NULL,
  currency     TEXT NOT NULL DEFAULT 'USD',
  category     TEXT NOT NULL,
  source       TEXT NOT NULL,       -- gate|webhook|provider_sync
  card_id      TEXT,
  external_id  TEXT,
  reversed_by  TEXT REFERENCES transactions(id),
  occurred_at  TEXT NOT NULL
);

CREATE TABLE cards (
  id            TEXT PRIMARY KEY,
  venture_id    TEXT REFERENCES ventures(id),
  provider_ref  TEXT NOT NULL,
  limit_cents   INTEGER NOT NULL,
  spent_cents   INTEGER NOT NULL DEFAULT 0,
  status        TEXT NOT NULL,      -- active|exhausted|frozen|closed
  issued_at     TEXT NOT NULL
);

CREATE TABLE events (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  trace_id    TEXT,
  venture_id  TEXT,
  session_id  TEXT,
  actor       TEXT NOT NULL,        -- core|persona:<id>|gate|webhook
  tool        TEXT,
  args        TEXT,
  status      TEXT,
  duration_ms INTEGER,
  tokens_in   INTEGER,
  tokens_out  INTEGER,
  cost_cents  INTEGER,
  occurred_at TEXT NOT NULL
);

CREATE TABLE accounts (
  id         TEXT PRIMARY KEY,
  platform   TEXT NOT NULL,
  handle     TEXT,
  owner      TEXT NOT NULL,
  credential TEXT NOT NULL,
  status     TEXT NOT NULL,         -- active|suspended|retired
  created_at TEXT NOT NULL
);

CREATE TABLE rate_usage (
  account_id  TEXT REFERENCES accounts(id),
  window_date TEXT NOT NULL,
  action      TEXT NOT NULL,
  count       INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (account_id, window_date, action)
);

CREATE TABLE skills (
  id            TEXT PRIMARY KEY,
  name          TEXT NOT NULL,
  status        TEXT NOT NULL,      -- candidate|promoted|retired
  uses          INTEGER DEFAULT 0,
  net_cents     INTEGER DEFAULT 0,
  created_at    TEXT NOT NULL,
  promoted_at   TEXT,
  retired_at    TEXT,
  retire_reason TEXT
);

CREATE TABLE lessons (
  id         TEXT PRIMARY KEY,
  venture_id TEXT REFERENCES ventures(id),
  context    TEXT NOT NULL,
  expected   TEXT NOT NULL,
  happened   TEXT NOT NULL,
  rule       TEXT NOT NULL,
  status     TEXT NOT NULL,         -- candidate|promoted|retired
  created_at TEXT NOT NULL
);

CREATE TABLE postmortems (
  id              TEXT PRIMARY KEY,
  venture_id      TEXT REFERENCES ventures(id),
  believed        TEXT NOT NULL,
  did             TEXT NOT NULL,
  happened        TEXT NOT NULL,
  earliest_signal TEXT,
  created_at      TEXT NOT NULL
);

CREATE TABLE heartbeats (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  service TEXT NOT NULL,
  at      TEXT NOT NULL
);
```

### 16.1 Write permissions

| Table | Agent | Gate | Webhook |
|---|---|---|---|
| `ventures`, `tasks`, `postmortems`, `lessons` | write | — | — |
| `intents` | insert (state `proposed`) | update state | — |
| `transactions` debit | — | insert | — |
| `transactions` credit | — | — | insert |
| `cards` | — | insert/update | — |
| `events` | — | insert via tap | — |
| `accounts`, `skills.status`, `rate_usage` | — | insert/update | — |

The agent cannot write a single row of revenue or spend. This table is the enforcement of principle 6.

---

## 17. Gate specification

### 17.1 Intent lifecycle

```
proposed → classify
  green → execute → executed | failed
  amber → held(hold_until) → [❌ vetoed] | [timeout → execute]
  red   → held → [✅ execute] | [❌ vetoed] | [7d → expired]
```

### 17.2 Classification order

Deny rules → account registry → category rules → cumulative ceilings → rate windows → provenance escalation → default. Unknown kind resolves to Red.

### 17.3 Execution

The gate is the only process holding Tier-2 credentials and the only one performing consequential external effects. It validates payload against a per-kind schema, checks and increments rate usage atomically, charges the venture's card, executes, writes the transaction, and returns a result the agent can read.

### 17.4 Idempotency

Every intent carries a key derived from the semantic content of the action, not a random identifier — a retry must produce the same key. Unique constraint plus a pre-execution state check. A replayed intent returns the original result rather than executing twice.

### 17.5 Reconciliation

Nightly, the gate reconciles its transaction table against the payment provider, the card issuer, the hosting provider, and the inference gateway. Divergence posts to `#status` and freezes the spend envelope until resolved. A gate that believes it spent $40 while the issuer reports $400 must stop, not continue.

---

## 18. Dashboard

The dashboard is remotely accessible: the operator can check on the company from a phone, anywhere, without being on the home network.

### 18.1 Split architecture

Remote access is delivered as two surfaces, not one hosted application.

**Local console** — `sabre-web`, server-rendered, bound to `127.0.0.1:8787`, running as `sabre-gate`. Full read and full control. Never exposed to the internet. This is where secrets management, envelope editing, and any privileged mutation live.

**Hosted mirror** — a small cloud application at a stable URL, serving a **read-only** snapshot of company state. The Mac connects outbound to publish; the cloud never connects inbound to the Mac. There is no tunnel, no port forward, no exposed service on the agent host, and no network path from the internet to the gate.

The asymmetry is deliberate. Reading from anywhere is the actual requirement. Writing from anywhere is already solved — Slack is the remote control plane, and it is authenticated, audited, and mobile-native by default. Approvals happen by reaction in `#approvals`. Direction happens in `#directives`. There is therefore no reason to build an internet-facing write path into a machine that holds live payment credentials, and every reason not to.

### 18.2 Publisher

`sabre-push`, running as `sabre-gate`, publishes a snapshot on a 60-second cadence and immediately on any material event (venture state change, intent decision, revenue, alert).

- Outbound HTTPS only, to one pinned host, with a bearer token held on the gate side.
- Payload is a computed projection — never a database dump, never raw rows.
- Publishing failures are non-blocking. A cloud outage must never stall the company. Missed publishes surface as a staleness banner on the mirror and an alert after 15 minutes.
- The snapshot is generated by the gate, so a compromised agent cannot alter what the operator sees remotely.

### 18.3 Redaction on publish

The mirror is the only component whose contents leave the machine, so the projection is filtered before it goes.

| Category | Local console | Hosted mirror |
|---|---|---|
| Financial aggregates, venture state, envelope headroom | Full | Full |
| Individual transactions | Full | Amount, category, venture — no external references |
| Event log | Full | Tool, target class, outcome, duration — arguments dropped |
| Outreach records | Full | Counts and outcomes only. **No recipient names, emails, or message bodies** |
| Account registry | Full | Platform and status only, no handles |
| Secrets | Names, tier, usage metadata | **Nothing. The screen does not exist remotely** |
| Credentials, tokens, keys | Never rendered anywhere | Never published |

The outreach line matters most: raw logs contain third-party personal data, and pushing that to a cloud host turns an internal tool into a data-protection obligation. Counts and outcomes carry all the signal the operator needs at a glance.

### 18.4 Authentication

Single operator, so no user system. Passkey (WebAuthn) bound to the operator's devices, with a recovery code held offline. No password, no email-link fallback — magic links inherit the security of the email account and become the weakest edge. Sessions expire in 12 hours. Every authentication attempt, successful or not, posts to `#status`.

### 18.5 The one permitted remote mutation

The hosted mirror exposes exactly one write action: **kill**.

It does not reach into the Mac. It sets a flag in the snapshot store; the local watcher polls it every 30 seconds and, on seeing it, engages the local kill switch. The path is pull-only from the Mac's side.

This exception is justified by its failure mode. If an attacker takes the mirror, the worst they achieve is stopping the company — recoverable in one local command. Every other mutation has an unsafe failure mode and therefore stays local or goes through Slack. The rule generalizes: an internet-facing control surface may only expose actions whose abuse is fail-safe.

### 18.6 Screens

| Screen | Local | Mirror |
|---|---|---|
| Overview — 30-day net, envelope headroom, active ventures, blocking requests, heartbeat | ✓ | ✓ |
| Ventures — status, spend, revenue, net, days alive, distance to each kill criterion | ✓ | ✓ |
| Money — transactions, card balances, inference cost, refunds, burn curve | ✓ | ✓ (aggregated) |
| Intents — every gated action with class, dissent, decision, timing | ✓ | ✓ (read) |
| Logs — full event stream, filterable; trace viewer | ✓ | ✓ (redacted) |
| Board — task board mirror | ✓ | ✓ |
| Skills & lessons — promotion state, uses, net contribution | ✓ | ✓ |
| Accounts — registry, rate usage, suspension status | ✓ | Partial |
| Secrets — name, tier, last used, error rate, rotate | ✓ | — |
| Envelopes — ceilings, usage, auto-raise, edit | ✓ | Read only |
| Kill | ✓ | ✓ |

Mobile-first layout on the mirror. The Overview must be readable and comprehensible on a phone in under ten seconds; that is its whole purpose.

### 18.7 Hosting

The mirror is a stateless application plus a small managed datastore, deployed to any commodity platform. It holds only published snapshots. Losing it entirely costs a redeploy and a re-publish — no company state lives there. It is explicitly **not** a component the company depends on to operate.

No separate frontend build step on the Mac side — a Node dev server alongside the agent and a browser will not fit comfortably in 8 GB. The mirror builds and runs in the cloud, where memory is not the constraint.

---

## 19. Scheduling and liveness

| Job | Cadence | Action |
|---|---|---|
| Heartbeat | 5 min | Write record; watcher alerts on 15-min gap |
| Main loop | 30 min | Claim highest-value ready task, work it |
| Opportunity scan | Daily 06:00 | Generate and score venture candidates |
| Status digest | Daily 08:00 | Post to `#status` |
| Kill sweep | Daily 09:00 | Evaluate every venture, auto-kill breaches |
| Reconciliation | Daily 02:00 | Gate vs. all providers |
| Weekly review | Mon 08:00 | Net position, promotions, envelope asks |
| Persona sync | Weekly | Diff upstream catalog |
| Snapshot publish | 60 s, and on event | Push redacted projection to the hosted mirror |
| Remote-kill poll | 30 s | Watcher checks the mirror's kill flag |
| Backup | Daily | Database, `work/`, config to encrypted destination |

Sleep is the most likely cause of silent death. The installer configures a keep-awake assertion and prevents sleep on power. The watcher posts to `#status` on a missed heartbeat — the operator should never discover a two-day outage by noticing the quiet.

---

## 20. Safety and failure modes

### 20.1 Kill switch

A file owned by the operator, mode 444, checked by the gate before every execution and by the watcher every 30 seconds. Present → all intents refused, agent sessions terminated, scheduled jobs unloaded. The agent cannot create, delete, or modify it. Also reachable via `sabre kill`, the dashboard, and a Slack command.

### 20.2 Runaway spend

Four independent brakes, in decreasing dependence on software: per-transaction ceiling, rolling daily ceiling, per-venture virtual card limit, and a hard monthly cap on the funding account set outside the system entirely. The outermost brake must not depend on the software that might be failing.

### 20.3 Prompt injection

Every fetched page, email reply, and DM is assumed to potentially contain instructions aimed at SABRE.

- Fetched content is wrapped in an explicit data boundary; the system prompt states that content inside it is information, never instruction.
- Provenance is tracked per intent. Any intent whose chain includes untrusted content and whose effect touches money or identity escalates to Amber minimum. Tracked mechanically, not judged by the agent.
- Tier-2 credentials and card ceilings remain unreachable regardless of persuasion. That is the actual defense; the rest is mitigation.

### 20.4 State corruption

`work/` is a git repository committed on every write and backed up daily. `core/` is protected and version-controlled. The database is owned by another user and backed up nightly with restore tested by `sabre restore --dry-run`.

### 20.5 Platform and legal events

Any ban, suspension, cease-and-desist, or payment dispute triggers immediate venture kill, account marked suspended, Red gate on revival, and a blocking post to `#requests`. These are precisely the events where autonomous continuation is the worst outcome.

### 20.6 Alert conditions

Missed heartbeat. Reconciliation divergence. Envelope at 80%. Red intent pending over 24h. Gate failure rate above 10%. Inference spend above 2× the 7-day average. Card approaching exhaustion. Any account status change. Snapshot publish failing for over 15 minutes. Any authentication attempt against the hosted mirror.

---

## 21. Resource budget

| Component | Approx. RSS |
|---|---|
| macOS baseline | ~3.0 GB |
| Agent runtime | 0.5–0.9 GB |
| 2 subagents | 0.3–0.6 GB |
| Browser (agent profile, headless) | 0.5–1.0 GB |
| Container VM, if credential proxy sandboxing enabled | 1.0–2.0 GB |
| Gate, web, hooks, watcher | ~0.2 GB |
| Headroom | ~0.5 GB |

Two supported postures. **Lean:** no container sandbox, Tier-2 secrets deferred, browser and subagents run freely. **Hardened:** container sandbox and credential proxy active, browser work serialized against subagent batches. `sabre setup` asks which, records it, and `sabre doctor` enforces the corresponding concurrency caps. Running a browser, a container VM, and three subagents together will swap.

---

## 22. Repository layout

```
sabre/
  install.sh
  pyproject.toml
  README.md
  core/                          # protected; agent proposes, gate merges
    gate/                        # policy engine, classifier, executors
    web/                         # dashboard
    hooks/                       # webhook receivers
    push/                        # snapshot projection + publisher
    watch/                       # heartbeat + kill switch
    cli/                         # sabre command
    setup/                       # wizard steps, doctor checks
    schema.sql
    migrations/
    channels/*.md                # channel contracts
    envelopes.yaml
    accounts.yaml
    personas/                    # converted persona skills
    launchd/*.plist.tmpl
  mirror/                        # hosted read-only dashboard (deployed separately)
  work/                          # agent's writable world (git repo)
    COMPANY.md
    board/
    ventures/
    scratch/
  tests/
```

---

## 23. Build phases

Each phase has an acceptance test. No phase starts before the previous passes.

| Phase | Deliverable | Acceptance |
|---|---|---|
| 0 | `install.sh`, CLI skeleton, three OS users | `sabre` cannot read the operator's home |
| 1 | Agent runtime installed and configured | Terminal chat runs a shell command |
| 2 | Slack app, gateway service, channel contracts | Message in `#directives` gets a reply; survives reboot |
| 3 | Schema, migrations, event tap | A green intent executes and appears in events and `#logs` |
| 4 | Policy engine, envelopes, classification, `#approvals` | Over-ceiling intent blocks; under-ceiling executes silently |
| 5 | Virtual card issuance and charging | A venture's card exhausts and further spend fails at the network |
| 6 | Local console | Overview shows a real venture and real spend |
| 6b | Hosted mirror, publisher, passkey auth | Operator reads live state on a phone off-network; remote kill engages within 60s |
| 7 | Account registry, dedicated browser profile | Agent posts to its own account and provably cannot reach the operator's |
| 8 | Persona conversion, team assembly, delegation lint | A 3-persona team completes a delegated build task |
| 9 | Webhooks, revenue ingest, reconciliation | A test payment appears in `#revenue` and reconciles |
| 10 | Kill criteria, postmortems, lessons, skill promotion | A venture auto-kills and produces a promoted lesson |
| 11 | Credential proxy, Tier-2 migration | Agent charges a card and provably cannot read the key |
| 12 | `sabre doctor` full suite, backup/restore | Clean-machine install to first agent turn under 45 min |
| 13 | First live venture | First dollar |

Phases 3–5 precede the dashboard and the personas deliberately. An agent with specialist teams and no ledger is an agent spending money that cannot be accounted for.

---

## 24. Open decisions

1. **Legal entity.** Ventures taking payment need an entity and a bank account. Whose name, and what does that imply for §7.3? Blocks phase 9.
2. **Envelope sizing.** The figures in §6.1 are placeholders. What monthly amount are you willing to lose entirely?
3. **Card provider.** Determines phase 5 and the strength of Layer 1.
4. **Posture.** Lean or hardened at first run (§21).
5. **Inference budget.** $25/day is a guess and will be the largest cost line before anything earns.
6. **Disclosure level.** Platform minimum, or tighter at some conversion cost.
7. **Backup destination.** Encrypted local volume, or an off-machine location the agent cannot reach.
8. **Mirror hosting and domain.** Which platform, which URL, and who holds the deploy credentials — noting the mirror's publish token is itself a Tier-1 secret on the gate.

---

## 25. Definition of done for v1

A clean Mac reaches a running SABRE in under 45 minutes. It then runs unattended for seven consecutive days: starts at least one venture, spends real money inside its envelope without asking, posts a daily status readable in thirty seconds, asks no more than three questions in the week, and produces at least one postmortem and one promoted skill. The dashboard accounts for every dollar. At no point does it touch an account or a credential it was not given, and at no point does it spend past a ceiling.

Revenue is the goal but not the completion criterion. A correct harness that has not yet earned is something you can iterate on. An earning system you cannot audit is one you will eventually have to switch off.
