from pathlib import Path
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.test import TestCase

from video_app.models import Video
from video_app.utils import RESOLUTIONS, build_hls_command, process_video

from .helpers import create_hls_file, create_video, isolated_media_and_cache, remove_temp_media_root


def tearDownModule() -> None:
    """Remove the temporary media folder after all tests of this file."""
    remove_temp_media_root()


@isolated_media_and_cache
@patch("video_app.signals.django_rq.get_queue")
class VideoSignalTests(TestCase):
    """Tests for the signals that start the conversion and clean up files."""

    def test_new_video_queues_processing(self, mock_get_queue: MagicMock) -> None:
        """Uploading a new video puts process_video into the 'default' queue."""
        with self.captureOnCommitCallbacks(execute=True):
            video = create_video()
        mock_get_queue.assert_called_once_with("default", autocommit=True)
        mock_queue = mock_get_queue.return_value
        mock_queue.enqueue.assert_called_once_with(process_video, video.pk, job_timeout=3600)

    def test_updating_video_does_not_queue_processing(self, mock_get_queue: MagicMock) -> None:
        """Changing an existing video does not start a new conversion."""
        video = create_video()
        mock_get_queue.reset_mock()
        with self.captureOnCommitCallbacks(execute=True):
            video.title = "New Title"
            video.save()
        mock_get_queue.assert_not_called()

    def test_deleting_video_removes_all_files(self, mock_get_queue: MagicMock) -> None:
        """Deleting a video removes the original file, the thumbnail and the HLS folder."""
        video = create_video()
        video_path = Path(video.video_file.path)
        thumbnail_name = f"thumbnails/{video.pk}.jpg"
        thumbnail_path = Path(settings.MEDIA_ROOT) / thumbnail_name
        thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
        thumbnail_path.write_bytes(b"image")
        Video.objects.filter(pk=video.pk).update(thumbnail=thumbnail_name)
        hls_file = create_hls_file(video.pk, "480p", "index.m3u8", b"#EXTM3U")
        Video.objects.get(pk=video.pk).delete()
        for path in [video_path, thumbnail_path, hls_file.parent.parent]:
            self.assertFalse(path.exists())


@isolated_media_and_cache
@patch("video_app.signals.django_rq.get_queue")
@patch("video_app.utils.subprocess.run")
class ProcessVideoTests(TestCase):
    """
    Tests for the background job process_video.

    subprocess.run is replaced by a mock, so FFmpeg is not really executed.
    The tests only check that the right commands are started.
    """

    def test_process_video_creates_thumbnail_and_all_resolutions(
        self, mock_run: MagicMock, mock_get_queue: MagicMock
    ) -> None:
        """FFmpeg runs once for the thumbnail and once for every resolution."""
        video = create_video()
        process_video(video.pk)
        self.assertEqual(mock_run.call_count, 1 + len(RESOLUTIONS))
        video.refresh_from_db()
        self.assertEqual(video.thumbnail.name, f"thumbnails/{video.pk}.jpg")

    def test_process_video_keeps_uploaded_thumbnail(
        self, mock_run: MagicMock, mock_get_queue: MagicMock
    ) -> None:
        """An uploaded thumbnail is not replaced, only the HLS files are created."""
        video = create_video()
        Video.objects.filter(pk=video.pk).update(thumbnail="thumbnails/custom.jpg")
        process_video(video.pk)
        self.assertEqual(mock_run.call_count, len(RESOLUTIONS))
        video.refresh_from_db()
        self.assertEqual(video.thumbnail.name, "thumbnails/custom.jpg")

    def test_build_hls_command_contains_course_options(
        self, mock_run: MagicMock, mock_get_queue: MagicMock
    ) -> None:
        """The FFmpeg command scales the video and uses the HLS options from the course."""
        command = build_hls_command("input.mp4", Path("/output"), 720)
        self.assertIn("scale=-2:720", command)
        for option in ["-start_number", "-hls_time", "-hls_list_size", "-f"]:
            self.assertIn(option, command)
        self.assertEqual(command[-1], str(Path("/output") / "index.m3u8"))
