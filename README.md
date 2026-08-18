# SABRE

Self-improving Agent Business Recursive Engine.

An installable autonomous company. One agent identifies revenue opportunities, spins up ventures, spends inside pre-authorized envelopes, and reports to one human through Slack.

SABRE starts with only a Slack workspace and an inference key. Cards, payments, hosting, and the hosted mirror are optional and can be enabled later without reinstalling.

## Quickstart

macOS 12+ or Linux, ≥ 8 GB RAM:

```bash
curl -fsSL https://raw.githubusercontent.com/<org>/sabre/main/install.sh | bash
sabre setup
sabre doctor
sabre up
```

Then open `#directives` in Slack. First run is **no-spend mode**: SABRE researches and builds but cannot buy anything until you run `sabre setup --step 10`.

Replace `<org>` with the GitHub org or user that hosts this repo.

## What you get

| Command | Purpose |
|---|---|
| `sabre setup` | Resumable wizard (Slack, isolation, envelopes) |
| `sabre doctor` | Preflight. Hard gate on `sabre up` |
| `sabre up` | Start services in dependency order |
| `sabre status` | One-screen summary |
| `sabre kill` | Engage the kill switch |

Local console (never internet-exposed): `http://127.0.0.1:8787`

## Docs

- [Product requirements](docs/SABRE-PRD.md)
- [Architecture and setup](docs/SABRE-ARCHITECTURE-SETUP.md)
- [First-run checklist](docs/FIRST-RUN.md)
- [Contributing](docs/CONTRIBUTING.md)

## Development

From a checkout (Python 3.11+):

```bash
uv sync --extra dev
python -m sabre --help
pytest
```

`SABRE_DEV=1` skips OS-user creation. Isolation checks remain **fatal** and are reported failed. `sabre up --dev` waives **only** `isolation.*` fatals — never schema, Slack, inference, ceilings, or the kill switch. Skipped isolation is never treated as passed.

## License

MIT
