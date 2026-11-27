from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework.test import APITestCase

from .helpers import TEST_EMAIL, TEST_PASSWORD, create_user


class PasswordHashingTests(APITestCase):
    """Tests that passwords are stored with Argon2id and old hashes are upgraded."""

    def test_new_password_is_hashed_with_argon2id(self) -> None:
        """A newly created user gets an Argon2id hash with its own salt."""
        user = create_user()
        self.assertTrue(user.password.startswith("argon2$argon2id$"))
        self.assertNotIn(TEST_PASSWORD, user.password)

    def test_same_password_gets_different_hashes(self) -> None:
        """Thanks to the random salt, two users with the same password have different hashes."""
        first_user = create_user(email="first@example.com")
        second_user = create_user(email="second@example.com")
        self.assertNotEqual(first_user.password, second_user.password)

    def test_old_pbkdf2_hash_is_upgraded_on_login(self) -> None:
        """A password stored with PBKDF2 is converted to Argon2id at the next login."""
        user = create_user()
        User.objects.filter(pk=user.pk).update(
            password=make_password(TEST_PASSWORD, hasher="pbkdf2_sha256"))
        login_data = {"email": TEST_EMAIL, "password": TEST_PASSWORD}
        self.client.post(reverse("login"), login_data, format="json")
        user.refresh_from_db()
        self.assertTrue(user.password.startswith("argon2$argon2id$"))
