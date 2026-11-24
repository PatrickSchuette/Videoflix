import shutil
import tempfile
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from video_app.models import Video
from video_app.utils import get_hls_directory

TEMP_MEDIA_ROOT = tempfile.mkdtemp()
LOCAL_MEMORY_CACHE = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

isolated_media_and_cache = override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT, CACHES=LOCAL_MEMORY_CACHE)


def create_video(title: str = "Test Movie", category: str = "Drama") -> Video:
    """
    Create a video with a small fake video file.

    The file only contains a few bytes, because the tests never run the real
    FFmpeg conversion. It is saved in the temporary media folder.
    """
    fake_file = SimpleUploadedFile("test.mp4", b"fake video content", content_type="video/mp4")
    return Video.objects.create(
        title=title, description="A test description", category=category, video_file=fake_file
    )


def create_hls_file(video_id: int, resolution: str, filename: str, content: bytes) -> Path:
    """Write a fake HLS file (playlist or segment) into the temporary media folder."""
    folder = get_hls_directory(video_id, resolution)
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / filename
    file_path.write_bytes(content)
    return file_path


def remove_temp_media_root() -> None:
    """Delete the temporary media folder, so the tests leave no files behind."""
    shutil.rmtree(TEMP_MEDIA_ROOT, ignore_errors=True)
