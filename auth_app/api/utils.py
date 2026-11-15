import django_rq
from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes, force_str
from django.utils.html import strip_tags
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_encode, urlsafe_base64_decode
from datetime import datetime, timedelta
from rest_framework.response import Response
from rest_framework_simplejwt.settings import api_settings as jwt_settings
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from django.utils import timezone


def encode_user_id(user: User) -> str:
    """Return the primary key of the user as a URL-safe base64 string (uidb64)."""
    return urlsafe_base64_encode(force_bytes(user.pk))


def build_frontend_link(page: str, uidb64: str, token: str) -> str:
    """
    Build a link to a page of the frontend's auth folder.

    The uid and token are attached as query parameters, because the frontend
    reads them from the URL and forwards them to the backend.
    """
    return f"{settings.FRONTEND_URL}/pages/auth/{page}?uid={uidb64}&token={token}"


def send_html_email(subject: str, template_name: str, context: dict, recipient: str) -> None:
    """
    Render an HTML email template and send it to a single recipient.

    A plain-text version is generated from the HTML as a fallback for email
    clients that cannot display HTML. This function runs inside the RQ worker.
    """
    html_content = render_to_string(template_name, context)
    text_content = strip_tags(html_content)
    email = EmailMultiAlternatives(subject, text_content, settings.DEFAULT_FROM_EMAIL, [recipient])
    email.attach_alternative(html_content, "text/html")
    email.send()


def get_token_expiry() -> datetime:
    """
    Return the date and time at which a token created right now will expire.

    Ceck only their age against the PASSWORD_RESET_TIMEOUT setting (default: 3 days), so the expiry date is
    calculated the same way.
    """
    return timezone.now() + timedelta(seconds=settings.PASSWORD_RESET_TIMEOUT)

def queue_activation_email(user: User, token: str) -> None:
    """
    Put the account activation email for the given user into the background queue.

    The request returns immediately, while the RQ worker sends the email.
    """
    link = build_frontend_link("activate.html", encode_user_id(user), token)
    context = {"user_name": user.email, "activation_link": link, "expiry_date": get_token_expiry()}
    django_rq.enqueue(send_html_email, "Confirm your email", "auth_app/activation_email.html", context, user.email)


def get_user_from_uid(uidb64: str) -> User | None:
    """
    Decode the uidb64 from an email link and return the matching user.

    Returns None if the value is not valid base64 or no user with this id
    exists, so the caller only has to check for None.
    """
    try:
        user_id = force_str(urlsafe_base64_decode(uidb64))
        return User.objects.get(pk=user_id)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return None


def set_jwt_cookie(response: Response, name: str, token: str, lifetime: timedelta) -> None:
    """Store a JWT token as an HttpOnly cookie on the given response."""
    response.set_cookie(
        key=name,
        value=token,
        max_age=int(lifetime.total_seconds()),
        httponly=True,
        secure=not settings.DEBUG,
        samesite="Lax",
    )


def set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    """Store the access token and the refresh token as HttpOnly cookies."""
    set_jwt_cookie(response, "access_token", access_token, jwt_settings.ACCESS_TOKEN_LIFETIME)
    set_jwt_cookie(response, "refresh_token", refresh_token, jwt_settings.REFRESH_TOKEN_LIFETIME)


def set_access_cookie(response: Response, access_token: str) -> None:
    """Store only a new access token as an HttpOnly cookie, used after a token refresh."""
    set_jwt_cookie(response, "access_token", access_token, jwt_settings.ACCESS_TOKEN_LIFETIME)


def delete_auth_cookies(response: Response) -> None:
    """Remove the access token and refresh token cookies from the browser."""
    response.delete_cookie("access_token", samesite="Lax")
    response.delete_cookie("refresh_token", samesite="Lax")


def blacklist_refresh_token(refresh_token: str) -> None:
    """Put the given refresh token on the blacklist, so it can never be used again."""
    try:
        RefreshToken(refresh_token).blacklist()
    except TokenError:
        pass
