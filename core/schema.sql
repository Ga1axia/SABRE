-- SABRE ledger. One SQLite database, owned by sabre-gate, WAL mode.
-- The agent never opens this file. All access is through gate I1.

CREATE TABLE IF NOT EXISTS ventures (
  id            TEXT PRIMARY KEY,
  slug          TEXT UNIQUE NOT NULL,
  name          TEXT NOT NULL,
  thesis        TEXT NOT NULL,
  icp           TEXT,
  status        TEXT NOT NULL,
  kill_criteria TEXT NOT NULL,
  card_id       TEXT,
  created_at    TEXT NOT NULL,
  closed_at     TEXT,
  close_reason  TEXT
);

CREATE TABLE IF NOT EXISTS tasks (
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

CREATE TABLE IF NOT EXISTS intents (
  id              TEXT PRIMARY KEY,
  venture_id      TEXT REFERENCES ventures(id),
  task_id         TEXT REFERENCES tasks(id),
  kind            TEXT NOT NULL,
  classification  TEXT NOT NULL,
  payload         TEXT NOT NULL,
  idempotency_key TEXT UNIQUE NOT NULL,
  rationale       TEXT NOT NULL,
  dissent         TEXT,
  provenance      TEXT,
  state           TEXT NOT NULL,
  hold_until      TEXT,
  slack_ts        TEXT,
  created_at      TEXT NOT NULL,
  decided_at      TEXT,
  executed_at     TEXT,
  error           TEXT
);

CREATE TABLE IF NOT EXISTS transactions (
  id           TEXT PRIMARY KEY,
  venture_id   TEXT REFERENCES ventures(id),
  intent_id    TEXT REFERENCES intents(id),
  direction    TEXT NOT NULL,
  amount_cents INTEGER NOT NULL,
  currency     TEXT NOT NULL DEFAULT 'USD',
  category     TEXT NOT NULL,
  source       TEXT NOT NULL,
  card_id      TEXT,
  external_id  TEXT,
  reversed_by  TEXT REFERENCES transactions(id),
  occurred_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cards (
  id            TEXT PRIMARY KEY,
  venture_id    TEXT REFERENCES ventures(id),
  provider_ref  TEXT NOT NULL,
  limit_cents   INTEGER NOT NULL,
  spent_cents   INTEGER NOT NULL DEFAULT 0,
  status        TEXT NOT NULL,
  issued_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  trace_id    TEXT,
  venture_id  TEXT,
  session_id  TEXT,
  actor       TEXT NOT NULL,
  tool        TEXT,
  args        TEXT,
  status      TEXT,
  duration_ms INTEGER,
  tokens_in   INTEGER,
  tokens_out  INTEGER,
  cost_cents  INTEGER,
  occurred_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
  id         TEXT PRIMARY KEY,
  platform   TEXT NOT NULL,
  handle     TEXT,
  owner      TEXT NOT NULL,
  credential TEXT NOT NULL,
  status     TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rate_usage (
  account_id  TEXT REFERENCES accounts(id),
  window_date TEXT NOT NULL,
  action      TEXT NOT NULL,
  count       INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (account_id, window_date, action)
);

CREATE TABLE IF NOT EXISTS skills (
  id            TEXT PRIMARY KEY,
  name          TEXT NOT NULL,
  status        TEXT NOT NULL,
  uses          INTEGER DEFAULT 0,
  net_cents     INTEGER DEFAULT 0,
  created_at    TEXT NOT NULL,
  promoted_at   TEXT,
  retired_at    TEXT,
  retire_reason TEXT
);

CREATE TABLE IF NOT EXISTS lessons (
  id         TEXT PRIMARY KEY,
  venture_id TEXT REFERENCES ventures(id),
  context    TEXT NOT NULL,
  expected   TEXT NOT NULL,
  happened   TEXT NOT NULL,
  rule       TEXT NOT NULL,
  status     TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS postmortems (
  id              TEXT PRIMARY KEY,
  venture_id      TEXT REFERENCES ventures(id),
  believed        TEXT NOT NULL,
  did             TEXT NOT NULL,
  happened        TEXT NOT NULL,
  earliest_signal TEXT,
  created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS heartbeats (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  service TEXT NOT NULL,
  at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS schema_migrations (
  id   TEXT PRIMARY KEY,
  applied_at TEXT NOT NULL
);
