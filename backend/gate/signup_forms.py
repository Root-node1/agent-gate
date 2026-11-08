from django import forms
from django.utils import timezone

from gate.models import AccountProfile


class AgentGateSignupForm(forms.Form):
    full_name = forms.CharField(max_length=150)
    organization = forms.CharField(max_length=150)
    accept_terms = forms.BooleanField()

    def signup(self, request, user):
        full_name = " ".join(self.cleaned_data["full_name"].split())
        first_name, _, last_name = full_name.partition(" ")
        user.first_name = first_name
        user.last_name = last_name
        user.save(update_fields=["first_name", "last_name"])
        AccountProfile.objects.create(
            user=user,
            full_name=full_name,
            organization=self.cleaned_data["organization"].strip(),
            terms_accepted_at=timezone.now(),
        )
