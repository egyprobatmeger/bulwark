"""the shared service layer.

UI handlers and the JSON API handlers call THESE functions for
create / fund / deliver / check / settle, so both channels run the
same code paths and produce the same states, events and messages.
Every action appends one row to the service-call log (db.log_service_call)
with its channel (`via`: "ui" or "api"), which is what the integrator
machine view renders.

Refusals raise ServiceError(message, http_status) carrying the same
message text the UI shows in its info banner.
"""
import hashlib
import os
import time
import uuid
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

from app.db import (
    get_job, get_party, create_job, add_event, add_delivery,
    set_job_funded, set_job_paypal_error, set_job_delivered,
    set_job_captured, set_job_settled, set_job_settle_error,
    set_job_voided_authorization_refusal,
    set_job_refunded, set_job_terms, set_job_checked, set_job_state,
    set_job_trust_credit, set_checker_vesting, set_checker_released,
    get_party_counters, emit_verdict_events, get_certificate_by_job,
    get_verdicts, get_deliveries, log_service_call, DELIVERIES_DIR,
    create_offer, get_offer, list_offers, set_offer_status,
    accept_offer as db_accept_offer, accepted_offer,
)
from app.brain import decide_terms
from app.checker import (
    run_check, can_check, CheckNotAllowedError,
    JUDGE_MODEL, JUDGE_FALLBACK_MODEL,
)
from app.paypal_client import (
    authorize_order, capture_authorization, capture_authorization_amount,
    create_payouts, create_or_adopt_payouts, void_authorization,
    refund_capture, get_order, get_capture,
    get_authorization, PayPalError, credentials_present,
    _parse_amount_to_cents,
)
from app.config import (
    WORKER_SPLIT_PERCENT, CHECKER_SPLIT_PERCENT,
    WORKER_RECEIVER_EMAIL, CHECKER_RECEIVER_EMAIL, PLATFORM_RECEIVER_EMAIL,
)

MAX_FILE_SIZE = 25 * 1024 * 1024  # per file, same cap as the UI


class ServiceError(Exception):
    def __init__(self, message: str, http_status: int = 400):
        super().__init__(message)
        self.message = message
        self.http_status = http_status


def _log(job_id, actor, via, action, endpoint, summary, status,
         paypal_ids=""):
    try:
        log_service_call(job_id, actor, via, action, endpoint, summary,
                         status, paypal_ids)
    except Exception:
        pass  # the log must never break the money path


def _paypal_ids(job) -> str:
    if job is None:
        return ""
    ids = []
    for label, value in (("order", job.paypal_order_id),
                         ("authorization", job.paypal_authorization_id),
                         ("capture", job.capture_id),
                         ("payout_batch", job.payout_batch_id),
                         ("refund", job.refund_id)):
        if value:
            ids.append(f"{label}={value}")
    return " ".join(ids)


# --- money helpers (moved from the request handler; the handler's
# --- methods of the same names now delegate here) --------------------

class CaptureLinkageUnverifiable(ServiceError):
    """Capture linkage could neither be proven nor refuted: PayPal
    reads stayed incomplete inside the retry window (sandbox loss
    waves), so NO verdict exists. This is not a refusal — callers
    park the job in a resumable state and never run payouts on it.
    Subclasses ServiceError so generic handlers still catch it;
    linkage call sites check for it FIRST."""


class _LinkageReadExhausted(Exception):
    """A PayPal read failed on transport in every retry attempt."""

    def __init__(self, last_error):
        super().__init__(str(last_error))
        self.last_error = last_error


# Sandbox loss waves (measured 2026-10-08..10) drop individual
# responses for seconds at a time; a read that decides money gets
# four attempts across ~31 s before anyone concludes anything.
_LINKAGE_READ_PAUSES = (3, 8, 20)


def _linkage_read(fn, *args):
    """Run one PayPal read with wave-shaped retry.

    Transport failures (PayPalError CONNECT_ERROR, or any other
    exception escaping a read — truncated bodies, resets) are
    retried with growing pauses; a definitive HTTP answer (404,
    other 4xx) propagates immediately. Raises
    _LinkageReadExhausted when every attempt failed on transport."""
    last = None
    for attempt in range(len(_LINKAGE_READ_PAUSES) + 1):
        if attempt:
            time.sleep(_LINKAGE_READ_PAUSES[attempt - 1])
        try:
            return fn(*args)
        except PayPalError as e:
            if e.issue != "CONNECT_ERROR":
                raise
            last = e
        except Exception as e:
            last = e
    raise _LinkageReadExhausted(last)


def _check_capture_fields(record, capture_status: str,
                          capture_cents: int, capture_currency: str):
    """Compare one PayPal capture record against the values the
    settlement presented. A mismatch is positive proof the
    presented capture is not this record — a definitive refusal."""
    amt = record.get('amount', {}) or {}
    exp_cents = int(round(float(amt.get('value', '0')) * 100))
    exp_currency = amt.get('currency_code', capture_currency)
    if exp_cents != capture_cents:
        raise ServiceError(
            f"Capture amount mismatch: expected {exp_cents} cents "
            f"but got {capture_cents} cents")
    if exp_currency != capture_currency:
        raise ServiceError(
            f"Capture currency mismatch: expected {exp_currency} "
            f"but got {capture_currency}")
    if record.get('status') != capture_status:
        raise ServiceError(
            f"Capture status mismatch: expected {record.get('status')} "
            f"but got {capture_status}")


def _validate_capture_linkage(job, capture_id: str, capture_status: str,
                             capture_cents: int, capture_currency: str, actor: str = "") -> None:
    """Validate that a capture belongs to this job's authorization.

    Three outcomes, by design:
    * returns quietly — linkage PROVEN;
    * raises ServiceError — linkage REFUTED by positive evidence:
      the capture's own record names a different authorization or
      order, a record found under this job's order contradicts the
      presented amount/currency/status, or the capture does not
      exist at PayPal on repeated reads;
    * raises CaptureLinkageUnverifiable — the evidence stayed
      incomplete inside the retry window (sandbox loss waves).
      Callers park the job resumably; payouts never run on it.

    Evidence paths, from live-measured sandbox shapes
    (factory/probe_linkage_objects.py, 2026-10-10):
    A. The order's purchase_units[].payments.captures list.
    B. The capture's own supplementary_data.related_ids, which
       names its authorization_id and order_id.
    The pre-2026-10-10 fallback read the AUTHORIZATION object's
    `captures` list; that object has no such key in the sandbox,
    so the branch could never prove anything — one dropped
    get_order response was enough for a false "does not belong"
    verdict on a genuine capture (demo snapshot job 11, $210).
    Both reads now retry across the wave before concluding.
    """
    if not job.paypal_order_id or not job.paypal_authorization_id:
        raise ServiceError("No PayPal order or authorization available for linkage validation")

    notes = []

    # Path A: the order's payments record (retried read).
    order = None
    try:
        order = _linkage_read(get_order, job.paypal_order_id)
    except _LinkageReadExhausted as e:
        notes.append(f"order read failed on transport ({e.last_error})")
    except PayPalError as e:
        notes.append(f"order read answered {e.status_code} {e.issue}")
    if order is not None:
        found = None
        for unit in order.get('purchase_units', []) or []:
            payments = unit.get('payments', {}) or {}
            for cap in payments.get('captures', []) or []:
                if cap.get('id') == capture_id:
                    found = cap
                    break
            if found is not None:
                break
        if found is not None:
            _check_capture_fields(found, capture_status,
                                  capture_cents, capture_currency)
            return
        notes.append("the capture is absent from the order's "
                     "payments record")

    # Path B: the capture names its own parents (retried read).
    cap_obj = None
    cap_missing = False
    try:
        cap_obj = _linkage_read(get_capture, capture_id)
    except _LinkageReadExhausted as e:
        notes.append(f"capture read failed on transport ({e.last_error})")
    except PayPalError as e:
        if e.status_code == 404:
            # One spaced confirmation: a 404 that survives a second
            # read seconds later is a definitive answer, not a wave.
            time.sleep(_LINKAGE_READ_PAUSES[0])
            try:
                cap_obj = get_capture(capture_id)
            except PayPalError as e2:
                if e2.status_code == 404:
                    cap_missing = True
                else:
                    notes.append(
                        f"capture re-read answered {e2.status_code} "
                        f"{e2.issue}")
            except Exception as e2:
                notes.append(f"capture re-read failed ({e2})")
        else:
            notes.append(f"capture read answered {e.status_code} "
                         f"{e.issue}")
    if cap_missing:
        raise ServiceError(
            f"Capture {capture_id} does not exist at PayPal "
            f"(repeated 404 reads). It cannot belong to this job's "
            f"authorization.")
    if cap_obj is not None:
        related = ((cap_obj.get('supplementary_data', {}) or {})
                   .get('related_ids', {}) or {})
        rel_auth = related.get('authorization_id')
        rel_order = related.get('order_id')
        if rel_auth:
            if rel_auth != job.paypal_authorization_id:
                raise ServiceError(
                    f"Capture {capture_id} belongs to authorization "
                    f"{rel_auth}, not this job's authorization "
                    f"{job.paypal_authorization_id}.")
            _check_capture_fields(cap_obj, capture_status,
                                  capture_cents, capture_currency)
            return
        if rel_order:
            if rel_order != job.paypal_order_id:
                raise ServiceError(
                    f"Capture {capture_id} belongs to order "
                    f"{rel_order}, not this job's order "
                    f"{job.paypal_order_id}.")
            _check_capture_fields(cap_obj, capture_status,
                                  capture_cents, capture_currency)
            return
        notes.append("the capture record carries no related_ids")

    raise CaptureLinkageUnverifiable(
        f"Capture {capture_id} linkage unverifiable: "
        + "; ".join(notes)
        + ". No evidence shows the capture is foreign; PayPal reads "
          "stayed incomplete. Settlement is parked resumably — "
          "retry when PayPal is reachable.")


def split_items(job, captured_cents: int):
    worker = captured_cents * WORKER_SPLIT_PERCENT // 100
    checker = captured_cents * CHECKER_SPLIT_PERCENT // 100
    platform = captured_cents - worker - checker
    worker_party = get_party(job.worker_id) if job.worker_id else None
    checker_party = get_party(job.checker_id) if job.checker_id else None
    worker_email = (worker_party['payout_email'] if worker_party
                    and worker_party['payout_email']
                    else WORKER_RECEIVER_EMAIL)
    checker_email = (checker_party['payout_email'] if checker_party
                     and checker_party['payout_email']
                     else CHECKER_RECEIVER_EMAIL)
    return [
        {"party": "worker", "receiver": worker_email,
         "amount_cents": worker},
        {"party": "checker", "receiver": checker_email,
         "amount_cents": checker},
        {"party": "platform", "receiver": PLATFORM_RECEIVER_EMAIL,
         "amount_cents": platform},
    ]


def do_payouts(job):
    """Run (or resume) ONLY the payouts leg for a captured job.
    the checker's fee is recorded as vesting, not paid.
    Returns True when the payouts batch was RECOVERED (an existing
    PayPal batch adopted after a lost create response) rather than
    freshly created."""
    job = ensure_advance_payout(job)
    if job.trust_credit_state == 'advanced':
        total = job.funded_amount_cents or job.price_cents
    else:
        total = job.captured_amount_cents
    items = split_items(job, total)
    checker_item = next(it for it in items if it["party"] == "checker")
    if job.trust_credit_state == 'advanced':
        for it in items:
            if it["party"] == "worker":
                it["amount_cents"] -= (job.advanced_cents or 0)
    pay_items = [it for it in items if it["party"] != "checker" and it["amount_cents"] > 0]
    batch_id, paid, payouts_recovered = create_or_adopt_payouts(
        str(job.id), pay_items, currency=job.captured_currency or 'USD')
    set_job_settled(job.id, batch_id, paid)
    
    settled_items = []
    for item in items:
        if item["party"] == "checker":
            if item["amount_cents"] == 0:
                settled_items.append({"party": item["party"],
                                     "amount_cents": item["amount_cents"],
                                     "payout_item_id": None,
                                     "status": "vesting"})
            else:
                settled_items.append({"party": item["party"],
                                     "amount_cents": item["amount_cents"],
                                     "payout_item_id": None,
                                     "status": "vesting"})
        elif item["amount_cents"] > 0:
            paid_item = next(p for p in paid if p["party"] == item["party"])
            settled_items.append({"party": item["party"],
                                 "amount_cents": item["amount_cents"],
                                 "payout_item_id": paid_item["payout_item_id"],
                                 "status": paid_item["status"]})
        else:
            settled_items.append({"party": item["party"],
                                 "amount_cents": item["amount_cents"],
                                 "payout_item_id": None,
                                 "status": "skipped_zero_amount"})
    
    add_event(job.id, 'settled', actor='client',
              detail={"payout_batch_id": batch_id,
                      "payouts_recovered": payouts_recovered,
                      "trust_credit_advanced_cents":
                          job.advanced_cents or 0,
                      "checker_fee_vesting_cents":
                          checker_item["amount_cents"],
                      "items": settled_items})
    if not job.checker_vesting_state:
        start_vesting(job, checker_item["amount_cents"])
    return payouts_recovered


def start_vesting(job, checker_amount_cents: int):
    hours = job.terms_vesting_hours \
        if job.terms_vesting_hours and job.terms_vesting_hours > 0 else 0
    release_at = (datetime.now(timezone.utc)
                  + timedelta(hours=hours)).isoformat()
    set_checker_vesting(job.id, checker_amount_cents, release_at)
    add_event(job.id, 'checker_fee_vesting', actor='system',
              detail={"amount_cents": checker_amount_cents,
                      "vesting_hours": hours,
                      "release_at": release_at})
    if hours == 0:
        release_vesting(get_job(job.id))


def release_vesting(job) -> bool:
    # An overturned dispute assigns the fee to the CLIENT. If that
    # recovery payout failed, the fee is still 'vesting' with
    # dispute_state 'overturned' — releasing it here would pay the
    # checker money the dispute decision gave to the client. The
    # fee may only be released when no dispute overturned it; a
    # failed client recovery stays held for retry through the
    # dispute path.
    if (job is None or job.checker_vesting_state != 'vesting'
            or job.dispute_state in ('open', 'overturned')):
        return False
    checker_party = get_party(job.checker_id) if job.checker_id else None
    receiver = (checker_party['payout_email']
                if checker_party and checker_party.get('payout_email')
                else CHECKER_RECEIVER_EMAIL)
    items = [{"party": "checker", "receiver": receiver,
              "amount_cents": job.checker_vesting_amount_cents}]
    items = [it for it in items if it["amount_cents"] > 0]
    if not items:
        set_checker_released(job.id, '', '')
        add_event(job.id, 'checker_fee_released', actor='system',
                  detail={"payout_batch_id": '',
                          "payout_item_id": '',
                          "amount_cents": 0})
        return True
    try:
        batch_id, paid, vesting_recovered = create_or_adopt_payouts(
            str(job.id), items,
            currency=job.captured_currency or job.currency or 'USD',
            batch_tag='vesting')
    except Exception as e:
        add_event(job.id, 'vesting_release_error', actor='system',
                  detail={"error": str(e)})
        return False
    item_id = paid[0]['payout_item_id'] if paid else ''
    set_checker_released(job.id, batch_id, item_id)
    add_event(job.id, 'checker_fee_released', actor='system',
              detail={"payout_batch_id": batch_id,
                      "payout_item_id": item_id,
                      "payouts_recovered": vesting_recovered,
                      "amount_cents": job.checker_vesting_amount_cents})
    return True


def maybe_release_vesting(job):
    """Release a due, undisputed vesting fee (page-view pattern)."""
    if (job is None or job.checker_vesting_state != 'vesting'
            or job.dispute_state == 'open' or not job.checker_release_at):
        return job
    try:
        due = datetime.fromisoformat(job.checker_release_at)
    except ValueError:
        return job
    if datetime.now(timezone.utc) >= due:
        release_vesting(job)
        return get_job(job.id) or job
    return job


def ensure_advance_payout(job):
    """Ensure the trust-credit advance payout exists and is complete.
    
    If the job is in the wedged state (trust_credit_state='advanced' but
    advance_batch_id is empty), rebuild the advance payout leg exactly as
    maybe_advance_trust_credit built it, using the same batch_tag='advance'
    to make PayPal-side adoption idempotent.
    
    The invariant: advanced_cents is deducted from the settle batch ONLY
    when the advance batch exists.
    """
    if (job.trust_credit_state != 'advanced' or job.advance_batch_id or
        (job.advanced_cents or 0) <= 0 or not job.advance_capture_id):
        return job
    
    total = job.funded_amount_cents or job.price_cents
    worker_email = split_items(job, total)[0]["receiver"]
    items = [{"party": "worker", "receiver": worker_email,
              "amount_cents": job.advanced_cents}]
    items = [it for it in items if it["amount_cents"] > 0]
    
    batch_id, paid, _advance_recovered = create_or_adopt_payouts(
        str(job.id), items,
        currency=job.funded_currency or 'USD', batch_tag='advance')
    
    set_job_trust_credit(job.id, job.advance_capture_id, batch_id, paid,
                         job.advanced_cents)
    add_event(job.id, 'trust_credit_advance_recovered',
              actor='system (trust credit)',
              detail={"amount_cents": job.advanced_cents,
                      "payout_batch_id": batch_id,
                      "payouts_recovered": _advance_recovered})
    
    return get_job(job.id)


def expected_advance_cents(job):
    """Helper: total = job.funded_amount_cents or job.price_cents;
    worker_share = total * WORKER_SPLIT_PERCENT // 100; return
    (worker_share * pct + 50) // 100 with pct =
    job.terms_trust_credit_percent or 0."""
    total = job.funded_amount_cents or job.price_cents
    worker_share = total * WORKER_SPLIT_PERCENT // 100
    pct = job.terms_trust_credit_percent or 0
    return (worker_share * pct + 50) // 100


def reconcile_advance_capture(job):
    """Helper: no-op returning job unchanged UNLESS:
    pct > 0, trust_credit_state != 'advanced', no advance_capture_id,
    job.paypal_order_id present, expected advance > 0.
    Read the order via get_order(job.paypal_order_id) (wrap in
    try/except: any failure -> return job unchanged; this helper
    NEVER raises).
    Scan purchase_units[].payments.captures for a capture whose
    amount in cents equals the expected advance exactly
    (parse the amount value the same way the codebase does —
    see _parse_amount_to_cents in app/paypal_client.py; import
    it if it is importable, else convert the decimal string).
    Require status COMPLETED. If exactly one match:
    set_job_trust_credit(job.id, cap_id, '', [], cap_cents);
    add_event 'trust_credit_advance_capture_recovered'
    (actor 'system (trust credit)') with detail {capture_id,
    amount_cents, note about the lost response}; then complete
    the payout leg by calling ensure_advance_payout(get_job(
    job.id)) (the FIX1 helper — it creates/adopts the advance
    batch now that the state is 'advanced' with an empty batch
    id) and return its result.
    Zero or multiple matches -> return job unchanged.
    """
    if not job.paypal_order_id:
        return job
    
    pct = job.terms_trust_credit_percent or 0
    if pct <= 0 or job.trust_credit_state == 'advanced' or job.advance_capture_id:
        return job
    
    expected = expected_advance_cents(job)
    if expected <= 0:
        return job
    
    try:
        order = get_order(job.paypal_order_id)
    except Exception:
        return job
    
    matches = []
    for unit in order.get('purchase_units', []) or []:
        payments = unit.get('payments', {}) or {}
        for cap in payments.get('captures', []) or []:
            cap_amount = cap.get('amount', {}) or {}
            cap_cents = _parse_amount_to_cents(cap_amount.get('value', ''))
            if cap_cents == expected and cap.get('status') == 'COMPLETED':
                matches.append((cap['id'], cap_cents))
    
    if len(matches) != 1:
        return job
    
    cap_id, cap_cents = matches[0]
    set_job_trust_credit(job.id, cap_id, '', [], cap_cents)
    add_event(job.id, 'trust_credit_advance_capture_recovered',
              actor='system (trust credit)',
              detail={"capture_id": cap_id,
                      "amount_cents": cap_cents,
                      "note": f"advance capture {cap_id} recovered from PayPal order {job.paypal_order_id} (lost-response case)"})
    return ensure_advance_payout(get_job(job.id))


def maybe_advance_trust_credit(job):
    """when a job reaches checked_pass and its stored
    terms grant trust credit, immediately capture that percent of
    the WORKER's share (partial capture, remainder stays held) and
    pay it out to the worker. Any failure is recorded as an event
    and changes nothing else. The advance is never clawed back."""
    try:
        if job.state != 'checked_pass':
            return
        pct = job.terms_trust_credit_percent or 0
        if pct <= 0 or job.trust_credit_state == 'advanced':
            return
        if not job.paypal_authorization_id or not credentials_present():
            return
        total = job.funded_amount_cents or job.price_cents
        worker_share = total * WORKER_SPLIT_PERCENT // 100
        advance = expected_advance_cents(job)
        if advance <= 0 or advance >= total:
            return
        cap_id, cap_status, cap_cents, cap_cur = \
            capture_authorization_amount(
                job.paypal_authorization_id, str(job.id), advance,
                job.funded_currency or 'USD', False, 'advance')
        if cap_status != 'COMPLETED' or not cap_id:
            raise RuntimeError(f"advance capture status {cap_status}")
        # Record the advance IMMEDIATELY, before the payout leg (see
        # the note in the 2.8 hardening: an unrecorded advance
        # capture wedges settlement).
        set_job_trust_credit(job.id, cap_id, '', [], cap_cents)
        worker_email = split_items(job, total)[0]["receiver"]
        items = [{"party": "worker", "receiver": worker_email,
                  "amount_cents": cap_cents}]
        items = [it for it in items if it["amount_cents"] > 0]
        if not items:
            return
        batch_id, paid, _advance_recovered = create_or_adopt_payouts(
            str(job.id), items,
            currency=cap_cur, batch_tag='advance')
        set_job_trust_credit(job.id, cap_id, batch_id, paid, cap_cents)
        add_event(job.id, 'trust_credit_advanced',
                  actor='system (trust credit)',
                  detail={"percent": pct, "amount_cents": cap_cents,
                          "capture_id": cap_id,
                          "payout_batch_id": batch_id})
    except Exception as e:
        job2 = reconcile_advance_capture(job)
        if job2.trust_credit_state == 'advanced':
            return job2
        add_event(job.id, 'trust_credit_error',
                  actor='system (trust credit)',
                  detail={"error": f"{type(e).__name__}: {e}"})


def do_refund(job, actor: str):
    """Return the client's money in full: void the authorization
    when uncaptured; refund the capture when one exists.
    
    Also refunds any trust-credit advance capture (partial capture) if present.
    An advance capture is a COMPLETED partial capture; a void alone never returns it.
    """
    advance_refund_id = None
    advance_refund_status = None
    authorization_voided = False
    
    if job.capture_id:
        refund_id, refund_status = refund_capture(
            job.capture_id, str(job.id),
            job.captured_amount_cents,
            job.captured_currency or 'USD')
        via_capture = True
    else:
        refund_status = void_authorization(
            job.paypal_authorization_id, str(job.id))
        refund_id = job.paypal_authorization_id  # the voided auth
        via_capture = False
        authorization_voided = True
    
    if job.advance_capture_id:
        advance_refund_id, advance_refund_status = refund_capture(
            job.advance_capture_id, str(job.id),
            job.advanced_cents,
            job.captured_currency or job.funded_currency or 'USD',
            suffix="advance")
    
    set_job_refunded(job.id, refund_id, refund_status)
    
    detail = {
        "refund_id": refund_id,
        "refund_status": refund_status,
        "via_capture": via_capture,
        "advance_refund_id": advance_refund_id,
        "advance_refund_status": advance_refund_status,
        "authorization_voided": authorization_voided,
    }
    add_event(job.id, 'refunded', actor=actor, detail=detail)


# --- actions ----------------------------------------------------------

def create_job_action(*, title, description, price_cents, currency,
                      criteria, client_id, worker_id, checker_id,
                      via, actor, endpoint, price_mode="fixed",
                      circle="", invited_worker_id=None):
    """Create a job (the /post form and POST /api/v1/jobs share this).

    price_mode 'open' posts the job WITHOUT a price (a listing):
    price_cents is forced to 0 and worker_id may be None — workers
    bid, and accepting one bid locks the worker and the price."""
    if price_mode == "open":
        price_cents = 0
    
    # Storage mapping (worker column / invited column):
    # - circle '' (legacy): exactly as today (worker_id as passed).
    # - 'invited': invited = worker_id; stored worker = worker_id
    #   when fixed, None when open price (as today for open).
    # - 'both': invited = worker_id; stored worker = 0 when fixed,
    #   None when open price.
    # - 'open': invited = 0; stored worker = 0 when fixed, None
    #   when open price.
    stored_worker_id = worker_id
    if circle == 'invited':
        stored_worker_id = worker_id if price_mode == 'fixed' else None
    elif circle == 'both':
        stored_worker_id = 0 if price_mode == 'fixed' else None
    elif circle == 'open':
        stored_worker_id = 0 if price_mode == 'fixed' else None
    
    # Set the invited_worker_id based on the storage mapping
    # If invited_worker_id is explicitly provided (API path), use it
    # Otherwise, derive it from worker_id for circle 'invited' or 'both',
    # or use 0 for other circles
    if invited_worker_id is not None:
        final_invited_worker_id = invited_worker_id
    else:
        final_invited_worker_id = worker_id if circle in ('invited', 'both') else 0
    
    job = create_job(title, description, price_cents, currency, criteria,
                     client_id=client_id, worker_id=stored_worker_id,
                     checker_id=checker_id, price_mode=price_mode,
                     circle=circle, invited_worker_id=final_invited_worker_id)
    
    event_detail = {"price_cents": price_cents, "currency": currency,
                    "price_mode": price_mode, "circle": circle}
    if invited_worker_id:
        event_detail["invited_worker_id"] = invited_worker_id
    
    add_event(job.id, 'posted', actor='client',
              detail=event_detail,
              created_at=job.created_at)
    
    log_msg = (f"title={title!r} price_cents={price_cents} "
               f"price_mode={price_mode} criteria={len(criteria)}")
    if circle:
        log_msg += f" circle={circle}"
    _log(job.id, actor, via, 'create', endpoint, log_msg, 201)
    return job


def fund_job_action(job_id, *, via, actor, endpoint):
    """Fund a posted job: authorize at PayPal, then the Settlement
    Brain sets the terms. Returns (job, note); raises ServiceError
    with the UI's messages on refusal."""
    job = get_job(job_id)
    if job is None:
        raise ServiceError("Job not found", 404)
    if job.paypal_order_id:
        note = ("Already funded: this job was previously authorized "
                "against PayPal (no new order created).")
        _log(job_id, actor, via, 'fund', endpoint, note, 200,
             _paypal_ids(job))
        return job, note
    if job.state != 'posted':
        msg = "Funding is only available on jobs in the 'posted' state."
        _log(job_id, actor, via, 'fund', endpoint, msg, 409)
        raise ServiceError(msg, 409)
    # Price-negotiation invariant: the vault only ever holds an
    # AGREED price. An open job has no price (and no worker) until
    # the client accepts an offer — funding before that is refused,
    # so a funded amount can never diverge from the locked price.
    if not price_agreed(job):
        if job.price_mode == 'fixed' and job.circle == 'invited':
            msg = ("This job is waiting for the invited worker to accept "
                   "the listed price (or counter-offer) — funding opens "
                   "once the price is agreed.")
        elif job.price_mode == 'fixed' and job.circle in ('open', 'both'):
            msg = ("No worker has been agreed yet — funding opens once the "
                   "client accepts a worker's offer.")
        else:
            msg = ("This job has no agreed price yet — the client must "
                   "accept an offer first. Funding opens once a price "
                   "is locked.")
        _log(job_id, actor, via, 'fund', endpoint, msg, 409)
        raise ServiceError(msg, 409)
    if not credentials_present():
        set_job_paypal_error(
            job_id, "PayPal credentials are absent from the environment.")
        _log(job_id, actor, via, 'fund', endpoint,
             "PayPal credentials absent", 500)
        return get_job(job_id), None
    try:
        order_id, auth_id, auth_status, funded_cents, funded_currency = \
            authorize_order(str(job.id), job.price_cents, job.currency)
    except PayPalError as e:
        err_msg = f"PayPal {e.status_code}"
        if e.issue:
            err_msg += f" — {e.issue}"
        if e.debug_id:
            err_msg += f" (debug_id: {e.debug_id})"
        if e.message:
            err_msg += f": {e.message}"
        set_job_paypal_error(job_id, err_msg)
        _log(job_id, actor, via, 'fund', endpoint, err_msg,
             e.status_code or 502)
        raise ServiceError(err_msg, e.status_code or 502)
    except Exception as e:
        err_msg = f"PayPal call failed: {type(e).__name__}: {e}"
        set_job_paypal_error(job_id, err_msg)
        _log(job_id, actor, via, 'fund', endpoint, err_msg, 502)
        raise ServiceError(err_msg, 502)

    # Invariant, enforced at the boundary: the authorized amount
    # must equal the job's locked price, to the cent and currency.
    if funded_cents != job.price_cents or \
            funded_currency != job.currency:
        err_msg = (f"Funding invariant violated: PayPal authorized "
                   f"{funded_cents} {funded_currency}, but the "
                   f"job's locked price is {job.price_cents} "
                   f"{job.currency}. Nothing was recorded; the "
                   "authorization is left untouched for inspection.")
        set_job_paypal_error(job_id, err_msg)
        _log(job_id, actor, via, 'fund', endpoint, err_msg, 502)
        raise ServiceError(err_msg, 502)

    set_job_funded(job_id, order_id, auth_id, auth_status,
                   funded_cents, funded_currency)
    job = get_job(job_id)
    worker_counters = get_party_counters(job.worker_id or 2)
    checker_counters = get_party_counters(job.checker_id or 3)
    brain_result = decide_terms(job, worker_counters, checker_counters)
    set_job_terms(job_id, brain_result["terms"],
                  brain_result["narrative"], brain_result["model"],
                  brain_result["degraded"])
    add_event(job_id, 'terms_set', actor='settlement_brain',
              detail={**brain_result["terms"],
                      "model": brain_result["model"],
                      "degraded": brain_result["degraded"]})
    add_event(job_id, 'funded', actor='client',
              detail={"order_id": order_id,
                      "authorization_id": auth_id,
                      "authorization_status": auth_status,
                      "amount_cents": funded_cents,
                      "currency": funded_currency})
    job = get_job(job_id)
    _log(job_id, actor, via, 'fund', endpoint,
         f"amount_cents={funded_cents} terms_model="
         f"{brain_result['model']} degraded={brain_result['degraded']}",
         200, _paypal_ids(job))
    return job, None


def _sanitize_filename(filename: str) -> str:
    base = os.path.basename(filename or "file")
    return "".join(c if (c.isalnum() or c in "._- ") else "_"
                   for c in base)[:120] or "file"


def deliver_job_action(job_id, files, note, *, via, actor, endpoint):
    """Store a delivery: files = [(original_filename, bytes)]."""
    job = get_job(job_id)
    if job is None:
        raise ServiceError("Job not found", 404)
    if job.state == 'delivered':
        msg = ("This job has already been delivered. Re-delivery is "
               "only possible through the revision path.")
        _log(job_id, actor, via, 'deliver', endpoint, msg, 409)
        raise ServiceError(msg, 409)
    if job.state != 'funded':
        msg = ("Delivery is only available on jobs in the 'funded' "
               "state.")
        _log(job_id, actor, via, 'deliver', endpoint, msg, 409)
        raise ServiceError(msg, 409)
    if not files:
        msg = "No file selected. Please choose at least one file to deliver."
        _log(job_id, actor, via, 'deliver', endpoint, msg, 400)
        raise ServiceError(msg, 400)
    for orig_filename, data in files:
        if len(data) > MAX_FILE_SIZE:
            msg = (f"File '{orig_filename}' is too large "
                   f"({len(data)} bytes). Maximum is 25 MB per file.")
            _log(job_id, actor, via, 'deliver', endpoint, msg, 413)
            raise ServiceError(msg, 413)
    job_dir = os.path.join(DELIVERIES_DIR, str(job_id))
    os.makedirs(job_dir, exist_ok=True)
    names = []
    for orig_filename, data in files:
        safe_name = _sanitize_filename(orig_filename)
        stored_name = f"{uuid.uuid4().hex}_{safe_name}"
        with open(os.path.join(job_dir, stored_name), 'wb') as f:
            f.write(data)
        add_delivery(job_id=job.id, filename=safe_name,
                     stored_name=stored_name, size_bytes=len(data),
                     sha256=hashlib.sha256(data).hexdigest(), note=note)
        names.append(orig_filename)
    set_job_delivered(job.id)
    add_event(job.id, 'delivered', actor='worker',
              detail={"files": names})
    job = get_job(job_id)
    _log(job_id, actor, via, 'deliver', endpoint,
         f"files={names} note={note[:80]!r}", 200, _paypal_ids(job))
    return job


def check_job_action(job_id, *, via, actor, endpoint):
    """Run the checker (single or dual per the job's Brain terms),
    record the verdict, advance trust credit on PASS, and auto-refund
    on a final (post-revision) FAIL — exactly the UI check path."""
    job = get_job(job_id)
    if job is None:
        raise ServiceError("Job not found", 404)
    allowed, reason = can_check(job_id)
    if not allowed:
        _log(job_id, actor, via, 'check', endpoint, reason, 409)
        raise ServiceError(reason, 409)
    if job.state != 'delivered':
        msg = ("Checking is only available on jobs in the 'delivered' "
               "state.")
        _log(job_id, actor, via, 'check', endpoint, msg, 409)
        raise ServiceError(msg, 409)
    try:
        if job.terms_verification_mode == 'dual':
            v1 = run_check(job_id, judge_model=JUDGE_MODEL,
                           suppress_first_events=True)
            v2 = run_check(job_id, judge_model=JUDGE_FALLBACK_MODEL,
                           suppress_first_events=True)
            dual_incomplete = bool(getattr(v1, 'incomplete', False)
                                   or getattr(v2, 'incomplete', False))
            both = bool(v1.overall_pass and v2.overall_pass)
            if dual_incomplete:
                # A completed first run may already have moved
                # the job internally; a combined incomplete run
                # decides nothing, so restore the pre-check state.
                set_job_state(job_id, job.state)
            else:
                set_job_checked(job_id, both)
                emit_verdict_events(job_id, both)
            verdict = SimpleNamespace(
                overall_pass=both and not dual_incomplete,
                judge_model=f"dual: {v1.judge_model} + {v2.judge_model}",
                items=list(v1.items) + list(v2.items),
                incomplete=dual_incomplete)
        else:
            verdict = run_check(job_id)
    except CheckNotAllowedError as e:
        _log(job_id, actor, via, 'check', endpoint, str(e), 409)
        raise ServiceError(str(e), 409)
    except Exception as e:
        msg = f"Check could not be completed: {type(e).__name__}: {e}"
        _log(job_id, actor, via, 'check', endpoint, msg, 502)
        raise ServiceError(msg, 502)
    job = get_job(job_id)
    if getattr(verdict, 'incomplete', False):
        # the judge was unavailable — nothing was
        # decided. Record the incomplete attempt on the timeline
        # and surface it; no verdict event, no trust credit, no
        # refund, and the job stays in 'delivered'.
        add_event(job_id, 'check_incomplete', actor='checker',
                  detail={"reason": "the AI judge was unavailable; "
                          "the check did not complete and nothing "
                          "was decided",
                          "judge_model": verdict.judge_model})
        _log(job_id, actor, via, 'check', endpoint,
             "check incomplete: judge unavailable", 503,
             _paypal_ids(job))
        raise ServiceError(
            "The check could not be completed — the AI judge is "
            "unavailable. Nothing was decided; please try again.",
            503)
    add_event(job_id, 'verdict', actor='checker',
              detail={"overall_pass": verdict.overall_pass,
                      "judge_model": verdict.judge_model,
                      "items": len(verdict.items)})
    if job is not None and job.state == 'checked_pass':
        maybe_advance_trust_credit(job)
    if not verdict.overall_pass and job.revision_used:
        try:
            do_refund(job, actor='system (second FAIL)')  # covers trust-credit advance capture as well
        except Exception as e:
            add_event(job_id, 'refund_error', actor='system',
                      detail={"error": f"{type(e).__name__}: {e}"})
        job = get_job(job_id)
    _log(job_id, actor, via, 'check', endpoint,
         f"overall_pass={verdict.overall_pass} judge="
         f"{verdict.judge_model} items={len(verdict.items)}",
         200, _paypal_ids(job))
    return job, verdict


def settle_job_action(job_id, *, via, actor, endpoint):
    """Settle a checked_pass job: capture (or resume payouts after a
    recorded capture). Returns (job, note); raises ServiceError."""
    job = get_job(job_id)
    if job is None:
        raise ServiceError("Job not found", 404)
    if job.state == 'settled':
        note = ("Already settled: capture and payouts are complete. "
                "Re-running settle moves no money.")
        _log(job_id, actor, via, 'settle', endpoint, note, 200,
             _paypal_ids(job))
        return job, note
    if not credentials_present():
        note = "PayPal credentials are absent from the environment."
        _log(job_id, actor, via, 'settle', endpoint, note, 500)
        return job, note
    # Start of settle_job_action: heal wedged advance on lost-response
    if (job.terms_trust_credit_percent or 0) > 0 and job.trust_credit_state != 'advanced':
        job = reconcile_advance_capture(job)
        job = get_job(job.id)
    # Resume path: capture already recorded -> retry payouts only.
    if job.state == 'settle_error' and job.capture_id:
        if not job.captured_amount_cents:
            try:
                from app.paypal_client import get_capture
                cap = get_capture(job.capture_id)
                amt = cap.get('amount', {}) or {}
                if amt.get('value'):
                    cents = int(round(float(amt['value']) * 100))
                    set_job_captured(
                        job_id, job.capture_id,
                        cap.get('status', job.capture_status),
                        cents, amt.get('currency_code', 'USD'))
                    job = get_job(job_id)
            except Exception:
                pass
        # Re-verify linkage before any payout runs: the earlier
        # attempt may have stopped at an unverifiable or refused
        # linkage, and the payouts leg must never run on a capture
        # whose linkage is unproven. (Before 2026-10-10 the resume
        # path trusted the recorded capture blindly; a proven
        # foreign capture parked in settle_error could have been
        # paid out by a resume.)
        if job.captured_amount_cents:
            try:
                _validate_capture_linkage(
                    job, job.capture_id, job.capture_status,
                    job.captured_amount_cents, job.captured_currency,
                    actor=actor)
            except CaptureLinkageUnverifiable as e:
                set_job_settle_error(
                    job_id,
                    f"Linkage verification still incomplete: {e}. "
                    f"No payouts have run.")
                job = get_job(job_id)
                _log(job_id, actor, via, 'settle', endpoint,
                     f"resume paused — linkage unverifiable: {e}", 502,
                     _paypal_ids(job))
                return job, (f"Resume paused — capture linkage could "
                             f"not be verified yet: {e}")
            except ServiceError as e:
                set_job_settle_error(
                    job_id,
                    f"Capture linkage refused on resume: {e}. "
                    f"Payouts remain blocked.")
                job = get_job(job_id)
                _log(job_id, actor, via, 'settle', endpoint,
                     f"resume blocked — linkage refused: {e}", 502,
                     _paypal_ids(job))
                return job, (f"Resume refused — capture linkage "
                             f"failed: {e}. Payouts remain blocked.")
        try:
            payouts_recovered = do_payouts(job)
        except Exception as e:
            set_job_settle_error(job_id, f"Payouts retry failed: {e}")
            job = get_job(job_id)
            _log(job_id, actor, via, 'settle', endpoint,
                 f"Payouts retry failed: {e}", 502, _paypal_ids(job))
            return job, f"Payouts retry failed: {e}"
        job = get_job(job_id)
        _log(job_id, actor, via, 'settle', endpoint,
             "payouts resumed (existing PayPal batch adopted)"
             if payouts_recovered else "payouts resumed",
             200, _paypal_ids(job))
        return job, None
    if job.state != 'checked_pass':
        msg = ("Settlement is only available on jobs in the "
               "'checked_pass' state.")
        _log(job_id, actor, via, 'settle', endpoint, msg, 409)
        raise ServiceError(msg, 409)
    # Leg 1: capture the held authorization (remainder when a
    # trust-credit advance was recorded; full amount otherwise).
    if not job.capture_id:
        expected_cents = ((job.funded_amount_cents or job.price_cents)
                          - (job.advanced_cents or 0)
        if job.trust_credit_state == 'advanced'
        else (job.funded_amount_cents or job.price_cents))
        try:
            if job.trust_credit_state == 'advanced':
                cap_id, cap_status, cap_cents, cap_cur = \
                    capture_authorization_amount(
                        job.paypal_authorization_id, str(job.id),
                        expected_cents, job.funded_currency or 'USD',
                        True, 'final')
            else:
                cap_id, cap_status, cap_cents, cap_cur = \
                    capture_authorization(job.paypal_authorization_id,
                                          str(job.id))
        except PayPalError as e:
            adopted = None
            if 'MAX_CAPTURE_AMOUNT_EXCEEDED' in str(e):
                try:
                    order = get_order(job.paypal_authorization_id)
                    for unit in order.get('purchase_units', []) or []:
                        payments = unit.get('payments', {}) or {}
                        for cap in payments.get('captures', []) or []:
                            amt = cap.get('amount', {}) or {}
                            cents = int(round(
                                float(amt.get('value', '0')) * 100))
                            if (cap.get('status') == 'COMPLETED'
                                    and cents == expected_cents):
                                adopted = (cap.get('id', ''),
                                           cap.get('status', ''), cents,
                                           amt.get('currency_code',
                                                   'USD'))
                except Exception:
                    adopted = None
            if adopted is None:
                if e.issue in ('AUTHORIZATION_DENIED', 'AUTHORIZATION_VOIDED', 'AUTHORIZATION_REJECTED', 'TRANSACTION_REFUSED'):
                    set_job_voided_authorization_refusal(job_id, f"Settlement refused: PayPal {e.status_code} — {e.issue}: {e.message}")
                    add_event(job_id, 'settle_refused_voided_authorization',
                              actor='system (settlement)',
                              detail={
                                  'error_code': e.issue,
                                  'error_message': e.message,
                                  'capture_id': job.capture_id,
                                  'authorization_id': job.paypal_authorization_id,
                                  'expected_cents': expected_cents,
                                  'note': 'Authorization was voided/denied at PayPal. The client can refund / close the job manually. No capture or payout occurred.'
                              })
                    _log(job_id, actor, via, 'settle', endpoint,
                         f"Settlement refused — voided authorization ({e.issue}): {e.message}", 502,
                         _paypal_ids(job))
                    return job, f"Settlement refused — authorization voided/denied at PayPal ({e.issue}). The client can refund / close the job manually."
                msg = f"Capture failed: {e}"
                _log(job_id, actor, via, 'settle', endpoint, msg, 502,
                     _paypal_ids(job))
                raise ServiceError(msg, 502)
            cap_id, cap_status, cap_cents, cap_cur = adopted
        except Exception as e:
            adopted = None
            if 'MAX_CAPTURE_AMOUNT_EXCEEDED' in str(e):
                try:
                    order = get_order(job.paypal_authorization_id)
                    for unit in order.get('purchase_units', []) or []:
                        payments = unit.get('payments', {}) or {}
                        for cap in payments.get('captures', []) or []:
                            amt = cap.get('amount', {}) or {}
                            cents = int(round(
                                float(amt.get('value', '0')) * 100))
                            if (cap.get('status') == 'COMPLETED'
                                    and cents == expected_cents):
                                adopted = (cap.get('id', ''),
                                           cap.get('status', ''), cents,
                                           amt.get('currency_code',
                                                   'USD'))
                except Exception:
                    adopted = None
            if adopted is None:
                msg = f"Capture failed: {e}"
                _log(job_id, actor, via, 'settle', endpoint, msg, 502,
                     _paypal_ids(job))
                raise ServiceError(msg, 502)
            cap_id, cap_status, cap_cents, cap_cur = adopted
        
        # Validate adopted capture linkage BEFORE recording capture_recovered
        job_before_captured = get_job(job_id)
        try:
            _validate_capture_linkage(job_before_captured, cap_id, cap_status,
                                     cap_cents, cap_cur, actor='system (settlement)')
        except CaptureLinkageUnverifiable as e:
            # NOT a refusal: no evidence says the capture is foreign;
            # PayPal reads stayed incomplete across the retry window.
            # The capture is NOT recorded and no refusal is written —
            # the job keeps its checked_pass state (the state-
            # preserving helper) with an honest "verification
            # incomplete" note, and pressing Settle again re-runs
            # the verification. No money moves.
            set_job_voided_authorization_refusal(
                job_id, f"Capture linkage verification incomplete: {e}")
            add_event(job_id, 'settle_linkage_unverifiable',
                      actor='system (settlement)',
                      detail={
                          'error': str(e),
                          'capture_id': cap_id,
                          'authorization_id': job_before_captured.paypal_authorization_id,
                          'expected_cents': expected_cents,
                          'note': 'Linkage verification incomplete (PayPal reads incomplete). Not a refusal: no capture recorded, no money moved. Press Settle again to re-verify.'
                      })
            _log(job_id, actor, via, 'settle', endpoint,
                 f"Settlement paused — capture linkage unverifiable: {e}", 502,
                 _paypal_ids(job_before_captured))
            return job_before_captured, (f"Settlement paused — the capture's linkage "
                                        f"could not be verified because PayPal reads "
                                        f"stayed incomplete: {e}. This is not a "
                                        f"refusal. Press Settle again to re-verify.")
        except ServiceError as e:
            # FD.3 coordinator micro-fix: the capture has NOT been
            # recorded as the job's own here, so the refusal keeps
            # state checked_pass (FD.2 discipline) — store the error
            # text via the state-preserving helper, not
            # set_job_settle_error.
            set_job_voided_authorization_refusal(job_id, f"Capture linkage validation failed: {e}")
            add_event(job_id, 'settle_refused_capture_linkage',
                      actor='system (settlement)',
                      detail={
                          'error': str(e),
                          'capture_id': cap_id,
                          'authorization_id': job_before_captured.paypal_authorization_id,
                          'expected_cents': expected_cents,
                          'note': 'Capture adoption refused: capture does not belong to this job\'s authorization. The client can refund / close the job manually.'
                      })
            _log(job_id, actor, via, 'settle', endpoint,
                 f"Settlement refused — capture linkage failed: {e}", 502,
                 _paypal_ids(job_before_captured))
            return job_before_captured, (f"Settlement refused — capture linkage failed: {e}. "
                                        f"The capture does not belong to this job's authorization. "
                                        f"The client can refund / close the job manually.")
        
        # Record capture_recovered event AFTER linkage validation passes
        add_event(job_id, 'capture_recovered',
                  actor='system (settlement)',
                  detail={"capture_id": cap_id,
                          "amount_cents": cap_cents,
                          "note": "capture adopted from PayPal "
                                  "after a lost response"})
        
        set_job_captured(job_id, cap_id, cap_status, cap_cents, cap_cur)
        add_event(job_id, 'captured', actor='client',
                  detail={"capture_id": cap_id,
                          "capture_status": cap_status,
                          "amount_cents": cap_cents,
                          "currency": cap_cur})
        job = get_job(job_id)
    # Leg 2: payouts (worker + platform now; checker fee vests).
    try:
        _validate_capture_linkage(job, job.capture_id, job.capture_status,
                                 job.captured_amount_cents, job.captured_currency,
                                 actor='client')
    except CaptureLinkageUnverifiable as e:
        # Parked resumably with honest wording: the capture is
        # recorded, no payouts have run, and this is NOT a refusal —
        # PayPal reads stayed incomplete across the retry window.
        set_job_settle_error(
            job_id,
            f"Capture {job.capture_id} completed, but its linkage "
            f"could not be verified (PayPal reads incomplete): {e}. "
            f"No payouts have run. Use 'Resume payouts' to re-verify "
            f"and continue.")
        job = get_job(job_id)
        _log(job_id, actor, via, 'settle', endpoint,
             f"linkage unverifiable: {e}", 502, _paypal_ids(job))
        return job, (f"Capture {job.capture_id} completed, but its "
                     f"linkage could not be verified yet: {e}")
    except Exception as e:
        # This is the direct/leg-2 refusal: capture WAS recorded, but validation failed
        set_job_settle_error(
            job_id,
            f"Capture {job.capture_id} completed, but payouts "
            f"failed: {e}. Use 'Resume payouts' to retry only the "
            f"payouts leg.")
        job = get_job(job_id)
        _log(job_id, actor, via, 'settle', endpoint,
             f"payouts failed: {e}", 502, _paypal_ids(job))
        return job, (f"Capture {job.capture_id} completed, but payouts "
                      f"failed: {e}")
    
    # AFTER linkage validation passes, run payouts (FD.3 fix).
    # A payouts failure here (e.g. the create response lost twice in
    # transit) lands in the same recoverable settle_error state as a
    # linkage refusal: the capture is recorded, the batch may already
    # exist at PayPal exactly once, and 'Resume payouts' adopts it —
    # the action never propagates as an unhandled error and never
    # starts a second batch.
    try:
        do_payouts(job)
    except Exception as e:
        set_job_settle_error(
            job_id,
            f"Capture {job.capture_id} completed, but payouts "
            f"failed: {e}. Use 'Resume payouts' to retry only the "
            f"payouts leg.")
        job = get_job(job_id)
        _log(job_id, actor, via, 'settle', endpoint,
             f"payouts failed: {e}", 502, _paypal_ids(job))
        return job, (f"Capture {job.capture_id} completed, but payouts "
                     f"failed: {e}")
    job = get_job(job_id)
    _log(job_id, actor, via, 'settle', endpoint,
         f"captured_cents={job.captured_amount_cents}", 200,
         _paypal_ids(job))
    return job, None


# --- price negotiation (posted state only) ---------------------------
# The negotiation window is exactly the 'posted' state: while a job
# is posted and unfunded, workers may offer and the client may
# accept. Acceptance locks the price (and, on an open job, the
# worker); from the moment of funding on, neither price nor criteria
# can change — no code path writes them outside this section, and
# every action here re-checks the state.

def _negotiation_open(job):
    """(ok, refusal_message): offers may be made/decided only on a
    posted job whose price is not already locked by an acceptance."""
    if job is None:
        return False, "Job not found"
    if job.state != 'posted':
        return False, ("Negotiation is closed: offers are only "
                       "possible while a job is posted and unfunded. "
                       "Once funding happens, the price and criteria "
                       "never change.")
    if accepted_offer(job.id) is not None:
        return False, ("A price is already agreed on this job — "
                       "negotiation is closed.")
    return True, ""


def _invitee_id(job):
    return job.invited_worker_id if job.invited_worker_id else (job.worker_id if job.circle == 'invited' else 0)


def _offer_event_detail(offer):
    worker = get_party(offer.worker_id)
    return {"offer_id": offer.id,
            "worker_id": offer.worker_id,
            "worker_name": worker["name"] if worker else "",
            "amount_cents": offer.amount_cents,
            "currency": offer.currency,
            "kind": offer.kind}


def price_agreed(job):
    """True when funding may proceed on agreement grounds: an
    agreed price AND a chosen worker. Open-price jobs agree by
    acceptance (price_cents > 0 only happens then); legacy
    fixed jobs agree at posting, as always; NEW fixed jobs
    (circle set) agree only when an offer stands accepted —
    the invited worker's explicit yes, or the client's
    acceptance of a claim/counter."""
    if job is None or not job.has_agreed_price or not job.worker_id:
        return False
    if job.price_mode == 'fixed' and job.circle in (
            'invited', 'open', 'both'):
        return accepted_offer(job.id) is not None
    return True


def make_offer_action(job_id, worker_id, amount_cents, *,
                      via, actor, endpoint):
    """A worker offers a price on a posted job: a bid on an
    open (priceless) job, or a counter-offer by the assigned
    worker on a priced job. A worker's new offer supersedes their
    own earlier pending one."""
    job = get_job(job_id)
    if job is None:
        raise ServiceError("Job not found", 404)
    ok, msg = _negotiation_open(job)
    if not ok:
        _log(job_id, actor, via, 'offer', endpoint, msg, 409)
        raise ServiceError(msg, 409)
    worker = get_party(worker_id) if worker_id else None
    if worker is None or worker.get('kind') != 'worker':
        msg = "Offers can only be made by a worker party."
        _log(job_id, actor, via, 'offer', endpoint, msg, 400)
        raise ServiceError(msg, 400)
    if worker_id == job.client_id:
        msg = "The job's client cannot offer on their own job."
        _log(job_id, actor, via, 'offer', endpoint, msg, 400)
        raise ServiceError(msg, 400)
    try:
        amount_cents = int(amount_cents)
    except (TypeError, ValueError):
        amount_cents = 0
    if amount_cents <= 0:
        msg = "An offer must be a positive amount."
        _log(job_id, actor, via, 'offer', endpoint, msg, 400)
        raise ServiceError(msg, 400)
    
    # Eligibility based on circle
    invitee = _invitee_id(job)
    if job.circle == 'invited':
        if worker_id != invitee:
            msg = ("This job is open to the invited worker only — "
                   "other workers cannot offer on it.")
            _log(job_id, actor, via, 'offer', endpoint, msg, 403)
            raise ServiceError(msg, 403)
    elif job.circle == '':
        # Legacy: today's rule — fixed: only job.worker_id, with today's exact 403 message
        if job.price_mode == 'fixed' and worker_id != job.worker_id:
            msg = ("On a priced job, only the assigned worker can "
                   "counter-offer. Other workers can bid on jobs "
                   "posted without a price.")
            _log(job_id, actor, via, 'offer', endpoint, msg, 403)
            raise ServiceError(msg, 403)
    elif job.circle in ('open', 'both'):
        pass  # Any worker party
    
    # Kind determination
    if job.is_open:
        kind = 'bid'
    else:
        if job.circle:
            if amount_cents == job.price_cents:
                kind = 'accept'
            else:
                kind = 'counter'
        else:
            if worker_id != job.worker_id:
                msg = ("On a priced job, only the assigned worker can "
                       "counter-offer. Other workers can bid on jobs "
                       "posted without a price.")
                _log(job_id, actor, via, 'offer', endpoint, msg, 403)
                raise ServiceError(msg, 403)
            kind = 'counter'
    
    # Auto-lock: when kind == 'accept' and circle == 'invited', the worker's yes
    # completes the agreement (the client's yes was the posting): after create_offer,
    # call db_accept_offer; on success add the 'offer_accepted' event with actor 'worker'
    # (detail via _offer_event_detail) and log the lock; on None raise the same
    # 409 race message accept_offer_action uses.
    offer = create_offer(job_id, worker_id, amount_cents,
                         job.currency, kind)
    
    if kind == 'accept' and job.circle == 'invited':
        accepted = db_accept_offer(offer.id)
        if accepted is None:
            msg = ("The job changed while the offer was being accepted "
                   "— nothing was locked.")
            _log(job_id, actor, via, 'offer', endpoint, msg, 409)
            raise ServiceError(msg, 409)
        add_event(job_id, 'offer_accepted', actor='worker',
                  detail=_offer_event_detail(accepted))
        _log(job_id, actor, via, 'offer', endpoint,
             f"offer={offer.id} locked_cents={accepted.amount_cents}",
             200, _paypal_ids(job))
    
    add_event(job_id, 'offer_made', actor='worker',
              detail=_offer_event_detail(offer))
    _log(job_id, actor, via, 'offer', endpoint,
         f"worker={worker_id} amount_cents={amount_cents} "
         f"kind={kind}", 201)
    return offer


def _pending_offer(job_id, offer_id):
    offer = get_offer(offer_id)
    if offer is None or offer.job_id != job_id:
        raise ServiceError("Offer not found on this job", 404)
    if offer.status != 'pending':
        raise ServiceError(
            f"This offer is already {offer.status} — it can no "
            "longer be decided.", 409)
    return offer


def accept_offer_action(job_id, offer_id, *, via, actor, endpoint):
    """The client accepts an offer: the price locks at the offered
    amount (and an open job gains its worker). Every other pending
    offer lapses. Only possible while the job is posted."""
    job = get_job(job_id)
    if job is None:
        raise ServiceError("Job not found", 404)
    ok, msg = _negotiation_open(job)
    if not ok:
        _log(job_id, actor, via, 'offer_accept', endpoint, msg, 409)
        raise ServiceError(msg, 409)
    offer = _pending_offer(job_id, offer_id)
    pending_before = {o.id: o for o in list_offers(job_id)
                      if o.status == 'pending' and o.id != offer_id}
    accepted = db_accept_offer(offer_id)
    if accepted is None:
        msg = ("The job changed while the offer was being accepted "
               "— nothing was locked.")
        _log(job_id, actor, via, 'offer_accept', endpoint, msg, 409)
        raise ServiceError(msg, 409)
    for other_id, other in pending_before.items():
        add_event(job_id, 'offer_superseded', actor='system',
                  detail=_offer_event_detail(other))
    add_event(job_id, 'offer_accepted', actor='client',
              detail=_offer_event_detail(accepted))
    job = get_job(job_id)
    _log(job_id, actor, via, 'offer_accept', endpoint,
         f"offer={offer_id} locked_cents={accepted.amount_cents}",
         200, _paypal_ids(job))
    return job, accepted


def reject_offer_action(job_id, offer_id, *, via, actor, endpoint):
    """The client rejects a pending offer. The job stays posted;
    the worker may offer again."""
    job = get_job(job_id)
    if job is None:
        raise ServiceError("Job not found", 404)
    if job.state != 'posted':
        msg = ("Negotiation is closed: this job is no longer in "
               "the posted state.")
        _log(job_id, actor, via, 'offer_reject', endpoint, msg, 409)
        raise ServiceError(msg, 409)
    offer = _pending_offer(job_id, offer_id)
    set_offer_status(offer_id, 'rejected')
    add_event(job_id, 'offer_rejected', actor='client',
              detail=_offer_event_detail(offer))
    _log(job_id, actor, via, 'offer_reject', endpoint,
         f"offer={offer_id}", 200)
    return get_offer(offer_id)


def withdraw_offer_action(job_id, offer_id, *, via, actor, endpoint):
    """The offering worker withdraws a pending offer."""
    job = get_job(job_id)
    if job is None:
        raise ServiceError("Job not found", 404)
    if job.state != 'posted':
        msg = ("Negotiation is closed: this job is no longer in "
               "the posted state.")
        _log(job_id, actor, via, 'offer_withdraw', endpoint, msg, 409)
        raise ServiceError(msg, 409)
    offer = _pending_offer(job_id, offer_id)
    set_offer_status(offer_id, 'withdrawn')
    add_event(job_id, 'offer_withdrawn', actor='worker',
              detail=_offer_event_detail(offer))
    _log(job_id, actor, via, 'offer_withdraw', endpoint,
         f"offer={offer_id}", 200)
    return get_offer(offer_id)


def job_status_dict(job) -> dict:
    """The full machine-readable status of one job (GET /api/v1/jobs)."""
    cert = get_certificate_by_job(job.id)
    verdicts = []
    for v in get_verdicts(job.id):
        verdicts.append({
            "check_id": v.get("id"),
            "overall_pass": bool(v.get("overall_pass")),
            "judge_model": v.get("judged_model", ""),
            "fraud_signal": v.get("fraud_signal", ""),
            "checked_at": v.get("checked_at", ""),
        })
    return {
        "id": job.id,
        "title": job.title,
        "description": job.description,
        "state": job.state,
        "price_cents": job.price_cents,
        "price_mode": job.price_mode,
        "circle": job.circle,
        "invited_worker_id": job.invited_worker_id,
        "currency": job.currency,
        "parties": {"client_id": job.client_id,
                    "worker_id": job.worker_id,
                    "checker_id": job.checker_id},
        "offers": [{"id": o.id, "worker_id": o.worker_id,
                    "amount_cents": o.amount_cents,
                    "currency": o.currency, "kind": o.kind,
                    "status": o.status, "created_at": o.created_at,
                    "decided_at": o.decided_at}
                   for o in list_offers(job.id)],
        "terms": {
            "verification_mode": job.terms_verification_mode,
            "vesting_hours": job.terms_vesting_hours,
            "trust_credit_percent": job.terms_trust_credit_percent,
            "brain_model": job.brain_model,
            "brain_degraded": bool(job.brain_degraded),
            "brain_narrative": job.brain_narrative,
        },
        "verdicts": verdicts,
        "price_agreed": price_agreed(job),
        "money": {
            "paypal_order_id": job.paypal_order_id,
            "paypal_authorization_id": job.paypal_authorization_id,
            "capture_id": job.capture_id,
            "capture_status": job.capture_status,
            "captured_amount_cents": job.captured_amount_cents,
            "payout_batch_id": job.payout_batch_id,
            "payout_items": job.payout_items,
            "refund_id": job.refund_id,
            "refund_status": job.refund_status,
            "trust_credit_state": job.trust_credit_state,
            "advanced_cents": job.advanced_cents,
            "captured_total_cents": job.captured_amount_cents + (job.advanced_cents or 0),
            "checker_vesting_state": job.checker_vesting_state,
            "checker_vesting_amount_cents":
                job.checker_vesting_amount_cents,
            "checker_release_at": job.checker_release_at,
            "settle_error": job.settle_error,
            "paypal_error": job.paypal_error,
        },
        "certificate": ({"serial": cert["serial"], "code": cert["code"]}
                        if cert else None),
        "deliveries": [{"filename": d.filename,
                        "sha256": d.sha256,
                        "size_bytes": d.size_bytes}
                       for d in get_deliveries(job.id)],
    }
