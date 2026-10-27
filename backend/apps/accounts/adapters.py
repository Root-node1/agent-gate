"""Allauth account adapter: email-domain allowlist for signups."""

from django.conf import settings
from django.core.exceptions import ValidationError

from allauth.account.adapter import DefaultAccountAdapter


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
