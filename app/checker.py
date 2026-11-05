"""
Bulwark checker.

Deterministic criteria evaluated by code against the delivered files, plus
ONE LLM judgment call via the in-app model through the factory surrogate
pattern. Produces a stored, itemized verdict.

Deterministic shapes (per factory/dispatch/implementer_1_4.md):
  file_count        =,>=,<=        count of delivered files
  format            =            file extension (e.g. CSV)
  row_count         >=,<=,=       CSV data rows (header excluded)
  contains_column   contains      CSV header row
  file_size_bytes   >=,<=          per-file size; measured = largest file
  contains_text     contains      substring in any delivered text/CSV file

An unknown criterion name/shape yields a FAIL item "unsupported criterion"
— never skipped, never auto-passed.

Judgment (criterion_type == "judgment"): ONE call to the in-app model
nvidia/nemotron-3-super-120b-a12b:free via OpenRouter chat completions,
auth'd by an hsurr:* surrogate for `custom.openrouter` obtained from the
local authd unix socket (/run/hatch/auth/authd.sock, POST
/v1/credentials/surrogate). The surrogate is held in memory only — never
logged, never stored. Expected response: JSON only {"pass": bool,
"reason": str}. On a hard error, one retry with the fallback
model google/gemma-4-31b-it:free; the item records which model judged.
If the judge cannot decide at all (infrastructure error or an
unparseable response), call_judge raises JudgeUnavailableError and
run_check records the criterion as NOT JUDGED: the run is then
"incomplete" — it never counts as a FAIL, never moves the job's
state, and never consumes the worker's revision or appeal rights
.
"""
import csv
import http.client
import io
import json
import os
import socket
import urllib.error
import urllib.request
import re
import hashlib
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Set
from collections import defaultdict

from app.db import (
    DELIVERIES_DIR, emit_reputation_event_once, get_deliveries, get_job,
    list_jobs, set_job_checked, store_check_with_originality, store_verdict,
)
from app.models import Criterion, Job

# ---------------------------------------------------------------------------
# Configuration constants (dispatch-fixed)
# ---------------------------------------------------------------------------
JUDGE_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"
JUDGE_FALLBACK_MODEL = "google/gemma-4-31b-it:free"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
AUTHD_SOCKET = "/run/hatch/auth/authd.sock"
SURROGATE_SUBJECT = "custom.openrouter"

# Bounded delivery excerpt for the judge prompt.
MAX_EXCERPT_LINES = 200
MAX_EXCERPT_BYTES = 8192
HTTP_TIMEOUT = 30

# SUPPORTED deterministic shapes — anything else is "unsupported criterion".
SUPPORTED_SHAPES = {
    "file_count",
    "format",
    "row_count",
    "contains_column",
    "file_size_bytes",
    "contains_text",
    "unique_column",
    "nonempty_column",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Delivery file resolution
# ---------------------------------------------------------------------------
def delivery_paths(job_id: int) -> List[str]:
    """Absolute filesystem paths for the CURRENT delivery batch.

    when a revision batch exists, the check measures ONLY
    the revised delivery (the original batch stays in history but is
    not re-measured); otherwise it measures the original batch."""
    deliveries = get_deliveries(job_id)
    revised = [d for d in deliveries if getattr(d, "is_revision", False)]
    batch = revised if revised else [
        d for d in deliveries if not getattr(d, "is_revision", False)]
    paths: List[str] = []
    for d in batch:
        path = os.path.join(DELIVERIES_DIR, str(job_id), d.stored_name)
        paths.append(path)
    return paths


# ---------------------------------------------------------------------------
# Criterion parsing helpers
# ---------------------------------------------------------------------------
_STORED_PREFIX = re.compile(r"^[0-9a-f]{32}_(.+)$")


def _display_name(path: str) -> str:
    """The original file name for a stored delivery path.

    Deliveries are stored as '<uuid4-hex>_<original name>'; the hash
    prefix is a storage detail. Measured/reason texts shown to humans
    name the file the worker actually delivered — never the raw
    stored name (a 37-char unbroken token that also overflows phone
    screens)."""
    base = os.path.basename(path)
    m = _STORED_PREFIX.match(base)
    return m.group(1) if m else base


def _num(value: str) -> Optional[float]:
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _eval_numeric_comparison(actual: float, operator: str,
                             expected: float) -> Tuple[bool, str]:
    if operator == "=":
        ok = actual == expected
    elif operator == ">=":
        ok = actual >= expected
    elif operator == "<=":
        ok = actual <= expected
    elif operator == ">":
        ok = actual > expected
    elif operator == "<":
        ok = actual < expected
    else:
        return False, f"unsupported operator '{operator}'"
    verdict = "meets" if ok else "below/above threshold"
    return ok, f"{int(actual)} {operator} {int(expected)} ({verdict})"


# ---------------------------------------------------------------------------
# Deterministic evaluators — each returns (passed, measured, reason)
# ---------------------------------------------------------------------------
def eval_file_count(criterion: Criterion,
                    paths: List[str]) -> Tuple[bool, str, str]:
    expected = criterion.expected_value
    actual = len(paths)
    exp_num = _num(expected)
    if exp_num is None:
        return False, str(actual), f"non-numeric expected value '{expected}'"
    ok, detail = _eval_numeric_comparison(float(actual), criterion.operator,
                                          exp_num)
    measured = f"{actual} files"
    reason = detail
    return ok, measured, reason


def eval_format(criterion: Criterion, paths: List[str]) -> Tuple[bool, str, str]:
    expected = (criterion.expected_value or "").strip().lower()
    if not expected:
        return False, "", "empty expected format"
    # Use the extension of the first (primary) delivered file.
    if not paths:
        return False, "0 files", "no delivered files to inspect"
    first_ext = os.path.splitext(paths[0])[1].lstrip(".").lower()
    if not first_ext:
        first_ext = ""
    ok = first_ext == expected
    measured = f"{len(paths)} file{'s' if len(paths) != 1 else ''}, extension '{first_ext}'"
    reason = f"format '{first_ext}' {('matches' if ok else 'does not match')} '{expected}'"
    return ok, measured, reason


def _read_csv_rows(path: str) -> Optional[List[str]]:
    """Return list of data row contents (header excluded) or None on error.
    A plain-text row_count also falls back to counting non-empty lines."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace",
                  newline="") as f:
            reader = csv.reader(f)
            rows = list(reader)
    except (OSError, csv.Error):
        return None
    header: List[str] = []
    data_rows: List[str] = []
    if rows:
        header = [c.strip() for c in rows[0]]
        for r in rows[1:]:
            data_rows.append(",".join(r))
    return header, data_rows, rows


def eval_row_count(criterion: Criterion, paths: List[str]) -> Tuple[bool, str, str]:
    expected = criterion.expected_value
    exp_num = _num(expected)
    if exp_num is None:
        return False, "0", f"non-numeric expected value '{expected}'"
    if not paths:
        return False, "0", "no delivered files"
    path = paths[0]
    parsed = _read_csv_rows(path)
    if parsed is None:
        return False, "0", (f"could not parse the delivered file "
                            f"({_display_name(path)}) as CSV")
    header, data_rows, _ = parsed
    actual = len(data_rows)
    ok, detail = _eval_numeric_comparison(float(actual), criterion.operator,
                                          exp_num)
    measured = f"{actual} data rows"
    reason = detail
    return ok, measured, reason


def _csv_header(path: str) -> Optional[List[str]]:
    parsed = _read_csv_rows(path)
    if parsed is None:
        return None
    header, _, _ = parsed
    return [h.strip() for h in header]


def eval_contains_column(criterion: Criterion,
                         paths: List[str]) -> Tuple[bool, str, str]:
    needle = (criterion.expected_value or "").strip()
    if not needle:
        return False, "", "empty expected column name"
    if not paths:
        return False, "", "no delivered files"
    found_in = None
    for p in paths:
        header = _csv_header(p)
        if header is None:
            continue
        normalised = [c.lower() for c in header]
        if needle.lower() in normalised or any(needle.lower() == c for c in normalised):
            found_in = _display_name(p)
            break
    ok = found_in is not None
    measured = f"looked in {len(paths)} file{'s' if len(paths) != 1 else ''}"
    reason = (f"column '{needle}' present in {found_in}" if ok
              else f"column '{needle}' absent from all headers")
    return ok, measured, reason


def eval_file_size_bytes(criterion: Criterion,
                         paths: List[str]) -> Tuple[bool, str, str]:
    if not paths:
        return False, "0", "no delivered files"
    expected = criterion.expected_value
    exp_num = _num(expected)
    if exp_num is None:
        return False, "0", f"non-numeric expected value '{expected}'"
    largest = 0
    largest_name = ""
    for p in paths:
        try:
            sz = os.path.getsize(p)
        except OSError:
            continue
        if sz > largest:
            largest = sz
            largest_name = _display_name(p)
    ok, detail = _eval_numeric_comparison(float(largest), criterion.operator,
                                          exp_num)
    measured = f"largest file {largest} bytes ({largest_name or 'none'})"
    reason = detail
    return ok, measured, reason


def _iter_text(paths: List[str]) -> List[Tuple[str, str]]:
    """Yield (path, text) for delivered CSV/text files."""
    out: List[Tuple[str, str]] = []
    for p in paths:
        if not os.path.exists(p):
            continue
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                out.append((p, f.read()))
        except OSError:
            continue
    return out


def eval_contains_text(criterion: Criterion,
                       paths: List[str]) -> Tuple[bool, str, str]:
    needle = (criterion.expected_value or "").strip()
    if not needle:
        return False, "", "empty expected substring"
    if not paths:
        return False, "", "no delivered files"
    texts = _iter_text(paths)
    found_in = None
    for p, text in texts:
        if needle.lower() in text.lower():
            found_in = _display_name(p)
            break
    ok = found_in is not None
    measured = f"searched {len(texts)} file(s)"
    reason = (f"substring '{needle}' present in {found_in}" if ok
              else f"substring '{needle}' absent from all files")
    return ok, measured, reason


def _column_values(paths: List[str], column: str):
    """(values, found_in, error): the values of a named CSV column in the
    first delivered CSV that has it (header match is case-insensitive,
    following eval_contains_column)."""
    needle = (column or "").strip()
    if not needle:
        return None, None, "empty expected column name"
    if not paths:
        return None, None, "no delivered files"
    for p in paths:
        parsed = _read_csv_rows(p)
        if parsed is None:
            continue
        header, _joined, raw_rows = parsed
        normalised = [h.strip().lower() for h in header]
        if needle.lower() in normalised:
            idx = normalised.index(needle.lower())
            values = [(r[idx] if idx < len(r) else "")
                      for r in raw_rows[1:]]
            return values, _display_name(p), None
    return None, None, f"column '{needle}' absent from all headers"


def eval_unique_column(criterion: Criterion,
                       paths: List[str]) -> Tuple[bool, str, str]:
    """PASS iff the named CSV column has no duplicate values.
    The expected value is the column name."""
    values, found_in, err = _column_values(paths, criterion.expected_value)
    if err:
        return False, "", err
    seen = set()
    dups = 0
    for v in values:
        if v in seen:
            dups += 1
        seen.add(v)
    ok = dups == 0
    measured = (f"{len(values)} values in '{criterion.expected_value}' "
                f"({found_in}), {dups} duplicate(s)")
    reason = ("all values unique" if ok else
              f"{dups} duplicate value(s) in column "
              f"'{criterion.expected_value}'")
    return ok, measured, reason


def eval_nonempty_column(criterion: Criterion,
                         paths: List[str]) -> Tuple[bool, str, str]:
    """PASS iff the named CSV column has no empty cells.
    The expected value is the column name."""
    values, found_in, err = _column_values(paths, criterion.expected_value)
    if err:
        return False, "", err
    empty = sum(1 for v in values if not str(v).strip())
    ok = empty == 0
    measured = (f"{len(values)} values in '{criterion.expected_value}' "
                f"({found_in}), {empty} empty")
    reason = ("no empty cells" if ok else
              f"{empty} empty cell(s) in column "
              f"'{criterion.expected_value}'")
    return ok, measured, reason


_DETERMINISTIC = {
    "file_count": eval_file_count,
    "format": eval_format,
    "row_count": eval_row_count,
    "contains_column": eval_contains_column,
    "file_size_bytes": eval_file_size_bytes,
    "contains_text": eval_contains_text,
    "unique_column": eval_unique_column,
    "nonempty_column": eval_nonempty_column,
}


# ---------------------------------------------------------------------------
# Judge client (surrogate auth from local authd socket -> OpenRouter)
# ---------------------------------------------------------------------------
def _obtain_surrogate() -> str:
    """POST /v1/credentials/surrogate to the local authd unix socket for
    `custom.openrouter`. Returns the surrogate bearer token (held in
    memory only). Raises on any failure."""
    if not os.path.exists(AUTHD_SOCKET):
        raise RuntimeError(f"authd socket not present at {AUTHD_SOCKET}")
    # authd contract (verified against factory/or_proxy.py's credential
    # helper): POST {"name": <credential>} -> {"credentials": [{"name":
    # "access_token", "surrogate": "hsurr:*"}, ...]}.
    body = json.dumps({"name": SURROGATE_SUBJECT}).encode("utf-8")
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(HTTP_TIMEOUT)
    sock.connect(AUTHD_SOCKET)
    try:
        req = (
            f"POST /v1/credentials/surrogate HTTP/1.1\r\n"
            f"Host: localhost\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        ).encode("utf-8") + body
        sock.sendall(req)
        chunks: List[bytes] = []
        while True:
            chunk = sock.recv(8192)
            if not chunk:
                break
            chunks.append(chunk)
    finally:
        sock.close()
    raw = b"".join(chunks)
    # Split HTTP header / body.
    sep = raw.find(b"\r\n\r\n")
    resp_body = raw[sep + 4:] if sep != -1 else raw
    text = resp_body.decode("utf-8", errors="replace")
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        raise RuntimeError(f"authd returned non-JSON: {text[:200]}")
    if isinstance(data, dict) and "error" in data:
        raise RuntimeError(f"authd error: {data.get('error')}")
    # Response shape: {"credentials": [{"name": "access_token",
    # "surrogate": "hsurr:*"}]} — take the access_token entry's surrogate.
    if isinstance(data, dict):
        for entry in data.get("credentials", []) or []:
            if isinstance(entry, dict) and entry.get("name") == "access_token":
                surrogate = str(entry.get("surrogate", "")).strip()
                if surrogate.startswith("hsurr:"):
                    return surrogate
    raise RuntimeError(f"authd response missing surrogate: {text[:200]}")


def _openrouter_chat(model: str, messages: List[Dict[str, str]],
                     bearer: str) -> Dict[str, Any]:
    payload = json.dumps({
        "model": model,
        "messages": messages,
        # 1024 (raised from 512 in the slice-1.4 repair round): the
        # primary judge is a reasoning model — at 512 tokens it can
        # spend the whole budget reasoning and return EMPTY content
        # (observed in the reviewer gate run, job 1001), which reads
        # as a failed judgment on a conforming delivery.
        "max_tokens": 1024,
    }).encode("utf-8")
    req = urllib.request.Request(OPENROUTER_URL, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {bearer}")
    # The hsurr:* surrogate is swapped for the real credential at this
    # environment's egress layer, so the judge call MUST travel the
    # ambient route (default opener, honouring the proxy env) — a
    # direct no-proxy connection reaches OpenRouter with the raw
    # surrogate and is rejected 401 (observed 2026-10-08, self-test 1.4).
    resp = urllib.request.urlopen(req, timeout=HTTP_TIMEOUT)
    return json.loads(resp.read().decode("utf-8"))


def _parse_judge_response(data: Dict[str, Any]) -> Tuple[Optional[bool], Optional[str], str]:
    """Extract {pass, reason} from an OpenRouter chat completion. Returns
    (pass, reason, error). On success error is ''. On parse failure pass and
    reason are None and error carries a short cause."""
    try:
        choice = data["choices"][0]
    except (KeyError, IndexError, TypeError):
        return None, None, "no choices in completion"
    msg = choice.get("message", {})
    content = (msg.get("content") or "").strip()
    if not content:
        return None, None, "empty model content"
    # JSON-only contract — parse defensively (strip markdown fences and
    # any prose around the JSON object before giving up).
    candidate = content
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        if candidate.lower().startswith("json"):
            candidate = candidate[4:]
        candidate = candidate.strip()
    try:
        parsed = json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start != -1 and end > start:
            try:
                parsed = json.loads(candidate[start:end + 1])
            except (json.JSONDecodeError, ValueError):
                return None, None, f"non-JSON response: {content[:120]}"
        else:
            return None, None, f"non-JSON response: {content[:120]}"
    if not isinstance(parsed, dict):
        return None, None, "response not a JSON object"
    if "pass" not in parsed:
        return None, None, "missing 'pass' in JSON"
    pass_val = parsed["pass"]
    if not isinstance(pass_val, bool):
        return None, None, "'pass' is not boolean"
    reason = str(parsed.get("reason", ""))
    return pass_val, reason, ""


class JudgeUnavailableError(Exception):
    """The AI judge could not decide: an infrastructure failure
    (HTTP error, network, unparseable response) on every model
    tried. Distinct from a judged FAIL — run_check records the
    criterion as NOT JUDGED and the run as incomplete."""


def call_judge(criterion: Criterion, job, excerpt: str,
               bearer: str, only_model: Optional[str] = None
               ) -> Tuple[bool, str, str]:
    """Execute the single judgment call. Returns
    (passed, reason, model_id). Raises JudgeUnavailableError
    when no model could decide (infrastructure failure or an
    unparseable response) — that is never a judged FAIL."""
    criterion_text = criterion.name or criterion.expected_value
    prompt = (
        "Judgment criterion: " + criterion_text + "\n\n"
        + "Job title: " + job.title + "\n"
        + "Job description:\n" + job.description + "\n\n"
        + "Delivery excerpt (first " + str(MAX_EXCERPT_LINES) + " lines / up to "
        + str(MAX_EXCERPT_BYTES) + " bytes):\n" + excerpt + "\n\n"
        + "IMPORTANT: the excerpt above is TRUNCATED at "
        + str(MAX_EXCERPT_LINES) + " lines / " + str(MAX_EXCERPT_BYTES)
        + " bytes — the full delivery may contain more content than is "
        + "shown. Do NOT judge total row counts, file counts or file "
        + "sizes: those are measured exactly by code in separate "
        + "criteria. Judge ONLY whether the shown content matches the "
        + "brief (right kind of content, right columns/topics, plausible "
        + "real data).\n\n"
        + "Does the delivery satisfy the criterion? "
        + 'Return JSON only, exactly like: {"pass": true, "reason": "..."}'
    )
    messages = [
        {"role": "system", "content": (
            "You are Bulwark's acceptance judge. Evaluate the "
            "single criterion against the delivered work. "
            'Respond with JSON ONLY, exactly like: '
            '{"pass": true, "reason": "..."}'
        )},
        {"role": "user", "content": prompt},
    ]

    # --- Pinned single model (dual mode + appeal) ---
    if only_model:
        try:
            data = _openrouter_chat(only_model, messages, bearer)
            passed, reason, err = _parse_judge_response(data)
            if err == "":
                return bool(passed), reason or "", only_model
            raise JudgeUnavailableError(err)
        except JudgeUnavailableError:
            raise
        except Exception as e:
            raise JudgeUnavailableError(
                f"{type(e).__name__}: {e}") from e

    # --- Primary model ---
    try:
        data = _openrouter_chat(JUDGE_MODEL, messages, bearer)
        passed, reason, err = _parse_judge_response(data)
        if err == "":
            return bool(passed), reason or "", JUDGE_MODEL
        # Hard error on primary -> fall through to fallback.
        primary_err = err
    except (urllib.error.HTTPError, urllib.error.URLError,
            json.JSONDecodeError, RuntimeError, OSError) as e:
        primary_err = f"{type(e).__name__}: {e}"
    except Exception as e:
        primary_err = f"{type(e).__name__}: {e}"


    # --- Fallback model (one retry on hard error) ---
    try:
        data = _openrouter_chat(JUDGE_FALLBACK_MODEL, messages, bearer)
        passed, reason, err = _parse_judge_response(data)
        if err == "":
            return bool(passed), reason or "", JUDGE_FALLBACK_MODEL
        fallback_err = f"{err}; primary: {primary_err}"
    except (urllib.error.HTTPError, urllib.error.URLError,
            json.JSONDecodeError, RuntimeError, OSError) as e:
        fallback_err = f"{type(e).__name__}: {e}; primary: {primary_err}"
    except Exception as e:
        fallback_err = f"{type(e).__name__}: {e}; primary: {primary_err}"
    
    # Both failed -> the judge could not decide. That is an
    # infrastructure outcome, not a verdict (never a FAIL): raise
    # so the caller records the criterion as NOT JUDGED.
    raise JudgeUnavailableError(fallback_err)

def _delivery_excerpt(paths: List[str]) -> str:
    """Bounded excerpt: first 200 lines / 8 KB across delivered text files."""
    texts = _iter_text(paths)
    if not texts:
        return "<no text/CSV files in this delivery>"
    blob = "\n".join("=== {} ===\n{}".format(os.path.basename(p), t)
                     for p, t in texts)
    lines = blob.splitlines()[:MAX_EXCERPT_LINES]
    out = "\n".join(lines)
    if len(out.encode("utf-8", errors="replace")) > MAX_EXCERPT_BYTES:
        out = out.encode("utf-8", errors="replace")[:MAX_EXCERPT_BYTES].decode(
            "utf-8", errors="replace")
    return out


# ---------------------------------------------------------------------------
# Verdict types
# ---------------------------------------------------------------------------
@dataclass
class VerdictItem:
    name: str
    expected: str
    measured: str
    passed: bool
    reason: str
    checked_at: str
    checker_kind: str      # "code" or "llm"
    model_id: str          # "" for code
    judged: bool = True    # False only when the judge never decided


@dataclass
class Verdict:
    job_id: int
    overall_pass: bool
    items: List[VerdictItem]
    checked_at: str
    judge_model: str       # which model judged ("" if no judgment criterion)
    originality: Dict[str, Any] = field(default_factory=dict)
    suppress_first_events: bool = False
    incomplete: bool = False   # a criterion was never judged


def _item_unsupported(criterion: Criterion) -> VerdictItem:
    return VerdictItem(
        name=criterion.name,
        expected=f"{criterion.operator} {criterion.expected_value}",
        measured="n/a",
        passed=False,
        reason="unsupported criterion",
        checked_at=_now_iso(),
        checker_kind="code",
        model_id="",
    )



# ---------------------------------------------------------------------------
# Originality analysis — deterministic, no AI.
# ---------------------------------------------------------------------------
TOKEN_RE = re.compile(r"[a-z0-9]+")
SIMILARITY_FRAUD_THRESHOLD = 0.90
CSV_DUP_FAIL_RATIO = 0.05


def text_shingles(text: str, k: int = 5) -> Set[str]:
    """Token k-gram shingles of a text (lowercase alphanumeric tokens)."""
    tokens = TOKEN_RE.findall(text.lower())
    if not tokens:
        return set()
    if len(tokens) < k:
        return {" ".join(tokens)}
    return {" ".join(tokens[i:i + k]) for i in range(len(tokens) - k + 1)}


def jaccard(a: Set[str], b: Set[str]) -> float:
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def csv_duplicate_ratio(text: str) -> float:
    """Share of exact-duplicate data rows (header excluded)."""
    try:
        rows = [r for r in csv.reader(io.StringIO(text)) if r]
    except Exception:
        return 0.0
    if len(rows) < 2:
        return 0.0
    data = [tuple(r) for r in rows[1:]]
    if not data:
        return 0.0
    return 1.0 - (len(set(data)) / len(data))


def _read_text(path: str) -> str:
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError:
        return ""
    return raw.decode("utf-8", errors="ignore")


def analyse_originality(job_id: int, paths: List[str]) -> Dict[str, Any]:
    """Compare this job's CURRENT delivery against every OTHER job's
    deliveries. A byte-identical file (sha256) or a token-shingle
    Jaccard similarity >= 0.90 against another job is FRAUD. Also
    measures the worst CSV duplicate-row ratio of this delivery."""
    result: Dict[str, Any] = {
        "fraud_signal": "", "similarity_max": -1.0,
        "similarity_job_id": -1, "csv_dup_ratio": -1.0, "reason": "",
    }
    cur_sha = set()
    cur_shingles: Set[str] = set()
    dup = -1.0
    for p in paths:
        try:
            with open(p, "rb") as fh:
                raw = fh.read()
        except OSError:
            continue
        cur_sha.add(hashlib.sha256(raw).hexdigest())
        text = raw.decode("utf-8", errors="ignore")
        cur_shingles |= text_shingles(text)
        if p.lower().endswith(".csv"):
            dup = max(dup, csv_duplicate_ratio(text))
    result["csv_dup_ratio"] = dup

    best = -1.0
    best_job = -1
    exact_job = -1
    for other in list_jobs():
        if other.id == job_id:
            continue
        # deliveries of ARCHIVED demo jobs are not part of
        # the originality corpus. An archived demo job is a superseded
        # demo run (Reset demo archives it), not real earlier work —
        # without this, re-running the demo would flag the new run's
        # genuine fixtures as copies of the previous run's, and the
        # demo could never be reset. ACTIVE jobs (demo or not) stay
        # fully in the corpus, so the live fraud story still fires.
        if getattr(other, "demo_tag", "") == "archived":
            continue
        other_shingles: Set[str] = set()
        for d in get_deliveries(other.id):
            if getattr(d, "sha256", "") and d.sha256 in cur_sha:
                exact_job = other.id
            op = os.path.join(DELIVERIES_DIR, str(other.id), d.stored_name)
            other_shingles |= text_shingles(_read_text(op))
        if cur_shingles and other_shingles:
            sim = jaccard(cur_shingles, other_shingles)
            if sim > best:
                best, best_job = sim, other.id
    if best >= 0:
        result["similarity_max"] = round(best, 4)
        result["similarity_job_id"] = best_job
    if exact_job >= 0:
        result["fraud_signal"] = "fraud"
        result["similarity_max"] = 1.0
        result["similarity_job_id"] = exact_job
        result["reason"] = ("This delivery is byte-identical to the "
                           f"delivery for job #{exact_job}.")
    elif best >= SIMILARITY_FRAUD_THRESHOLD:
        result["fraud_signal"] = "fraud"
        result["reason"] = (f"This delivery is {best * 100:.0f}% similar "
                            f"to the delivery for job #{best_job} — "
                            "treated as a copy.")
    return result


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def run_check(job_id: int, judge_model: Optional[str] = None,
              is_appeal: bool = False,
              suppress_first_events: bool = False,
              is_dispute: bool = False) -> Verdict:
    """Run the full check against a delivered job and store the verdict.
    Transitions the job state to checked_pass / checked_fail.
    Raises CheckNotAllowedError if re-checking an already-checked job
    against the same delivery."""
    job = get_job(job_id)
    if job is None:
        raise ValueError(f"job {job_id} not found")

    items: List[VerdictItem] = []
    judge_model_used = ""

    for criterion in job.criteria:
        if criterion.criterion_type == "judgment":
            excerpt = _delivery_excerpt(delivery_paths(job_id))
            # The judge needs the surrogate bearer. Obtain lazily so the
            # deterministic items still run even if the judge path has no
            # socket available — the judgment item then reports
            # "judge unavailable".
            try:
                bearer = _obtain_surrogate()
            except Exception as e:
                items.append(VerdictItem(
                    name=criterion.name,
                    expected="content matches brief",
                    measured="judge not reached",
                    passed=False,
                    reason=f"judge unavailable: {type(e).__name__}: {e}",
                    checked_at=_now_iso(),
                    checker_kind="llm",
                    model_id="",
                    judged=False,
                ))
                continue
            try:
                passed, reason, model_id = call_judge(
                    criterion, job, excerpt, bearer, only_model=judge_model)
            except JudgeUnavailableError as e:
                items.append(VerdictItem(
                    name=criterion.name,
                    expected=f"judgment: {criterion.expected_value}",
                    measured="model evaluation",
                    passed=False,
                    reason=f"judge unavailable: {e}",
                    checked_at=_now_iso(),
                    checker_kind="llm",
                    model_id="",
                    judged=False,
                ))
                continue
            judge_model_used = model_id
            items.append(VerdictItem(
                name=criterion.name,
                expected=f"judgment: {criterion.expected_value}",
                measured="model evaluation",
                passed=passed,
                reason=reason,
                checked_at=_now_iso(),
                checker_kind="llm",
                model_id=model_id,
            ))
            # One judgment criterion — stop after it (dispatch: "ONE call").
            continue

        # --- Deterministic ---
        shape = criterion.name
        if shape not in _DETERMINISTIC:
            items.append(_item_unsupported(criterion))
            continue

        paths = delivery_paths(job_id)
        try:
            ok, measured, reason = _DETERMINISTIC[shape](criterion, paths)
        except Exception as e:
            ok, measured, reason = False, "n/a", (
                f"evaluation error: {type(e).__name__}: {e}")
        items.append(VerdictItem(
            name=shape,
            expected=f"{criterion.operator} {criterion.expected_value}",
            measured=measured,
            passed=ok,
            reason=reason,
            checked_at=_now_iso(),
            checker_kind="code",
            model_id="",
        ))

    # --- Originality analysis: always measured, always
    # recorded as an item. Fraud or excessive CSV duplication FAILs the
    # delivery regardless of the criteria.
    orig = analyse_originality(job_id, delivery_paths(job_id))
    if orig["fraud_signal"] == "fraud":
        items.append(VerdictItem(
            name="originality",
            expected="an original delivery, not a copy of another "
                     "job's work",
            measured=(f"similarity {orig['similarity_max']:.2f} vs "
                      f"job #{orig['similarity_job_id']}"),
            passed=False,
            reason=orig["reason"],
            checked_at=_now_iso(), checker_kind="code", model_id=""))
    elif orig["csv_dup_ratio"] > CSV_DUP_FAIL_RATIO:
        items.append(VerdictItem(
            name="originality",
            expected="CSV duplicate data rows <= 5%",
            measured=f"{orig['csv_dup_ratio'] * 100:.1f}% duplicate rows",
            passed=False,
            reason=(f"{orig['csv_dup_ratio'] * 100:.1f}% of the CSV data "
                    "rows are exact duplicates (limit 5%)."),
            checked_at=_now_iso(), checker_kind="code", model_id=""))
    else:
        if orig["similarity_max"] >= 0:
            sim_txt = (f"max similarity {orig['similarity_max'] * 100:.0f}% "
                       f"vs job #{orig['similarity_job_id']}")
        else:
            sim_txt = "no comparable earlier deliveries"
        items.append(VerdictItem(
            name="originality",
            expected="an original delivery, not a copy of another "
                     "job's work",
            measured=sim_txt,
            passed=True,
            reason="No copy of an earlier delivery detected.",
            checked_at=_now_iso(), checker_kind="code", model_id=""))

    # a criterion the judge never decided makes the
    # run INCOMPLETE — unless another, actually-judged item
    # already failed the delivery on its own merits (a fraud
    # flag or a deterministic miss is a real FAIL; the outage
    # itself decided nothing either way).
    unjudged = any(not it.judged for it in items)
    judged_failed = any(it.judged and not it.passed for it in items)
    incomplete = bool(unjudged and not judged_failed)
    overall = (len(items) > 0 and all(it.passed for it in items)
               and not incomplete)
    verdict = Verdict(
        job_id=job_id,
        overall_pass=overall,
        items=items,
        checked_at=_now_iso(),
        judge_model=judge_model_used,
        originality=orig,
        suppress_first_events=suppress_first_events,
        incomplete=incomplete,
    )
    check_id = store_verdict(verdict)
    store_check_with_originality(
        check_id, orig["fraud_signal"], orig["similarity_max"],
        orig["similarity_job_id"], orig["csv_dup_ratio"],
        is_appeal=1 if (is_appeal and not incomplete) else -1,
        is_dispute=1 if is_dispute else -1)
    if orig["fraud_signal"] == "fraud":
        emit_reputation_event_once(
            job.worker_id or 2, job_id, "fraud_flag",
            {"similarity_max": orig["similarity_max"],
             "matched_job_id": orig["similarity_job_id"]})
    if not is_dispute and not incomplete:
        # A dispute re-check must not move a settled job
        # back to a checked state; the dispute handler owns the state.
        # An incomplete run must not move the job either:
        # nothing was decided.
        set_job_checked(job_id, overall)
    return verdict


class CheckNotAllowedError(Exception):
    """Raised when a re-check is attempted on an already-checked job against
    the same delivery."""
    pass


def can_check(job_id: int) -> Tuple[bool, str]:
    """Gate: re-checking an already-checked job (same delivery) is refused
    visibly. Returns (allowed, reason)."""
    job = get_job(job_id)
    if job is None:
        return False, "job not found"
    if job.state in ("checked_pass", "checked_fail"):
        # Visible refusal.
        return False, (
            f"Check already run on this delivery (state: {job.state}). "
            f"A verdict is already stored. Re-checks happen only via the "
            f"revision path.")
    return True, ""
