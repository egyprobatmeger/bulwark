"""the demo cast: three stories as built-in demo data.

Reset (POST /demo/reset) ensures the demo parties exist (by name,
idempotent), archives the previous run's demo jobs, and creates the
story jobs fresh in `posted` state through the normal create_job
path. Running a story uses ONLY the normal flows (fund / deliver /
check / settle-or-refund through the UI or the API) — this module
never pre-bakes a state beyond `posted`.
"""
import json
import os
import time

from app.db import (archive_active_demo_jobs, create_job, create_party,
                    list_parties, set_job_demo_tag,
                    set_party_certifications)
from app.models import Criterion


def _crit(name, expected, operator="="):
    return Criterion(name=name, operator=operator,
                     expected_value=expected,
                     criterion_type="deterministic")


SAMPLE_TEMPLATES = [
    {
        "id": "sample-translation-pricelist",
        "card_title": "Translation price list (EN→DE)",
        "blurb": "LinguaCert translates Mira's Shop spring price list "
                 "into German — a clean, passing delivery is attached.",
        "title": "Translate the spring price list into German (EN→DE)",
        "description": "Translate the shop's spring price list into German "
                       "and deliver it as one CSV: at least 24 items, every "
                       "item id unique, a German translation in every row.",
        "price_cents": 18000,
        "client": "Mira's Shop",
        "worker": "LinguaCert Agency",
        "criteria": [
            _crit("file_count", "1"),
            _crit("format", "CSV"),
            _crit("row_count", "24", ">="),
            _crit("unique_column", "item_id"),
            _crit("nonempty_column", "de"),
        ],
        "fixtures": ["sample_translation_pricelist.csv"],
    },
    {
        "id": "sample-supplier-cleanup",
        "card_title": "Supplier list cleanup",
        "blurb": "DataMill Co cleans and de-duplicates the supplier contact "
                 "list — a clean, passing delivery is attached.",
        "title": "Clean and de-duplicate the supplier contact list",
        "description": "Clean the supplier contact list and deliver it as "
                       "one CSV: at least 25 suppliers, every supplier id "
                       "unique, an email address in every row.",
        "price_cents": 24000,
        "client": "Mira's Shop",
        "worker": "DataMill Co",
        "criteria": [
            _crit("file_count", "1"),
            _crit("format", "CSV"),
            _crit("row_count", "25", ">="),
            _crit("unique_column", "supplier_id"),
            _crit("nonempty_column", "email"),
        ],
        "fixtures": ["sample_supplier_list.csv"],
    },
    {
        "id": "sample-inventory-dedup",
        "card_title": "Inventory duplicate check",
        "blurb": "DataMill Co de-duplicates the warehouse inventory export "
                 "— a clean, passing delivery is attached.",
        "title": "De-duplicate the warehouse inventory export",
        "description": "De-duplicate the warehouse inventory export and "
                       "deliver it as one CSV: at least 30 stock lines, "
                       "every SKU unique, a warehouse recorded on every row.",
        "price_cents": 21000,
        "client": "Mira's Shop",
        "worker": "DataMill Co",
        "criteria": [
            _crit("file_count", "1"),
            _crit("format", "CSV"),
            _crit("row_count", "30", ">="),
            _crit("unique_column", "sku"),
            _crit("nonempty_column", "warehouse"),
        ],
        "fixtures": ["sample_inventory.csv"],
    },
]

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "demo_data")


def sample_template(template_id):
    """Return the sample template dict with the given id, or None."""
    for template in SAMPLE_TEMPLATES:
        if template["id"] == template_id:
            return template
    return None


def attach_sample_template(job, template_id):
    """If the template exists, set_job_demo_tag(job.id, f"sample:{template_id}"), True; else False."""
    template = sample_template(template_id)
    if template:
        set_job_demo_tag(job.id, f"sample:{template_id}")
        return True
    return False


# Each story: key, headline, one-line description, the job(s) it
# creates, and the delivery fixture(s) the visitor uses.
#
# The cast are SPECIALISTS and the work is specialist work — the
# kind a client only hands to a credentialed party, at amounts
# where escrow and the checker-as-insurer actually matter
#. Every fixture honestly passes
# or fails the deterministic acceptance test it is measured
# against; the stories run on the real flows only.
STORIES = [
    {
        "key": "story1",
        "headline": "Story 1 — Agent hires a certified specialist",
        "blurb": "ShopAgent (for Mira's Shop) hires LinguaCert "
                 "Agency — ISO 17100 certified — for a sworn legal "
                 "translation. Clean delivery, full arc: fund → "
                 "deliver → check → settle.",
        "jobs": [
            {
                "slot": "main",
                "title": "Sworn legal translation of the supply "
                         "agreement (EN→DE)",
                "description": "Certified translation of the "
                               "supply agreement's clause register "
                               "into German, by an ISO 17100 "
                               "certified service. Acceptance test: "
                               "one CSV, at least 20 clause rows, "
                               "every clause id unique, no empty "
                               "German cell.",
                "price_cents": 45000,
                "client": "ShopAgent",
                "worker": "LinguaCert Agency",
                "criteria": [
                    _crit("file_count", "1"),
                    _crit("format", "CSV"),
                    _crit("row_count", "20", ">="),
                    _crit("unique_column", "clause_id"),
                    _crit("nonempty_column", "de"),
                ],
                "fixtures": ["story1_legal_translation.csv"],
            },
        ],
    },
    {
        "key": "story2",
        "headline": "Story 2 — The licensed auditor",
        "blurb": "Kovács Anna, a licensed WCAG 2.2 accessibility "
                 "auditor, audits the shop's checkout flow. Her "
                 "first report still has a duplicated check and a "
                 "missing result and FAILS; the revision passes "
                 "and settles.",
        "jobs": [
            {
                "slot": "main",
                "title": "WCAG 2.2 AA accessibility audit — "
                         "checkout flow",
                "description": "Audit the checkout flow against "
                               "the WCAG 2.2 AA checklist and "
                               "deliver the evidence register. "
                               "Acceptance test: one CSV, at least "
                               "15 checks, every check id unique, "
                               "a result recorded for every check.",
                "price_cents": 30000,
                "client": "Mira's Shop",
                "worker": "Kovács Anna",
                "criteria": [
                    _crit("file_count", "1"),
                    _crit("format", "CSV"),
                    _crit("row_count", "15", ">="),
                    _crit("unique_column", "check_id"),
                    _crit("nonempty_column", "result"),
                ],
                "fixtures": ["story2_wcag_v1.csv",
                             "story2_wcag_v2.csv"],
            },
        ],
    },
    {
        "key": "story3",
        "headline": "Story 3 — The fraudster",
        "blurb": "DataMill Co converts a medical-device manual's "
                 "terminology to the regulator's strict format on "
                 "the source job. FastPix then 'delivers' a "
                 "byte-copy of it on its own job — the originality "
                 "screen catches it: FRAUD, no revision, refund.",
        "jobs": [
            {
                "slot": "source",
                "title": "Infusion-pump manual terminology — "
                         "regulator-format conversion",
                "description": "Convert the infusion-pump "
                               "manual's terminology table to the "
                               "regulator's strict exchange format: "
                               "one CSV, at least 12 term rows. Run "
                               "this job first — its delivery is "
                               "the genuine original Story 3 is "
                               "measured against.",
                "price_cents": 60000,
                "client": "Mira's Shop",
                "worker": "DataMill Co",
                "criteria": [
                    _crit("file_count", "1"),
                    _crit("format", "CSV"),
                    _crit("row_count", "12", ">="),
                ],
                "fixtures": ["story3_terms_source.csv"],
            },
            {
                "slot": "fraud",
                "title": "Urgent: re-deliver the pump-manual "
                         "terminology table",
                "description": "Re-deliver the pump-manual "
                               "terminology table in the "
                               "regulator's format: one CSV, at "
                               "least 12 rows. (The demo fixture "
                               "for this job is a byte-copy of "
                               "DataMill's delivery — watch what "
                               "the checker does with it.)",
                "price_cents": 60000,
                "client": "Mira's Shop",
                "worker": "FastPix",
                "criteria": [
                    _crit("file_count", "1"),
                    _crit("format", "CSV"),
                    _crit("row_count", "12", ">="),
                ],
                "fixtures": ["story3_terms_copy.csv"],
            },
        ],
    },
]


def load_demo_parties():
    with open(os.path.join(DATA_DIR, "parties.json"),
              encoding="utf-8") as f:
        return json.load(f)


def ensure_demo_parties():
    """Create the demo parties if missing (matched by name) and
    keep their public certifications on record: the cast are
    specialists, and the credentials on their profiles are part of
    the product surface, not decoration. Returns {name: party
    dict} for the demo set + the checker."""
    by_name = {p["name"]: p for p in list_parties()}
    for spec in load_demo_parties():
        certs = spec.get("certifications") or []
        if spec["name"] not in by_name:
            pid = create_party(spec["name"], spec["kind"],
                               spec["form"], spec["payout_email"],
                               certifications=certs)
            by_name[spec["name"]] = {
                "id": pid, "name": spec["name"], "kind": spec["kind"],
                "form": spec["form"],
                "payout_email": spec["payout_email"], "created_at": "",
                "certifications": list(certs)}
        elif certs and not by_name[spec["name"]].get("certifications"):
            set_party_certifications(by_name[spec["name"]]["id"],
                                      certs)
            by_name[spec["name"]]["certifications"] = list(certs)
    return by_name


def checker_party_id(by_name):
    p = by_name.get("Verifier Prime")
    return p["id"] if p else 3


def reset_demo():
    """Archive the previous run and create the story jobs fresh in
    posted state. Returns {story_key: {slot: job_id}}."""
    parties = ensure_demo_parties()
    checker_id = checker_party_id(parties)
    archive_active_demo_jobs()
    created = {}
    for story in STORIES:
        created[story["key"]] = {}
        for spec in story["jobs"]:
            job = create_job(
                spec["title"], spec["description"],
                spec["price_cents"], "USD", spec["criteria"],
                client_id=parties[spec["client"]]["id"],
                worker_id=parties[spec["worker"]]["id"],
                checker_id=checker_id)
            set_job_demo_tag(job.id, "active")
            created[story["key"]][spec["slot"]] = job.id
    return created


def active_demo_jobs():
    """The current demo run's jobs: {story_key: {slot: Job}}."""
    from app.db import list_jobs
    from app.demo import STORIES as _S  # self, for title matching
    active = [j for j in list_jobs() if j.demo_tag == "active"]
    by_title = {j.title: j for j in active}
    out = {}
    for story in _S:
        out[story["key"]] = {}
        for spec in story["jobs"]:
            job = by_title.get(spec["title"])
            if job is not None:
                out[story["key"]][spec["slot"]] = job
    return out


# --- Seeded history --------------------------------------------------
# Three FINISHED projects, played end-to-end through the real service
# flows by seed_history() below (fund at PayPal, deliver, check,
# settle / revise / auto-refund) — never written into the database
# directly, so every timeline event, reputation change, certificate
# and PayPal id on them is genuine. They carry demo_tag 'history':
# visible on the board (unlike archived runs) and untouched by Reset.

HISTORY = [
    {
        "title": "Certified translation of the master services "
                 "agreement (EN→DE)",
        "description": "Sworn translation of the master services "
                       "agreement's clause register into German by "
                       "an ISO 17100 certified service. Acceptance "
                       "test: one CSV, at least 18 clause rows, "
                       "every clause id unique, no empty German "
                       "cell.",
        "price_cents": 72000,
        "client": "ShopAgent",
        "worker": "LinguaCert Agency",
        "criteria": [
            _crit("file_count", "1"),
            _crit("format", "CSV"),
            _crit("row_count", "18", ">="),
            _crit("unique_column", "clause_id"),
            _crit("nonempty_column", "de"),
        ],
        "arc": "settle",
        "fixtures": ["history_legal_msa.csv"],
    },
    {
        "title": "GDPR processing-register audit — evidence pack",
        "description": "Audit of the records of processing "
                       "activities against the GDPR checklist, "
                       "delivered as an evidence register. "
                       "Acceptance test: one CSV, at least 14 "
                       "records, every record id unique, a status "
                       "recorded for every record.",
        "price_cents": 54000,
        "client": "Mira's Shop",
        "worker": "AccessAudit Labs",
        "criteria": [
            _crit("file_count", "1"),
            _crit("format", "CSV"),
            _crit("row_count", "14", ">="),
            _crit("unique_column", "record_id"),
            _crit("nonempty_column", "status"),
        ],
        "arc": "settle",
        "fixtures": ["history_gdpr_register.csv"],
    },
    {
        "title": "Terminology conversion for the dialysis-machine "
                 "manual",
        "description": "Convert the dialysis-machine manual's "
                       "terminology table to the regulator's "
                       "strict format. Acceptance test: one CSV, "
                       "at least 10 rows, every term id unique. "
                       "The worker's delivery — and the one "
                       "permitted revision — both kept duplicate "
                       "term ids, so the job ended in an automatic "
                       "full refund.",
        "price_cents": 38000,
        "client": "Mira's Shop",
        "worker": "DataMill Co",
        "criteria": [
            _crit("file_count", "1"),
            _crit("format", "CSV"),
            _crit("row_count", "10", ">="),
            _crit("unique_column", "term_id"),
        ],
        "arc": "refund",
        "fixtures": ["history_terms_bad1.csv",
                     "history_terms_bad2.csv"],
    },
    {
        "title": "Certified translation of the product warranty terms "
                  "(EN→DE)",
        "description": "Certified translation of the product warranty "
                       "terms into German by an ISO 17100 certified "
                       "service. Acceptance test: one CSV, at least "
                       "12 term rows, every term id unique, no empty "
                       "German cell. The worker's delivery — and the "
                       "one permitted revision — both kept a duplicate "
                       "term id, so the job ended in an automatic full "
                       "refund.",
        "price_cents": 34000,
        "client": "ShopAgent",
        "worker": "LinguaCert Agency",
        "criteria": [
            _crit("file_count", "1"),
            _crit("format", "CSV"),
            _crit("row_count", "12", ">="),
            _crit("unique_column", "term_id"),
            _crit("nonempty_column", "de"),
        ],
        "arc": "refund",
        "fixtures": ["history_warranty_bad1.csv",
                     "history_warranty_bad2.csv"],
    },
]

_SEED_NOTE = None


def set_seed_note(text):
    global _SEED_NOTE
    _SEED_NOTE = text


def pop_seed_note():
    global _SEED_NOTE
    note, _SEED_NOTE = _SEED_NOTE, None
    return note


def history_jobs():
    """The seeded finished projects (demo_tag 'history'), oldest
    first."""
    from app.db import list_jobs
    return sorted((j for j in list_jobs() if j.demo_tag == "history"),
                  key=lambda j: j.id)


def _fixture_bytes(name):
    with open(os.path.join(DATA_DIR, name), "rb") as f:
        return f.read()


def _revision_deliver(job_id, name, note):
    """The one permitted revision delivery — the same writes the
    /job/<id>/revise handler performs (delivery row flagged as a
    revision, revision marked used, job back to delivered)."""
    import hashlib
    import uuid

    from app.db import (DELIVERIES_DIR, add_delivery, add_event,
                        set_job_state, set_revision_used)
    data = _fixture_bytes(name)
    job_dir = os.path.join(DELIVERIES_DIR, str(job_id))
    os.makedirs(job_dir, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}_{name}"
    with open(os.path.join(job_dir, stored_name), "wb") as f:
        f.write(data)
    add_delivery(job_id=job_id, filename=name, stored_name=stored_name,
                 size_bytes=len(data),
                 sha256=hashlib.sha256(data).hexdigest(), note=note,
                 is_revision=True)
    set_revision_used(job_id)
    set_job_state(job_id, "delivered")
    add_event(job_id, "revised", actor="worker",
              detail={"files": [name]})


def _settle_patiently(job_id, get_job, via, endpoint):
    """Settle with the patience the job page's own Settle button
    offers: a soft note or a transient PayPal error is retried, and
    only a stored state of 'settled' counts. Returns (ok, last_note).
    """
    from app.service import ServiceError, settle_job_action
    last_note = ""
    for attempt in range(3):
        try:
            _, note = settle_job_action(
                job_id, via=via, actor="system (demo seed)",
                endpoint=endpoint)
            last_note = note or ""
        except ServiceError as e:
            last_note = e.message
        if get_job(job_id).state == "settled":
            return True, ""
        if attempt < 2:
            time.sleep(15)
    return False, last_note


def _drive_history_job(spec, parties, checker_id, via, endpoint):
    """Create (if needed) and advance one history project from
    whatever state it is in to its arc's end, through the real
    service flows. Returns a one-line human outcome. Safe to call
    again after a stop: every step is gated by the job's state."""
    from app.db import get_job
    from app.service import (ServiceError, check_job_action,
                             create_job_action, deliver_job_action,
                             do_refund, fund_job_action)
    title = spec["title"]
    job = next((j for j in history_jobs() if j.title == title), None)
    if job is None:
        job = create_job_action(
            title=title, description=spec["description"],
            price_cents=spec["price_cents"], currency="USD",
            criteria=spec["criteria"],
            client_id=parties[spec["client"]]["id"],
            worker_id=parties[spec["worker"]]["id"],
            checker_id=checker_id,
            via=via, actor="demo seeder", endpoint=endpoint)
        set_job_demo_tag(job.id, "history")
    fx = spec["fixtures"]
    try:
        for _step in range(8):
            job = get_job(job.id)
            state = job.state
            if state in ("settled", "refunded"):
                break
            if state == "posted":
                fund_job_action(job.id, via=via,
                                actor="client (demo seed)",
                                endpoint=endpoint)
            elif state == "funded":
                deliver_job_action(
                    job.id, [(fx[0], _fixture_bytes(fx[0]))],
                    "Seeded history delivery", via=via,
                    actor="worker (demo seed)", endpoint=endpoint)
            elif state == "delivered":
                check_job_action(job.id, via=via,
                                 actor="checker (demo seed)",
                                 endpoint=endpoint)
            elif state == "checked_pass" and spec["arc"] == "settle":
                ok, note = _settle_patiently(job.id, get_job, via,
                                             endpoint)
                if not ok:
                    return (f"“{title}” — passed its check; "
                            f"settlement did not complete "
                            f"({note or 'see job page'}). It can be "
                            "settled from its job page.")
                break
            elif state == "checked_fail" and spec["arc"] == "refund":
                if job.revision_used:
                    # The second FAIL's automatic refund can itself
                    # be interrupted by a PayPal wave (the check
                    # path logs a refund_error event and keeps the
                    # job in checked_fail). Completing it here is
                    # the same call the check path and the client's
                    # reject button make.
                    do_refund(job, actor="system (demo seed)")
                else:
                    _revision_deliver(job.id, fx[1],
                                      "Seeded history revision")
            else:
                return (f"“{title}” — left in state {state} for "
                        "inspection.")
    except ServiceError as e:
        job = get_job(job.id)
        return (f"“{title}” — stopped in state {job.state}: "
                f"{e.message} Press Seed again to resume it.")
    except Exception as e:  # a PayPal wave must not kill the seed
        job = get_job(job.id)
        return (f"“{title}” — stopped in state {job.state}: "
                f"{type(e).__name__}: {e} Press Seed again to "
                "resume it.")
    job = get_job(job.id)
    if spec["arc"] == "settle" and job.state == "settled":
        return f"“{title}” — settled ({job.formatted_price()})."
    if spec["arc"] == "refund" and job.state == "refunded":
        return (f"“{title}” — failed twice, automatically "
                "refunded in full.")
    return f"“{title}” — ended in state {job.state}."


def seed_history():
    """Play the HISTORY projects through the real flows, resuming
    any that stopped mid-arc. Returns a human summary."""
    parties = ensure_demo_parties()
    checker_id = checker_party_id(parties)
    via, endpoint = "demo-seed", "/demo/seed-history"
    existing = history_jobs()
    if existing and all(j.state in ("settled", "refunded")
                         for j in existing) \
            and len(existing) >= len(HISTORY):
        return ("Demo history is already seeded — the finished "
                "projects are on the board (Settled / Refunded).")
    lines = [_drive_history_job(spec, parties, checker_id, via,
                                endpoint) for spec in HISTORY]
    return "Demo history: " + " ".join(lines)


# --- Ready-made job (judge-friendly trial path) ----------------------
# a judge cannot be expected to invent a job AND
# author a conforming document before Bulwark does anything. The
# /demo page therefore offers ONE ready-made job — fully filled in,
# in posted state — whose acceptance test the demo sample generator
# (app/samplegen.py) can satisfy, so the whole arc (fund → generate
# & deliver → check → settle → certificate) takes a few clicks. It is
# a demo convenience, labelled "Demo shortcut" in the UI; posting a
# job of your own and uploading a real file work exactly as before.

READY_JOB = {
    "title": "Assemble the accessibility-audit evidence register",
    "description": "Compile the evidence register for a WCAG 2.2 "
                   "accessibility audit as one CSV: at least 15 "
                   "rows with id and result columns, every id "
                   "unique, a result recorded on every row.",
    "price_cents": 25000,
    "client": "Mira's Shop",
    "worker": "Kovács Anna",
    "criteria": [
        _crit("file_count", "1"),
        _crit("format", "CSV"),
        _crit("row_count", "15", ">="),
        _crit("contains_column", "result"),
        _crit("unique_column", "id"),
        _crit("nonempty_column", "result"),
    ],
}


def ready_job():
    """The live ready-made job (demo_tag 'active', not yet in a
    terminal state), or None. Identified by its fixed title, like
    the story jobs."""
    from app.db import list_jobs
    for j in list_jobs():
        if j.title == READY_JOB["title"] and j.demo_tag == "active" \
                and j.state not in ("settled", "refunded"):
            return j
    return None


def _ensure_prepared_file(job):
    """Generate the ready-made job's deliverable AT CREATION TIME
    and store it with the job, so the visitor's arc is pure clicks:
    open → Fund → Deliver the prepared file → check → settle →
    certificate. The file is synthesized from the job's own
    criteria by the same generator the live shortcut uses; the
    real checker still judges it on delivery, unmodified."""
    from app.db import get_prepared_file, store_prepared_file
    if get_prepared_file(job.id) is not None:
        return
    from app.samplegen import generate_sample_delivery
    files, unsupported = generate_sample_delivery(job)
    if files and not unsupported:
        store_prepared_file(job.id, files[0][0], files[0][1])


def post_ready_job():
    """Create the ready-made job in posted state through the normal
    service action (or return the one already waiting), with its
    prepared deliverable stored and ready for one-tap delivery.
    Tagged 'active' like the story jobs, so Reset archives it with
    them."""
    existing = ready_job()
    if existing is not None:
        _ensure_prepared_file(existing)
        return existing
    from app.service import create_job_action
    parties = ensure_demo_parties()
    checker_id = checker_party_id(parties)
    job = create_job_action(
        title=READY_JOB["title"], description=READY_JOB["description"],
        price_cents=READY_JOB["price_cents"], currency="USD",
        criteria=READY_JOB["criteria"],
        client_id=parties[READY_JOB["client"]]["id"],
        worker_id=parties[READY_JOB["worker"]]["id"],
        checker_id=checker_id,
        via="demo", actor="client (demo)", endpoint="/demo/ready-job")
    set_job_demo_tag(job.id, "active")
    _ensure_prepared_file(job)
    return job


# --- Auto-seed fallback ----------------------------------------------
# The hosted demo ships a bundled database snapshot (see
# DEPLOY_PATCHES.md in the deploy repo) and restores it at startup
# whenever the live database is missing or empty — that is the
# primary self-healing path and needs no PayPal calls at all. This
# section is the FALLBACK for a deploy whose snapshot is missing or
# corrupt: when enabled (BULWARK_AUTO_SEED, set by the demo deploy
# only), the demo baseline is rebuilt live through the same
# state-driven flows as the manual Reset / ready-job / Seed
# buttons. Every step is gated by the current state, so an
# interrupted run resumes where it stopped instead of duplicating
# anything, and if PayPal is unreachable the content fills in as
# far as it can and a later attempt continues it.

import threading

_AUTO_SEED_LOCK = threading.Lock()
_AUTO_SEED_THREAD = None
_AUTO_SEED_ACTIVE = False
_AUTO_SEED_MESSAGE = ""
_AUTO_SEED_LAST_FINISH = 0.0


def auto_seed_enabled():
    return os.environ.get("BULWARK_AUTO_SEED", "").strip().lower() in (
        "1", "true", "yes", "on")


def auto_seed_status():
    """(active, message) — the message is fit to show a visitor
    while the demo content is being prepared."""
    return _AUTO_SEED_ACTIVE, _AUTO_SEED_MESSAGE


def _set_auto_seed_status(active, message):
    global _AUTO_SEED_ACTIVE, _AUTO_SEED_MESSAGE
    _AUTO_SEED_ACTIVE = active
    _AUTO_SEED_MESSAGE = message


def _history_complete():
    existing = history_jobs()
    return len(existing) >= len(HISTORY) and all(
        j.state in ("settled", "refunded") for j in existing)


def _stories_complete():
    active = active_demo_jobs()
    for story in STORIES:
        slots = active.get(story["key"], {})
        for spec in story["jobs"]:
            if spec["slot"] not in slots:
                return False
    return True


def _ready_present():
    from app.db import list_jobs
    return any(j.title == READY_JOB["title"] and j.demo_tag == "active"
               for j in list_jobs())


def demo_content_complete():
    """The full demo baseline: the story jobs, the ready-made job
    and the finished history projects (in their end states)."""
    return (_stories_complete() and _ready_present()
            and _history_complete())


def _ensure_story_jobs():
    """Create any missing story jobs (matched by title among the
    active-tagged jobs) without touching the ones already there.
    With no active jobs at all, a clean Reset is the honest way to
    (re)build the run; a partial run is topped up job by job, so a
    visitor's half-played story is never archived under them."""
    from app.db import create_job, list_jobs
    parties = ensure_demo_parties()
    active_titles = {j.title for j in list_jobs()
                     if j.demo_tag == "active"}
    if not active_titles:
        reset_demo()
        return
    checker_id = checker_party_id(parties)
    for story in STORIES:
        for spec in story["jobs"]:
            if spec["title"] not in active_titles:
                job = create_job(
                    spec["title"], spec["description"],
                    spec["price_cents"], "USD", spec["criteria"],
                    client_id=parties[spec["client"]]["id"],
                    worker_id=parties[spec["worker"]]["id"],
                    checker_id=checker_id)
                set_job_demo_tag(job.id, "active")


def ensure_demo_content():
    """Build or resume the full demo baseline through the real
    flows: story jobs + ready-made job + seeded history. Safe to
    call any number of times; each step checks the state it finds."""
    _set_auto_seed_status(
        True, "Preparing the demo: creating the story jobs…")
    _ensure_story_jobs()
    _set_auto_seed_status(
        True, "Preparing the demo: posting the ready-made job…")
    post_ready_job()
    if not _history_complete():
        _set_auto_seed_status(
            True, "Preparing the demo: playing the finished example "
                  "projects through the real payment flows — this "
                  "can take a minute…")
        set_seed_note(seed_history())
    _set_auto_seed_status(False, "")


def _auto_seed_worker():
    global _AUTO_SEED_LAST_FINISH
    try:
        ensure_demo_content()
    except Exception as e:  # never die silently; the note says why
        set_seed_note(f"Automatic demo preparation stopped: "
                      f"{type(e).__name__}: {e}")
        _set_auto_seed_status(False, "")
    finally:
        _AUTO_SEED_LAST_FINISH = time.time()


def maybe_start_auto_seed():
    """Start the fallback builder in the background if the demo
    content is incomplete. Cheap to call on every request (a lock
    plus a state check). A finished attempt is not restarted for a
    minute, so a PayPal outage cannot turn into a retry storm; the
    state-driven steps simply resume on the next attempt."""
    global _AUTO_SEED_THREAD
    if not auto_seed_enabled():
        return
    with _AUTO_SEED_LOCK:
        if _AUTO_SEED_THREAD is not None and _AUTO_SEED_THREAD.is_alive():
            return
        if time.time() - _AUTO_SEED_LAST_FINISH < 60:
            return
        try:
            if demo_content_complete():
                return
        except Exception:
            return  # database not ready yet; a later call retries
        _AUTO_SEED_THREAD = threading.Thread(
            target=_auto_seed_worker, name="bulwark-auto-seed",
            daemon=True)
        _AUTO_SEED_THREAD.start()


def sample_template(template_id):
    """Return the sample template dict with the given id, or None."""
    for template in SAMPLE_TEMPLATES:
        if template["id"] == template_id:
            return template
    return None


def attach_sample_template(job, template_id):
    """If the template exists, set_job_demo_tag(job.id, f"sample:{template_id}"), True; else False."""
    template = sample_template(template_id)
    if template:
        set_job_demo_tag(job.id, f"sample:{template_id}")
        return True
    return False


def fixtures_for_job(job):
    """The prepared delivery files for an active demo job (matched
    by title, like active_demo_jobs); [] for any other job. Used by
    the one-tap delivery on the job page: the demo visitor delivers
    the prepared material without a download/upload round-trip.
    Story jobs resolve to fixture files in the demo data dir; the
    ready-made job resolves to the file generated and stored with
    it at creation time."""
    # Handle sample templates (demo_tag starting with "sample:")
    demo_tag = getattr(job, "demo_tag", "")
    if demo_tag and demo_tag.startswith("sample:"):
        template_id = demo_tag[len("sample:"):]
        template = sample_template(template_id)
        if template:
            return list(template.get("fixtures") or [])
        return []
    
    if job is None or getattr(job, "demo_tag", "") != "active":
        return []
    for story in STORIES:
        for spec in story["jobs"]:
            if spec["title"] == job.title:
                return list(spec.get("fixtures") or [])
    if job.title == READY_JOB["title"]:
        from app.db import get_prepared_file
        prepared = get_prepared_file(job.id)
        if prepared is not None:
            return [prepared[0]]
    
    return []
