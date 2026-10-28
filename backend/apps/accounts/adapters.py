"""Allauth adapters: email-domain allowlist for signups and social login."""

import logging

from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest

logger = logging.getLogger(__name__)


class CustomAccountAdapter(DefaultAccountAdapter):
    """Restrict signup email domains to an explicit allowlist.

    The allowlist is read from ``ACCOUNT_ALLOWED_SIGNUP_DOMAINS`` (a list of
    lower-cased domains). When the list is empty, every domain is accepted so
    that the restriction is opt-in. This is intentionally separate from the
    future org-auto-assignment step (AUTH-06): signup never grants an
    organization membership or an elevated role.
    """

    def clean_email(self, email):
        email = super().clean_email(email)
        allowed = settings.ACCOUNT_ALLOWED_SIGNUP_DOMAINS
        if allowed and email:
            domain = email.rsplit("@", 1)[-1].lower()
            if domain not in {d.lower() for d in allowed}:
                raise ValidationError("Signups from this email domain are not allowed.")
        return email


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    """Enforces the email-domain allowlist for GitHub OAuth signups.

    Q2 (Tech Lead-approved): does NOT override ``is_email_verified``. GitHub&rsquo;s
    native per-email ``verified`` flag from ``GET /user/emails`` is already
    correctly extracted by allauth&rsquo;s GitHub provider and preserved through
    ``cleanup_email_addresses`` (which only upgrades, never downgrades).

    Q4 (Tech Lead-approved): does NOT enable email-based account linking
    (``SOCIALACCOUNT_EMAIL_AUTHENTICATION`` remains ``False``). Existing local
    accounts are never connected to a GitHub account based on matching emails.

    Q6 (Tech Lead-approved): enforces the ``ACCOUNT_ALLOWED_SIGNUP_DOMAINS``
    allowlist in ``pre_social_login`` (server-side, pre-user-creation).
    """

    def pre_social_login(self, request: HttpRequest, sociallogin) -> None:
        """Reject social signups from disallowed email domains before any
        user record is created.

        This runs inside ``flows.login.complete_login`` before ``lookup()``
        creates or retrieves a user. Raising ``PermissionDenied`` causes
        allauth&rsquo;s ``OAuth2CallbackView`` to call
        ``render_authentication_error``, which (in headless mode) redirects
        the SPA to the ``callback_url`` with ``?error=permission_denied``.

        The email is read from the raw provider data (``extra_data``) because
        ``CustomAccountAdapter.clean_email`` (invoked inside allauth&rsquo;s
        ``cleanup_email_addresses`` via ``valid_email_or_none``) may have
        already dropped the email from ``sociallogin.user.email`` for a
        disallowed domain, leaving it empty.
        """
        super().pre_social_login(request, sociallogin)
        email = self._get_sociallogin_email(sociallogin)
        if not email:
            return
        allowed = settings.ACCOUNT_ALLOWED_SIGNUP_DOMAINS
        if allowed:
            domain = email.rsplit("@", 1)[-1].lower()
            if domain not in {d.lower() for d in allowed}:
                logger.info(
                    "GitHub social login rejected: domain %r not in allowlist",
                    domain,
                )
                raise PermissionDenied(
                    "Email domain is not allowed for signups."
                )

    def _get_sociallogin_email(self, sociallogin) -> str | None:
        """Return the first non-empty email from any source on the sociallogin."""
        if sociallogin.user and sociallogin.user.email:
            return sociallogin.user.email
        if sociallogin.account and (extra := sociallogin.account.extra_data):
            if email := extra.get("email"):
                return email
        if sociallogin.email_addresses:
            return sociallogin.email_addresses[0].email

    def on_authentication_error(self, request, provider, error=None, exception=None, extra_context=None):
        """Log provider/auth errors server-side for ops visibility.

        Does NOT raise ``ImmediateHttpResponse`` &mdash; defers to allauth&rsquo;s
        headless error handler, which redirects the SPA to the ``callback_url``
        with an ``?error=...`` query parameter.
        """
        logger.warning(
            "Social authentication error: provider=%s error=%s exception=%r",
            getattr(provider, "id", provider),
            error,
            exception,
        )

