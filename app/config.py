"""
Bulwark configuration — Slice 1.2+: Funding, payout split, sandbox fixtures.

Money-path constants live here only. Credentials NEVER come from here
they are read from the environment at runtime by paypal_client.py.
This module holds: (a) fixed payout split percentages, (b) payout
receiver emails, (c) the sandbox test-card fixture.
"""
import os

# ---------------------------------------------------------------------------
# Payout split (Stage 1 fixed terms, see stage1_brief.md)
# Percentages of the captured amount. Sum must equal 100.
# The rounding remainder (the sub-cent that can't be split) goes to the
# platform so the three parts always sum exactly to the captured total.
# ---------------------------------------------------------------------------
WORKER_SPLIT_PERCENT = 85
CHECKER_SPLIT_PERCENT = 5
PLATFORM_SPLIT_PERCENT = 10

# ---------------------------------------------------------------------------
# Payout receiver emails
# ---------------------------------------------------------------------------
# Platform is the real sandbox business account — read from the environment
# at runtime. If the env var is absent (e.g. unit test) leave it None and
# the code will surface the issue rather than fabricate a value.
PLATFORM_RECEIVER_EMAIL = os.environ.get('PAYPAL_SANDBOX_BUSINESS_EMAIL')

# Worker / checker receivers are SANDBOX PLACEHOLDER emails.
# These are NOT real sandbox test accounts — they exist only so the Payouts
# call can be formed and PayPal returns its real (PENDING) item statuses.
# They are safe to commit: they carry no credential value and are plainly
# documented as replaceable once real sandbox test accounts are linked.
WORKER_RECEIVER_EMAIL = "worker@example.com"   # replace with real sandbox test account when linked
CHECKER_RECEIVER_EMAIL = "checker@example.com"  # replace with real sandbox test account when linked
CLIENT_RECEIVER_EMAIL = "client@example.com"  # dispute-recovery fallback (Slice 2.5)


# ---------------------------------------------------------------------------
# Sandbox test-card fixture
# ---------------------------------------------------------------------------
# The funding card for the sandbox demo. This is a PayPal sandbox TEST
# card number (Luhn-valid), NOT a real card. It is the client fixture used
# to authorize a vault order against the sandbox (intent=AUTHORIZE).
# Sourced from the coordinator's live sandbox probe (see
# factory/probe_log_sandbox.md) which proved 4111111111111111 authorizes
# cleanly. Never use in production — sandbox only.
# ---------------------------------------------------------------------------
SANDBOX_TEST_CARD = {
    "number": "4111111111111111",
    "expiry": "2030-01",          # MM-YYYY
    "security_code": "123",
    "name": "Sandbox Client",
    "billing_address": {
        "country_code": "US",
        "address_line_1": "123 Sandbox St",
        "address_city": "San Jose",
        "address_state": "CA",
        "postal_code": "95131",
    },
}

# Pool of sandbox test cards PROVEN to authorize against this sandbox
# app (coordinator probe, 2026-10-10): all four returned HTTP 201
# COMPLETED on live authorize attempts. When the sandbox card
# processor refuses one instrument during a refusal wave, the funding
# flow rotates to the next card in the pool. All entries are public
# PayPal sandbox test numbers — sandbox only, never production.
SANDBOX_TEST_CARDS = [
    SANDBOX_TEST_CARD,
    {**SANDBOX_TEST_CARD, "number": "5555555555554444"},
    {**SANDBOX_TEST_CARD, "number": "371449635398431",
     "security_code": "1234"},
    {**SANDBOX_TEST_CARD, "number": "378282246310005",
     "security_code": "1234"},
]
