import json
import os
import sqlite3
from dataclasses import asdict
from typing import Dict, List, Optional

from app.models import Criterion, Delivery, Job, Offer

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
DB_PATH = os.path.join(DB_DIR, 'bulwark.db')
DELIVERIES_DIR = os.path.join(DB_DIR, 'deliveries')


def get_db_path() -> str:
    return os.environ.get('BULWARK_DB', DB_PATH)


def installation_id() -> str:
    """A random id minted once per database, kept in the meta
    table. It scopes every PayPal idempotency key: job ids repeat
    across databases (each fresh install, demo redeploy or test DB
    starts at 1), while PayPal replays the original response for a
    repeated PayPal-Request-Id — without the scope, a new database
    could be handed a previous database's orders and captures."""
    import secrets
    conn = sqlite3.connect(get_db_path())
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS meta "
                     "(key TEXT PRIMARY KEY, value TEXT)")
        row = conn.execute(
            "SELECT value FROM meta WHERE key = 'installation_id'"
        ).fetchone()
        if row:
            return row[0]
        value = secrets.token_hex(5)
        conn.execute(
            "INSERT INTO meta (key, value) VALUES "
            "('installation_id', ?)", (value,))
        conn.commit()
        return value
    finally:
        conn.close()


def set_job_terms(job_id: int, terms: dict, narrative: str, model: str, degraded: int) -> None:
    """Store Settlement Brain terms and narrative for a job."""
    conn = sqlite3.connect(get_db_path())
    conn.execute(
        """
        UPDATE jobs
           SET terms_verification_mode = ?,
               terms_vesting_hours = ?,
               terms_trust_credit_percent = ?,
               terms_stake_percent = ?,
               brain_narrative = ?,
               brain_model = ?,
               brain_degraded = ?
         WHERE id = ?
        """,
        (
            terms.get("verification_mode", ""),
            terms.get("vesting_hours", -1),
            terms.get("trust_credit_percent", -1),
            terms.get("stake_percent", -1),
            narrative,
            model,
            degraded,
            job_id,
        ),
    )
    conn.commit()
    conn.close()


def ensure_db() -> None:
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(get_db_path())
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT NOT NULL,
            description TEXT NOT NULL,
            price_cents INTEGER NOT NULL,
            currency    TEXT NOT NULL DEFAULT 'USD',
            state       TEXT NOT NULL DEFAULT 'posted',
            criteria    TEXT NOT NULL DEFAULT '[]',
            created_at  TEXT NOT NULL
        )
        """
    )
    # --- Migration: add PayPal vault columns ---
    # Migration-safe: only add columns that do not already exist.
    cols = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    alters = {
        'paypal_order_id':
            "ALTER TABLE jobs ADD COLUMN paypal_order_id TEXT DEFAULT ''",
        'paypal_authorization_id':
            "ALTER TABLE jobs ADD COLUMN paypal_authorization_id TEXT DEFAULT ''",
        'authorization_status':
            "ALTER TABLE jobs ADD COLUMN authorization_status TEXT DEFAULT ''",
        'funded_amount_cents':
            "ALTER TABLE jobs ADD COLUMN funded_amount_cents INTEGER DEFAULT 0",
        'funded_currency':
            "ALTER TABLE jobs ADD COLUMN funded_currency TEXT DEFAULT ''",
        'funded_at':
            "ALTER TABLE jobs ADD COLUMN funded_at TEXT DEFAULT ''",
        'paypal_error':
            "ALTER TABLE jobs ADD COLUMN paypal_error TEXT DEFAULT ''",
        # --- settlement columns ---
        'capture_id':
            "ALTER TABLE jobs ADD COLUMN capture_id TEXT DEFAULT ''",
        'capture_status':
            "ALTER TABLE jobs ADD COLUMN capture_status TEXT DEFAULT ''",
        'captured_amount_cents':
            "ALTER TABLE jobs ADD COLUMN captured_amount_cents INTEGER DEFAULT 0",
        'captured_currency':
            "ALTER TABLE jobs ADD COLUMN captured_currency TEXT DEFAULT ''",
        'captured_at':
            "ALTER TABLE jobs ADD COLUMN captured_at TEXT DEFAULT ''",
        'payout_batch_id':
            "ALTER TABLE jobs ADD COLUMN payout_batch_id TEXT DEFAULT ''",
        'payout_items':
            "ALTER TABLE jobs ADD COLUMN payout_items TEXT DEFAULT '[]'",
        'settled_at':
            "ALTER TABLE jobs ADD COLUMN settled_at TEXT DEFAULT ''",
        'settle_error':
            "ALTER TABLE jobs ADD COLUMN settle_error TEXT DEFAULT ''",
    # --- refund / revision columns ---
    'refund_id':
        "ALTER TABLE jobs ADD COLUMN refund_id TEXT DEFAULT ''",
    'refund_status':
        "ALTER TABLE jobs ADD COLUMN refund_status TEXT DEFAULT ''",
    'refunded_at':
        "ALTER TABLE jobs ADD COLUMN refunded_at TEXT DEFAULT ''",
    'revision_used':
        "ALTER TABLE jobs ADD COLUMN revision_used INTEGER DEFAULT 0",
    # --- Settlement Brain storage ---
    'terms_verification_mode':
        "ALTER TABLE jobs ADD COLUMN terms_verification_mode TEXT DEFAULT ''",
    'terms_vesting_hours':
        "ALTER TABLE jobs ADD COLUMN terms_vesting_hours INTEGER DEFAULT -1",
    'terms_trust_credit_percent':
        "ALTER TABLE jobs ADD COLUMN terms_trust_credit_percent INTEGER DEFAULT -1",
    'terms_stake_percent':
        "ALTER TABLE jobs ADD COLUMN terms_stake_percent INTEGER DEFAULT -1",
    'brain_narrative':
        "ALTER TABLE jobs ADD COLUMN brain_narrative TEXT DEFAULT ''",
    'brain_model':
        "ALTER TABLE jobs ADD COLUMN brain_model TEXT DEFAULT ''",
    'brain_degraded':
        "ALTER TABLE jobs ADD COLUMN brain_degraded INTEGER DEFAULT 0",
    # --- trust credit storage ---
    'trust_credit_state':
        "ALTER TABLE jobs ADD COLUMN trust_credit_state TEXT DEFAULT ''",
    'advance_capture_id':
        "ALTER TABLE jobs ADD COLUMN advance_capture_id TEXT DEFAULT ''",
    'advance_batch_id':
        "ALTER TABLE jobs ADD COLUMN advance_batch_id TEXT DEFAULT ''",
    'advanced_cents':
        "ALTER TABLE jobs ADD COLUMN advanced_cents INTEGER DEFAULT 0",
    'advance_payout_items':
        "ALTER TABLE jobs ADD COLUMN advance_payout_items TEXT DEFAULT ''",
    # --- checker-fee vesting + dispute window ---
    'checker_vesting_state':
        "ALTER TABLE jobs ADD COLUMN checker_vesting_state TEXT DEFAULT ''",
    'checker_vesting_amount_cents':
        "ALTER TABLE jobs ADD COLUMN checker_vesting_amount_cents INTEGER DEFAULT 0",
    'checker_release_at':
        "ALTER TABLE jobs ADD COLUMN checker_release_at TEXT DEFAULT ''",
    'checker_released_batch_id':
        "ALTER TABLE jobs ADD COLUMN checker_released_batch_id TEXT DEFAULT ''",
    'checker_released_item_id':
        "ALTER TABLE jobs ADD COLUMN checker_released_item_id TEXT DEFAULT ''",
    'dispute_state':
        "ALTER TABLE jobs ADD COLUMN dispute_state TEXT DEFAULT ''",
    'dispute_reason':
        "ALTER TABLE jobs ADD COLUMN dispute_reason TEXT DEFAULT ''",
    'dispute_opened_at':
        "ALTER TABLE jobs ADD COLUMN dispute_opened_at TEXT DEFAULT ''",
    'dispute_resolved_at':
        "ALTER TABLE jobs ADD COLUMN dispute_resolved_at TEXT DEFAULT ''",
    # --- demo cast tagging ('' | active | archived) ---
    'demo_tag':
        "ALTER TABLE jobs ADD COLUMN demo_tag TEXT DEFAULT ''",
    # --- Price negotiation: 'fixed' | 'open' (posted without a price) ---
    'price_mode':
        "ALTER TABLE jobs ADD COLUMN price_mode TEXT DEFAULT 'fixed'",
    # --- circle × price posting model ---
    'circle':
        "ALTER TABLE jobs ADD COLUMN circle TEXT DEFAULT ''",
    'invited_worker_id':
        "ALTER TABLE jobs ADD COLUMN invited_worker_id INTEGER DEFAULT 0",
    }
    for col, sql in alters.items():
        if col not in cols:
            conn.execute(sql)

    # --- Migration: deliveries.is_revision ---
    dcols = {row[1] for row in conn.execute("PRAGMA table_info(deliveries)").fetchall()}
    if dcols and "is_revision" not in dcols:
        conn.execute("ALTER TABLE deliveries ADD COLUMN is_revision INTEGER DEFAULT 0")

    # --- job_events (timeline / audit trail) ---
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS job_events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id      INTEGER NOT NULL,
            kind        TEXT NOT NULL,
            actor       TEXT NOT NULL DEFAULT '',
            source      TEXT NOT NULL DEFAULT 'action',
            detail      TEXT NOT NULL DEFAULT '{}',
            created_at  TEXT NOT NULL,
            FOREIGN KEY (job_id) REFERENCES jobs(id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_job_events_job_id "
        "ON job_events(job_id)"
    )

    # --- parties & reputation (foundation) ---
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS parties (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            kind        TEXT NOT NULL,
            form        TEXT NOT NULL,
            payout_email TEXT,
            created_at  TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reputation_events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            party_id    INTEGER NOT NULL,
            job_id      INTEGER NOT NULL,
            kind        TEXT NOT NULL,
            detail      TEXT NOT NULL DEFAULT '{}',
            created_at  TEXT NOT NULL,
            FOREIGN KEY (party_id) REFERENCES parties(id),
            FOREIGN KEY (job_id) REFERENCES jobs(id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_reputation_events_party_id "
        "ON reputation_events(party_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_reputation_events_job_id "
        "ON reputation_events(job_id)"
    )
    # Reputation events are once-per-(party, job, kind) by design
    # (the counters are plain row counts), but the emissions were
    # check-then-insert or unconditional inserts, so two concurrent
    # closings of the same job double-counted it. Enforce once-only
    # in the schema: collapse any duplicate rows (keeping the
    # earliest of each triple), then a unique index makes every
    # emission atomic — the call sites use INSERT OR IGNORE, so a
    # racing duplicate is a no-op, never an error and never a
    # second count. One-time migration: it runs only while the
    # unique index does not exist yet.
    _rep_once_idx = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'index' "
        "AND name = 'idx_reputation_events_once'"
    ).fetchone()
    if _rep_once_idx is None:
        conn.execute(
            "DELETE FROM reputation_events WHERE id NOT IN "
            "(SELECT MIN(id) FROM reputation_events "
            "GROUP BY party_id, job_id, kind)"
        )
        conn.execute(
            "CREATE UNIQUE INDEX idx_reputation_events_once "
            "ON reputation_events(party_id, job_id, kind)"
        )
        # Commit now: the DELETE above opened an implicit
        # transaction, and the seed block below issues its own
        # explicit BEGIN TRANSACTION.
        conn.commit()

    # Seed built-in parties idempotently
    conn.execute("BEGIN TRANSACTION")
    try:
        # Check if parties table is empty
        count = conn.execute("SELECT COUNT(*) FROM parties").fetchone()[0]
        if count == 0:
            # Insert built-in parties
            conn.execute(
                "INSERT INTO parties (name, kind, form, payout_email, created_at) VALUES (?, ?, ?, ?, ?)",
                ("Default Client", "client", "human", "", _now())
            )
            conn.execute(
                "INSERT INTO parties (name, kind, form, payout_email, created_at) VALUES (?, ?, ?, ?, ?)",
                ("Default Worker", "worker", "human", "worker@example.com", _now())
            )
            conn.execute(
                "INSERT INTO parties (name, kind, form, payout_email, created_at) VALUES (?, ?, ?, ?, ?)",
                ("Verifier Prime", "checker", "agent", "checker@example.com", _now())
            )
            conn.execute(
                "INSERT INTO parties (name, kind, form, payout_email, created_at) VALUES (?, ?, ?, ?, ?)",
                ("Bulwark Platform", "platform", "company",
                 os.environ.get("PAYPAL_SANDBOX_BUSINESS_EMAIL") or "platform@example.com", _now())
            )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e

    # Add job party columns with migration safety
    cols = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    job_party_cols = {
        'client_id': 'ALTER TABLE jobs ADD COLUMN client_id INTEGER DEFAULT 1',
        'worker_id': 'ALTER TABLE jobs ADD COLUMN worker_id INTEGER DEFAULT 2',
        'checker_id': 'ALTER TABLE jobs ADD COLUMN checker_id INTEGER DEFAULT 3',
    }
    for col, sql in job_party_cols.items():
        if col not in cols:
            conn.execute(sql)

    # Backfill existing jobs to built-in parties
    conn.execute("BEGIN TRANSACTION")
    try:
        jobs_with_party_ids = conn.execute("SELECT id FROM jobs WHERE (client_id IS NULL OR client_id = 0) AND (worker_id IS NULL OR worker_id = 0) AND (checker_id IS NULL OR checker_id = 0)").fetchall()
        for (job_id,) in jobs_with_party_ids:
            conn.execute("UPDATE jobs SET client_id = 1, worker_id = 2, checker_id = 3 WHERE id = ?", (job_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e

    # Party certifications (public credentials on the profile).
    pcols2 = {row[1] for row in conn.execute(
        "PRAGMA table_info(parties)").fetchall()}
    if pcols2 and "certifications" not in pcols2:
        conn.execute(
            "ALTER TABLE parties ADD COLUMN certifications "
            "TEXT DEFAULT '[]'")

    _ensure_deliveries_table(conn)
    _ensure_checks_table(conn)
    _ensure_offers_table(conn)
    conn.commit()
    conn.close()


def _ensure_offers_table(conn: sqlite3.Connection) -> None:
    """Price negotiation: offers on posted jobs. An offer is only
    ever live while its job is in 'posted' state; acceptance is the
    single write that locks the job's price (and, on an open job,
    its worker)."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS offers (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id      INTEGER NOT NULL,
            worker_id   INTEGER NOT NULL,
            amount_cents INTEGER NOT NULL,
            currency    TEXT NOT NULL DEFAULT 'USD',
            kind        TEXT NOT NULL DEFAULT 'bid',
            status      TEXT NOT NULL DEFAULT 'pending',
            created_at  TEXT NOT NULL,
            decided_at  TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (job_id) REFERENCES jobs(id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_offers_job_id ON offers(job_id)")
    conn.commit()


def _ensure_deliveries_table(conn: sqlite3.Connection) -> None:
    """Migration: deliveries table."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS deliveries (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id      INTEGER NOT NULL,
            filename    TEXT NOT NULL,
            stored_name TEXT NOT NULL,
            size_bytes  INTEGER NOT NULL,
            sha256      TEXT NOT NULL,
            uploaded_at TEXT NOT NULL,
            note        TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (job_id) REFERENCES jobs(id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_deliveries_job_id "
        "ON deliveries(job_id)"
    )
    conn.commit()


def _ensure_checks_table(conn: sqlite3.Connection) -> None:
    """Migration: checks table — stores the itemized verdict."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS checks (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id            INTEGER NOT NULL,
            overall_pass      INTEGER NOT NULL,
            verdict_json      TEXT NOT NULL,
            judged_model      TEXT NOT NULL DEFAULT '',
            checked_at       TEXT NOT NULL,
            fraud_signal      TEXT DEFAULT '',
            similarity_max    REAL DEFAULT -1,
            similarity_job_id INTEGER DEFAULT -1,
            csv_dup_ratio     REAL DEFAULT -1,
            is_appeal         INTEGER DEFAULT 0,
            FOREIGN KEY (job_id) REFERENCES jobs(id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_checks_job_id "
        "ON checks(job_id)"
    )
    # birth certificates for settled jobs.
    conn.execute(
        """CREATE TABLE IF NOT EXISTS certificates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            serial TEXT UNIQUE,
            job_id INTEGER UNIQUE,
            issued_at TEXT,
            code TEXT,
            facts_json TEXT
        )"""
    )
    # service-call log (API + UI money actions) and
    # per-party API keys (hashed at rest; plaintext shown once).
    conn.execute(
        """CREATE TABLE IF NOT EXISTS service_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER,
            actor TEXT NOT NULL DEFAULT '',
            via TEXT NOT NULL DEFAULT '',
            action TEXT NOT NULL DEFAULT '',
            endpoint TEXT NOT NULL DEFAULT '',
            request_summary TEXT NOT NULL DEFAULT '',
            response_status INTEGER NOT NULL DEFAULT 0,
            paypal_ids TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT ''
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_service_calls_job_id "
        "ON service_calls(job_id)"
    )
    pcols = {row[1] for row in conn.execute(
        "PRAGMA table_info(parties)").fetchall()}
    if pcols and "api_key_hash" not in pcols:
        conn.execute(
            "ALTER TABLE parties ADD COLUMN api_key_hash TEXT DEFAULT ''")
    # Ensure the new columns exist on pre-existing DBs (defensive).
    cols = {row[1] for row in conn.execute("PRAGMA table_info(checks)").fetchall()}
    for col, sql in {
        'fraud_signal': "ALTER TABLE checks ADD COLUMN fraud_signal TEXT DEFAULT ''",
        'similarity_max': "ALTER TABLE checks ADD COLUMN similarity_max REAL DEFAULT -1",
        'similarity_job_id': "ALTER TABLE checks ADD COLUMN similarity_job_id INTEGER DEFAULT -1",
        'csv_dup_ratio': "ALTER TABLE checks ADD COLUMN csv_dup_ratio REAL DEFAULT -1",
        'is_appeal': "ALTER TABLE checks ADD COLUMN is_appeal INTEGER DEFAULT 0",
        'is_dispute': "ALTER TABLE checks ADD COLUMN is_dispute INTEGER DEFAULT 0",
    }.items():
        if col not in cols:
            conn.execute(sql)
    conn.commit()


def _checks_row_to_verdict(row) -> Optional[Dict]:
    """Build a verdict dict from a checks row READ BY COLUMN NAME
    (same migration-history lesson as the jobs table — the
    checks table grew columns by ALTER in different eras, so positional
    reads are unsafe. Callers pass sqlite3.Row rows.)"""
    if row is None:
        return None
    d = dict(row)
    try:
        verdict = json.loads(d.get("verdict_json") or "{}")
    except (TypeError, json.JSONDecodeError, ValueError):
        verdict = {}

    def _f(name, default):
        v = d.get(name)
        return default if v is None else v

    return {
        "id": d["id"],
        "job_id": d["job_id"],
        "overall_pass": bool(d["overall_pass"]),
        "verdict": verdict,
        "judged_model": d.get("judged_model") or "",
        "checked_at": d.get("checked_at") or "",
        "fraud_signal": d.get("fraud_signal") or "",
        "similarity_max": float(_f("similarity_max", -1)),
        "similarity_job_id": int(_f("similarity_job_id", -1)),
        "csv_dup_ratio": float(_f("csv_dup_ratio", -1)),
        "is_appeal": int(_f("is_appeal", 0)),
        "is_dispute": int(_f("is_dispute", 0)),
        "incomplete": bool(verdict.get("incomplete", False)),
    }


def store_check_with_originality(check_id: int, fraud_signal: str, similarity_max: float, similarity_job_id: int, csv_dup_ratio: float, is_appeal: int = -1, is_dispute: int = -1) -> None:
    """Store originality analysis results for a check."""
    conn = sqlite3.connect(get_db_path())
    conn.execute(
        """
        UPDATE checks
           SET fraud_signal = ?,
               similarity_max = ?,
               similarity_job_id = ?,
               csv_dup_ratio = ?
         WHERE id = ?
        """,
        (fraud_signal, similarity_max, similarity_job_id, csv_dup_ratio, check_id),
    )
    if is_appeal >= 0:
        conn.execute(
            "UPDATE checks SET is_appeal = ? WHERE id = ?",
            (is_appeal, check_id),
        )
    if is_dispute >= 0:
        conn.execute(
            "UPDATE checks SET is_dispute = ? WHERE id = ?",
            (is_dispute, check_id),
        )
    conn.commit()
    conn.close()


def store_verdict(verdict) -> int:
    """Persist a Verdict (from app.checker) for a job. Returns the check id.
    
    Emits reputation events exactly once: only when this is the job's FIRST
    verdict. Worker party gets verdict_pass_first or verdict_fail_first;
    checker party gets verdict_issued."""
    verdict_json = json.dumps({
        "job_id": verdict.job_id,
        "overall_pass": verdict.overall_pass,
        "checked_at": verdict.checked_at,
        "judge_model": verdict.judge_model,
        "items": [asdict(it) for it in verdict.items],
        "incomplete": bool(getattr(verdict, "incomplete", False)),
    }, default=str)
    conn = sqlite3.connect(get_db_path())
    _ensure_checks_table(conn)
    
    # Check if this is the first verdict for this job.
    # incomplete runs (judge unavailable) are stored for
    # the record but are not verdicts for reputation purposes —
    # the "first verdict" below means the first COMPLETED one,
    # so a completed check after an incomplete attempt still
    # emits its first-verdict events exactly once.
    existing_count = conn.execute(
        "SELECT COUNT(*) FROM checks WHERE job_id = ?",
        (verdict.job_id,)
    ).fetchone()[0]
    completed_count = 0
    for (prior_json,) in conn.execute(
            "SELECT verdict_json FROM checks WHERE job_id = ?",
            (verdict.job_id,)).fetchall():
        try:
            if not json.loads(prior_json).get("incomplete"):
                completed_count += 1
        except (ValueError, TypeError):
            completed_count += 1
    
    cursor = conn.execute(
        """
        INSERT INTO checks
            (job_id, overall_pass, verdict_json, judged_model, checked_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (verdict.job_id, 1 if verdict.overall_pass else 0, verdict_json,
         verdict.judge_model, verdict.checked_at),
    )
    conn.commit()
    check_id = cursor.lastrowid
    
    # Get job's party assignments
    job_row = conn.execute(
        "SELECT worker_id, checker_id FROM jobs WHERE id = ?",
        (verdict.job_id,)
    ).fetchone()
    
    worker_party_id = job_row[0] if job_row and job_row[0] else 2  # default to Default Worker
    checker_party_id = job_row[1] if job_row and job_row[1] else 3  # default to Verifier Prime
    
    # Emit reputation events exactly once (only on first verdict).
    # dual/appeal runs suppress this and emit the combined /
    # final outcome themselves via emit_verdict_events.
    if completed_count == 0 and not getattr(verdict, "suppress_first_events", False) and not getattr(verdict, "incomplete", False):
        verdict_kind = "pass" if verdict.overall_pass else "fail"
        # Worker gets verdict_pass_first or verdict_fail_first
        conn.execute(
            "INSERT OR IGNORE INTO reputation_events (party_id, job_id, kind, detail, created_at) VALUES (?, ?, ?, ?, ?)",
            (worker_party_id, verdict.job_id, 
             "verdict_pass_first" if verdict.overall_pass else "verdict_fail_first",
             json.dumps({}), _now())
        )
        # Checker gets verdict_issued
        conn.execute(
            "INSERT OR IGNORE INTO reputation_events (party_id, job_id, kind, detail, created_at) VALUES (?, ?, ?, ?, ?)",
            (checker_party_id, verdict.job_id, "verdict_issued",
             json.dumps({}), _now())
        )
        conn.commit()
    
    conn.close()
    return check_id


def get_verdicts(job_id: int) -> List[Dict]:
    """Return all stored verdicts for a job, newest first."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    _ensure_checks_table(conn)
    rows = conn.execute(
        "SELECT * FROM checks WHERE job_id = ? ORDER BY checked_at DESC",
        (job_id,),
    ).fetchall()
    conn.close()
    return [v for v in (_checks_row_to_verdict(r) for r in rows) if v]


def latest_verdict(job_id: int) -> Optional[Dict]:
    vs = get_verdicts(job_id)
    return vs[0] if vs else None


def set_job_checked(job_id: int, passed: bool) -> Job:
    """Transition job state to checked_pass / checked_fail."""
    state = "checked_pass" if passed else "checked_fail"
    conn = sqlite3.connect(get_db_path())
    conn.execute(
        "UPDATE jobs SET state = ? WHERE id = ?",
        (state, job_id),
    )
    conn.commit()
    conn.close()
    return get_job(job_id)


def count_appeals(job_id: int) -> int:
    """How many appeal verdicts exist for a job."""
    conn = sqlite3.connect(get_db_path())
    _ensure_checks_table(conn)
    n = conn.execute(
        "SELECT COUNT(*) FROM checks WHERE job_id = ? AND is_appeal = 1",
        (job_id,),
    ).fetchone()[0]
    conn.close()
    return int(n)


def emit_reputation_event_once(party_id: int, job_id: int, kind: str,
                               detail: Optional[dict] = None) -> bool:
    """Insert a reputation event unless the same (party, job, kind)
    already exists. Returns True when inserted. (dual/appeal/
    fraud paths must not double-emit).

    The old SELECT-then-INSERT let two concurrent callers both
    pass the existence check and both insert. The insert is now a
    single INSERT OR IGNORE against the unique (party_id, job_id,
    kind) index — atomic, so exactly one racer inserts and the
    other is a no-op."""
    conn = sqlite3.connect(get_db_path())
    ensure_db()
    cur = conn.execute(
        "INSERT OR IGNORE INTO reputation_events (party_id, job_id, kind, detail, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (party_id, job_id, kind, json.dumps(detail or {}), _now()),
    )
    conn.commit()
    inserted = cur.rowcount == 1
    conn.close()
    return inserted


def emit_verdict_events(job_id: int, passed: bool) -> None:
    """The first-verdict reputation events (worker's verdict_pass_first /
    verdict_fail_first + checker's verdict_issued), each at most once per
    job. Used by the dual and appeal paths; store_verdict keeps its own
    inline first-verdict emission for the single path."""
    conn = sqlite3.connect(get_db_path())
    row = conn.execute(
        "SELECT worker_id, checker_id FROM jobs WHERE id = ?",
        (job_id,),
    ).fetchone()
    conn.close()
    if row is None:
        return
    worker_id = row[0] or 2
    checker_id = row[1] or 3
    emit_reputation_event_once(
        worker_id, job_id,
        "verdict_pass_first" if passed else "verdict_fail_first")
    emit_reputation_event_once(checker_id, job_id, "verdict_issued")


def _row_to_job(row) -> Job:
    """Build a Job from a sqlite3.Row (or dict) read BY COLUMN NAME.

    gate fix: the jobs table's physical column ORDER depends
    on the database's migration history (each era's ALTERs append in
    the order that era first ran), so positional reads silently swap
    fields on databases created in a different era (observed: terms
    and party columns exchanged on fresh 2.2-era DBs). Name-based
    reads are immune. Callers must pass a Row/dict, not a tuple.
    """
    d = dict(row)

    def _s(name, default=""):
        v = d.get(name)
        return v if v else default

    def _i(name, default=0):
        v = d.get(name)
        return v if v is not None else default

    criteria = [
        Criterion(
            name=c['name'],
            operator=c['operator'],
            expected_value=str(c['expected_value']),
            criterion_type=c['type'],
        )
        for c in json.loads(d.get('criteria') or '[]')
    ]
    def _json_list(name):
        try:
            v = json.loads(_s(name) or "[]")
            return v if isinstance(v, list) else []
        except (ValueError, TypeError):
            return []

    payout_items = _json_list('payout_items')
    return Job(
        id=d['id'],
        title=d['title'],
        description=d['description'],
        price_cents=d['price_cents'],
        currency=d['currency'],
        state=d['state'],
        created_at=d['created_at'],
        criteria=criteria,
        paypal_order_id=_s('paypal_order_id'),
        paypal_authorization_id=_s('paypal_authorization_id'),
        authorization_status=_s('authorization_status'),
        funded_amount_cents=_i('funded_amount_cents'),
        funded_currency=_s('funded_currency'),
        funded_at=_s('funded_at'),
        paypal_error=_s('paypal_error'),
        capture_id=_s('capture_id'),
        capture_status=_s('capture_status'),
        captured_amount_cents=_i('captured_amount_cents'),
        captured_currency=_s('captured_currency'),
        captured_at=_s('captured_at'),
        payout_batch_id=_s('payout_batch_id'),
        payout_items=payout_items,
        settled_at=_s('settled_at'),
        settle_error=_s('settle_error'),
        refund_id=_s('refund_id'),
        refund_status=_s('refund_status'),
        refunded_at=_s('refunded_at'),
        revision_used=bool(_i('revision_used')),
        client_id=_i('client_id') or 1,
        # An open (priceless) job has NO worker until an offer is
        # accepted: worker_id is stored NULL and reads back as 0.
        # Every other job keeps the legacy default of party 2.
        worker_id=(d.get('worker_id') if d.get('worker_id') is not None
                   else (0 if d.get('price_mode') == 'open' else 2)),
        checker_id=_i('checker_id') or 3,
        terms_verification_mode=_s('terms_verification_mode'),
        terms_vesting_hours=_i('terms_vesting_hours', -1),
        terms_trust_credit_percent=_i('terms_trust_credit_percent', -1),
        terms_stake_percent=_i('terms_stake_percent', -1),
        brain_narrative=_s('brain_narrative'),
        brain_model=_s('brain_model'),
        brain_degraded=_i('brain_degraded'),
        trust_credit_state=_s('trust_credit_state'),
        advance_capture_id=_s('advance_capture_id'),
        advance_batch_id=_s('advance_batch_id'),
        advanced_cents=_i('advanced_cents'),
        advance_payout_items=_json_list('advance_payout_items'),
        checker_vesting_state=_s('checker_vesting_state'),
        checker_vesting_amount_cents=_i('checker_vesting_amount_cents'),
        checker_release_at=_s('checker_release_at'),
        checker_released_batch_id=_s('checker_released_batch_id'),
        checker_released_item_id=_s('checker_released_item_id'),
        dispute_state=_s('dispute_state'),
        dispute_reason=_s('dispute_reason'),
        dispute_opened_at=_s('dispute_opened_at'),
        dispute_resolved_at=_s('dispute_resolved_at'),
        demo_tag=_s('demo_tag'),
        price_mode=_s('price_mode') or 'fixed',
        circle=_s('circle') or '',
        invited_worker_id=_i('invited_worker_id') or 0,
    )


def list_jobs() -> List[Job]:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM jobs ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [_row_to_job(r) for r in rows]


def get_job(job_id: int) -> Optional[Job]:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM jobs WHERE id = ?", (job_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return _row_to_job(row)


def create_job(title: str, description: str, price_cents: int, currency: str,
               criteria: List[Criterion], client_id: int = 1,
               worker_id: int = 2, checker_id: int = 3,
               price_mode: str = "fixed", circle: str = "", invited_worker_id: int = 0) -> Job:
    """worker_id may be None for an open (priceless) job: it is
    stored NULL and stays unassigned until an offer is accepted."""
    criteria_json = json.dumps(
        [
            {
                'name': c.name,
                'operator': c.operator,
                'expected_value': c.expected_value,
                'type': c.criterion_type,
            }
            for c in criteria
        ]
    )
    from datetime import datetime, timezone
    created_at = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(get_db_path())
    cursor = conn.execute(
        "INSERT INTO jobs (title, description, price_cents, currency, state, criteria, created_at, client_id, worker_id, checker_id, price_mode, circle, invited_worker_id) "
        "VALUES (?, ?, ?, ?, 'posted', ?, ?, ?, ?, ?, ?, ?, ?)",
        (title, description, price_cents, currency, criteria_json, created_at,
         client_id, worker_id, checker_id, price_mode, circle, invited_worker_id),
    )
    job_id = cursor.lastrowid
    # the client party gains a jobs_posted reputation event.
    conn.execute(
        "INSERT OR IGNORE INTO reputation_events (party_id, job_id, kind, detail, created_at) VALUES (?, ?, ?, ?, ?)",
        (client_id, job_id, "jobs_posted", json.dumps({}), created_at),
    )
    conn.commit()
    conn.close()
    return get_job(job_id)


def set_job_trust_credit(job_id: int, capture_id: str, batch_id: str,
                         items: list, advanced_cents: int) -> Job:
    """record a trust-credit advance (partial capture + the
    worker's advance payout batch) on the job."""
    conn = sqlite3.connect(get_db_path())
    conn.execute(
        """
        UPDATE jobs
           SET trust_credit_state = 'advanced',
               advance_capture_id = ?,
               advance_batch_id = ?,
               advanced_cents = ?,
               advance_payout_items = ?
         WHERE id = ?
        """,
        (capture_id, batch_id, advanced_cents,
         json.dumps(items, default=str), job_id),
    )
    conn.commit()
    conn.close()
    return get_job(job_id)


def set_checker_vesting(job_id: int, amount_cents: int, release_at: str) -> None:
    """record the checker fee as vesting at settle time."""
    conn = sqlite3.connect(get_db_path())
    ensure_db()
    conn.execute(
        "UPDATE jobs SET checker_vesting_state = 'vesting', "
        "checker_vesting_amount_cents = ?, checker_release_at = ? "
        "WHERE id = ?", (amount_cents, release_at, job_id))
    conn.commit()
    conn.close()


def set_checker_released(job_id: int, batch_id: str, item_id: str) -> None:
    conn = sqlite3.connect(get_db_path())
    ensure_db()
    conn.execute(
        "UPDATE jobs SET checker_vesting_state = 'released', "
        "checker_released_batch_id = ?, checker_released_item_id = ? "
        "WHERE id = ?", (batch_id, item_id, job_id))
    conn.commit()
    conn.close()


def set_checker_dispute_paid(job_id: int, batch_id: str, item_id: str) -> None:
    conn = sqlite3.connect(get_db_path())
    ensure_db()
    conn.execute(
        "UPDATE jobs SET checker_vesting_state = 'paid_to_client', "
        "checker_released_batch_id = ?, checker_released_item_id = ? "
        "WHERE id = ?", (batch_id, item_id, job_id))
    conn.commit()
    conn.close()


def set_dispute(job_id: int, state: str, reason: str = None,
                opened_at: str = None, resolved_at: str = None) -> None:
    conn = sqlite3.connect(get_db_path())
    ensure_db()
    sets = ["dispute_state = ?"]
    vals = [state]
    if reason is not None:
        sets.append("dispute_reason = ?")
        vals.append(reason)
    if opened_at is not None:
        sets.append("dispute_opened_at = ?")
        vals.append(opened_at)
    if resolved_at is not None:
        sets.append("dispute_resolved_at = ?")
        vals.append(resolved_at)
    vals.append(job_id)
    conn.execute(f"UPDATE jobs SET {', '.join(sets)} WHERE id = ?", vals)
    conn.commit()
    conn.close()


def set_job_funded(job_id: int, paypal_order_id: str,
                   paypal_authorization_id: str, authorization_status: str,
                   funded_amount_cents: int, funded_currency: str) -> Job:
    """Persist the vault funding result and advance job state to `funded`.
    Clears any prior paypal_error on success."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(get_db_path())
    conn.execute(
        """
        UPDATE jobs
           SET paypal_order_id = ?,
               paypal_authorization_id = ?,
               authorization_status = ?,
               funded_amount_cents = ?,
               funded_currency = ?,
               funded_at = ?,
               paypal_error = '',
               state = 'funded'
         WHERE id = ?
        """,
        (paypal_order_id, paypal_authorization_id, authorization_status,
         funded_amount_cents, funded_currency, now, job_id),
    )
    conn.commit()
    conn.close()
    return get_job(job_id)


def set_job_paypal_error(job_id: int, message: str) -> Job:
    """Store a PayPal error on the job for visible surfacing on the detail
    page. The job state is NOT changed — funding failed, do not fake it."""
    conn = sqlite3.connect(get_db_path())
    conn.execute(
        "UPDATE jobs SET paypal_error = ? WHERE id = ?",
        (message, job_id),
    )
    conn.commit()
    conn.close()
    return get_job(job_id)


def add_delivery(job_id: int, filename: str, stored_name: str,
                 size_bytes: int, sha256: str, note: str = "",
                 is_revision: bool = False) -> None:
    """Record a delivered file in the DB. Does NOT change job
    state — the caller advances state to `delivered` separately so the two
    operations are explicit and ordered."""
    from datetime import datetime, timezone
    uploaded_at = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(get_db_path())
    cols = {row[1] for row in conn.execute("PRAGMA table_info(deliveries)").fetchall()}
    if "is_revision" in cols:
        conn.execute(
            """
            INSERT INTO deliveries
                (job_id, filename, stored_name, size_bytes, sha256, uploaded_at, note, is_revision)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (job_id, filename, stored_name, size_bytes, sha256, uploaded_at,
             note, 1 if is_revision else 0),
        )
    else:
        conn.execute(
            """
            INSERT INTO deliveries
                (job_id, filename, stored_name, size_bytes, sha256, uploaded_at, note)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (job_id, filename, stored_name, size_bytes, sha256, uploaded_at, note),
        )
    conn.commit()
    conn.close()


def get_deliveries(job_id: int) -> List[Delivery]:
    """Return all delivery records for a job, newest first."""
    conn = sqlite3.connect(get_db_path())
    rows = conn.execute(
        "SELECT * FROM deliveries WHERE job_id = ? ORDER BY uploaded_at DESC",
        (job_id,),
    ).fetchall()
    conn.close()
    return [
        Delivery(
            id=row[0], job_id=row[1], filename=row[2], stored_name=row[3],
            size_bytes=row[4], sha256=row[5], uploaded_at=row[6], note=row[7],
            is_revision=bool(row[8]) if len(row) > 8 and row[8] else False,
        )
        for row in rows
    ]


def set_job_delivered(job_id: int) -> Job:
    """Advance a job to `delivered`. Money does NOT move."""
    conn = sqlite3.connect(get_db_path())
    conn.execute(
        "UPDATE jobs SET state = 'delivered' WHERE id = ?",
        (job_id,),
    )
    # the worker party gains a jobs_delivered reputation event.
    job_row = conn.execute(
        "SELECT worker_id FROM jobs WHERE id = ?", (job_id,)
    ).fetchone()
    worker_party_id = job_row[0] if job_row and job_row[0] else 2
    conn.execute(
        "INSERT OR IGNORE INTO reputation_events (party_id, job_id, kind, detail, created_at) VALUES (?, ?, ?, ?, ?)",
        (worker_party_id, job_id, "jobs_delivered", json.dumps({}), _now()),
    )
    conn.commit()
    conn.close()
    return get_job(job_id)


# ---------------------------------------------------------------------------
# settlement storage
# ---------------------------------------------------------------------------
def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def set_job_state(job_id: int, state: str) -> Job:
    conn = sqlite3.connect(get_db_path())
    conn.execute("UPDATE jobs SET state = ? WHERE id = ?", (state, job_id))
    conn.commit()
    conn.close()
    return get_job(job_id)


def set_job_captured(job_id: int, capture_id: str, capture_status: str,
                     captured_amount_cents: int, captured_currency: str) -> Job:
    conn = sqlite3.connect(get_db_path())
    conn.execute(
        """
        UPDATE jobs
           SET capture_id = ?, capture_status = ?,
               captured_amount_cents = ?, captured_currency = ?,
               captured_at = ?
         WHERE id = ?
        """,
        (capture_id, capture_status, captured_amount_cents,
         captured_currency, _now(), job_id),
    )
    conn.commit()
    conn.close()
    return get_job(job_id)


def set_job_settled(job_id: int, payout_batch_id: str, payout_items) -> Job:
    """Set job state to 'settled' and emit job_settled reputation event
    for the worker party."""
    conn = sqlite3.connect(get_db_path())
    conn.execute(
        """
        UPDATE jobs
           SET payout_batch_id = ?, payout_items = ?, settled_at = ?,
               settle_error = '', state = 'settled'
         WHERE id = ?
        """,
        (payout_batch_id, json.dumps(payout_items), _now(), job_id),
    )
    
    # Get job's worker party id
    job_row = conn.execute(
        "SELECT worker_id FROM jobs WHERE id = ?",
        (job_id,)
    ).fetchone()
    worker_party_id = job_row[0] if job_row else 2  # default to Default Worker
    
    # Emit job_settled reputation event for worker party
    conn.execute(
        "INSERT OR IGNORE INTO reputation_events (party_id, job_id, kind, detail, created_at) VALUES (?, ?, ?, ?, ?)",
        (worker_party_id, job_id, "job_settled", json.dumps({}), _now())
    )
    _issue_certificate(conn, job_id)
    conn.commit()
    conn.close()
    return get_job(job_id)


def set_job_settle_error(job_id: int, message: str) -> Job:
    conn = sqlite3.connect(get_db_path())
    conn.execute(
        "UPDATE jobs SET settle_error = ?, state = 'settle_error' WHERE id = ?",
        (message, job_id),
    )
    conn.commit()
    conn.close()
    return get_job(job_id)


def set_job_voided_authorization_refusal(job_id: int, message: str) -> Job:
    """Store voided authorization refusal error without changing job state.
    
    FD.2 FIX: Keep job state as checked_pass while storing the refusal error
    for UI display on the job page.
    """
    conn = sqlite3.connect(get_db_path())
    conn.execute(
        "UPDATE jobs SET settle_error = ? WHERE id = ?",
        (message, job_id),
    )
    conn.commit()
    conn.close()
    return get_job(job_id)


def update_payout_items(job_id: int, payout_items) -> None:
    conn = sqlite3.connect(get_db_path())
    conn.execute(
        "UPDATE jobs SET payout_items = ? WHERE id = ?",
        (json.dumps(payout_items), job_id),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# refund / revision storage
# ---------------------------------------------------------------------------
def set_job_refunded(job_id: int, refund_id: str, refund_status: str) -> Job:
    """Set job state to 'refunded' and emit job_refunded_final reputation
    events for the client and worker parties."""
    conn = sqlite3.connect(get_db_path())
    conn.execute(
        """
        UPDATE jobs
           SET refund_id = ?, refund_status = ?, refunded_at = ?,
               state = 'refunded'
         WHERE id = ?
        """,
        (refund_id, refund_status, _now(), job_id),
    )
    
    # Get job's client party id
    job_row = conn.execute(
        "SELECT client_id FROM jobs WHERE id = ?",
        (job_id,)
    ).fetchone()
    client_party_id = job_row[0] if job_row and job_row[0] else 1  # default to Default Client
    
    # Emit job_refunded_final reputation events (client + worker parties;
    # the brief lists jobs refunded-final in both parties' counters).
    conn.execute(
        "INSERT OR IGNORE INTO reputation_events (party_id, job_id, kind, detail, created_at) VALUES (?, ?, ?, ?, ?)",
        (client_party_id, job_id, "job_refunded_final", json.dumps({}), _now())
    )
    worker_row = conn.execute(
        "SELECT worker_id FROM jobs WHERE id = ?", (job_id,)
    ).fetchone()
    worker_party_id = worker_row[0] if worker_row and worker_row[0] else 2
    conn.execute(
        "INSERT OR IGNORE INTO reputation_events (party_id, job_id, kind, detail, created_at) VALUES (?, ?, ?, ?, ?)",
        (worker_party_id, job_id, "job_refunded_final", json.dumps({}), _now())
    )
    conn.commit()
    conn.close()
    return get_job(job_id)


def set_revision_used(job_id: int) -> Job:
    conn = sqlite3.connect(get_db_path())
    conn.execute(
        "UPDATE jobs SET revision_used = 1 WHERE id = ?", (job_id,))
    conn.commit()
    conn.close()
    return get_job(job_id)


# ---------------------------------------------------------------------------
# job events (timeline / audit trail)
# ---------------------------------------------------------------------------
def add_event(job_id: int, kind: str, actor: str = "", source: str = "action",
              detail: Optional[dict] = None, created_at: str = "") -> int:
    conn = sqlite3.connect(get_db_path())
    cursor = conn.execute(
        """
        INSERT INTO job_events (job_id, kind, actor, source, detail, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (job_id, kind, actor, source, json.dumps(detail or {}),
         created_at or _now()),
    )
    conn.commit()
    event_id = cursor.lastrowid
    conn.close()
    return event_id


def get_events(job_id: int) -> List[dict]:
    conn = sqlite3.connect(get_db_path())
    try:
        rows = conn.execute(
            "SELECT * FROM job_events WHERE job_id = ? ORDER BY created_at, id",
            (job_id,),
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []
    conn.close()
    out = []
    for r in rows:
        try:
            detail = json.loads(r[5])
        except (ValueError, TypeError):
            detail = {}
        out.append({
            "id": r[0], "job_id": r[1], "kind": r[2], "actor": r[3],
            "source": r[4], "detail": detail, "created_at": r[6],
        })
    return out


def _row_to_party(row) -> Dict:
    """Party dict read BY COLUMN NAME (the parties table grew
    columns by ALTER in different eras — api_key_hash, then
    certifications — so positional reads are unsafe, the same
    lesson as the jobs table)."""
    d = dict(row)
    try:
        certs = json.loads(d.get("certifications") or "[]")
        if not isinstance(certs, list):
            certs = []
    except (ValueError, TypeError):
        certs = []
    return {
        "id": d["id"],
        "name": d["name"],
        "kind": d["kind"],
        "form": d["form"],
        "payout_email": d.get("payout_email"),
        "created_at": d.get("created_at") or "",
        "certifications": certs,
        "api_key_hash": d.get("api_key_hash") or "",
    }


def get_party(party_id: int) -> Optional[Dict]:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM parties WHERE id = ?", (party_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return _row_to_party(row)


def list_parties() -> List[Dict]:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM parties ORDER BY name"
    ).fetchall()
    conn.close()
    return [_row_to_party(row) for row in rows]


def get_party_counters(party_id: int) -> Dict:
    """Compute a party's reputation counters by counting its rows in
    reputation_events. NO stored counter columns anywhere."""
    conn = sqlite3.connect(get_db_path())
    counts = {
        "jobs_posted": 0,
        "jobs_delivered": 0,
        "verdict_pass_first": 0,
        "verdict_fail_first": 0,
        "job_settled": 0,
        "job_refunded_final": 0,
        "verdict_issued": 0,
        "verdicts_upheld": 0,
        "verdicts_overturned": 0,
        "fraud_flags": False,
    }
    
    # Count all reputation_events for this party
    rows = conn.execute(
        "SELECT kind FROM reputation_events WHERE party_id = ?",
        (party_id,)
    ).fetchall()
    
    _kind_map = {
        "jobs_posted": "jobs_posted",
        "jobs_delivered": "jobs_delivered",
        "verdict_pass_first": "verdict_pass_first",
        "verdict_fail_first": "verdict_fail_first",
        "job_settled": "job_settled",
        "job_refunded_final": "job_refunded_final",
        "verdict_issued": "verdict_issued",
        "verdict_upheld": "verdicts_upheld",
        "verdict_overturned": "verdicts_overturned",
    }
    for row in rows:
        kind = row[0]
        if kind == "fraud_flag":
            counts["fraud_flags"] = True
        elif kind in _kind_map:
            counts[_kind_map[kind]] += 1
    
    conn.close()
    return counts


def store_reputation_event(party_id: int, job_id: int, kind: str, detail: Optional[dict] = None) -> int:
    conn = sqlite3.connect(get_db_path())
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO reputation_events (party_id, job_id, kind, detail, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (party_id, job_id, kind, json.dumps(detail or {}), _now())
    )
    conn.commit()
    event_id = cursor.lastrowid
    conn.close()
    return event_id


def get_party_events(party_id: int) -> List[Dict]:
    conn = sqlite3.connect(get_db_path())
    rows = conn.execute(
        "SELECT * FROM reputation_events WHERE party_id = ? ORDER BY created_at DESC",
        (party_id,)
    ).fetchall()
    conn.close()
    return [
        {
            "id": row[0],
            "party_id": row[1],
            "job_id": row[2],
            "kind": row[3],
            "detail": json.loads(row[4]),
            "created_at": row[5],
        }
        for row in rows
    ]


def create_party(name: str, kind: str, form: str,
                 payout_email: str = "",
                 certifications: Optional[list] = None) -> int:
    """Insert a user-added party and return its id."""
    conn = sqlite3.connect(get_db_path())
    cols = {row[1] for row in conn.execute(
        "PRAGMA table_info(parties)").fetchall()}
    if "certifications" in cols:
        cursor = conn.execute(
            "INSERT INTO parties (name, kind, form, payout_email, "
            "created_at, certifications) VALUES (?, ?, ?, ?, ?, ?)",
            (name, kind, form, payout_email or None, _now(),
             json.dumps(certifications or [])),
        )
    else:
        cursor = conn.execute(
            "INSERT INTO parties (name, kind, form, payout_email, created_at) VALUES (?, ?, ?, ?, ?)",
            (name, kind, form, payout_email or None, _now()),
        )
    party_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return party_id


def set_party_certifications(party_id: int,
                             certifications: list) -> None:
    """Record a party's public certifications (shown on its
    profile). Used by the demo cast to credential existing parties
    idempotently."""
    conn = sqlite3.connect(get_db_path())
    cols = {row[1] for row in conn.execute(
        "PRAGMA table_info(parties)").fetchall()}
    if "certifications" in cols:
        conn.execute(
            "UPDATE parties SET certifications = ? WHERE id = ?",
            (json.dumps(certifications or []), party_id))
        conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# birth certificates
# ---------------------------------------------------------------------------
def _issue_certificate(conn, job_id: int) -> None:
    """Issue the job's birth certificate exactly once, inside the
    settle transaction. Serial BW-<year>-<seq>, seq gapless by
    issuance order; the verification code is a truncated sha256 over
    the certificate's recorded facts."""
    import hashlib
    exists = conn.execute(
        "SELECT COUNT(*) FROM certificates WHERE job_id = ?",
        (job_id,)).fetchone()[0]
    if exists:
        return
    job = conn.execute("SELECT * FROM jobs WHERE id = ?",
                       (job_id,)).fetchone()
    keys = [d[0] for d in conn.execute(
        "SELECT * FROM jobs LIMIT 0").description]

    def g(name, default=""):
        try:
            return job[keys.index(name)]
        except (ValueError, IndexError):
            return default

    year = _now()[:4]
    seq = conn.execute(
        "SELECT COALESCE(MAX(id), 0) + 1 FROM certificates").fetchone()[0]
    serial = f"BW-{year}-{seq:04d}"
    chk = conn.execute(
        "SELECT overall_pass, judged_model FROM checks WHERE job_id = ? "
        "ORDER BY id DESC LIMIT 1", (job_id,)).fetchone()
    facts = {
        "serial": serial,
        "job_id": job_id,
        "title": g("title"),
        "price_cents": g("price_cents", 0),
        "currency": g("currency", "USD"),
        "client_id": g("client_id", 0),
        "worker_id": g("worker_id", 0),
        "checker_id": g("checker_id", 0),
        "verdict_pass": (chk[0] if chk else None),
        "judge_model": (chk[1] if chk else ""),
        "order_id": g("paypal_order_id"),
        "capture_id": g("capture_id"),
        "payout_batch_id": g("payout_batch_id"),
        "issued_at": _now(),
    }
    basis = "|".join(str(facts[k]) for k in sorted(facts))
    code = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]
    facts["code"] = code
    conn.execute(
        "INSERT INTO certificates (serial, job_id, issued_at, code, "
        "facts_json) VALUES (?, ?, ?, ?, ?)",
        (serial, job_id, facts["issued_at"], code, json.dumps(facts)))


def get_certificate_by_job(job_id: int):
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    ensure_db()
    row = conn.execute("SELECT * FROM certificates WHERE job_id = ?",
                       (job_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    d = dict(row)
    d["facts"] = json.loads(d.get("facts_json") or "{}")
    return d


def get_certificate(serial: str):
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    ensure_db()
    row = conn.execute("SELECT * FROM certificates WHERE serial = ?",
                       (serial,)).fetchone()
    conn.close()
    if row is None:
        return None
    d = dict(row)
    d["facts"] = json.loads(d.get("facts_json") or "{}")
    return d


def list_certificates_for_worker(party_id: int):
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    ensure_db()
    rows = conn.execute(
        "SELECT c.* FROM certificates c JOIN jobs j ON j.id = c.job_id "
        "WHERE j.worker_id = ? ORDER BY c.id", (party_id,)).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["facts"] = json.loads(d.get("facts_json") or "{}")
        out.append(d)
    return out


# ---------------------------------------------------------------------------
# demo cast storage helpers
# ---------------------------------------------------------------------------
def set_job_demo_tag(job_id: int, tag: str) -> None:
    conn = sqlite3.connect(get_db_path())
    conn.execute("UPDATE jobs SET demo_tag = ? WHERE id = ?",
                 (tag, job_id))
    conn.commit()
    conn.close()


def archive_active_demo_jobs() -> int:
    """Tag every currently-active demo job as archived (a demo reset
    supersedes the previous run). Returns how many were archived."""
    conn = sqlite3.connect(get_db_path())
    cur = conn.execute(
        "UPDATE jobs SET demo_tag = 'archived' WHERE demo_tag = 'active'")
    n = cur.rowcount
    conn.commit()
    conn.close()
    return n


# ---------------------------------------------------------------------------
# Price negotiation — offers (pre-funding only)
# ---------------------------------------------------------------------------
def _row_to_offer(row) -> Offer:
    d = dict(row)
    return Offer(
        id=d['id'], job_id=d['job_id'], worker_id=d['worker_id'],
        amount_cents=d['amount_cents'],
        currency=d.get('currency') or 'USD',
        kind=d.get('kind') or 'bid',
        status=d.get('status') or 'pending',
        created_at=d.get('created_at') or '',
        decided_at=d.get('decided_at') or '',
    )


def create_offer(job_id: int, worker_id: int, amount_cents: int,
                 currency: str, kind: str) -> Offer:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    _ensure_offers_table(conn)
    cursor = conn.execute(
        "INSERT INTO offers (job_id, worker_id, amount_cents, "
        "currency, kind, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, 'pending', ?)",
        (job_id, worker_id, amount_cents, currency, kind, _now()),
    )
    offer_id = cursor.lastrowid
    conn.commit()
    row = conn.execute("SELECT * FROM offers WHERE id = ?",
                       (offer_id,)).fetchone()
    conn.close()
    return _row_to_offer(row)


def get_offer(offer_id: int) -> Optional[Offer]:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    _ensure_offers_table(conn)
    row = conn.execute("SELECT * FROM offers WHERE id = ?",
                       (offer_id,)).fetchone()
    conn.close()
    return _row_to_offer(row) if row else None


def list_offers(job_id: int) -> List[Offer]:
    """All offers on a job, oldest first (negotiation order)."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    _ensure_offers_table(conn)
    rows = conn.execute(
        "SELECT * FROM offers WHERE job_id = ? ORDER BY id ASC",
        (job_id,)).fetchall()
    conn.close()
    return [_row_to_offer(r) for r in rows]


def accepted_offer(job_id: int) -> Optional[Offer]:
    for o in list_offers(job_id):
        if o.status == 'accepted':
            return o
    return None


def set_offer_status(offer_id: int, status: str) -> None:
    conn = sqlite3.connect(get_db_path())
    _ensure_offers_table(conn)
    conn.execute(
        "UPDATE offers SET status = ?, decided_at = ? WHERE id = ?",
        (status, _now(), offer_id))
    conn.commit()
    conn.close()


def accept_offer(offer_id: int) -> Optional[Offer]:
    """The single locking write of the negotiation: the offer
    becomes 'accepted', every other pending offer on the job is
    superseded, and the job's price is set to the offer amount —
    on an open job its worker is set too. The job row is only
    touched while it is still 'posted'; the service layer checks
    the state first, and the WHERE clause here is the second lock.
    Returns the accepted offer, or None if the job was no longer
    posted (nothing written in that case)."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    _ensure_offers_table(conn)
    row = conn.execute("SELECT * FROM offers WHERE id = ?",
                       (offer_id,)).fetchone()
    if row is None:
        conn.close()
        return None
    offer = _row_to_offer(row)
    job_row = conn.execute(
        "SELECT price_mode, worker_id FROM jobs WHERE id = ?",
        (offer.job_id,)).fetchone()
    if job_row is None:
        conn.close()
        return None
    if job_row[0] == 'open':
        cur = conn.execute(
            "UPDATE jobs SET price_cents = ?, worker_id = ? "
            "WHERE id = ? AND state = 'posted'",
            (offer.amount_cents, offer.worker_id, offer.job_id))
    else:
        # When the job currently has NO worker (NULL or 0), set worker_id from the offer
        # for any price mode; otherwise set only the price
        current_worker_id = job_row[1] if job_row[1] is not None else 0
        if current_worker_id == 0:
            cur = conn.execute(
                "UPDATE jobs SET price_cents = ?, worker_id = ? "
                "WHERE id = ? AND state = 'posted'",
                (offer.amount_cents, offer.worker_id, offer.job_id))
        else:
            cur = conn.execute(
                "UPDATE jobs SET price_cents = ? "
                "WHERE id = ? AND state = 'posted'",
                (offer.amount_cents, offer.job_id))
    if cur.rowcount != 1:
        conn.rollback()
        conn.close()
        return None
    conn.execute(
        "UPDATE offers SET status = 'accepted', decided_at = ? "
        "WHERE id = ?", (_now(), offer_id))
    conn.execute(
        "UPDATE offers SET status = 'superseded', decided_at = ? "
        "WHERE job_id = ? AND status = 'pending' AND id != ?",
        (_now(), offer.job_id, offer_id))
    conn.commit()
    row = conn.execute("SELECT * FROM offers WHERE id = ?",
                       (offer_id,)).fetchone()
    conn.close()
    return _row_to_offer(row)


# ---------------------------------------------------------------------------
# Prepared demo files — a deliverable generated when a demo job is
# created and stored ready for the one-tap "Deliver the prepared
# file" button (the ready-made job's sample; story jobs use fixture
# files from the demo data dir instead).
# ---------------------------------------------------------------------------
def _ensure_prepared_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS prepared_files (
            job_id     INTEGER PRIMARY KEY,
            filename   TEXT NOT NULL,
            content    BLOB NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()


def store_prepared_file(job_id: int, filename: str,
                        content: bytes) -> None:
    conn = sqlite3.connect(get_db_path())
    _ensure_prepared_table(conn)
    conn.execute(
        "INSERT OR REPLACE INTO prepared_files "
        "(job_id, filename, content, created_at) VALUES (?, ?, ?, ?)",
        (job_id, filename, content, _now()))
    conn.commit()
    conn.close()


def get_prepared_file(job_id: int):
    """(filename, bytes) stored for this job, or None."""
    conn = sqlite3.connect(get_db_path())
    _ensure_prepared_table(conn)
    row = conn.execute(
        "SELECT filename, content FROM prepared_files "
        "WHERE job_id = ?", (job_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    return row[0], bytes(row[1])


# --- service-call log + party API keys --------------------

def log_service_call(job_id, actor: str, via: str, action: str,
                     endpoint: str, request_summary: str,
                     response_status: int, paypal_ids: str = "") -> None:
    """Append one row to the service-call log. Called by the shared
    service layer for every API call and every UI money action, so
    the integrator machine view shows one ordered stream per job."""
    conn = sqlite3.connect(get_db_path())
    conn.execute(
        "INSERT INTO service_calls (job_id, actor, via, action, "
        "endpoint, request_summary, response_status, paypal_ids, "
        "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (job_id, actor or '', via or '', action or '', endpoint or '',
         (request_summary or '')[:500], int(response_status or 0),
         paypal_ids or '', _now()))
    conn.commit()
    conn.close()


def get_service_calls(job_id: int) -> List[dict]:
    """All logged calls for one job, in call order (id ascending)."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM service_calls WHERE job_id = ? ORDER BY id ASC",
        (job_id,))]
    conn.close()
    return rows


def set_party_api_key_hash(party_id: int, key_hash: str) -> None:
    """Store the sha256 hash of a party's API key (the plaintext is
    shown to the party exactly once, at issuance, and never stored)."""
    conn = sqlite3.connect(get_db_path())
    conn.execute("UPDATE parties SET api_key_hash = ? WHERE id = ?",
                 (key_hash, party_id))
    conn.commit()
    conn.close()


def get_party_by_api_key_hash(key_hash: str):
    """Resolve an API key hash to its party row (dict) or None."""
    if not key_hash:
        return None
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM parties WHERE api_key_hash = ?",
        (key_hash,)).fetchone()
    conn.close()
    return dict(row) if row else None
