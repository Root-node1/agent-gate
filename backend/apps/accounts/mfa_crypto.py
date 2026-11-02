"""Fernet-backed encryption for MFA secrets at rest.

Secrets persisted by django-allauth's ``allauth.mfa`` &mdash; TOTP keys (in
``Authenticator.data["secret"]``) and recovery-code seeds (in
``Authenticator.data["seed"]``) &mdash; are routed through
``CustomMFAAdapter.encrypt`` / ``decrypt`` (allauth/mfa/utils.py wraps the
adapter calls).  This module supplies the ``MultiFernet`` key ring used by
that adapter.

Key management
--------------
``MFA_ENCRYPTION_KEY``
    Primary Fernet key (urlsafe base64 of 32 bytes, e.g.
    ``Fernet.generate_key().decode()``).  New ciphertext is always produced
    under this key.

 ``MFA_ENCRYPTION_PREVIOUS_KEYS``
     Comma-separated list of older keys authorized for **decryption only**.
     Enables zero-downtime key rotation.

     1. Generate a new primary key, deploy it as ``MFA_ENCRYPTION_KEY``.
     2. Add the old primary to ``MFA_ENCRYPTION_PREVIOUS_KEYS``.
     3. Existing ciphertext (encrypted under the old key) still decrypts;
        new ciphertext uses the new primary.
     4. After all old ciphertext is re-encrypted under the new key, remove
        the old key from the previous list.

 Key rotation procedure (MultiFernet lifecycle)
 ---------------------------------------------
 This is a **manual, operator-driven** procedure.  Do NOT automate it in
 application code &mdash; there is no management command and no data migration
 unless evidence of plaintext MFA records is found (there should be none, since
 ``CustomMFAAdapter`` encrypts on write from day one).

 Prerequisites
     * The operator has a current backup of the ``Authenticator`` table.
     * ``python manage.py check`` passes with the **new** key ring (both keys
       valid &mdash; see the system check in ``apps.accounts.checks``).
     * A rollback plan: if step 4 fails, the new key can be removed from the
       ring and traffic reverted to the old primary.

 Step-by-step (do not execute in production here &mdash; document only)
     1. **Generate** a new primary key:
        ``python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"``
     2. **Configure** the new key ring in the environment:
        ``MFA_ENCRYPTION_KEY=<new-key>``
        ``MFA_ENCRYPTION_PREVIOUS_KEYS=<old-primary-key>``
        Deploy to **all** workers simultaneously (URL configuration is loaded
        per-worker, so an inconsistent ring would cause some workers to encrypt
        under the new key while others still need the old key to decrypt).
     3. **Verify** that existing records decrypt: a read of any
        ``Authenticator`` with an old ciphertext must succeed because
        ``MultiFernet`` tries the primary first, then each previous key.
     4. **Re-encrypt** existing ``Authenticator`` records so they use the new
        primary.  A one-off data migration or management command reads each
        record's ``data["secret"]`` (or ``data["seed"]``) via
        ``CustomMFAAdapter.decrypt()``, then writes it back via
        ``CustomMFAAdapter.encrypt()``.  This must be done during a maintenance
        window with write traffic paused &mdash; once records are re-encrypted
        under the new key, the old key is no longer needed for them.
     5. **Verify** that all records decrypt with the new primary alone:
        temporarily set ``MFA_ENCRYPTION_PREVIOUS_KEYS=[]`` (keeping only the
        new ``MFA_ENCRYPTION_KEY``) and confirm no ``InvalidToken`` errors
        surface in logs.
     6. **Retire** the old key: remove it from ``MFA_ENCRYPTION_PREVIOUS_KEYS``
        in the environment, redeploy, and monitor.  The old key can be
        recreated from backup only in an extreme rollback scenario.

Security properties
--------------------
* Independent of ``DJANGO_SECRET_KEY``.  Rotating the Django secret
  (done on every deploy via ``run.sh``) invalidates sessions but must not
  invalidate MFA enrollment.  See docs/totp-2fa-contract.html &sect;5.5.
* Never derives a key from ``DJANGO_SECRET_KEY`` or any other secondary secret.
* Never logs keys or MFA secrets.
* Missing or malformed key configuration raises ``ImproperlyConfigured``
  so the system fails closed &mdash; enrollment and login are blocked, never
  falling back to plaintext.
 * Malformed or tampered ciphertext raises ``cryptography.fernet.InvalidToken``,
   also failing closed.

See: docs/totp-2fa-contract.html &sect;4.3, &sect;5.5
"""

import logging

from cryptography.fernet import Fernet, MultiFernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)


def _make_fernet(key: str, label: str) -> Fernet:
    """Validate and construct a single Fernet key.

    Raises ``ImproperlyConfigured`` when the key is absent or malformed.
    """
    if not key:
        raise ImproperlyConfigured(
            f"{label} is not configured. Set a urlsafe-base64 Fernet key "
            f"(e.g. Fernet.generate_key().decode()) in your environment."
        )
    try:
        return Fernet(key)
    except Exception as exc:
        raise ImproperlyConfigured(f"{label} is not a valid Fernet key.") from exc


def get_mfa_fernet() -> MultiFernet:
    """Build a ``MultiFernet`` key ring from Django settings.

    The primary key (``MFA_ENCRYPTION_KEY``) encrypts new ciphertext and is
    tried first during decryption.  Each key in
    ``MFA_ENCRYPTION_PREVIOUS_KEYS`` is tried in order for decryption only.

    Settings are read fresh on every call (no module-level cache) so that
    test ``@override_settings`` and live key rotation take effect immediately.

    Raises
    ------
    ImproperlyConfigured
        If the primary key is missing or any configured key is malformed.
    """
    fernets = [
        _make_fernet(
            getattr(settings, "MFA_ENCRYPTION_KEY", "") or "",
            "MFA_ENCRYPTION_KEY",
        )
    ]

    previous_keys = getattr(settings, "MFA_ENCRYPTION_PREVIOUS_KEYS", []) or []
    for i, key in enumerate(previous_keys):
        if key:
            fernets.append(_make_fernet(key, f"MFA_ENCRYPTION_PREVIOUS_KEYS[{i}]"))

    return MultiFernet(fernets)
