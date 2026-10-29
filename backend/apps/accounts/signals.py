"""Security event signal handlers for django-allauth MFA signals (AUTH-05B.9C.2).

Wires allauth MFA signals to the ``agentgate.security`` logger declared in
``config.settings.base``.  Each handler builds an allowlisted JSON payload
from primitive fields only — never TOTP secrets, codes, recovery-code
seeds, encryption keys, request bodies, headers, cookies, IP addresses,
email addresses, or exception messages.
"""

import json
import logging
import sys

from allauth.mfa import signals as mfa_signals
from allauth.mfa.models import Authenticator
from django.dispatch import receiver

_logger = logging.getLogger("agentgate.security")

# Fields permitted in the JSON event payload.  Anything not in this set is
# stripped defensively by _build_payload.
_ALLOWED_EVENT_FIELDS = frozenset(
    {
        "event",
        "user_id",
        "authenticator_type",
        "authenticator_id",
        "reauthentication",
    }
)


def _build_payload(event, user, authenticator, **extra):
    """Assemble an allowlisted JSON payload from primitive fields only.

    All values are coerced to JSON-native primitives (str, int, bool).
    ``user_id`` is explicitly stringified (UUID support) and
    ``authenticator.data`` is never accessed.
    """
    payload = {
        "event": event,
        "user_id": str(user.id),
        "authenticator_type": str(authenticator.type),
        "authenticator_id": authenticator.id,
    }
    for key, value in extra.items():
        if key in _ALLOWED_EVENT_FIELDS:
            payload[key] = value
    return payload


def _emit(level, event, user, authenticator, **metadata):
    """Emit a serialized security event with failure isolation.

    Payload construction, JSON serialization, and log emission are each
    wrapped in narrowly scoped ``try``/``except`` blocks.  If any step
    fails, a safe diagnostic line is written to **stderr** — the
    ``agentgate.security`` logger is never invoked recursively, and no
    sensitive metadata is included.
    """
    try:
        payload = _build_payload(event, user, authenticator, **metadata)
        message = json.dumps(payload, sort_keys=True)
    except (TypeError, ValueError, AttributeError, KeyError):
        sys.stderr.write(
            "agentgate.security: failed to construct event "
            f"'{event}'\n"
        )
        return

    try:
        if level == logging.WARNING:
            _logger.warning(message)
        else:
            _logger.info(message)
    except Exception:
        sys.stderr.write(
            f"agentgate.security: emission failed for event '{event}'\n"
        )


@receiver(mfa_signals.authenticator_added, sender=Authenticator,
          dispatch_uid="mfa_security_authenticator_added")
def _on_authenticator_added(sender, request, user, authenticator, **kwargs):
    """Emit ``mfa.totp_activated`` when a TOTP authenticator is added.

    Recovery-code authenticators (auto-generated during TOTP enrollment)
    are silently skipped so they are never mislabeled as TOTP activation.
    """
    if authenticator.type == Authenticator.Type.RECOVERY_CODES:
        return
    _emit(logging.WARNING, "mfa.totp_activated", user, authenticator)


@receiver(mfa_signals.authenticator_removed, sender=Authenticator,
          dispatch_uid="mfa_security_authenticator_removed")
def _on_authenticator_removed(sender, request, user, authenticator, **kwargs):
    """Emit ``mfa.authenticator_removed`` with the authenticator type.

    When ``delete_and_cleanup`` removes both a TOTP authenticator and its
    dangling recovery-code authenticator, allauth sends one
    ``authenticator_removed`` signal per authenticator.  Each emits a single
    event with the correct ``authenticator_type`` — TOTP removals are never
    duplicated.
    """
    _emit(logging.WARNING, "mfa.authenticator_removed", user, authenticator)


@receiver(mfa_signals.authenticator_reset, sender=Authenticator,
          dispatch_uid="mfa_security_authenticator_reset")
def _on_authenticator_reset(sender, request, user, authenticator, **kwargs):
    """Emit ``mfa.recovery_codes_regenerated`` when recovery codes are reset."""
    _emit(logging.WARNING, "mfa.recovery_codes_regenerated", user, authenticator)


@receiver(mfa_signals.authenticator_used, sender=Authenticator,
          dispatch_uid="mfa_security_authenticator_used")
def _on_authenticator_used(sender, request, user, authenticator, **kwargs):
    """Emit ``mfa.challenge_succeeded`` (TOTP) or ``mfa.recovery_code_used``.

    Recovery-code usage is elevated to WARNING because it indicates the user
    lacks their TOTP device.  The ``reauthenticated`` kwarg from allauth is
    mapped to the ``reauthentication`` metadata field.
    """
    reauthenticated = kwargs.get("reauthenticated", False)
    if authenticator.type == Authenticator.Type.RECOVERY_CODES:
        _emit(
            logging.WARNING,
            "mfa.recovery_code_used",
            user,
            authenticator,
            reauthentication=reauthenticated,
        )
    else:
        _emit(
            logging.INFO,
            "mfa.challenge_succeeded",
            user,
            authenticator,
            reauthentication=reauthenticated,
        )


@receiver(mfa_signals.authentication_failed, sender=Authenticator,
          dispatch_uid="mfa_security_authentication_failed")
def _on_authentication_failed(sender, request, user, authenticator, **kwargs):
    """Emit ``mfa.challenge_failed`` with the authenticator type allauth selected.

    The ``authenticator`` supplied by allauth is its best-effort *primary*
    authenticator, not necessarily the code type the user attempted.  The
    ``authenticator_type`` is recorded for correlation but should not be
    treated as definitive of the attempted credential.
    """
    reauthentication = kwargs.get("reauthentication", False)
    _emit(
        logging.WARNING,
        "mfa.challenge_failed",
        user,
        authenticator,
        reauthentication=reauthentication,
    )
