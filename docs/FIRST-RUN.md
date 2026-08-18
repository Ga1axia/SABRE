# Manual first-run (macOS or Linux)

Do this on a POSIX machine. Native Windows is not a target.

1. `./install.sh` (or `curl …/install.sh | bash` once published) → `sabre` on PATH.
2. `sabre setup` with cards, payments, hosting, and mirror skipped. Isolation proofs fail-closed unless OS users were created.
3. Contributor path: `SABRE_DEV=1 SABRE_SKIP_LIVE=1 sabre setup` then `sabre up --dev`. Isolation checks stay fatal; `--dev` is explicit.
4. `sabre doctor` — fatals green on a real Mac with users + Slack + key; warnings for backup/optional providers.
5. `sabre up` → message in `#directives` gets a reply that has read `COMPANY.md`.
6. Re-run `install.sh` does not wipe `config/` or `work/`.
7. `sabre setup --step 10` is the path out of no-spend mode.
