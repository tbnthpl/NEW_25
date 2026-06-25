import json

from backend.models import AuditLog


SENSITIVE_AUDIT_KEYS = frozenset(
    k.lower()
    for k in (
        "account_no",
        "account_number",
        "accountnumber",
        "customer_id",
        "customerid",
        "cif",
        "cif_no",
        "cif_number",
        "card_no",
        "password",
        "secret",
        "token",
    )
)


def _mask(value):
    if value is None:
        return None
    s = str(value)
    if not s:
        return s
    if len(s) <= 4:
        return "*" * len(s)
    return s[:2] + ("*" * (len(s) - 4)) + s[-2:]


def _redact(value):
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            try:
                key_l = str(k).lower()
            except Exception:
                key_l = ""
            if key_l in SENSITIVE_AUDIT_KEYS:
                out[k] = _mask(v)
            else:
                out[k] = _redact(v)
        return out
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    return value


def _to_number(value):
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_text(value):
    if value is None:
        return None
    redacted = _redact(value) if isinstance(value, (dict, list, tuple)) else value
    if isinstance(redacted, (dict, list, tuple)):
        return json.dumps(redacted, default=str)
    return str(redacted)


def log_audit(db, entity_type, entity_id, action, old_data, new_data, changed_by):
    entry = AuditLog(
        entity_type=entity_type,
        entity_id=_to_number(entity_id),
        action=action,
        old_data=_to_text(old_data),
        new_data=_to_text(new_data),
        changed_by=changed_by,
    )
    db.add(entry)
    return entry
