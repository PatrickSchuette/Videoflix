from django.contrib.auth.tokens import default_token_generator
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from .serializers import RegistrationSerializer
from .utils import queue_activation_email

GENERIC_ERROR = {"detail": "Please check your input and try again."}


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
