from django.db import models


class Video(models.Model):
    """
    A movie that can be streamed on Videoflix.

    The original upload is stored in 'video_file'. After the upload a
    background job creates the thumbnail and the HLS files for the
    resolutions 480p, 720p and 1080p.
    """

    CATEGORY_CHOICES = [
        ("Action", "Action"),
        ("Comedy", "Comedy"),
        ("Documentary", "Documentary"),
        ("Drama", "Drama"),
        ("Romance", "Romance"),
        ("Sci-Fi", "Sci-Fi"),
    ]

    created_at = models.DateTimeField(auto_now_add=True)
    title = models.CharField(max_length=100)
    description = models.TextField()
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    video_file = models.FileField(upload_to="videos/")
    thumbnail = models.FileField(upload_to="thumbnails/", blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        """Return the title, so the admin shows a readable name for each video."""
        return self.title
