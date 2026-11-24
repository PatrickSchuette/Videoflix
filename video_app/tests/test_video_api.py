from django.http import FileResponse
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from auth_app.tests.helpers import create_user
from video_app.models import Video

from .helpers import create_hls_file, create_video, isolated_media_and_cache, remove_temp_media_root


def tearDownModule() -> None:
    """Remove the temporary media folder after all tests of this file."""
    remove_temp_media_root()


class VideoApiTestCase(APITestCase):
    """
    Base class for all video endpoint tests.

    Logs the user in by setting the access_token cookie directly, the same
    cookie the login endpoint would set.
    """

    def setUp(self) -> None:
        """Create a user and store a valid access token in the cookie."""
        self.user = create_user()
        self.client.cookies["access_token"] = str(AccessToken.for_user(self.user))

    def get_file_content(self, response: FileResponse) -> bytes:
        """
        Read the complete content of a FileResponse.

        Django streams files in chunks, so the chunks are joined together.
        The file is closed automatically once all chunks have been read.
        """
        return b"".join(response.streaming_content)


@isolated_media_and_cache
class VideoListTests(VideoApiTestCase):
    """Tests for GET /api/video/."""

    def test_video_list_requires_login(self) -> None:
        """Without the access_token cookie the endpoint returns 401."""
        del self.client.cookies["access_token"]
        response = self.client.get(reverse("video_list"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_video_list_with_invalid_token_fails(self) -> None:
        """A manipulated access token returns 401."""
        self.client.cookies["access_token"] = "invalid-token"
        response = self.client.get(reverse("video_list"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_video_list_returns_expected_fields(self) -> None:
        """Every video contains exactly the fields from the endpoint documentation."""
        create_video()
        response = self.client.get(reverse("video_list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        expected_fields = {"id", "created_at", "title", "description", "thumbnail_url", "category"}
        self.assertEqual(set(response.data[0].keys()), expected_fields)

    def test_video_list_is_sorted_newest_first(self) -> None:
        """The newest video is the first one in the list."""
        create_video(title="Old Movie")
        create_video(title="New Movie")
        response = self.client.get(reverse("video_list"))
        titles = [video["title"] for video in response.data]
        self.assertEqual(titles, ["New Movie", "Old Movie"])

    def test_thumbnail_url_is_absolute(self) -> None:
        """The thumbnail URL contains the full address, so the frontend can load it."""
        video = create_video()
        Video.objects.filter(pk=video.pk).update(thumbnail=f"thumbnails/{video.pk}.jpg")
        response = self.client.get(reverse("video_list"))
        expected_url = f"http://testserver/media/thumbnails/{video.pk}.jpg"
        self.assertEqual(response.data[0]["thumbnail_url"], expected_url)

    def test_thumbnail_url_is_none_without_thumbnail(self) -> None:
        """As long as no thumbnail exists, thumbnail_url is None."""
        create_video()
        response = self.client.get(reverse("video_list"))
        self.assertIsNone(response.data[0]["thumbnail_url"])

    def test_video_list_is_served_from_cache(self) -> None:
        """
        A second request returns the cached list.

        update() changes the database without sending a signal, so the cache
        is not cleared and the old title must still be returned.
        """
        video = create_video(title="Cached Title")
        self.client.get(reverse("video_list"))
        Video.objects.filter(pk=video.pk).update(title="Changed Title")
        response = self.client.get(reverse("video_list"))
        self.assertEqual(response.data[0]["title"], "Cached Title")

    def test_cache_is_cleared_when_video_is_saved(self) -> None:
        """Saving a video clears the cache, so the list shows the new title."""
        video = create_video(title="Old Title")
        self.client.get(reverse("video_list"))
        video.title = "New Title"
        video.save()
        response = self.client.get(reverse("video_list"))
        self.assertEqual(response.data[0]["title"], "New Title")


@isolated_media_and_cache
class HLSEndpointTests(VideoApiTestCase):
    """Tests for the HLS playlist and segment endpoints."""

    def setUp(self) -> None:
        """Log in and create a video with a fake playlist and segment in 480p."""
        super().setUp()
        self.video = create_video()
        create_hls_file(self.video.pk, "480p", "index.m3u8", b"#EXTM3U")
        create_hls_file(self.video.pk, "480p", "000.ts", b"segment data")

    def get_playlist_url(self, resolution: str = "480p") -> str:
        """Return the playlist URL of the test video for the given resolution."""
        return reverse("video_playlist", kwargs={"movie_id": self.video.pk, "resolution": resolution})

    def get_segment_url(self, segment: str = "000.ts") -> str:
        """Return the URL of a segment of the test video in 480p."""
        kwargs = {"movie_id": self.video.pk, "resolution": "480p", "segment": segment}
        return reverse("video_segment", kwargs=kwargs)

    def test_playlist_is_returned(self) -> None:
        """The playlist is returned with the HLS content type."""
        response = self.client.get(self.get_playlist_url())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "application/vnd.apple.mpegurl")
        self.assertEqual(self.get_file_content(response), b"#EXTM3U")

    def test_playlist_for_missing_resolution_returns_404(self) -> None:
        """A resolution without converted files returns 404."""
        response = self.client.get(self.get_playlist_url("720p"))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_playlist_for_unknown_resolution_returns_404(self) -> None:
        """A resolution that is not offered at all returns 404."""
        response = self.client.get(self.get_playlist_url("999p"))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_segment_is_returned(self) -> None:
        """A segment is returned with the MPEG-TS content type."""
        response = self.client.get(self.get_segment_url())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "video/MP2T")
        self.assertEqual(self.get_file_content(response), b"segment data")

    def test_missing_segment_returns_404(self) -> None:
        """A segment that does not exist returns 404."""
        response = self.client.get(self.get_segment_url("999.ts"))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_hls_files_require_login(self) -> None:
        """Without the access_token cookie playlist and segments return 401."""
        del self.client.cookies["access_token"]
        for url in [self.get_playlist_url(), self.get_segment_url()]:
            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
