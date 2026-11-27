from django.contrib import admin
from import_export import resources
from import_export.admin import ImportExportModelAdmin

from .models import Video


class VideoResource(resources.ModelResource):
    """
    Defines which video fields are exported to and imported from files like CSV or Excel.

    The file fields only contain the path inside the media folder, the video
    files themselves are not part of the export.
    """

    class Meta:
        model = Video
        fields = ["id", "title", "description", "category", "video_file", "thumbnail", "created_at"]
        export_order = fields


@admin.register(Video)
class VideoAdmin(ImportExportModelAdmin):
    """Admin view for uploading and managing videos, with import and export buttons."""

    resource_classes = [VideoResource]
    list_display = ["title", "category", "created_at"]
    list_filter = ["category"]
    search_fields = ["title", "description"]
