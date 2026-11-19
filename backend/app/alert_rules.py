"""Shared alert-rule logic for the fictional demo and the internal alerts module.

Pure functions only: no database, network or model. An algorithm never publishes
anything; it only proposes candidates that an authenticated administrator reviews.
"""
from datetime import datetime, timezone

# Values (expected or observed) below this are shown as PROTECTED everywhere.
MINIMUM_COUNT = 5
PROTECTED = 'protegido'
MAX_CONSECUTIVE = 4
CANDIDATE_STATES = ('pending', 'approved_internal', 'discarded')
DISCARD_REASONS = ('false_alarm', 'insufficient_context', 'duplicate', 'other')
CITIZEN_PUBLICATION = 'blocked_out_of_scope'


class CitizenPublicationBlocked(Exception):
    """Publishing an alert to citizens is outside the prototype scope."""


def block_citizen_publication():
    raise CitizenPublicationBlocked('La publicación ciudadana de alertas está fuera del alcance del prototipo y bloqueada.')


def meets_threshold(value, threshold):
    """None means unknown, never zero."""
    return None if value is None else value >= threshold


def disclose(value, digits=2):
    """Small-cell protection: 0..4 (including zero) is never disclosed."""
    if value is None:
        return None
    if 0 <= value < MINIMUM_COUNT:
        return PROTECTED
    value = round(float(value), digits)
    return int(value) if value.is_integer() else value


def disclose_split(part, total):
    """A subset count is hidden when it or its complement is small (no subtraction attacks)."""
    if part is None or total is None:
        return None
    return PROTECTED if part < MINIMUM_COUNT or total - part < MINIMUM_COUNT else part


def window_outcome(conditions):
    """Consecutive-week rule: fires only if every week in the window met the condition.

    Any known False stops it; otherwise a missing value means insufficient data, so a
    candidate is never generated from unavailable predictions.
    """
    if any(c is False for c in conditions):
        return 'not_met'
    if not conditions or any(c is None for c in conditions):
        return 'insufficient_data'
    return 'fired'


def audit_entry(actor_id, action, details):
    return dict(actor_id=actor_id, action=action, created_at=datetime.now(timezone.utc).isoformat(), details=details)
