from unittest.mock import MagicMock, patch

from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from auth_app.api.utils import encode_user_id

from .helpers import TEST_EMAIL, create_user, run_job_immediately

NEW_PASSWORD = "BrandNewPassword123"


@patch("auth_app.api.utils.django_rq.enqueue", side_effect=run_job_immediately)
class PasswordResetTests(APITestCase):
    """Tests for POST /api/password_reset/."""

    def setUp(self) -> None:
        """Create an active user and prepare the reset URL."""
        self.user = create_user()
        self.url = reverse("password_reset")

    def test_reset_sends_email_to_existing_user(self, mock_enqueue: MagicMock) -> None:
        """For an existing active user a reset email with the correct link is sent."""
        response = self.client.post(self.url, {"email": TEST_EMAIL}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)
        html_content = mail.outbox[0].alternatives[0][0]
        self.assertIn(f"confirm_password.html?uid={encode_user_id(self.user)}", html_content)

    def test_reset_for_unknown_email_sends_no_email(self, mock_enqueue: MagicMock) -> None:
        """An unknown email returns the same 200 response, but no email is sent."""
        response = self.client.post(self.url, {"email": "unknown@example.com"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 0)

    def test_reset_for_inactive_user_sends_no_email(self, mock_enqueue: MagicMock) -> None:
        """Inactive users do not get a reset email."""
        self.user.is_active = False
        self.user.save()
        self.client.post(self.url, {"email": TEST_EMAIL}, format="json")
        self.assertEqual(len(mail.outbox), 0)

    def test_reset_with_invalid_email_fails(self, mock_enqueue: MagicMock) -> None:
        """A value that is not an email address returns 400."""
        response = self.client.post(self.url, {"email": "no-email"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class PasswordConfirmTests(APITestCase):
    """Tests for POST /api/password_confirm/<uidb64>/<token>/."""

    def setUp(self) -> None:
        """Create an active user and a valid password reset link."""
        self.user = create_user()
        token = default_token_generator.make_token(self.user)
        kwargs = {"uidb64": encode_user_id(self.user), "token": token}
        self.url = reverse("password_confirm", kwargs=kwargs)
        self.data = {"new_password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD}

    def test_confirm_sets_new_password(self) -> None:
        """A valid link and matching passwords change the password."""
        response = self.client.post(self.url, self.data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))

    def test_confirm_link_can_only_be_used_once(self) -> None:
        """After a successful reset the same link is no longer valid."""
        self.client.post(self.url, self.data, format="json")
        response = self.client.post(self.url, self.data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_confirm_with_different_passwords_fails(self) -> None:
        """Different values in both password fields return 400."""
        self.data["confirm_password"] = "AnotherPassword123"
        response = self.client.post(self.url, self.data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertFalse(self.user.check_password(NEW_PASSWORD))

    def test_confirm_with_invalid_token_fails(self) -> None:
        """A manipulated token returns 400."""
        kwargs = {"uidb64": encode_user_id(self.user), "token": "invalid-token"}
        url = reverse("password_confirm", kwargs=kwargs)
        response = self.client.post(url, self.data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
