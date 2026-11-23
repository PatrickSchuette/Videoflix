from django.http import FileResponse
from rest_framework import generics, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from video_app.models import Video
from video_app.utils import get_hls_file_path

from .serializers import VideoSerializer


class VideoListView(generics.ListAPIView):
    """
    GET /api/video/

    Returns all videos, newest first (ordering is defined in the model).
    Only available for logged-in users.
    """

    queryset = Video.objects.all()
    serializer_class = VideoSerializer


class HLSPlaylistView(APIView):
    """
    GET /api/video/<movie_id>/<resolution>/index.m3u8

    Returns the HLS playlist of a video in the requested resolution.
    The player reads this file to find out which segments it has to load.
    """

    def get(self, request: Request, movie_id: int, resolution: str) -> FileResponse | Response:
        """Send the index.m3u8 file or answer with 404 if it does not exist."""
        file_path = get_hls_file_path(movie_id, resolution, "index.m3u8")
        if file_path is None:
            return Response({"detail": "Video or manifest not found."}, status=status.HTTP_404_NOT_FOUND)
        return FileResponse(open(file_path, "rb"), content_type="application/vnd.apple.mpegurl")


class HLSSegmentView(APIView):
    """
    GET /api/video/<movie_id>/<resolution>/<segment>

    Returns a single HLS video segment (e.g. 000.ts) in the requested resolution.
    """

    def get(self, request: Request, movie_id: int, resolution: str, segment: str) -> FileResponse | Response:
        """Send the requested .ts segment or answer with 404 if it does not exist."""
        file_path = get_hls_file_path(movie_id, resolution, segment)
        if file_path is None:
            return Response({"detail": "Video or segment not found."}, status=status.HTTP_404_NOT_FOUND)
        return FileResponse(open(file_path, "rb"), content_type="video/MP2T")
