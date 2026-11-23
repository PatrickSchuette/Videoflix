from rest_framework import serializers

from video_app.models import Video


class VideoSerializer(serializers.ModelSerializer):
    """Converts a video into the JSON format the frontend expects."""

    thumbnail_url = serializers.SerializerMethodField()

    class Meta:
        model = Video
        fields = ["id", "created_at", "title",
                  "description", "thumbnail_url", "category"]

    def get_thumbnail_url(self, obj: Video) -> str | None:
        """Return the absolute URL of the thumbnail, or None if it was not created yet."""
        if not obj.thumbnail:
            return None
        return self.context["request"].build_absolute_uri(obj.thumbnail.url)
