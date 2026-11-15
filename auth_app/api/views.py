from django.contrib.auth.tokens import default_token_generator
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from django.contrib.auth.models import update_last_login
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import RegistrationSerializer, LoginSerializer
from .utils import queue_activation_email, encode_user_id, build_frontend_link, get_user_from_uid, set_auth_cookies, blacklist_refresh_token, delete_auth_cookies, set_access_cookie

GENERIC_ERROR = {"detail": "Please check your input and try again."}
MISSING_REFRESH_TOKEN = {"detail": "Refresh token missing."}

class RegistrationView(generics.GenericAPIView):
    """
    POST /api/register/

    Creates a new inactive user and sends an activation email in the background.
    Error messages are kept generic for security reasons, so nobody can find out
    which email addresses are already registered.
    """

    serializer_class = RegistrationSerializer
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        """Validate the input, create the user and queue the activation email."""
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response(GENERIC_ERROR, status=status.HTTP_400_BAD_REQUEST)
        user = serializer.save()
        token = default_token_generator.make_token(user)
        queue_activation_email(user, token)
        response_data = {"user": {"id": user.id, "email": user.email}, "token": token}
        return Response(response_data, status=status.HTTP_201_CREATED)
    

class ActivateAccountView(APIView):
    """
    GET /api/activate/<uidb64>/<token>/

    Activates a user account with the uid and token from the activation email.
    The frontend calls this endpoint after the user clicked the link in the email.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request: Request, uidb64: str, token: str) -> Response:
        """Check uid and token and set the user to active if both are valid."""
        user = get_user_from_uid(uidb64)
        if user is None or not default_token_generator.check_token(user, token):
            return Response({"message": "Activation failed."}, status=status.HTTP_400_BAD_REQUEST)
        user.is_active = True
        user.save(update_fields=["is_active"])
        return Response({"message": "Account successfully activated."}, status=status.HTTP_200_OK)


class LoginView(generics.GenericAPIView):
    """
    POST /api/login/

    Authenticates the user with email and password. On success the JWT access
    and refresh tokens are set as HttpOnly cookies instead of being returned
    in the response body.
    """

    serializer_class = LoginSerializer
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        """Check the credentials, create JWT tokens and store them as cookies."""
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response(GENERIC_ERROR, status=status.HTTP_400_BAD_REQUEST)
        user = serializer.validated_data["user"]
        update_last_login(None, user)
        refresh = RefreshToken.for_user(user)
        response_data = {"detail": "Login successful", "user": {"id": user.id, "username": user.email}}
        response = Response(response_data, status=status.HTTP_200_OK)
        set_auth_cookies(response, str(refresh.access_token), str(refresh))
        return response


class LogoutView(APIView):
    """
    POST /api/logout/

    Logs the user out by putting the refresh token on the blacklist and
    deleting both JWT cookies. Requires the refresh_token cookie.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        """Blacklist the refresh token from the cookie and delete all auth cookies."""
        refresh_token = request.COOKIES.get("refresh_token")
        if refresh_token is None:
            return Response(MISSING_REFRESH_TOKEN, status=status.HTTP_400_BAD_REQUEST)
        blacklist_refresh_token(refresh_token)
        response_data = {
            "detail": "Logout successful! All tokens will be deleted. Refresh token is now invalid."
        }
        response = Response(response_data, status=status.HTTP_200_OK)
        delete_auth_cookies(response)
        return response


class TokenRefreshView(APIView):
    """
    POST /api/token/refresh/

    Issues a new access token when the old one has expired. The refresh token
    is read from the HttpOnly cookie and the new access token is set as a cookie.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        """Validate the refresh token from the cookie and set a new access token cookie."""
        refresh_token = request.COOKIES.get("refresh_token")
        if refresh_token is None:
            return Response(MISSING_REFRESH_TOKEN, status=status.HTTP_400_BAD_REQUEST)
        try:
            refresh = RefreshToken(refresh_token)
        except TokenError:
            return Response({"detail": "Invalid refresh token."}, status=status.HTTP_401_UNAUTHORIZED)
        access_token = str(refresh.access_token)
        response = Response({"detail": "Token refreshed", "access": access_token}, status=status.HTTP_200_OK)
        set_access_cookie(response, access_token)
        return response
