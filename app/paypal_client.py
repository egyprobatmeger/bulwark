"""
PayPal sandbox client — Funding (Orders authorize).

urllib only. Credentials are read from the environment at runtime; they are
never stored in this file, never printed, never logged. Money-path calls are
explicit about amounts and currency (decimal strings).

Flow per factory/probe_log_sandbox.md and factory/dispatch/implementer_1_2.md:
  1. OAuth2 client_credentials (Basic auth) -> access token (in-memory cache).
  2. POST /v2/checkout/orders  intent=AUTHORIZE
       header PayPal-Request-Id: bulwark-fund-<installation>-<job_id>
       payment_source.card = SANDBOX_TEST_CARD
  3. Extract authorization id + status + amount from purchase_units.
  4. GET order to confirm.
"""
import base64
import http.client
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple
from urllib.parse import quote

from app.config import SANDBOX_TEST_CARD, SANDBOX_TEST_CARDS

# Read credentials ONLY from the environment at runtime.
_CLIENT_ID = os.environ.get('PAYPAL_CLIENT_ID')
_CLIENT_SECRET = os.environ.get('PAYPAL_CLIENT_SECRET')
_API_BASE = os.environ.get('PAYPAL_API_BASE')


class PayPalError(Exception):
    """Raised on a non-2xx PayPal response. Carries status + issue code."""
    def __init__(self, status_code: int, message: str, issue: str = "",
                 debug_id: str = "", raw: Optional[Dict] = None):
        self.status_code = status_code
        self.message = message
        self.issue = issue
        self.debug_id = debug_id
        self.raw = raw
        super().__init__(f"[{status_code}] {issue or message}")


# ---------------------------------------------------------------------------
# OAuth2 token (cached in memory until near expiry)
# ---------------------------------------------------------------------------
_token_cache: Optional[str] = None
_token_expires_at: float = 0.0

_TOKEN_TTL_SLACK = 30  # seconds before real expiry to refresh

# PayPal calls must bypass ambient proxy env vars (e.g. ALL_PROXY) — the
# egress proxy in this environment cannot carry PayPal traffic. A direct
# opener is correct on this machine and anywhere else: the PayPal sandbox
# is reachable directly via HTTPS.
_NO_PROXY_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({})
)


def credentials_present() -> bool:
    return bool(_CLIENT_ID and _CLIENT_SECRET and _API_BASE)


def _oauth_basic_header() -> str:
    raw = f"{_CLIENT_ID}:{_CLIENT_SECRET}"
    encoded = base64.b64encode(raw.encode('utf-8')).decode('ascii')
    return f"Basic {encoded}"


def _read_json(resp) -> Any:
    raw = resp.read().decode('utf-8')
    if not raw.strip():
        # 204 No Content (e.g. a successful authorization void) —
        # an empty body is a valid money-path response.
        return {}
    return json.loads(raw)


def _handle_http_error(e: urllib.error.HTTPError) -> None:
    """Parse PayPal error body and raise PayPalError carrying the issue code."""
    raw = ''
    status_code = e.code
    data: Dict[str, Any] = {}

    try:
        raw = e.read().decode('utf-8', errors='replace')
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                data = parsed
        except (json.JSONDecodeError, ValueError):
            pass
    except Exception:
        pass

    issue = ""
    message = ""
    debug_id = ""
    detail = data.get('details', []) if isinstance(data, dict) else []
    if isinstance(detail, list) and detail:
        first = detail[0] if isinstance(detail[0], dict) else {}
        issue = first.get('issue', '') or data.get('issue', '')
        message = first.get('description', '') or data.get('message', '')
        debug_id = first.get('debug_id', '') or data.get('debug_id', '')
    else:
        if isinstance(data, dict):
            issue = data.get('issue', '')
            message = data.get('description', '') or data.get('message', '')
            debug_id = data.get('debug_id', '')

    if not message:
        message = raw[:500] if raw else f"HTTP {status_code} error"
    if (not issue or issue == 'UNKNOWN') and isinstance(data, dict):
        # Payouts-style errors carry the code in the top-level `name`
        # (e.g. INSUFFICIENT_FUNDS) instead of details[].issue.
        issue = data.get('name', '') or issue
        if not message and data.get('message'):
            message = data['message']
    raise PayPalError(status_code, message, issue=issue or 'UNKNOWN',
                      debug_id=debug_id, raw=data)


class _BufferedResponse:
    """A response whose body was read eagerly inside
    _urlopen_with_error_handling, so a transport failure DURING the
    read is converted to CONNECT_ERROR there (and is therefore
    covered by the callers' retries) instead of escaping raw from
    _read_json at some later line. (Found live 2026-10-09: OAuth,
    authorize and capture reads all lost bodies this way.)"""

    def __init__(self, body: bytes, status: int = 200, headers=None):
        self._body = body
        self.status = status
        self.headers = headers

    def read(self, *args) -> bytes:
        return self._body


def _urlopen_with_error_handling(req: urllib.request.Request):
    """Open a URL with comprehensive error handling for transport-level failures."""
    try:
        # Timeout 120s (raised from 30s,
        # 2026-10-09): under parallel sandbox load the egress
        # regularly answers money POSTs after >30s. A 30s client
        # timeout then looks like a transport failure, the caller's
        # one safe retry re-sends the POST — and the sandbox,
        # which HAS executed the first attempt, refuses the second
        # (422 TRANSACTION_REFUSED on authorize; 400 "sender_batch_id
        # already exists" on payouts, whose batch id the app can
        # then never learn). Three independent occurrences in one
        # night (coordinator jobs 90004 + 666001, reviewer job
        # 30003) all match this signature. A long timeout makes the
        # retry path the rare exception it was designed to be.
        resp = _NO_PROXY_OPENER.open(req, timeout=120)
        body = resp.read()  # eager: read failures land in the
        # transport-error conversion below, not in the caller.
        return _BufferedResponse(body, status=getattr(resp, 'status',
                                                       200),
                                  headers=resp.headers)
    except urllib.error.HTTPError:
        # A real HTTP response (e.g. a PayPal 4xx with an issue code) is
        # NOT a connectivity failure — let the caller's error handler
        # parse it. (HTTPError subclasses URLError; catching it in the
        # URLError branch below would mislabel it CONNECT_ERROR.)
        raise
    except http.client.RemoteDisconnected as e:
        raise PayPalError(502, f"PayPal endpoint disconnected: {e}",
                          issue="CONNECT_ERROR")
    except urllib.error.URLError as e:
        raise PayPalError(502, f"PayPal endpoint unreachable: {e}",
                          issue="CONNECT_ERROR")
    except Exception as e:
        # Catch any other transport-level error and wrap it
        raise PayPalError(502, f"PayPal connectivity error: {e}",
                          issue="CONNECT_ERROR")


def get_access_token() -> str:
    """Return a cached access token, refreshing when near expiry."""
    global _token_cache, _token_expires_at
    if _token_cache and time.time() < (_token_expires_at - _TOKEN_TTL_SLACK):
        return _token_cache

    if not credentials_present():
        raise PayPalError(500, "PayPal credentials not set in environment",
                          issue="CREDENTIALS_ABSENT")

    url = f"{_API_BASE}/v1/oauth2/token"
    body = "grant_type=client_credentials"
    req = urllib.request.Request(url, data=body.encode('utf-8'), method='POST')
    req.add_header('Content-Type', 'application/x-www-form-urlencoded')
    req.add_header('Authorization', _oauth_basic_header())

    # One retry on a transport-level failure (observed 2026-10-08:
    # IncompleteRead / RemoteDisconnected windows on this route).
    try:
        resp = _urlopen_with_error_handling(req)
    except PayPalError as e:
        if e.issue != "CONNECT_ERROR":
            raise
        resp = _urlopen_with_error_handling(req)
    except urllib.error.HTTPError as e:
        _handle_http_error(e)

    data = _read_json(resp)
    token = data.get('access_token')
    if not token:
        raise PayPalError(500, str(data), issue="NO_ACCESS_TOKEN")

    expires_in = int(data.get('expires_in', 3600))
    _token_cache = token
    _token_expires_at = time.time() + expires_in
    return token


def _build_request(path: str, token: str, method: str = 'GET',
                   body: Optional[Dict[Any, Any]] = None,
                   request_id: Optional[str] = None) -> urllib.request.Request:
    url = f"{_API_BASE}{path}"
    payload = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(url, data=payload, method=method)
    req.add_header('Content-Type', 'application/json')
    req.add_header('Authorization', f"Bearer {token}")
    if request_id:
        req.add_header('PayPal-Request-Id', request_id)
    return req


def get_order(order_id: str, token: Optional[str] = None) -> Dict[Any, Any]:
    """GET /v2/checkout/orders/{order_id} and return the parsed JSON."""
    if token is None:
        token = get_access_token()
    req = _build_request(f'/v2/checkout/orders/{order_id}', token, method='GET')
    try:
        resp = _urlopen_with_error_handling(req)
    except urllib.error.HTTPError as e:
        _handle_http_error(e)
    return _read_json(resp)


def get_authorization(auth_id: str, token: Optional[str] = None) -> Dict[Any, Any]:
    """GET /v2/payments/authorizations/{auth_id} and return parsed JSON."""
    if token is None:
        token = get_access_token()
    req = _build_request(f'/v2/payments/authorizations/{auth_id}', token,
                         method='GET')
    try:
        resp = _urlopen_with_error_handling(req)
    except urllib.error.HTTPError as e:
        _handle_http_error(e)
    return _read_json(resp)


def _create_authorize_order_once(token: str, job_id: str,
                                 amount_value: str, currency: str,
                                 card: Dict[str, Any], request_id: str
                                 ) -> Dict[str, Any]:
    """One POST /v2/checkout/orders authorize attempt with one card.

    Returns the parsed response on success; raises PayPalError
    otherwise. A refused attempt (4xx) creates no order and no
    authorization on the PayPal side, so callers may safely retry
    with another card and a fresh request id.
    """
    card_payload = {
        "number": card["number"],
        "expiry": card["expiry"],  # MM-YYYY format as per probe log
        "security_code": card["security_code"],
        "name": card["name"],
        "billing_address": card["billing_address"],
    }

    body = {
        "intent": "AUTHORIZE",
        "payment_source": {"card": card_payload},
        "purchase_units": [
            {
                "reference_id": job_id,
                "amount": {
                    "currency_code": currency,
                    "value": amount_value,
                },
            }
        ],
    }

    req = _build_request('/v2/checkout/orders', token, method='POST',
                         body=body, request_id=request_id)

    # One retry on a transport-level failure only, under the same
    # request id, so a retry can never create a second order.
    # (Observed 2026-10-08: sandbox/egress transport drops —
    # RemoteDisconnected, proxy 406 — on otherwise valid calls.)
    def _open_orders():
        try:
            return _urlopen_with_error_handling(req)
        except urllib.error.HTTPError as e:
            _handle_http_error(e)  # raises PayPalError with the issue code

    def _attempt_orders():
        resp = _open_orders()
        try:
            return _read_json(resp)
        except Exception as e:
            # Same lost-response hole as _post_with_retry: a cut
            # response body must retry under the stable request id.
            raise PayPalError(502, f"PayPal response read failed: {e}",
                              issue="CONNECT_ERROR")

    try:
        return _attempt_orders()
    except PayPalError as e:
        if e.issue != "CONNECT_ERROR":
            raise
        return _attempt_orders()


def authorize_order(job_id: str, price_cents: int, currency: str = 'USD'
                    ) -> Tuple[str, str, str, int, str]:
    """
    Create an AUTHORIZE order using the sandbox test card pool.

    Returns (order_id, authorization_id, authorization_status,
             amount_minor_units, currency).
    The first attempt's PayPal-Request-Id is bulwark-fund-<installation>-<job_id>;
    rotation attempts suffix it (-a2, -a3, ...).

    Sandbox refusal waves (measured live, 2026-10-10): the sandbox
    card processor intermittently answers 422 TRANSACTION_REFUSED for
    stretches at a time — every card, every amount — then recovers;
    inside a wave, isolated attempts still pass. A refusal creates
    no order and no authorization, so rotating across the proven
    test-card pool and repeating the round after a pause is safe and
    cannot double-fund. Any other error surfaces immediately.
    """
    token = get_access_token()

    dollars = price_cents // 100
    cents = price_cents % 100
    amount_value = f"{dollars}.{cents:02d}"

    cards = SANDBOX_TEST_CARDS or [SANDBOX_TEST_CARD]
    round_pauses = (0, 20, 40)  # seconds slept before rounds 1..3
    data = None
    last_error: Optional[PayPalError] = None
    attempt_no = 0
    for pause in round_pauses:
        if pause:
            time.sleep(pause)
        for card in cards:
            attempt_no += 1
            request_id = (_idem("fund", job_id) if attempt_no == 1
                          else _idem("fund", job_id, f"a{attempt_no}"))
            try:
                data = _create_authorize_order_once(
                    token, job_id, amount_value, currency, card,
                    request_id)
                break
            except PayPalError as e:
                if e.issue != "TRANSACTION_REFUSED":
                    raise
                last_error = e
        if data is not None:
            break
    if data is None:
        raise last_error  # type: ignore[misc]

    order_id = data.get('id', '')
    status = data.get('status', '')

    # Confirm via GET the order (dispatch step 2: "GET the order to confirm").
    confirmed = get_order(order_id, token)
    if confirmed.get('status'):
        status = confirmed.get('status')

    # Extract authorization details from purchase_units.
    auth_id = ""
    auth_status = status
    auth_amount_cents = price_cents
    auth_currency = currency

    units = confirmed.get('purchase_units', []) or data.get('purchase_units', [])
    if units:
        payments = units[0].get('payments', {}) or {}
        authorizations = payments.get('authorizations', [])
        if authorizations:
            a = authorizations[0] if isinstance(authorizations[0], dict) else {}
            auth_id = a.get('authorization_id', '') or a.get('id', '')
            auth_status = a.get('status', auth_status) or auth_status
            amt = a.get('amount', {}) or {}
            value = amt.get('value', '')
            cur = amt.get('currency_code', currency)
            if value:
                auth_amount_cents = _parse_amount_to_cents(value)
            if cur:
                auth_currency = cur

    return order_id, auth_id, auth_status, auth_amount_cents, auth_currency


def _idem(kind: str, job_id, suffix: str = "") -> str:
    """Installation-scoped PayPal idempotency key: retries within
    one database stay idempotent, and a repeated key from another
    database's lifetime can never replay its responses here."""
    from app.db import installation_id
    key = f"bulwark-{kind}-{installation_id()}-{job_id}"
    return key + (f"-{suffix}" if suffix else "")


def _parse_amount_to_cents(value: str) -> int:
    """Convert a PayPal decimal string like '10.00' to integer cents."""
    try:
        return int(round(float(value) * 100))
    except (ValueError, TypeError):
        return 0


def _cents_to_value(cents: int) -> str:
    """Integer minor units -> PayPal decimal string ('10.01')."""
    return f"{cents // 100}.{cents % 100:02d}"


def _post_with_retry(path: str, token: str, body: Optional[Dict] = None,
                     request_id: Optional[str] = None) -> Dict[Any, Any]:
    """POST a money-path call; ONE retry on a transport-level failure
    only (stable PayPal-Request-Id makes this safe). HTTP errors are
    converted to PayPalError carrying the PayPal issue code."""
    req = _build_request(path, token, method='POST', body=body,
                         request_id=request_id)

    def _open():
        try:
            return _urlopen_with_error_handling(req)
        except urllib.error.HTTPError as e:
            _handle_http_error(e)

    def _attempt():
        resp = _open()
        try:
            return _read_json(resp)
        except Exception as e:
            # A transport failure while READING the body (e.g.
            # IncompleteRead on a dropped connection) is the same
            # lost-response case as a failed open: the request may
            # well have executed at PayPal. It must surface as
            # CONNECT_ERROR so the single safe retry below replays
            # the call under its stable PayPal-Request-Id and returns
            # the original result. (Found live 2026-10-09:
            # a trust-credit advance capture landed at PayPal, its
            # response body was cut, the raw IncompleteRead escaped
            # unretried, and the unrecorded capture wedged the job.)
            raise PayPalError(502, f"PayPal response read failed: {e}",
                              issue="CONNECT_ERROR")

    try:
        return _attempt()
    except PayPalError as e:
        if e.issue != "CONNECT_ERROR":
            raise
        return _attempt()


def capture_authorization(auth_id: str, job_id: str,
                          token: Optional[str] = None
                          ) -> Tuple[str, str, int, str]:
    """capture the full held amount of an authorization.

    Returns (capture_id, capture_status, captured_amount_cents,
    currency). Idempotency header: bulwark-capture-<installation>-<job_id>."""
    if token is None:
        token = get_access_token()
    data = _post_with_retry(
        f'/v2/payments/authorizations/{auth_id}/capture', token, body={},
        request_id=_idem("capture", job_id))
    capture_id = data.get('id', '')
    status = data.get('status', '')
    amt = data.get('amount', {}) or {}
    cents = _parse_amount_to_cents(amt.get('value', '')) if amt.get('value') else 0
    currency = amt.get('currency_code', '') or 'USD'
    if capture_id and not cents:
        # The capture POST response can omit the amount — GET the
        # capture resource, which always carries it (observed
        # 2026-10-08: POST returned no amount).
        got = get_capture(capture_id, token)
        status = got.get('status', status) or status
        gamt = got.get('amount', {}) or {}
        if gamt.get('value'):
            cents = _parse_amount_to_cents(gamt['value'])
        currency = gamt.get('currency_code', currency) or currency
    return capture_id, status, cents, currency


def capture_authorization_amount(auth_id: str, job_id: str,
                                 amount_cents: int, currency: str,
                                 final_capture: bool, tag: str,
                                 token: Optional[str] = None
                                 ) -> Tuple[str, str, int, str]:
    """(trust credit): capture a SPECIFIC amount of an
    authorization. `final_capture=False` leaves the remainder capturable
    (proven on this sandbox by factory/probe_2_4_partial_capture.py:
    $0.50 non-final + $1.50 final on one $2.00 authorization, both
    COMPLETED). Request-id: bulwark-capture-<installation>-<job_id>-<tag>.
    Returns (capture_id, status, captured_amount_cents, currency)."""
    if token is None:
        token = get_access_token()
    body = {
        "amount": {"value": _cents_to_value(amount_cents),
                   "currency_code": currency},
        "final_capture": bool(final_capture),
    }
    data = _post_with_retry(
        f'/v2/payments/authorizations/{auth_id}/capture', token, body=body,
        request_id=_idem("capture", job_id, tag))
    capture_id = data.get('id', '')
    status = data.get('status', '')
    amt = data.get('amount', {}) or {}
    cents = _parse_amount_to_cents(amt.get('value', '')) if amt.get('value') else 0
    cur = amt.get('currency_code', '') or currency
    if capture_id and not cents:
        got = get_capture(capture_id, token)
        status = got.get('status', status) or status
        gamt = got.get('amount', {}) or {}
        if gamt.get('value'):
            cents = _parse_amount_to_cents(gamt['value'])
        cur = gamt.get('currency_code', cur) or cur
    return capture_id, status, cents, cur


def get_capture(capture_id: str, token: Optional[str] = None
                ) -> Dict[Any, Any]:
    """GET /v2/payments/captures/{capture_id} and return parsed JSON."""
    if token is None:
        token = get_access_token()
    req = _build_request(f'/v2/payments/captures/{capture_id}', token,
                         method='GET')
    try:
        resp = _urlopen_with_error_handling(req)
    except urllib.error.HTTPError as e:
        _handle_http_error(e)
    return _read_json(resp)


def create_payouts(job_id: str, items: list, currency: str = 'USD',
                   token: Optional[str] = None,
                   batch_tag: str = '') -> Tuple[str, list]:
    """one Payouts batch with the three split items.

    `items` is a list of dicts: {party, receiver, amount_cents}.
    Returns (payout_batch_id, [{party, receiver, amount_cents,
    payout_item_id, status}]) with statuses exactly as PayPal reports.
    Idempotency: PayPal-Request-Id bulwark-payouts-<job_id> and
    sender_batch_id bulwark-<job_id>."""
    items = [it for it in items if it.get("amount_cents", 0) > 0]
    if not items:
        raise PayPalError(400, "No payout items remaining after filtering zero-amount items",
                         issue="NO_ITEMS_REMAINING")
    if token is None:
        token = get_access_token()
    sender_batch_id = _idem("batch", job_id, batch_tag)
    body = {
        "sender_batch_header": {
            "sender_batch_id": sender_batch_id,
            "email_subject": f"Bulwark settlement for job {job_id}",
            "email_message": f"Your Bulwark share for job {job_id}.",
        },
        "items": [
            {
                "recipient_type": "EMAIL",
                "receiver": it["receiver"],
                "amount": {"value": _cents_to_value(it["amount_cents"]),
                           "currency": currency},
                "sender_item_id": f"{job_id}-{it['party']}",
                "note": f"Bulwark job {job_id} — {it['party']} share",
            }
            for it in items
        ],
    }
    try:
        data = _post_with_retry('/v1/payments/payouts', token, body=body,
                                request_id=_idem("payouts", job_id, batch_tag))
    except PayPalError as e:
        # Duplicate-batch case (2026-10-09): if an earlier
        # attempt DID create the batch at PayPal but its response never
        # reached us (transport drop on a slow route), the retry is
        # refused with "Batch with given sender_batch_id already
        # exists" (HTTP 400; the text arrives in the error's ISSUE
        # field, not the message — the first version of this handler
        # checked the message field and never matched). The refusal
        # proves the batch exists exactly once, so no payment was or
        # will be duplicated by retrying.
        #
        # Recovery correction (measured live 2026-10-10): the batch
        # id CAN be recovered — the refusal's details[] entry carries
        # a `link` array whose self href points at the existing
        # batch (.../v1/payments/payouts/<payout_batch_id>). The
        # 2026-10-09 check that concluded otherwise inspected only
        # the message/issue fields, and the payouts LIST endpoint
        # does return 404 for this app (re-verified 2026-10-10), so
        # this link is the read-back path. The refusal is re-raised
        # as a distinct BATCH_ALREADY_EXISTS error carrying the
        # recovered id on `.existing_batch_id`;
        # create_or_adopt_payouts() uses it to adopt the batch.
        combined = f"{e.issue or ''} {e.message or ''}"
        if not (e.status_code in (400, 422)
                and 'sender_batch_id' in combined
                and 'already exists' in combined):
            raise
        err = PayPalError(
            e.status_code,
            "This settlement's payout batch already exists at PayPal "
            f"(sender_batch_id {sender_batch_id}): an earlier attempt "
            "created it and its response was lost in transit. The "
            "batch was created exactly once — retrying made no "
            "duplicate payment.",
            issue="BATCH_ALREADY_EXISTS")
        err.existing_batch_id = _batch_id_from_error(e.raw)
        raise err
    header = data.get('batch_header', {}) or {}
    batch_id = header.get('payout_batch_id', '')
    # The POST response carries NO items (observed 2026-10-08: batch
    # created, items list empty) — the authoritative item ids and
    # statuses come from a GET on the batch. Fall back to the locally
    # constructed items (status PENDING) if the GET fails; the job
    # page refreshes them from PayPal on view either way.
    out = []
    if batch_id:
        try:
            out = get_payout_batch_items(batch_id, items, token)
        except Exception:
            out = []
    if not out:
        out = [{
            "party": it["party"], "receiver": it["receiver"],
            "amount_cents": it["amount_cents"], "payout_item_id": "",
            "status": "PENDING",
        } for it in items]
    return batch_id, out


def get_payout_batch_items(batch_id: str, base_items: Optional[list] = None,
                           token: Optional[str] = None) -> list:
    """GET a payouts batch and return the full item records:
    [{party, receiver, amount_cents, payout_item_id, status}] with
    values exactly as PayPal reports (receiver/amount from the
    batch's payout_item echo when present)."""
    if token is None:
        token = get_access_token()
    req = _build_request(f'/v1/payments/payouts/{batch_id}', token,
                         method='GET')
    try:
        resp = _urlopen_with_error_handling(req)
    except urllib.error.HTTPError as e:
        _handle_http_error(e)
    data = _read_json(resp)
    by_party = {it["party"]: it for it in (base_items or [])}
    out = []
    for pit in data.get('items', []) or []:
        inner = pit.get('payout_item', {}) or {}
        sid = pit.get('sender_item_id', '') or inner.get('sender_item_id', '')
        party = sid.split('-', 1)[1] if '-' in sid else sid
        base = by_party.get(party, {})
        amt = (inner.get('amount', {}) or {}).get('value', '')
        out.append({
            "party": base.get("party", party),
            "receiver": base.get("receiver", inner.get('receiver', '')),
            "amount_cents": base.get(
                "amount_cents",
                _parse_amount_to_cents(amt) if amt else 0),
            "payout_item_id": pit.get('payout_item_id', ''),
            "status": pit.get('transaction_status', ''),
        })
    return out


def get_payout_batch(batch_id: str, token: Optional[str] = None
                     ) -> Dict[str, str]:
    """GET a payouts batch; returns {sender_item_id: transaction_status}
    exactly as PayPal reports."""
    if token is None:
        token = get_access_token()
    req = _build_request(f'/v1/payments/payouts/{batch_id}', token,
                         method='GET')
    try:
        resp = _urlopen_with_error_handling(req)
    except urllib.error.HTTPError as e:
        _handle_http_error(e)
    data = _read_json(resp)
    out = {}
    for pit in data.get('items', []) or []:
        inner = pit.get('payout_item', {}) or {}
        sid = pit.get('sender_item_id', '') or inner.get('sender_item_id', '')
        if sid:
            out[sid] = pit.get('transaction_status', '')
    return out


def _batch_id_from_error(raw) -> str:
    """Recover the existing payout_batch_id from a duplicate-batch
    refusal: details[].link[] carries a self href of the form
    .../v1/payments/payouts/<payout_batch_id> (measured live
    2026-10-10). Returns '' when no parseable link is present."""
    if not isinstance(raw, dict):
        return ""
    for detail in raw.get('details', []) or []:
        if not isinstance(detail, dict):
            continue
        for link in detail.get('link', []) or []:
            if not isinstance(link, dict):
                continue
            href = link.get('href', '') or ''
            marker = '/v1/payments/payouts/'
            if marker in href:
                tail = href.split(marker, 1)[1].strip().strip('/')
                if tail and all(c.isalnum() for c in tail):
                    return tail
    return ""


def get_payout_batch_raw(batch_id: str, token: Optional[str] = None
                         ) -> Dict[Any, Any]:
    """GET a payouts batch and return the full parsed JSON exactly
    as PayPal reports it (batch_header + items with PayPal's own
    receiver/amount/status values)."""
    if token is None:
        token = get_access_token()
    req = _build_request(f'/v1/payments/payouts/{batch_id}', token,
                         method='GET')
    try:
        resp = _urlopen_with_error_handling(req)
    except urllib.error.HTTPError as e:
        _handle_http_error(e)
    return _read_json(resp)


# Payout item transaction_status values in which the money
# definitively did NOT reach (or returned from) the receiver, or is
# held by a PayPal block: adopting a batch containing one must
# refuse and surface the precise status instead of settling.
PAYOUT_ITEM_FAILURE_STATUSES = frozenset({
    "FAILED", "DENIED", "REFUNDED", "RETURNED", "REVERSED", "BLOCKED",
})


def adopt_existing_payout_batch(batch_id: str, job_id: str,
                                requested_items: list,
                                token: Optional[str] = None) -> list:
    """Adopt an already-existing payouts batch as this job's own:
    GET it from PayPal, verify that its items are EXACTLY the
    requested ones (same sender_item_id, receiver and amount for
    every item — a mismatch means the batch is not this settlement's
    and must not be adopted), and refuse if any item sits in a
    failure status. Returns the normalized item list
    [{party, receiver, amount_cents, payout_item_id, status}] with
    statuses exactly as PayPal reports (PENDING/SUCCESS/UNCLAIMED
    are adopted as-is; the job page keeps refreshing them live,
    exactly like a fresh batch). Raises PayPalError with issue
    ADOPT_MISMATCH or PAYOUT_ITEMS_FAILED otherwise."""
    if token is None:
        token = get_access_token()
    data = get_payout_batch_raw(batch_id, token)
    header = data.get('batch_header', {}) or {}
    batch_status = header.get('batch_status', '')
    if batch_status in ("DENIED", "CANCELED"):
        raise PayPalError(
            409,
            f"Existing payout batch {batch_id} has batch_status "
            f"{batch_status} at PayPal — no payment went out.",
            issue="PAYOUT_ITEMS_FAILED")
    raw_by_sid = {}
    for pit in data.get('items', []) or []:
        inner = pit.get('payout_item', {}) or {}
        sid = pit.get('sender_item_id', '') or inner.get('sender_item_id', '')
        if sid:
            raw_by_sid[sid] = pit
    problems = []
    failed = []
    for it in requested_items:
        sid = f"{job_id}-{it['party']}"
        pit = raw_by_sid.pop(sid, None)
        if pit is None:
            problems.append(f"item {sid} missing from batch {batch_id}")
            continue
        inner = pit.get('payout_item', {}) or {}
        receiver = inner.get('receiver', '')
        amt = (inner.get('amount', {}) or {}).get('value', '')
        cents = _parse_amount_to_cents(amt) if amt else 0
        if (receiver.lower() != str(it["receiver"]).lower()
                or cents != it["amount_cents"]):
            problems.append(
                f"item {sid} differs at PayPal (receiver {receiver}, "
                f"amount {amt}) from this settlement (receiver "
                f"{it['receiver']}, amount_cents {it['amount_cents']})")
            continue
        status = pit.get('transaction_status', '')
        if status in PAYOUT_ITEM_FAILURE_STATUSES:
            detail = pit.get('errors', {}) or {}
            if (status == "FAILED"
                    and detail.get('name') == 'SELF_PAY_NOT_ALLOWED'):
                # Not a broken payment leg: the item's receiver IS
                # the sender account (the platform share's receiver
                # is the platform's own PayPal account), so PayPal
                # refuses a transfer to self — the share by
                # construction remains in the sender account, and
                # every batch this app creates converges to exactly
                # this reported state (measured live 2026-10-10).
                # The item is adopted with its true status recorded
                # verbatim, as the primary path records it.
                continue
            failed.append(f"{it['party']}: {status}"
                          + (f" ({detail})" if detail else ""))
    if raw_by_sid:
        problems.append(
            f"batch {batch_id} carries unexpected items: "
            f"{sorted(raw_by_sid)}")
    if problems:
        raise PayPalError(
            409,
            "Existing payout batch does not match this settlement — "
            "refusing to adopt it: " + "; ".join(problems),
            issue="ADOPT_MISMATCH")
    if failed:
        raise PayPalError(
            409,
            f"Existing payout batch {batch_id} has failed items at "
            f"PayPal: " + "; ".join(failed),
            issue="PAYOUT_ITEMS_FAILED")
    return get_payout_batch_items(batch_id, requested_items, token)


def create_or_adopt_payouts(job_id: str, items: list,
                            currency: str = 'USD',
                            token: Optional[str] = None,
                            batch_tag: str = '') -> Tuple[str, list, bool]:
    """create_payouts with lost-response recovery. Returns
    (payout_batch_id, items, adopted).

    If the create POST is refused because this job's batch already
    exists at PayPal (an earlier attempt created it and its response
    was lost in transit), the existing batch is located via the
    refusal's self link, verified item-by-item, and ADOPTED — so a
    settlement always ends up with exactly one batch, never a
    second one, and the recovery is itself idempotent (re-running
    it adopts the same batch again). When the refusal carries no
    recoverable batch id, the original BATCH_ALREADY_EXISTS error
    propagates unchanged."""
    items = [it for it in items if it.get("amount_cents", 0) > 0]
    if not items:
        raise PayPalError(
            400, "No payout items remaining after filtering "
            "zero-amount items", issue="NO_ITEMS_REMAINING")
    try:
        batch_id, paid = create_payouts(
            job_id, items, currency=currency, token=token,
            batch_tag=batch_tag)
        return batch_id, paid, False
    except PayPalError as e:
        if e.issue != "BATCH_ALREADY_EXISTS":
            raise
        existing = getattr(e, 'existing_batch_id', '') or ''
        if not existing:
            raise
        try:
            paid = adopt_existing_payout_batch(existing, job_id, items,
                                               token)
        except PayPalError as adopt_err:
            if adopt_err.issue != "CONNECT_ERROR":
                raise
            # Recovery runs exactly when transport is flaky (that is
            # how the batch was orphaned) — one retry of the
            # read-back before giving up.
            paid = adopt_existing_payout_batch(existing, job_id, items,
                                               token)
        return existing, paid, True


def void_authorization(auth_id: str, job_id: str,
                       token: Optional[str] = None) -> str:
    """void an uncaptured authorization (refund path).
    Returns the authorization status PayPal reports after the void.
    Idempotency header: bulwark-void-<installation>-<job_id>."""
    if token is None:
        token = get_access_token()
    _post_with_retry(f'/v2/payments/authorizations/{auth_id}/void',
                     token, body={}, request_id=_idem("void", job_id))
    auth = get_authorization(auth_id, token)
    return auth.get('status', '')


def refund_capture(capture_id: str, job_id: str, amount_cents: int,
                    currency: str = 'USD', token: Optional[str] = None,
                    suffix: str = "") -> Tuple[str, str]:
    """(defensive path): refund a capture in full.
    Returns (refund_id, refund_status). Idempotency header:
    bulwark-refund-<installation>-<job_id>[-{suffix}]."""
    if token is None:
        token = get_access_token()
    body = {"amount": {"value": _cents_to_value(amount_cents),
                       "currency_code": currency}}
    data = _post_with_retry(
        f'/v2/payments/captures/{capture_id}/refund', token, body=body,
        request_id=_idem("refund", job_id, suffix))
    return data.get('id', ''), data.get('status', '')
