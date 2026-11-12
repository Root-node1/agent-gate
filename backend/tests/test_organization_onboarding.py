import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import Organization, OrgMembership

User = get_user_model()
HEADLESS_BASE = "/api/auth/headless/browser/v1"


class OrganizationOnboardingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username=f"owner-{uuid.uuid4().hex[:8]}",
            email=f"owner-{uuid.uuid4().hex[:8]}@example.com",
            password="Abc!12345",
        )
        self.client = APIClient(enforce_csrf_checks=True)
        self.client.force_login(self.user)
        self.csrf_token = self.client.get("/api/auth/csrf/").json()["csrfToken"]

    def create_workspace(self, name):
        return self.client.post(
            "/api/auth/organizations/",
            {"name": name},
            format="json",
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )

    def test_authenticated_user_creates_workspace_as_initial_admin(self):
        response = self.create_workspace("Northstar Studio")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["name"], "Northstar Studio")
        self.assertEqual(response.json()["role"], OrgMembership.Role.ADMIN)
        membership = OrgMembership.objects.get(user=self.user)
        self.assertEqual(str(membership.organization_id), response.json()["id"])
        self.assertEqual(membership.organization.name, "Northstar Studio")

        profile = self.client.get("/api/auth/user/").json()
        self.assertEqual(
            profile["memberships"],
            [
                {
                    "organization_id": str(membership.organization_id),
                    "organization": "Northstar Studio",
                    "role": OrgMembership.Role.ADMIN,
                }
            ],
        )

    def test_duplicate_workspace_name_never_grants_existing_membership(self):
        organization = Organization.objects.create(name="Northstar Studio")
        OrgMembership.objects.create(
            user=self.user,
            organization=organization,
            role=OrgMembership.Role.VIEWER,
        )
        other_user = User.objects.create_user(
            username=f"other-{uuid.uuid4().hex[:8]}",
            email=f"other-{uuid.uuid4().hex[:8]}@example.com",
            password="Abc!12345",
        )
        other_client = APIClient(enforce_csrf_checks=True)
        other_client.force_login(other_user)
        csrf = other_client.get("/api/auth/csrf/").json()["csrfToken"]

        response = other_client.post(
            "/api/auth/organizations/",
            {"name": organization.name},
            format="json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        self.assertEqual(response.status_code, 409)
        self.assertFalse(OrgMembership.objects.filter(user=other_user).exists())
        self.assertEqual(
            OrgMembership.objects.filter(organization=organization).count(),
            1,
        )

    def test_workspace_and_initial_membership_roll_back_together(self):
        with patch(
            "apps.accounts.views.OrgMembership.objects.create",
            side_effect=IntegrityError("injected membership write failure"),
        ):
            response = self.create_workspace("Orphan Guard")

        self.assertEqual(response.status_code, 503)
        self.assertFalse(Organization.objects.filter(name="Orphan Guard").exists())

    def test_workspace_creation_requires_authenticated_dashboard_session(self):
        anonymous = APIClient(enforce_csrf_checks=True)
        anonymous.get("/api/auth/csrf/")
        response = anonymous.post(
            "/api/auth/organizations/",
            {"name": "Northstar Studio"},
            format="json",
        )

        self.assertEqual(response.status_code, 401)
        self.assertFalse(Organization.objects.filter(name="Northstar Studio").exists())

    def test_signup_cannot_self_assign_to_an_existing_organization(self):
        organization = Organization.objects.create(name="Northstar Studio")
        email = f"signup-{uuid.uuid4().hex[:8]}@example.com"

        response = APIClient().post(
            f"{HEADLESS_BASE}/auth/signup",
            {
                "email": email,
                "password": "Abc!12345",
                "organization": organization.name,
            },
            format="json",
        )

        self.assertIn(response.status_code, (200, 201, 401))
        signed_up_user = User.objects.get(email=email)
        self.assertFalse(OrgMembership.objects.filter(user=signed_up_user).exists())
        self.assertEqual(
            OrgMembership.objects.filter(organization=organization).count(),
            0,
        )
