"""
Slice 2.2 — Settlement Brain.

Uses the job price/currency, acceptance criteria, and party reputation
counters to set protective terms per job at funding time.
The terms are stored on the job, shown plainly in the UI, and consumed by
later slices. Money movement itself does NOT change in this slice.
"""
import json
import os

from app.checker import _openrouter_chat

# Constants
BRAIN_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"
BRAIN_FALLBACK_MODEL = "google/gemma-4-31b-it:free"
BULWARK_BRAIN_MODEL = os.environ.get("BULWARK_BRAIN_MODEL")
if BULWARK_BRAIN_MODEL:
    BRAIN_MODEL = BULWARK_BRAIN_MODEL

# Fallback terms
FALLBACK_TERMS = {
    "verification_mode": "single",
    "vesting_hours": 24,
    "trust_credit_percent": 0,
    "stake_percent": 0,
}


class BrainUnavailableError(Exception):
    """Raised when both primary and fallback brain models are unavailable."""


def _get_surrogate():
    """Wrapper around app.checker._obtain_surrogate for reuse."""
    from app.checker import _obtain_surrogate
    return _obtain_surrogate()


def decide_terms(job, worker_counters, checker_counters):
    """
    Decide settlement terms for a job based on its characteristics.

    Args:
        job: Job object with title, description, price_cents, currency, and criteria
        worker_counters: Dictionary of worker reputation counters
        checker_counters: Dictionary of checker reputation counters

    Returns:
        dict: {"terms": {...}, "narrative": str, "model": str, "degraded": bool}

    The prompt includes job details and instructs the brain to choose terms.
    On any failure, returns FALLBACK_TERMS with degraded=True.
    """
    # Prepare the prompt for the brain
    criteria_text = "\n".join([
        f"- {c.name} ({c.criterion_type}): {c.operator} {c.expected_value}"
        for c in job.criteria
    ])

    prompt = f"""Analyze this job to decide protective settlement terms:

Job details:
- Title: {job.title}
- Description: {job.description}
- Price: ${job.price_cents / 100:.2f} {job.currency}

Acceptance criteria:
{criteria_text}

Worker reputation counters:
- Jobs posted: {worker_counters.get("jobs_posted", 0)}
- Jobs delivered: {worker_counters.get("jobs_delivered", 0)}
- Verdicts passed (first): {worker_counters.get("verdict_pass_first", 0)}
- Verdicts failed (first): {worker_counters.get("verdict_fail_first", 0)}
- Job settled: {worker_counters.get("job_settled", 0)}
- Fraud flags: {worker_counters.get("fraud_flags", False)}

Checker reputation counters:
- Verdicts issued: {checker_counters.get("verdict_issued", 0)}
- Verdicts upheld: {checker_counters.get("verdicts_upheld", 0)}
- Verdicts overturned: {checker_counters.get("verdicts_overturned", 0)}

Choose protective terms for this job:

1. Verification mode: Choose "single" or "dual" (dual = two independent AI verdicts)
   - Use dual for high value jobs or weak reputation history
   - Use single for low value jobs or strong reputation

2. Vesting hours: Choose from [0, 24, 72]
   - 0 = immediate release after settlement
   - 24 = 24-hour hold of checker's fee after settlement
   - 72 = 72-hour hold of checker's fee after settlement

3. Trust credit percent: Choose from [0, 25, 50]
   - 0 = none (worker gets full fee at delivery)
   - 25 = Bulwark may advance 25% of worker fee at delivery
   - 50 = Bulwark may advance 50% of worker fee at delivery
   - Note: Only recorded in this slice, used by slice 2.5

4. Worker stake percent: Choose from [0, 10]
   - 0 = none (no stake on first jobs)
   - 10 = 10% worker stake on first jobs
   - Note: Only recorded in this slice, used by slice 2.5

Reply with JSON ONLY: {{"verification_mode": "...", "vesting_hours": ..., "trust_credit_percent": ..., "stake_percent": ..., "narrative": "1-3 plain sentences explaining the choice for THIS job"}}
"""

    try:
        bearer = _get_surrogate()
        messages = [
            {"role": "system", "content": (
                "You are Bulwark's Settlement Brain AI. Analyze the job "
                "characteristics and reputation history to decide protective "
                "terms at funding time. The terms protect the platform and "
                "checkers while rewarding good performers. Think about "
                "risk assessment, fairness, and incentive alignment. "
                "Respond with JSON ONLY exactly as specified."
            )},
            {"role": "user", "content": prompt},
        ]

        # Primary model
        try:
            data = _openrouter_chat(BRAIN_MODEL, messages, bearer)
            parsed = json.loads(data["choices"][0]["message"]["content"])
        except (json.JSONDecodeError, KeyError, IndexError, Exception):
            # Fallback to fallback model
            try:
                data = _openrouter_chat(BRAIN_FALLBACK_MODEL, messages, bearer)
                parsed = json.loads(data["choices"][0]["message"]["content"])
            except (json.JSONDecodeError, KeyError, IndexError, Exception):
                # Both models failed
                return {
                    "terms": FALLBACK_TERMS,
                    "narrative": (
                        "Settlement Brain unavailable — standard protective terms "
                        "applied (single verification, 24-hour checker-fee vesting, "
                        "no trust credit, no stake)."
                    ),
                    "model": "",
                    "degraded": True,
                }

        # Validate parsed response
        validated = validate_terms(parsed)
        if validated is not None:
            return {
                "terms": validated,
                "narrative": validated["narrative"],
                "model": BRAIN_MODEL,
                "degraded": False,
            }

        # Validation failed
        return {
            "terms": FALLBACK_TERMS,
            "narrative": (
                "Settlement Brain unavailable — standard protective terms "
                "applied (single verification, 24-hour checker-fee vesting, "
                "no trust credit, no stake)."
            ),
            "model": "",
            "degraded": True,
        }

    except BrainUnavailableError as e:
        # This shouldn't happen with our current implementation, but handle it
        return {
            "terms": FALLBACK_TERMS,
            "narrative": (
                "Settlement Brain unavailable — standard protective terms "
                "applied (single verification, 24-hour checker-fee vesting, "
                "no trust credit, no stake)."
            ),
            "model": "",
            "degraded": True,
        }
    except Exception as e:
        # Any other error - fallback
        return {
            "terms": FALLBACK_TERMS,
            "narrative": (
                "Settlement Brain unavailable — standard protective terms "
                "applied (single verification, 24-hour checker-fee vesting, "
                "no trust credit, no stake)."
            ),
            "model": "",
            "degraded": True,
        }


def validate_terms(raw):
    """
    Strictly validate a raw terms dict.

    Args:
        raw: dict from brain response

    Returns:
        dict with valid terms if validation passes, None otherwise
    """
    # All four keys must be present
    required_keys = {"verification_mode", "vesting_hours", "trust_credit_percent", "stake_percent", "narrative"}
    if not isinstance(raw, dict) or not all(key in raw for key in required_keys):
        return None

    # validation_mode must be "single" or "dual"
    if raw["verification_mode"] not in {"single", "dual"}:
        return None

    # vesting_hours must be 0, 24, or 72
    if raw["vesting_hours"] not in {0, 24, 72}:
        return None

    # trust_credit_percent must be 0, 25, or 50
    if raw["trust_credit_percent"] not in {0, 25, 50}:
        return None

    # stake_percent must be 0 or 10
    if raw["stake_percent"] not in {0, 10}:
        return None

    # narrative must be non-empty string <= 600 chars
    narrative = raw["narrative"]
    if not isinstance(narrative, str) or len(narrative) == 0 or len(narrative) > 600:
        return None

    # All validations passed
    return raw
