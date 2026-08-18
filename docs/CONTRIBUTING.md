# Contributing to SABRE

Read [Architecture & Setup](SABRE-ARCHITECTURE-SETUP.md) §3–§8 and §17 before changing core.

## Adding a provider driver

1. Implement the protocol in `core/drivers/<capability>/<name>.py`.
2. Register the entry point in `pyproject.toml`.
3. Add a wizard step fragment under `core/setup/steps/drivers/` if the driver needs credentials.
4. Add contract tests. The shared suite in `tests/drivers/` runs against every driver.
5. Document required credentials and their tier.

Payment drivers must implement `is_internal_payer` correctly. Returning `False` unconditionally credits SABRE-issued cards as revenue. The contract test issues a memory card, pays from it, and asserts `ingest_payment` does not write a credit.

## Adding a policy rule

Rules live in `core/gate/rules/`, run in fixed order, and each returns `allow | escalate | deny` with a reason. Rules must be pure functions of the intent plus ledger state — no network, no clock beyond an injected timestamp.

## Non-negotiables

Changes that violate any of these are rejected:

- The agent gains no direct database handle.
- The agent gains no path to Tier-2 credential values.
- No inbound connection to the agent host.
- No new intent kind defaults to green.
- No revenue write path outside the webhook receiver.
- No mutation endpoint on the hosted mirror except kill.

## Dev install

```bash
uv sync --extra dev
python -m sabre --help
pytest
```

`SABRE_DEV=1` skips OS-user creation. Isolation checks remain fatal. `sabre up --dev` is required. Never treat skipped isolation as passed.
