"""
Cookie-backed storage for analysis payloads.

On Vercel each serverless instance receives its own ephemeral SQLite file, so
an upload handled by one instance is invisible to the next request that lands
on a different instance. To keep the dashboard populated, the prediction rows
are mirrored into the Flask signed-session cookie, which travels with the
browser instead of the server.

Payloads are encoded as CSV, compressed with zlib and base64-encoded so they
stay small. When the encoded cookie would exceed the browser budget the
storage automatically downgrades to a reduced field set and, if necessary,
drops the oldest stored analysis.
"""

import base64
import csv
import io
import json
import zlib

try:
    from backend.config import (
        FULL_PREDICTION_FIELDS,
        REDUCED_PREDICTION_FIELDS,
        SESSION_ANALYSES_KEY,
        SESSION_COOKIE_MAX_BYTES,
    )
except ImportError:
    from config import (
        FULL_PREDICTION_FIELDS,
        REDUCED_PREDICTION_FIELDS,
        SESSION_ANALYSES_KEY,
        SESSION_COOKIE_MAX_BYTES,
    )


# Fields written to the CSV export even when they were dropped from the
# session payload. They are emitted as empty strings to keep the schema stable.
CSV_EXPORT_FIELDS = [
    "parental_education",
    "extracurricular",
    "sports",
    "music",
    "volunteering",
]

# Fields restored from a reduced payload as empty strings.
_REDUCED_PLACEHOLDERS = {
    "parental_education": "",
    "extracurricular": "",
    "sports": "",
    "music": "",
    "volunteering": "",
}


def pack_predictions(rows, fields):
    """
    Encodes prediction rows as a compressed, base64-safe string.
    The field order is preserved so the rows can be rebuilt exactly.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(fields)
    for row in rows:
        writer.writerow(["" if row.get(f) is None else row.get(f) for f in fields])

    compressed = zlib.compress(buffer.getvalue().encode("utf-8"), 9)
    return base64.b64encode(compressed).decode("ascii")


def unpack_predictions(blob, fields):
    """
    Decodes a payload produced by pack_predictions back into row dictionaries.
    """
    if not blob:
        return []

    try:
        raw = zlib.decompress(base64.b64decode(blob)).decode("utf-8")
    except (ValueError, zlib.error):
        return []

    reader = csv.reader(io.StringIO(raw))
    try:
        header = next(reader)
    except StopIteration:
        return []

    rows = []
    for record in reader:
        if not record:
            continue
        row = {}
        for index, field in enumerate(header):
            value = record[index] if index < len(record) else ""
            row[field] = _coerce(value, field)
        # Reduced payloads omit columns the dashboard never renders; restore
        # them as empty strings so every row keeps the same stable shape.
        for field in CSV_EXPORT_FIELDS:
            row.setdefault(field, _REDUCED_PLACEHOLDERS[field])
        for field in fields:
            row.setdefault(field, None)
        rows.append(row)

    return rows


def _coerce(value, field):
    """
    Restores the original Python type of a value after the CSV round-trip.
    """
    if value == "":
        return None

    if field in ("student_row", "absences", "tutoring", "parental_support",
                 "parental_education", "extracurricular", "sports", "music",
                 "volunteering"):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    if field in ("study_time", "predicted_gpa", "actual_gpa"):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    return value


def default_measure(session_dict):
    """
    Approximates the encoded size of a session cookie payload.

    Used when no exact measurement callback is supplied. The calculation
    mirrors what Flask does: compact JSON, optional zlib compression,
    URL-safe base64 without padding, plus room for the timestamp and the
    HMAC signature that itsdangerous appends.
    """
    payload = json.dumps(session_dict, separators=(",", ":"), default=str)
    payload = payload.encode("utf-8")

    compressed = zlib.compress(payload, 9)
    marker = 0
    if len(compressed) < len(payload) - 1:
        payload = compressed
        marker = 1

    encoded = base64.urlsafe_b64encode(payload).rstrip(b"=")
    return len(encoded) + marker + 64


def _make_entry(analysis_id, meta, rows, fields):
    return {
        "id": analysis_id,
        "meta": meta,
        "fields": list(fields),
        "rows": pack_predictions(rows, fields),
    }


def store_analysis(session, analysis_id, meta, rows, measure=None):
    """
    Stores an analysis payload in the session, respecting the cookie budget.

    The size of the resulting cookie is measured with the supplied
    ``measure`` callback, which receives the complete session dictionary and
    returns the number of bytes the encoded cookie would occupy. When no
    callback is given, :func:`default_measure` is used.

    The payload is first tried with the full field set, then with the reduced
    field set, then the oldest stored analyses are evicted one by one. As a
    last resort the stored rows are trimmed so that at least a partial
    result survives.

    Returns the mode that was used ("full", "reduced") or None if the
    payload could not be stored at all.
    """
    measure = measure or default_measure

    # Replace a previous entry for the same id so re-uploads do not pile up.
    stored = [
        e for e in session.get(SESSION_ANALYSES_KEY, [])
        if e.get("id") != analysis_id
    ]

    def size_of(entries):
        probe = dict(session)
        probe[SESSION_ANALYSES_KEY] = entries
        return measure(probe)

    def attempt(entries, fields, payload_rows):
        entry = _make_entry(analysis_id, meta, payload_rows, fields)
        trial = [entry] + entries
        if size_of(trial) <= SESSION_COOKIE_MAX_BYTES:
            mode = "full" if fields is FULL_PREDICTION_FIELDS else "reduced"
            return trial, mode
        return None, None

    for fields in (FULL_PREDICTION_FIELDS, REDUCED_PREDICTION_FIELDS):
        trial, mode = attempt(stored, fields, rows)
        if trial is not None:
            session[SESSION_ANALYSES_KEY] = trial
            return mode

    # Evict the oldest analyses until the new payload fits.
    while stored:
        stored.pop()
        for fields in (FULL_PREDICTION_FIELDS, REDUCED_PREDICTION_FIELDS):
            trial, mode = attempt(stored, fields, rows)
            if trial is not None:
                session[SESSION_ANALYSES_KEY] = trial
                return mode

    # Still too large: keep as many of the leading rows as the budget allows.
    trimmed = list(rows)
    while trimmed:
        candidate_meta = dict(meta)
        candidate_meta["truncated"] = len(trimmed) < len(rows)
        candidate_meta["rows_stored"] = len(trimmed)
        entry = _make_entry(
            analysis_id, candidate_meta, trimmed, REDUCED_PREDICTION_FIELDS
        )
        if size_of([entry]) <= SESSION_COOKIE_MAX_BYTES:
            session[SESSION_ANALYSES_KEY] = [entry]
            return "reduced"
        trimmed.pop()

    # Nothing fits; the database copy remains the source of truth.
    session[SESSION_ANALYSES_KEY] = []
    return None


def load_analysis(session, analysis_id):
    """
    Returns (meta, rows) for an analysis stored in the session, or None.
    """
    for entry in session.get(SESSION_ANALYSES_KEY, []):
        if entry.get("id") == analysis_id:
            rows = unpack_predictions(entry.get("rows"), entry.get("fields") or [])
            return entry.get("meta") or {}, rows
    return None


def list_stored_analyses(session):
    """
    Returns lightweight metadata for every analysis stored in the session,
    newest first, suitable for the "reopen past analysis" dropdown.
    """
    results = []
    for entry in session.get(SESSION_ANALYSES_KEY, []):
        meta = dict(entry.get("meta") or {})
        meta["id"] = entry.get("id")
        results.append(meta)
    return results


def latest_stored_analysis_id(session):
    """
    Returns the id of the most recently stored session analysis, or None.
    """
    entries = session.get(SESSION_ANALYSES_KEY, [])
    if not entries:
        return None
    return entries[0].get("id")
