from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken

from .helpers import TEST_EMAIL, TEST_PASSWORD, create_user


class LoginTests(APITestCase):
    """Tests for POST /api/login/."""

    def setUp(self) -> None:
        """Create an active user and prepare the login URL and data."""
        self.user = create_user()
        self.url = reverse("login")
        self.data = {"email": TEST_EMAIL, "password": TEST_PASSWORD}

    def test_login_returns_user_data(self) -> None:
        """A successful login returns 200 with the user id and username."""
        response = self.client.post(self.url, self.data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["detail"], "Login successful")
        self.assertEqual(response.data["user"], {"id": self.user.id, "username": TEST_EMAIL})

    def test_login_sets_httponly_cookies(self) -> None:
        """The JWT tokens are set as HttpOnly cookies and not sent in the body."""
        response = self.client.post(self.url, self.data, format="json")
        for cookie_name in ["access_token", "refresh_token"]:
            self.assertIn(cookie_name, response.cookies)
            self.assertTrue(response.cookies[cookie_name]["httponly"])
            self.assertNotIn(cookie_name, response.data)

    def test_login_is_case_insensitive_for_email(self) -> None:
        """The email address can be written in upper case letters."""
        self.data["email"] = "USER@Example.com"
        response = self.client.post(self.url, self.data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_login_with_wrong_password_fails(self) -> None:
        """A wrong password returns a generic 400 error without cookies."""
        self.data["password"] = "WrongPassword123"
        response = self.client.post(self.url, self.data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], "Please check your input and try again.")
        self.assertNotIn("access_token", response.cookies)

    def test_login_with_inactive_user_fails(self) -> None:
        """A user who has not activated the account cannot log in."""
        self.user.is_active = False
        self.user.save()
        response = self.client.post(self.url, self.data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_updates_last_login(self) -> None:
        """A successful login stores the login time on the user."""
        self.client.post(self.url, self.data, format="json")
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.last_login)


class LoggedInTestCase(APITestCase):
    """
    Base class for tests that need a logged-in user.

    The login endpoint is called in setUp, so the test client already has
    the access_token and refresh_token cookies for every test.
    """

    def setUp(self) -> None:
        """Create an active user and log in to get the JWT cookies."""
        self.user = create_user()
        login_data = {"email": TEST_EMAIL, "password": TEST_PASSWORD}
        self.client.post(reverse("login"), login_data, format="json")


class LogoutTests(LoggedInTestCase):
    """Tests for POST /api/logout/."""

    def test_logout_deletes_cookies(self) -> None:
        """A successful logout returns 200 and empties both JWT cookies."""
        response = self.client.post(reverse("logout"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.cookies["access_token"].value, "")
        self.assertEqual(response.cookies["refresh_token"].value, "")

    def test_logout_blacklists_refresh_token(self) -> None:
        """After the logout the refresh token is on the blacklist."""
        self.client.post(reverse("logout"))
        self.assertEqual(BlacklistedToken.objects.count(), 1)

    def test_logout_without_refresh_token_fails(self) -> None:
        """Without the refresh_token cookie the logout returns 400."""
        del self.client.cookies["refresh_token"]
        response = self.client.post(reverse("logout"))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class TokenRefreshTests(LoggedInTestCase):
    """Tests for POST /api/token/refresh/."""

    def test_refresh_sets_new_access_cookie(self) -> None:
        """A valid refresh token returns 200 and sets a new access_token cookie."""
        response = self.client.post(reverse("token_refresh"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["detail"], "Token refreshed")
        self.assertIn("access_token", response.cookies)

    def test_refresh_without_cookie_fails(self) -> None:
        """Without the refresh_token cookie the refresh returns 400."""
        del self.client.cookies["refresh_token"]
        response = self.client.post(reverse("token_refresh"))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_refresh_with_invalid_token_fails(self) -> None:
        """A manipulated refresh token returns 401."""
        self.client.cookies["refresh_token"] = "invalid-token"
        response = self.client.post(reverse("token_refresh"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_after_logout_fails(self) -> None:
        """A blacklisted refresh token can no longer be used for a refresh."""
        refresh_token = self.client.cookies["refresh_token"].value
        self.client.post(reverse("logout"))
        self.client.cookies["refresh_token"] = refresh_token
        response = self.client.post(reverse("token_refresh"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
