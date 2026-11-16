from django.contrib.auth.models import User
from rest_framework import serializers
from django.contrib.auth import authenticate


class RegistrationSerializer(serializers.Serializer):
    """
    Validates the registration data sent by the frontend and creates a new user.

    The user is created inactive and must confirm the email address before the
    first login. The email address is also used as the username, because the
    default Django user model requires a unique username.
    """

    email = serializers.EmailField(max_length=150)
    password = serializers.CharField(write_only=True, min_length=8)
    confirmed_password = serializers.CharField(write_only=True)

    def validate_email(self, value: str) -> str:
        """
        Ensure that the email address is not registered yet.

        The check is case-insensitive and the address is stored in lowercase,
        so 'Max@Mail.de' and 'max@mail.de' count as the same user.
        """
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Email already in use.")
        return value.lower()

    def validate(self, attrs: dict) -> dict:
        """Ensure that 'password' and 'confirmed_password' contain the same value."""
        if attrs["password"] != attrs["confirmed_password"]:
            raise serializers.ValidationError("Passwords do not match.")
        return attrs

    def create(self, validated_data: dict) -> User:
        """Create and return a new inactive user with a hashed password."""
        email = validated_data["email"]
        return User.objects.create_user(
            username=email,
            email=email,
            password=validated_data["password"],
            is_active=False,
        )


class LoginSerializer(serializers.Serializer):
    """
    Validates the login data and checks the credentials.
    """

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs: dict) -> dict:
        """
        Authenticate the user with email and password.
        """
        user = authenticate(
            username=attrs["email"].lower(), password=attrs["password"])
        if user is None:
            raise serializers.ValidationError("Invalid credentials.")
        attrs["user"] = user
        return attrs


class PasswordResetSerializer(serializers.Serializer):
    """Validates that the password reset request contains a valid email address."""

    email = serializers.EmailField()


class PasswordConfirmSerializer(serializers.Serializer):
    """
    Validates the new password sent from the reset password page.

    Both fields must match and the password needs at least 8 characters,
    the same rule as during registration.
    """

    new_password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs: dict) -> dict:
        """Ensure that 'new_password' and 'confirm_password' contain the same value."""
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError("Passwords do not match.")
        return attrs
