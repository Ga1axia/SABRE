# SABRE — Architecture & Setup Specification

Implementation and wiring companion to the PRD.
v1.0 · 17 August 2026

The PRD defines what SABRE does and why. This document defines how the pieces connect, what each file is, what every interface carries, and the exact sequence that takes a stranger from `git clone` to a running autonomous company. Anything a contributor or self-hoster needs that isn't a product requirement lives here.

---

## 1. Audience and assumptions

Written for two readers:

- **The self-hoster** — has a machine, a Slack workspace, and a card. Wants it running today. Reads §9–§13.
- **The contributor** — wants to add a provider driver, change the gate, or port to another host. Reads §3–§8 and §17.

Assumed available: a POSIX host, a Slack workspace where they can install apps, an inference provider account. Everything else — payments, virtual cards, hosting, a legal entity — is optional at first run and gated behind capability flags. **SABRE must start and be useful with only a Slack workspace and an inference key.** That is a hard design constraint, not a nicety: a setup that demands a business bank account before the first agent turn will never be tried by anyone.

---

## 2. Topology

SABRE ships two supported topologies. The wizard asks once and records the answer; every downstream config derives from it.

### 2.1 `solo` — single host

Everything on one machine, isolated by OS user. Simplest, cheapest, fewest moving parts. Chosen by default for first-time setup.

Costs: the host is a single point of failure for the ledger and the gate, and the hosted mirror needs a separate deploy.

### 2.2 `split` — agent local, control plane remote (recommended for production)

The agent runs on the operator's machine, where the RAM and the browser are. The gate, database, webhook receiver, and dashboard run on a small VPS, where uptime and reachability are.

| Component | `solo` | `split` |
|---|---|---|
| Agent runtime | Local | Local |
| Browser profile | Local | Local |
| Venture working tree | Local | Local |
| Policy engine (gate) | Local, user `sabre-gate` | VPS |
| Database | Local | VPS |
| Webhook receiver | Local + tunnel | VPS, public endpoint |
| Credential proxy | Local | VPS |
| Dashboard | Local console + published mirror | Single hosted dashboard |

`split` is better on every axis except cost and setup time: the ledger survives the laptop, webhooks need no tunnel, credentials never sit on the same disk as the agent, and the dashboard is reachable without a publish-mirror dance. The trade is a VPS and one more step in the wizard.

**Everything below is written topology-agnostic.** Components address each other through a resolved endpoint, never a hardcoded socket, so the same code runs in both modes.

---

## 3. Component map

```
                        ┌────────────────────────┐
   Slack  ◄────────────►│   agent (runtime)      │  user: sabre
                        │   personas, browser,   │
                        │   venture worktree     │
                        └───────────┬────────────┘
                                    │ HTTPS + mTLS
                                    │ (intents, reads)
                        ┌───────────▼────────────┐
   Providers ◄─────────►│   gate (policy)        │  user: sabre-gate
   (cards, pay,         │   classify, execute,   │
    hosting)            │   reconcile, ledger    │
                        └──┬──────┬─────────┬────┘
                           │      │         │
              ┌────────────▼┐  ┌──▼──────┐ ┌▼────────────┐
              │  database   │  │  proxy  │ │  web / push │
              └─────────────┘  └────┬────┘ └──────┬──────┘
                                    │             │
                          agent egress ───►   dashboard / mirror
                                                  │
   Slack  ◄──────── hooks (payments) ────────────┘
```

Six services. Each is a separate process with a single responsibility and no shared memory.

| Service | Responsibility | Holds |
|---|---|---|
| `agent` | Reasoning, delegation, tool use, browser, code | Tier-1 credentials only |
| `gate` | Classification, execution, ledger writes, reconciliation | Tier-2 credentials, DB write |
| `proxy` | Credential injection at network boundary | Tier-2 values in memory |
| `hooks` | Inbound webhooks from payment and provider APIs | Webhook signing secrets |
| `web` | Dashboard (console and/or hosted) | Read session keys |
| `watch` | Heartbeat, kill switch, alerting | Nothing |

---

## 4. Interfaces

Every arrow in §3, exhaustively. If an interaction isn't in this table, it isn't allowed.

| # | From → To | Transport | Auth | Direction | Carries |
|---|---|---|---|---|---|
| I1 | agent → gate | HTTPS/JSON | mTLS client cert, per-install | Request/response | Intent submission, ledger reads, task claims |
| I2 | gate → agent | none | — | — | **No inbound path.** Gate never calls the agent |
| I3 | agent → proxy | HTTPS via `HTTPS_PROXY` | Opaque proxy tokens | Outbound | All external agent traffic |
| I4 | proxy → internet | HTTPS | Real credentials, injected | Outbound | Provider and platform API calls |
| I5 | gate → providers | HTTPS | Real credentials | Outbound | Charges, card issuance, deploys |
| I6 | providers → hooks | HTTPS | Signature verification | Inbound | Payment events, card events, refunds |
| I7 | gate → database | Local socket / file | OS permission | Read/write | Everything |
| I8 | agent → database | via I1 only | — | Read | **Agent never opens the DB directly** |
| I9 | gate → Slack | HTTPS | Bot token | Outbound | Approval posts, alerts, revenue |
| I10 | agent ↔ Slack | Socket Mode WS | App + bot token | Bidirectional | Conversation, logs mirror |
| I11 | push → mirror | HTTPS | Bearer, gate-held | Outbound only | Redacted snapshot |
| I12 | watch → mirror | HTTPS | Bearer | Outbound poll | Remote kill flag |
| I13 | watch → gate | HTTPS | mTLS | Outbound | Heartbeat verification, kill assertion |
| I14 | operator → web | HTTPS | Passkey | Bidirectional | Console and dashboard |

Two invariants worth stating loudly because most mistakes violate one of them:

- **The agent never touches the database directly.** Everything goes through I1. This is what makes the write-permission table in the PRD enforceable rather than aspirational.
- **Nothing initiates a connection *into* the agent host.** Not the gate, not the mirror, not the operator. Every remote interaction is the agent host reaching out.

### 4.1 Gate API

Served over I1. Versioned at `/v1`. All requests carry a client cert; all responses are JSON.

```
POST   /v1/intents                  submit intent → {id, classification, state}
GET    /v1/intents/{id}             poll state
GET    /v1/intents?state=&venture=  list

GET    /v1/ledger/ventures
POST   /v1/ledger/ventures          create venture (agent-writable)
PATCH  /v1/ledger/ventures/{slug}   status, thesis (not financials)
GET    /v1/ledger/transactions      read-only to agent
GET    /v1/ledger/envelopes         current ceilings and headroom

POST   /v1/tasks/{id}/claim         atomic claim with lease
POST   /v1/tasks/{id}/release
POST   /v1/tasks                    create
PATCH  /v1/tasks/{id}

POST   /v1/lessons                  candidate lesson
POST   /v1/postmortems
POST   /v1/skills/{id}/record-use   attaches outcome for promotion math

GET    /v1/accounts                 registry, no credentials
GET    /v1/health
```

Anything not listed does not exist for the agent. Notably absent and deliberately so: any write to `transactions`, any write to `envelopes`, any read of credential values, any endpoint that mutates `accounts`.

### 4.2 Intent schema

```json
{
  "kind": "spend",
  "venture": "geo-audit",
  "task_id": "T-0142",
  "idempotency_key": "spend:geo-audit:namecheap:geoaudit.io:2026-08-17",
  "rationale": "Domain for the landing page. Sole cost of launch.",
  "provenance": [
    {"source": "web_fetch", "host": "namecheap.com", "trust": "untrusted"}
  ],
  "payload": {
    "category": "domains",
    "amount_cents": 1299,
    "currency": "USD",
    "vendor": "namecheap",
    "description": "geoaudit.io, 1 year"
  }
}
```

`idempotency_key` is derived from semantic content, never random — a retry must collide. `provenance` is appended mechanically by the runtime tap, not written by the agent's judgment.

Response:

```json
{
  "id": "I-00871",
  "classification": "green",
  "state": "executed",
  "transaction_id": "TX-00412",
  "card_id": "CARD-geo-audit"
}
```

---

## 5. Repository layout

```
sabre/
  install.sh                     entry point, POSIX sh, no deps
  uninstall.sh
  pyproject.toml
  README.md                      quickstart only, links here
  LICENSE

  core/
    cli/
      __main__.py                the `sabre` command
      commands/                  one module per verb
    setup/
      wizard.py                  step runner, resumable
      steps/                     one module per step, each: prompt/apply/verify
      doctor.py                  check registry
      checks/                    one module per check
    gate/
      server.py                  I1 endpoint
      classify.py                the policy engine
      rules/                     deny, category, ceiling, rate, provenance
      execute/                   one executor per intent kind
      reconcile.py
      ledger.py
    drivers/                     ← provider abstraction, see §6
      inference/
      cards/
      payments/
      hosting/
      messaging/
    hooks/
      server.py
      verify.py                  per-provider signature verification
    web/
      console.py                 local, full control
      mirror.py                  hosted, read-only
      templates/
    push/
      project.py                 snapshot projection + redaction
      publish.py
    watch/
      heartbeat.py
      killswitch.py
      alert.py
    runtime/
      tap.py                     tool-call event hook
      redact.py
      provenance.py
      personas/convert.py        catalog → runtime skills
    schema.sql
    migrations/NNNN_*.sql
    channels/*.md                channel contracts, verbatim prompts
    services/                    launchd + systemd templates
    slack/manifest.yaml.tmpl

  config/                        user-owned, gitignored after first write
    sabre.yaml                   topology, capabilities, paths
    envelopes.yaml
    accounts.yaml
    personas.yaml                which bundles are enabled

  work/                          agent's writable world, separate git repo
    COMPANY.md
    board/
    ventures/
    scratch/

  mirror/                        hosted dashboard, deployed separately
  tests/
  docs/
```

`core/` is protected: owned by root or the gate user, not writable by the agent. `config/` and `work/` are the only mutable surfaces, and `config/` only via the gate.

---

## 6. Provider drivers

The single most important thing for "anyone can use this." Nothing in `core/` names a specific vendor. Every external capability is a driver with a fixed interface, selected in config, discovered by entry point.

```yaml
# config/sabre.yaml
drivers:
  inference:  { name: <provider>,  model_core: <id>, model_worker: <id>, model_review: <id> }
  messaging:  { name: slack }
  cards:      { name: <issuer>,    enabled: false }
  payments:   { name: <processor>, enabled: false }
  hosting:    { name: <platform>,  enabled: true }
```

### 6.1 Interfaces

```python
class CardDriver(Protocol):
    def issue(self, venture: str, limit_cents: int) -> Card: ...
    def freeze(self, card_id: str) -> None: ...
    def close(self, card_id: str) -> None: ...
    def balance(self, card_id: str) -> Balance: ...
    def list_transactions(self, card_id: str, since: str) -> list[Charge]: ...

class PaymentDriver(Protocol):
    def verify_webhook(self, body: bytes, headers: Mapping) -> Event | None: ...
    def list_charges(self, since: str) -> list[Charge]: ...
    def refunds(self, since: str) -> list[Refund]: ...
    def is_internal_payer(self, charge: Charge) -> bool: ...   # circular-revenue guard

class HostingDriver(Protocol):
    def deploy(self, path: str, project: str) -> Deployment: ...
    def domains(self, project: str) -> list[str]: ...
    def teardown(self, project: str) -> None: ...

class MessagingDriver(Protocol):
    def post(self, channel: str, blocks: list) -> str: ...
    def react_listener(self, cb: Callable) -> None: ...
    def ensure_channels(self, names: list[str]) -> dict[str, str]: ...

class InferenceDriver(Protocol):
    def complete(self, messages, model, tools=None) -> Completion: ...
    def usage(self, since: str) -> Usage: ...      # for cost attribution
```

`is_internal_payer` is not optional. A payment driver that cannot tell whether a charge came from a card SABRE itself issued lets the agent manufacture its own revenue signal, and the fitness function stops meaning anything.

### 6.2 Capability degradation

Missing drivers degrade rather than block.

| Missing | Effect |
|---|---|
| cards | `no-spend mode`: all spend intents → Red, ceilings inert. Everything else runs |
| payments | Revenue tracking disabled; ventures cannot be scored; kill criteria fall back to time and spend only |
| hosting | Deploy intents → Red with a `#requests` post |
| messaging | Fatal. Slack is the control plane |
| inference | Fatal |

**No-spend mode is the default first run.** A new user gets a working, thinking, planning, code-writing agent within an hour, with money wired up later once they've decided they want it. This is the difference between a repo people try and a repo people bounce off.

---

## 7. Configuration model

Three layers, later overriding earlier:

1. `core/defaults.yaml` — shipped, never edited
2. `config/*.yaml` — user-owned, written by the wizard, editable
3. Environment — `SABRE_*` prefix, for secrets and CI

```
SABRE_HOME                  install root, default ~/.sabre
SABRE_TOPOLOGY              solo | split
SABRE_GATE_URL              resolved endpoint for I1
SABRE_DB_URL
SABRE_SLACK_BOT_TOKEN
SABRE_SLACK_APP_TOKEN
SABRE_OPERATOR_ID           Slack member ID, the allowlist
SABRE_INFERENCE_KEY
SABRE_MIRROR_URL
SABRE_MIRROR_TOKEN
SABRE_KILL_FILE
```

Secrets never land in `config/*.yaml`. The wizard writes them to the environment file owned by the gate user, mode 600, or into the proxy store for Tier 2.

**No values in this repo are operator-specific.** There is no baked-in name, handle, domain, or workspace. Everything identifying comes from the wizard.

---

## 8. Data flow: one action, end to end

Worth reading once, because every subtle bug in this system is a violation of this sequence.

1. Cron fires the main loop. The agent claims the highest-priority ready task via `POST /v1/tasks/{id}/claim`.
2. The agent plans. It assembles a persona team and delegates subtasks. Every tool call is written to `events` by the runtime tap, with provenance recorded for anything fetched.
3. A subagent concludes a domain must be bought. The agent submits an intent (§4.2) via I1.
4. The gate classifies: deny rules → account registry → category → ceilings → rate windows → provenance escalation. Result: green.
5. The gate checks the idempotency key. Not seen before.
6. The gate calls the card driver, charging the venture's card. **If the card is exhausted, the charge fails at the network regardless of what the gate believed.**
7. The gate writes a `transactions` debit and updates `cards.spent_cents`.
8. The gate returns the result on I1. The agent proceeds.
9. The tap mirrors a filtered line to `#logs`. The push service publishes a new snapshot within 60 seconds.
10. Overnight, reconciliation compares the gate's transactions against the card issuer and the payment processor. Divergence beyond tolerance escalates.

If the intent had classified Amber, step 6 waits for the hold window while a post sits in `#approvals` carrying the adversarial dissent. If Red, it waits for a reaction.

---

## 9. Install

```bash
curl -fsSL https://raw.githubusercontent.com/<org>/sabre/main/install.sh | bash
```

`install.sh` is POSIX sh with no dependencies beyond `curl` and `git`. It:

1. Detects OS and arch. Refuses unsupported platforms with a named reason.
2. Verifies RAM, disk, and required commands.
3. Installs `uv` and a pinned Python into `$SABRE_HOME/runtime` — never touching system Python.
4. Clones the repo to `$SABRE_HOME/app` at a pinned tag.
5. Creates a venv, installs the package.
6. Installs the agent runtime.
7. Symlinks `sabre` onto PATH.
8. Prints exactly one next command.

It does **not**: create OS users, start services, open network connections beyond package fetches, or write anything outside `$SABRE_HOME` and one PATH symlink.

Idempotent. Re-running upgrades the app and leaves `config/` and `work/` untouched. `uninstall.sh` reverses everything except `work/` and `config/`, which it moves aside with a timestamp and tells you where.

---

## 10. Setup wizard

`sabre setup`. State in `$SABRE_HOME/config/setup.json`. Every step is `prompt → apply → verify`, and a failed verify halts with a remediation string rather than continuing.

Resume with `sabre setup --resume`. Re-run one step with `sabre setup --step N`.

| # | Step | Prompts | Writes | Verifies |
|---|---|---|---|---|
| 1 | Topology | solo or split; VPS host if split | `sabre.yaml` | Reachability if split |
| 2 | OS users | sudo password | Users, home dirs, permissions | Agent user cannot read operator home |
| 3 | Database | — | `sabre.db`, migrations | Schema at head |
| 4 | Certificates | — | mTLS CA, gate cert, agent client cert | Handshake succeeds |
| 5 | Inference | Provider, key, model tier choices | Env file | Live completion returns; usage API returns a cost |
| 6 | Slack app | Opens browser with pre-filled manifest; paste two tokens | Env file | `auth.test` succeeds |
| 7 | Operator identity | Slack member ID (auto-detected, confirmed) | `sabre.yaml` | ID resolves to a real user |
| 8 | Channels | Confirm names or accept defaults | Channel IDs | Bot is a member of each; round trip on each |
| 9 | Envelopes | Monthly loss tolerance → derives all ceilings | `envelopes.yaml` | Synthetic over-ceiling intent is refused |
| 10 | Cards *(optional)* | Issuer, key, funding limit | Proxy store | Test card issues and freezes |
| 11 | Payments *(optional)* | Processor, key, webhook URL | Proxy store, hooks config | Test webhook verifies |
| 12 | Hosting *(optional)* | Platform, token | Env or proxy | Test deploy of a static file |
| 13 | Browser profile | — | Isolated profile dir | Launches; cookie jar is empty and separate |
| 14 | Personas | Which bundles | `personas.yaml`, converted skills | Skills load; count matches |
| 15 | Mirror *(optional)* | Deploy target, or skip | Mirror URL and token | Snapshot round trip; passkey enrolled |
| 16 | Services | — | launchd/systemd units | All services start and report healthy |
| 17 | Kill switch | sudo | Kill file, operator-owned, 444 | Agent user cannot delete it |
| 18 | Company identity | Company name, what it will and won't do | `work/COMPANY.md` | File committed |

Step 9 deserves note: it asks one human question — *what monthly amount are you willing to lose entirely?* — and derives every ceiling from it. Asking a new user for six separate limits produces six arbitrary numbers. Asking for one produces a considered one.

Steps 10–12 and 15 are skippable. Skipping puts the corresponding capability in degraded mode per §6.2 and prints how to enable it later.

### 10.1 Slack app creation

Step 6 generates a manifest from `core/slack/manifest.yaml.tmpl` and opens the browser to Slack's app-creation page with it pre-filled. The user creates the app, enables Socket Mode, installs to workspace, and pastes two tokens back.

Required scopes:

```
bot:  app_mentions:read, channels:history, channels:join, channels:manage,
      channels:read, chat:write, commands, groups:history, groups:read,
      reactions:read, reactions:write, users:read
events: message.channels, message.groups, app_mention,
        reaction_added, reaction_removed
slash: /sabre, /kill, /status, /approve, /veto
```

Changing scopes later requires reinstalling the app. The wizard says so at the point where it matters, not in a footnote.

### 10.2 Channel bootstrap

Step 8 creates any missing channels, joins them, posts a pinned contract summary to each, and verifies a round trip. Bots do not auto-join; the wizard invites explicitly. The pinned message is how a new operator learns what each channel is for without reading this document.

---

## 11. Doctor

`sabre doctor` is a hard gate on `sabre up`. Checks are registered modules with `id`, `severity`, `run()`, and `remedy`.

**Fatal** — blocks start.

| ID | Check |
|---|---|
| `env.python` | Pinned interpreter present and correct |
| `db.schema` | At migration head |
| `certs.mtls` | Agent↔gate handshake succeeds |
| `inference.live` | Completion returns; cost accounting returns figures |
| `slack.auth` | Tokens valid, Socket Mode connects |
| `slack.channels` | Every required channel exists, bot is a member |
| `isolation.home` | Agent user **cannot** read operator home |
| `isolation.browser` | Agent user **cannot** read operator browser profile |
| `isolation.secrets` | Agent user **cannot** read the credential store |
| `isolation.db` | Agent user **cannot** open the database file directly |
| `isolation.core` | Agent user **cannot** write `core/` |
| `gate.ceiling` | Synthetic over-ceiling intent is refused |
| `gate.unknown` | Synthetic unknown-kind intent classifies Red |
| `killswitch` | Present, operator-owned, mode 444, agent cannot delete |

The five `isolation.*` checks are active adversarial tests, not permission inspections. Doctor literally attempts the read as the agent user and requires failure. A permission bit that looks right and behaves wrong is exactly the bug this catches.

**Warning** — starts but reports.

`mem.headroom`, `disk.free`, `sleep.disabled`, `backup.recent`, `providers.optional`, `mirror.reachable`, `reconcile.clean`, `personas.synced`.

`sabre doctor --json` for CI. `sabre doctor --fix` applies the subset of remedies that are safe to automate and prints the rest.

---

## 12. Services

Templates in `core/services/`, rendered at step 16 with resolved paths and users.

| Unit | User | Depends on | Restart |
|---|---|---|---|
| `sabre-gate` | gate | database | always, 5s backoff |
| `sabre-proxy` | gate | — | always |
| `sabre-hooks` | gate | gate | always |
| `sabre-web` | gate | gate | always |
| `sabre-agent` | agent | gate, proxy | always, 15s backoff |
| `sabre-push` | gate | gate | always |
| `sabre-watch` | operator | — | always |

Start order matters: the agent refuses to start if the gate is unreachable, and says so rather than running ungated. `sabre up` starts in dependency order and waits for each health check.

On macOS: launchd plists in the appropriate `LaunchAgents`/`LaunchDaemons` directory per user, plus a keep-awake assertion and a check that sleep-on-power is disabled. On Linux: systemd units, user or system scope by topology.

---

## 13. First run

What the operator actually sees, end to end.

```
$ curl -fsSL .../install.sh | bash
  ✓ macOS 14.4, 8 GB RAM, 42 GB free
  ✓ runtime installed
  ✓ sabre 1.0.0
  → next: sabre setup

$ sabre setup
  [1/18] Topology .................. solo
  [2/18] OS users .................. created, isolation verified
  ...
  [9/18] Envelopes
         What monthly amount are you willing to lose entirely? $600
         → per-transaction $25 · daily $75 · per-venture $200 · monthly $600
         ✓ over-ceiling intent refused
  [10/18] Cards .................... skipped (no-spend mode)
  ...
  [18/18] Company identity ......... work/COMPANY.md written
  Setup complete. Run: sabre doctor

$ sabre doctor
  ✓ 14 fatal checks passed
  ⚠ backup.recent — no backup yet (sabre backup)
  ⚠ providers.optional — cards, payments not configured (no-spend mode)
  Ready.

$ sabre up
  ✓ gate · proxy · hooks · web · agent · push · watch
  Console: http://127.0.0.1:8787
  Slack:   #directives

# in #directives
  SABRE: I'm up. No spend capability configured, so I'll research
  and build but can't buy anything yet. I've read COMPANY.md.
  What should I look at first?
```

Under 45 minutes, and the last 40 of it is Slack app creation and reading prompts.

---

## 14. Upgrade and migration

```bash
sabre upgrade            # pinned tag → latest, with migration
sabre upgrade --to 1.2.0
```

Sequence: stop services → back up database and config → fetch → run forward migrations → `sabre doctor` → start. Any failure rolls back to the prior tag and restores the database snapshot. Migrations are forward-only and numbered; there are no down-migrations, because rollback is by snapshot restore, which is the only mechanism that actually works under partial failure.

Config gains new keys with shipped defaults on upgrade. Removed keys are warned about, never silently dropped.

---

## 15. Backup and recovery

`sabre backup` writes an encrypted archive of the database, `config/`, `work/`, and the credential store manifest — never credential values. Daily by schedule, on demand by command, and always immediately before upgrade.

`sabre restore <snapshot>` stops services, restores, migrates forward, runs doctor, restarts. `--dry-run` verifies an archive without touching live state, and should be run monthly. An untested backup is not a backup.

Recovery scenarios:

| Lost | Recovery |
|---|---|
| Database | Restore snapshot, re-reconcile against providers to close the gap |
| `work/` | git remote, or snapshot |
| Whole machine | Fresh install, restore, re-enroll Slack tokens and certificates |
| Mirror | Redeploy, republish. No company state lives there |
| Credential store | Rotate every Tier-2 credential at the provider. Values are unrecoverable by design |

---

## 16. Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| Agent silent in Slack | Socket Mode dropped | `sabre logs --service agent`; restart |
| Every intent classifies Red | Envelope file unparseable, or unknown kinds | `sabre envelope show`; check gate logs |
| Intents pile up in `#approvals` | Ceilings too tight for actual work | Raise, or add classification for the recurring kind |
| Tool calls time out mysteriously | Memory pressure and swap | Reduce `max_concurrent_children`; check §21 of the PRD |
| Reconciliation freezes spend nightly | Provider API flakiness | Check tolerance band; retries before freeze |
| Mirror stale | Publish failing | `sabre logs --service push`; verify token |
| Doctor fails `isolation.*` | Permissions drifted after an OS update | `sabre setup --step 2` |

Every service logs structured JSON to `$SABRE_HOME/logs/<service>.jsonl`, rotated daily, and `sabre logs` is the unified reader.

---

## 17. Contributing

### 17.1 Adding a provider driver

1. Implement the protocol in `core/drivers/<capability>/<name>.py`.
2. Register the entry point in `pyproject.toml`.
3. Add a wizard step fragment under `core/setup/steps/drivers/`.
4. Add contract tests — the shared suite runs against every driver, and a new driver passes it or is not merged.
5. Document required credentials and their tier.

Payment drivers additionally must implement `is_internal_payer` correctly. A driver that returns `False` unconditionally will pass the type checker and silently break the fitness function; the contract test covers this specifically.

### 17.2 Adding a policy rule

Rules live in `core/gate/rules/`, run in fixed order, and each returns `allow | escalate | deny` with a reason string. Rules must be pure functions of the intent plus ledger state — no network, no clock beyond an injected timestamp — so they are testable and their decisions reproducible from the ledger alone.

### 17.3 Non-negotiables for contributors

Changes that violate any of these are rejected regardless of merit:

- The agent gains no direct database handle.
- The agent gains no path to Tier-2 credential values.
- No inbound connection to the agent host.
- No new intent kind defaults to green.
- No revenue write path outside the webhook receiver.
- No mutation endpoint on the hosted mirror except kill.

---

## 18. Security notes for self-hosters

Read before running with real money.

- **The isolation is only as good as the OS user separation.** If you run everything as one user because it was faster, you have a system with no security properties. Doctor will tell you; do not `--force` past it.
- **A virtual card limit is your real ceiling.** Software limits are defense in depth, not the boundary. Fund the card with what you can lose.
- **Your inference bill is the largest cost before anything earns.** Set a hard cap at the provider, not just in config.
- **Anything the agent publishes is attributable to you.** Domains, accounts, and outreach carry your reputation, not the agent's.
- **Prospect data in logs is personal data.** If you enable the hosted mirror, redaction is on by default. Do not turn it off.
- **The repo has no telemetry.** If a fork asks to phone home, that is a fork, not this project.

---

## 19. Acceptance

This document is done when a person who has never seen the project can, from a clean machine and this repo alone:

1. Install, complete setup, and pass doctor in under 45 minutes.
2. Get a substantive agent reply in `#directives` on first run without configuring payments.
3. Enable spending later without reinstalling.
4. Read §3 and §4 and correctly predict which component talks to which, over what, in which direction.
5. Add a driver for a provider nobody anticipated, without modifying `core/`.
