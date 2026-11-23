from django.apps import AppConfig


class VideoAppConfig(AppConfig):
    """Configuration of the video app, which also registers its signal handlers."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "video_app"

    def ready(self) -> None:
        """Import the signal handlers, so Django connects them when the app starts."""
        from . import signals
