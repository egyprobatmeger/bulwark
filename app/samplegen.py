"""Demo sample generator — a DEMO SHORTCUT, not a product feature.

Judge-friendliness requirement: a demo visitor (a hackathon
judge) cannot be expected to invent a job AND author a conforming
document before Bulwark does anything interesting. This module
synthesizes ONE sample delivery from a job's OWN recorded acceptance
criteria, and the job page delivers it through the very same
service-layer delivery action as a manual upload — the checker,
originality screen, payout and certificate that follow are the real
ones, unmodified.

Honesty rules:
- Only deterministic criteria in the checker's supported set can be
  synthesized. A judgment criterion (a Verifier AI call on content)
  or an unsupported shape is reported back by name and NO delivery
  is produced — the generator never fakes a pass.
- If the criteria contradict each other (e.g. row_count asked two
  incompatible ways), that is reported too, not papered over.
- The upload form remains the real path and is untouched; this is a
  convenience for trying the flow, labelled as such in the UI.
"""
import csv
import io
import re
import unicodedata

from app.checker import SUPPORTED_SHAPES

_FIRST = ["Anna", "Bela", "Csilla", "David", "Eszter", "Ferenc",
          "Greta", "Henrik", "Ildiko", "Janos", "Katalin", "Laszlo",
          "Maria", "Norbert", "Orsolya", "Peter"]
_LAST = ["Kovacs", "Nagy", "Szabo", "Toth", "Horvath", "Varga",
         "Kiss", "Molnar", "Nemeth", "Farkas", "Balogh", "Papp",
         "Takacs", "Juhasz", "Lakatos", "Meszaros"]
_CITIES = ["Budapest", "Debrecen", "Szeged", "Pecs", "Gyor",
           "Kecskemet", "Nyiregyhaza", "Szekesfehervar"]
_DOMAINS = ["example.com", "example.org", "example.net"]
_TOPICS = ["workshop", "delivery", "review", "training", "handover",
           "inspection", "summary", "planning"]

def _cmp(n, op, v):
    return {"=": n == v, ">=": n >= v, "<=": n <= v,
            ">": n > v, "<": n < v}.get(op, False)


def _pick_count(constraints):
    """A row count satisfying every row_count constraint, or None
    when they contradict each other."""
    n = 12
    exact = None
    for op, v in constraints:
        if op == "=":
            exact = v
        elif op == ">=":
            n = max(n, v)
        elif op == ">":
            n = max(n, v + 1)
        elif op == "<=" and n > v:
            n = v
        elif op == "<" and n >= v:
            n = v - 1
    if exact is not None:
        n = exact
    if n < 0 or n > 5000:
        return None
    if all(_cmp(n, op, v) for op, v in constraints):
        # A small cushion over a bare minimum reads more natural —
        # kept only if every constraint still holds.
        cushioned = n + 3
        if all(_cmp(cushioned, op, v) for op, v in constraints):
            return cushioned
        return n
    return None


def _cell(column, i, salt):
    """One plausible, non-empty cell value for a column at row i
    (1-based). Index-bearing generators are unique per row by
    construction."""
    key = column.strip().lower()
    if "email" in key:
        first = _FIRST[(i + salt) % len(_FIRST)].lower()
        last = _LAST[(i * 3 + salt) % len(_LAST)].lower()
        return f"{first}.{last}{i}@{_DOMAINS[salt % len(_DOMAINS)]}"
    if key == "id" or key.endswith("_id") or key == "no" \
            or key == "number":
        return str(i)
    if "sku" in key or "code" in key or "ref" in key:
        return f"{key.upper()[:3]}-{i:03d}"
    if "name" in key:
        first = _FIRST[(i + salt) % len(_FIRST)]
        last = _LAST[(i * 3 + salt) % len(_LAST)]
        return f"{first} {last}"
    if "city" in key or "town" in key:
        return _CITIES[(i + salt) % len(_CITIES)]
    if "price" in key or "amount" in key or "cost" in key:
        return f"{10 + (i * 7) % 80}.{(i * 37) % 100:02d}"
    if "date" in key:
        return f"2026-{((i - 1) % 12) + 1:02d}-{((i - 1) % 28) + 1:02d}"
    if "title" in key or "topic" in key or "subject" in key:
        return f"{_TOPICS[(i + salt) % len(_TOPICS)].title()} {i}"
    return f"{column} {i}"


def _slug(title):
    ascii_title = unicodedata.normalize("NFKD", title or "") \
        .encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_title.lower()).strip("_")
    return slug[:48] or "sample_delivery"


def _build_csv(job, columns, n_rows, needles):
    """(bytes, notes_column_or_None): a CSV whose rows satisfy the
    column / uniqueness / non-emptiness / contains-text inputs."""
    salt = job.id or 0
    cols = list(columns)
    notes_col = None
    if needles:
        notes_col = next((c for c in cols
                          if c.strip().lower() == "notes"), None)
        if notes_col is None:
            notes_col = "notes"
            cols.append(notes_col)
    rows = []
    for i in range(1, n_rows + 1):
        row = {}
        for c in cols:
            if c == notes_col:
                row[c] = ("; ".join(needles) if i == 1
                          else f"Entry {i} confirmed.")
            else:
                row[c] = _cell(c, i, salt)
        rows.append(row)
    return cols, rows


def _serialize_csv(cols, rows):
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=cols)
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    return buf.getvalue().encode("utf-8")


def _enforce_unique(cols, rows, unique_cols):
    """Safety net: if a column that must be unique still holds a
    duplicate (name lists can cycle on very long files), disambiguate
    the repeats in place."""
    for c in unique_cols:
        if c not in cols:
            continue
        seen = set()
        for idx, r in enumerate(rows, 1):
            v = r.get(c, "")
            if v in seen:
                r[c] = f"{v}-{idx}"
            seen.add(r[c])


def _pad_csv(cols, rows, current_len, target):
    """Grow a CSV to at least `target` bytes by lengthening a notes
    column — never a unique one — with distinct addenda, so no other
    criterion moves."""
    notes_col = next((c for c in cols
                      if c.strip().lower() == "notes"), None)
    if notes_col is None:
        notes_col = "notes"
        cols.append(notes_col)
        for idx, r in enumerate(rows, 1):
            r[notes_col] = f"Entry {idx} confirmed."
    data = _serialize_csv(cols, rows)
    k = 0
    while len(data) < target and k < 400:
        k += 1
        for idx, r in enumerate(rows, 1):
            r[notes_col] = (r[notes_col] +
                            f" Supplementary detail {k}-{idx}"
                            " recorded for this entry.")
            data = _serialize_csv(cols, rows)
            if len(data) >= target:
                break
    return data


def _pad_csv_exact(cols, rows, target):
    """Grow a CSV to EXACTLY `target` bytes (for a file_size_bytes
    '=' criterion): filler 'x' characters carry no CSV meaning, so
    the byte count moves exactly with their number. Returns None
    when the file is already too long or has no row to hold the
    filler."""
    data = _serialize_csv(cols, rows)
    if len(data) > target or not rows:
        return None
    notes_col = next((c for c in cols
                      if c.strip().lower() == "notes"), None)
    if notes_col is None:
        notes_col = "notes"
        cols.append(notes_col)
        for idx, r in enumerate(rows, 1):
            r[notes_col] = f"Entry {idx} confirmed."
        data = _serialize_csv(cols, rows)
        if len(data) > target:
            return None
    delta = target - len(data)
    rows[-1][notes_col] = rows[-1][notes_col] + "x" * delta
    data = _serialize_csv(cols, rows)
    return data if len(data) == target else None


def _build_text(job, n_rows, needles):
    """A plain-text sample: a heading line plus n_rows distinct
    content lines (the row counter treats line 1 as the header)."""
    lines = [job.title or "Sample delivery"]
    for i in range(1, n_rows + 1):
        line = (f"Entry {i}: {_TOPICS[(i + (job.id or 0)) % len(_TOPICS)]}"
                f" completed and recorded.")
        if i == 1 and needles:
            line += " " + " ".join(needles)
        lines.append(line)
    if n_rows == 0 and needles:
        lines.append(" ".join(needles))
    return ("\n".join(lines) + "\n").encode("utf-8")


def generate_sample_delivery(job):
    """Synthesize a delivery for `job` from its own criteria.

    Returns (files, unsupported): files is a list of
    (filename, bytes) ready for deliver_job_action — empty whenever
    unsupported is non-empty. unsupported names, in plain words, the
    criteria the generator cannot honestly produce."""
    unsupported = []
    fmt = ""
    row_constraints = []
    count_constraints = []
    size_constraints = []
    columns = []
    unique_cols = []
    nonempty_cols = []
    needles = []

    for c in job.criteria:
        if c.criterion_type == "judgment":
            unsupported.append(
                f"the judgment criterion “{c.expected_value or c.name}”"
                " — a Verifier AI judges the content itself, so no"
                " generated file can be promised to pass it")
            continue
        if c.name not in SUPPORTED_SHAPES:
            unsupported.append(
                f"criterion “{c.name}” — the checker itself does not"
                " support this shape")
            continue
        value = (c.expected_value or "").strip()
        if c.name == "format":
            fmt = value.lower()
        elif c.name == "row_count":
            try:
                row_constraints.append((c.operator, int(float(value))))
            except ValueError:
                unsupported.append(
                    f"row_count “{c.operator} {value}” — not a number"
                    " the generator can aim at")
        elif c.name == "file_count":
            try:
                count_constraints.append((c.operator,
                                          int(float(value))))
            except ValueError:
                unsupported.append(
                    f"file_count “{c.operator} {value}” — not a number")
        elif c.name == "file_size_bytes":
            try:
                size_constraints.append((c.operator,
                                         int(float(value))))
            except ValueError:
                unsupported.append(
                    f"file_size_bytes “{c.operator} {value}” — not a"
                    " number")
        elif c.name == "contains_column":
            if value and value not in columns:
                columns.append(value)
        elif c.name == "unique_column":
            if value:
                unique_cols.append(value)
                if value not in columns:
                    columns.append(value)
        elif c.name == "nonempty_column":
            if value:
                nonempty_cols.append(value)
                if value not in columns:
                    columns.append(value)
        elif c.name == "contains_text":
            if value:
                needles.append(value)
    if unsupported:
        return [], unsupported

    if fmt and fmt not in ("csv", "txt"):
        return [], [f"format “{fmt}” — the generator writes honest"
                    " CSV or plain-text samples, not a file that only"
                    " wears another format's name"]
    csv_kind = fmt == "csv" or bool(
        row_constraints or columns or unique_cols or nonempty_cols) \
        or fmt == ""
    if fmt == "txt":
        csv_kind = False
    if not csv_kind and (unique_cols or nonempty_cols or columns):
        return [], ["column criteria on a plain-text job — the"
                    " generator cannot express columns without a CSV"]

    n_rows = _pick_count(row_constraints)
    if n_rows is None:
        return [], ["the row_count criteria contradict each other"
                    " — no single file can satisfy all of them"]

    if csv_kind:
        cols = columns or ["id", "name", "email"]
        cols, rows = _build_csv(job, cols, n_rows, needles)
        _enforce_unique(cols, rows, unique_cols)
        data = _serialize_csv(cols, rows)
        filename = _slug(job.title) + ".csv"
    else:
        data = _build_text(job, n_rows, needles)
        filename = _slug(job.title) + ".txt"

    for op, v in size_constraints:
        if op == "=":
            if len(data) != v:
                exact = _pad_csv_exact(cols, rows, v) \
                    if csv_kind else None
                if exact is None:
                    return [], [
                        f"file_size_bytes “= {v}” — the generator"
                        f" cannot land on exactly {v} bytes for"
                        " these criteria"]
                data = exact
        elif op in (">=", ">"):
            target = v if op == ">=" else v + 1
            if len(data) < target:
                if csv_kind:
                    data = _pad_csv(cols, rows, len(data), target)
                else:
                    text = data.decode("utf-8")
                    lines = text.splitlines()
                    while len(data) < target:
                        lines = [ln + " Additional recorded detail."
                                 for ln in lines]
                        data = ("\n".join(lines) + "\n").encode("utf-8")
        elif op in ("<=", "<"):
            limit = v if op == "<=" else v - 1
            if len(data) > limit:
                return [], [
                    f"file_size_bytes “{op} {v}” — the smallest"
                    f" honest sample for these criteria is"
                    f" {len(data)} bytes"]

    files = [(filename, data)]
    n_files = 1
    for op, v in count_constraints:
        if op == "=":
            n_files = v
        elif op == ">=":
            n_files = max(n_files, v)
        elif op == ">":
            n_files = max(n_files, v + 1)
        elif op in ("<=", "<"):
            limit = v if op == "<=" else v - 1
            if n_files > limit:
                return [], [
                    f"file_count “{op} {v}” conflicts with the rest"
                    " of the acceptance test"]
    if n_files < 1:
        return [], ["file_count asks for zero files — there would"
                    " be nothing to check"]
    for k in range(2, n_files + 1):
        extra = (f"Sample attachment {k} for job #{job.id}.\n"
                 f"Supporting note {k}: recorded alongside the main"
                 " delivery.\n").encode("utf-8")
        files.append((f"sample_attachment_{k}.txt", extra))
    return files, []
