from dataclasses import dataclass, field
from typing import List


@dataclass
class Criterion:
    name: str
    operator: str
    expected_value: str
    criterion_type: str  # "deterministic" or "judgment"


@dataclass
class Delivery:
    id: int
    job_id: int
    filename: str
    stored_name: str
    size_bytes: int
    sha256: str
    uploaded_at: str
    note: str = ""
    is_revision: bool = False

    def short_hash(self) -> str:
        return self.sha256[:16] if self.sha256 else ""

    def formatted_size(self) -> str:
        if self.size_bytes < 1024:
            return f"{self.size_bytes} B"
        elif self.size_bytes < 1024 * 1024:
            return f"{self.size_bytes / 1024:.1f} KB"
        else:
            return f"{self.size_bytes / (1024 * 1024):.1f} MB"


@dataclass
class Offer:
    """A price offer on a posted job (price negotiation, pre-funding
    only). kind: 'counter' — the assigned worker's counter-offer on a
    priced job; 'bid' — a worker's bid on a job posted without a
    price; 'accept' — a worker taking a fixed-price job at exactly
    the listed price. status: pending | accepted | rejected |
    withdrawn | superseded. Once one offer is accepted the job's
    price is locked and no further offers are possible."""
    id: int
    job_id: int
    worker_id: int
    amount_cents: int
    currency: str
    kind: str
    status: str
    created_at: str
    decided_at: str = ""

    def formatted_amount(self) -> str:
        dollars = self.amount_cents // 100
        rem = self.amount_cents % 100
        return f"${dollars:,}.{rem:02d} {self.currency}"


@dataclass
class Party:
    id: int
    name: str
    kind: str
    form: str
    payout_email: str
    created_at: str

    def short_hash(self) -> str:
        return self.name[:16]


@dataclass
class ReputationEvent:
    id: int
    party_id: int
    job_id: int
    kind: str
    detail: dict
    created_at: str


@dataclass
class Job:
    id: int
    title: str
    description: str
    price_cents: int
    currency: str
    state: str
    created_at: str
    criteria: List[Criterion] = field(default_factory=list)
    # PayPal vault fields (the build). Nullable until funded.
    paypal_order_id: str = ""
    paypal_authorization_id: str = ""
    authorization_status: str = ""
    funded_amount_cents: int = 0
    funded_currency: str = ""
    funded_at: str = ""
    paypal_error: str = ""
    # Party assignments. Always populated after migration.
    client_id: int = 1
    worker_id: int = 2
    checker_id: int = 3
    # Settlement fields. Nullable until settled.
    capture_id: str = ""
    capture_status: str = ""
    captured_amount_cents: int = 0
    captured_currency: str = ""
    captured_at: str = ""
    payout_batch_id: str = ""
    payout_items: List[dict] = field(default_factory=list)
    settled_at: str = ""
    settle_error: str = ""
    # Refund fields. Nullable until refunded.
    refund_id: str = ""
    refund_status: str = ""
    refunded_at: str = ""
    revision_used: bool = False
    # Settlement Brain fields
    terms_verification_mode: str = ""
    terms_vesting_hours: int = -1
    terms_trust_credit_percent: int = -1
    terms_stake_percent: int = -1
    brain_narrative: str = ""
    brain_model: str = ""
    brain_degraded: int = 0
    # trust credit
    trust_credit_state: str = ""
    advance_capture_id: str = ""
    advance_batch_id: str = ""
    advanced_cents: int = 0
    advance_payout_items: list = field(default_factory=list)
    # checker-fee vesting + dispute window.
    checker_vesting_state: str = ""  # '' | vesting | released | paid_to_client
    checker_vesting_amount_cents: int = 0
    checker_release_at: str = ""
    checker_released_batch_id: str = ""
    checker_released_item_id: str = ""
    dispute_state: str = ""  # '' | open | upheld_closed | overturned
    dispute_reason: str = ""
    dispute_opened_at: str = ""
    dispute_resolved_at: str = ""
    # demo cast tagging ('' | active | archived)
    demo_tag: str = ""
    # Price negotiation: 'fixed' (posted with a price) or 'open'
    # (posted without a price — workers bid, the client picks one).
    # An open job has price_cents 0 and worker_id 0 until an offer
    # is accepted; acceptance locks both, irrevocably.
    price_mode: str = "fixed"
    # Circle: '' (legacy) | 'invited' | 'open' | 'both'
    circle: str = ""
    # Invited worker when circle is 'invited' or 'both'
    invited_worker_id: int = 0

    @property
    def is_open(self) -> bool:
        return self.price_mode == 'open'

    @property
    def has_agreed_price(self) -> bool:
        """A price exists that funding may use: the posted price, or
        the accepted offer's amount. Open jobs have none until an
        offer is accepted."""
        return self.price_cents > 0

    @property
    def has_terms(self) -> bool:
        """Check if the job has Settlement Brain terms set."""
        return bool(self.terms_verification_mode or self.brain_narrative)

    def formatted_price(self) -> str:
        if self.price_mode == 'open' and self.price_cents <= 0:
            return "Open to offers"
        dollars = self.price_cents // 100
        rem = self.price_cents % 100
        return f"${dollars:,}.{rem:02d} {self.currency}"

    def formatted_funded_amount(self) -> str:
        dollars = self.funded_amount_cents // 100
        rem = self.funded_amount_cents % 100
        cur = self.funded_currency or self.currency
        return f"${dollars:,}.{rem:02d} {cur}"


def parse_price_cents(raw: str) -> int:
    raw = raw.strip()
    if not raw:
        raise ValueError("Empty price")
    parts = raw.split('.')
    if len(parts) == 1:
        dollars = int(parts[0])
        cents = 0
    elif len(parts) == 2:
        dollars = int(parts[0])
        frac = parts[1].ljust(2, '0')[:2]
        cents = int(frac)
    else:
        raise ValueError("Invalid price format")
    return dollars * 100 + cents
