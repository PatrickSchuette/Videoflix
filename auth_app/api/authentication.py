from rest_framework.request import Request
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import Token

from django.contrib.auth.models import User


class CookieJWTAuthentication(JWTAuthentication):
    """
    Authenticates API requests with the JWT access token from the HttpOnly cookie.

    simple jwt normally expects the token in the 'Authorization' header. The token is read directly from
    the 'access_token' cookie that the browser sends with every request.
    """

    def authenticate(self, request: Request) -> tuple[User, Token] | None:
        """Return the user and the validated token, or None if no cookie is present."""
        raw_token = request.COOKIES.get("access_token")
        if raw_token is None:
            return None
        validated_token = self.get_validated_token(raw_token)
        return self.get_user(validated_token), validated_token
