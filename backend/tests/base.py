import base64
import secrets

from allauth.mfa.models import Authenticator
from allauth.mfa.utils import encrypt as mfa_encrypt
from django.db import connection
from django.test import TransactionTestCase

AUDIT_TABLE = "audit_auditevent"


def force_mfa(user, secret=None):
    """Create a TOTP Authenticator record at the DB level (bypasses allauth flow).

    This makes ``is_mfa_enabled(user)`` return ``True`` so that DRF permission
    gates (``MFAEnrollmentRequired``) pass.  The secret is encrypted via the
    configured MFA adapter so that allauth internals (e.g. login-time MFA
    challenges) continue to work if the test later exercises them.
    """
    if secret is None:
        secret = base64.b32encode(secrets.token_bytes(20)).decode("ascii")
    Authenticator.objects.create(
        user=user,
        type=Authenticator.Type.TOTP,
        data={"secret": mfa_encrypt(secret)},
    )
    return secret


class PostgresTransactionTestCase(TransactionTestCase):
    """Transaction test case that can flush the append-only audit table."""

    def _audit_triggers(self):
        if connection.vendor != "postgresql":
            return []
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT tgname FROM pg_trigger WHERE tgrelid = to_regclass(%s) AND NOT tgisinternal",
                [AUDIT_TABLE],
            )
            return [row[0] for row in cursor.fetchall()]

    def _fixture_teardown(self):
        triggers = self._audit_triggers()
        for trigger in triggers:
            with connection.cursor() as cursor:
                cursor.execute(f"ALTER TABLE {AUDIT_TABLE} DISABLE TRIGGER {trigger}")
        try:
            super()._fixture_teardown()
        finally:
            for trigger in triggers:
                with connection.cursor() as cursor:
                    cursor.execute(f"ALTER TABLE {AUDIT_TABLE} ENABLE TRIGGER {trigger}")
