from collections.abc import Callable
from typing import Any

from django.contrib.auth.models import User

TEST_EMAIL = "user@example.com"
TEST_PASSWORD = "SecurePassword123"


def create_user(email: str = TEST_EMAIL, password: str = TEST_PASSWORD, is_active: bool = True) -> User:
    """
    Create a user the same way the registration does (email as username).

    Most tests need an already activated user, so is_active is True by default.
    """
    return User.objects.create_user(username=email, email=email, password=password, is_active=is_active)


def run_job_immediately(func: Callable, *args: Any, **kwargs: Any) -> Any:
    """
    Replacement for django_rq.enqueue in tests.

    Instead of putting the job into Redis, the function is executed directly.
    This way the emails end up in Django's test outbox (mail.outbox) and the
    tests do not need a running RQ worker.
    """
    return func(*args)
