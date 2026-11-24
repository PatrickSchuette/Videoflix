from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from auth_app.api.utils import encode_user_id

from .helpers import TEST_EMAIL, TEST_PASSWORD, create_user, run_job_immediately


@patch("auth_app.api.utils.django_rq.enqueue", side_effect=run_job_immediately)
class RegistrationTests(APITestCase):
    """Tests for POST /api/register/."""

    def setUp(self) -> None:
        """Prepare the URL and valid registration data for every test."""
        self.url = reverse("register")
        self.data = {
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
            "confirmed_password": TEST_PASSWORD,
        }

    def test_register_creates_inactive_user(self, mock_enqueue: MagicMock) -> None:
        """A successful registration returns 201 and creates an inactive user."""
        response = self.client.post(self.url, self.data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(email=TEST_EMAIL)
        self.assertFalse(user.is_active)
        self.assertEqual(user.username, TEST_EMAIL)

    def test_register_returns_user_and_token(self, mock_enqueue: MagicMock) -> None:
        """The response contains the user id, the email and an activation token."""
        response = self.client.post(self.url, self.data, format="json")
        self.assertEqual(response.data["user"]["email"], TEST_EMAIL)
        self.assertIn("id", response.data["user"])
        self.assertTrue(response.data["token"])

    def test_register_sends_activation_email(self, mock_enqueue: MagicMock) -> None:
        """After registration exactly one activation email with the correct link is sent."""
        response = self.client.post(self.url, self.data, format="json")
        user = User.objects.get(email=TEST_EMAIL)
        self.assertEqual(len(mail.outbox), 1)
        html_content = mail.outbox[0].alternatives[0][0]
        self.assertIn(f"activate.html?uid={encode_user_id(user)}", html_content)
        self.assertIn(response.data["token"], html_content)

    def test_register_stores_email_in_lowercase(self, mock_enqueue: MagicMock) -> None:
        """Email addresses are stored in lowercase, so the login is case-insensitive."""
        self.data["email"] = "User@Example.COM"
        self.client.post(self.url, self.data, format="json")
        self.assertTrue(User.objects.filter(email=TEST_EMAIL).exists())

    def test_register_with_existing_email_fails(self, mock_enqueue: MagicMock) -> None:
        """An already used email address leads to a generic 400 error."""
        create_user()
        response = self.client.post(self.url, self.data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], "Please check your input and try again.")

    def test_register_with_different_passwords_fails(self, mock_enqueue: MagicMock) -> None:
        """Different values in password and confirmed_password lead to a 400 error."""
        self.data["confirmed_password"] = "AnotherPassword123"
        response = self.client.post(self.url, self.data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.exists())

    def test_register_with_short_password_fails(self, mock_enqueue: MagicMock) -> None:
        """Passwords with less than 8 characters are rejected."""
        self.data["password"] = self.data["confirmed_password"] = "short"
        response = self.client.post(self.url, self.data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class ActivationTests(APITestCase):
    """Tests for GET /api/activate/<uidb64>/<token>/."""

    def setUp(self) -> None:
        """Create an inactive user and a valid activation token for every test."""
        self.user = create_user(is_active=False)
        self.uidb64 = encode_user_id(self.user)
        self.token = default_token_generator.make_token(self.user)

    def get_activation_url(self, uidb64: str, token: str) -> str:
        """Return the activation URL for the given uid and token."""
        return reverse("activate", kwargs={"uidb64": uidb64, "token": token})

    def test_activation_with_valid_link_activates_user(self) -> None:
        """A valid uid and token activate the account and return 200."""
        response = self.client.get(self.get_activation_url(self.uidb64, self.token))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["message"], "Account successfully activated.")
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

    def test_activation_with_invalid_token_fails(self) -> None:
        """A manipulated token returns 400 and the user stays inactive."""
        response = self.client.get(self.get_activation_url(self.uidb64, "invalid-token"))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

    def test_activation_with_invalid_uid_fails(self) -> None:
        """A uid that does not belong to any user returns 400."""
        response = self.client.get(self.get_activation_url("invalid", self.token))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
