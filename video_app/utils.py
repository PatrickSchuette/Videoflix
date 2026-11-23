import subprocess
import shutil
from pathlib import Path

from django.conf import settings

from .models import Video

RESOLUTIONS = {"480p": 480, "720p": 720, "1080p": 1080}


def get_hls_directory(video_id: int, resolution: str) -> Path:
    """Return the folder in which the HLS files of one video in one resolution are stored."""
    return Path(settings.MEDIA_ROOT) / "hls" / str(video_id) / resolution


def get_hls_file_path(video_id: int, resolution: str, filename: str) -> Path | None:
    """
    Return the path of an HLS file (playlist or segment) if it exists.

    Returns None for unknown resolutions or missing files. 
    """
    if resolution not in RESOLUTIONS:
        return None
    file_path = get_hls_directory(video_id, resolution) / filename
    return file_path if file_path.is_file() else None

def delete_video_files(video: Video) -> None:
    """
    Delete all files that belong to a video from the media folder.

    This includes the original upload, the thumbnail and the complete HLS
    folder with all resolutions. Missing files are ignored.
    """
    video.video_file.delete(save=False)
    if video.thumbnail:
        video.thumbnail.delete(save=False)
    shutil.rmtree(Path(settings.MEDIA_ROOT) / "hls" / str(video.id), ignore_errors=True)
    
    
def build_hls_command(source_path: str, output_dir: Path, height: int) -> list[str]:
    """
    Build the FFmpeg command that converts a video into HLS format.

    The video is scaled to the given height (the width is calculated automatically), 
    encoded as H.264 with AAC audio and split into segments of 10 seconds named 000.ts, 001.ts, ...
    plus a playlist called index.m3u8.
    """
    return [
        "ffmpeg", "-y", "-i", source_path,
        "-vf", f"scale=-2:{height}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-start_number", "0",
        "-hls_time", "10",
        "-hls_list_size", "0",
        "-hls_playlist_type", "vod",
        "-hls_segment_filename", str(output_dir / "%03d.ts"),
        "-f", "hls",
        str(output_dir / "index.m3u8"),
    ]


def convert_to_hls(source_path: str, video_id: int, resolution: str) -> None:
    """Create the HLS playlist and segments of a video for one resolution."""
    output_dir = get_hls_directory(video_id, resolution)
    output_dir.mkdir(parents=True, exist_ok=True)
    command = build_hls_command(source_path, output_dir, RESOLUTIONS[resolution])
    subprocess.run(command, check=True, capture_output=True)


def create_thumbnail(source_path: str, video_id: int) -> str:
    """
    Save a single frame from the first second of the video as a JPG thumbnail.

    Returns the path relative to MEDIA_ROOT.
    """
    relative_path = f"thumbnails/{video_id}.jpg"
    output_path = Path(settings.MEDIA_ROOT) / relative_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = ["ffmpeg", "-y", "-ss", "1", "-i", source_path,
               "-frames:v", "1", "-vf", "scale=640:-2", str(output_path)]
    subprocess.run(command, check=True, capture_output=True)
    return relative_path


def process_video(video_id: int) -> None:
    """
    Background job that runs in the RQ worker after a new video was uploaded.

    Creates a thumbnail (only if none was uploaded manually) and converts
    the video into HLS for every resolution in RESOLUTIONS.
    """
    video = Video.objects.get(pk=video_id)
    source_path = video.video_file.path
    if not video.thumbnail:
        thumbnail_path = create_thumbnail(source_path, video_id)
        Video.objects.filter(pk=video_id).update(thumbnail=thumbnail_path)
    for resolution in RESOLUTIONS:
        convert_to_hls(source_path, video_id, resolution)
