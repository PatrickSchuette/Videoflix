import django_rq
from django.db import transaction
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from .models import Video
from .utils import process_video, delete_video_files

@receiver(post_save, sender=Video)
def queue_video_processing(sender: type[Video], instance: Video, created: bool, **kwargs) -> None:
    """
    Start the thumbnail and HLS conversion in the background after a new upload.

    The job is put into the 'default' queue of Django-RQ and executed by the
    RQ worker, so the slow FFmpeg conversion does not block the backend.
    The job is only queued once the database transaction is finished, so the
    worker can be sure that the video already exists in the database.
    Editing an existing video (created=False) does not start a new conversion.
    """
    if created:
        queue = django_rq.get_queue("default", autocommit=True)
        transaction.on_commit(
            lambda: queue.enqueue(process_video, instance.id, job_timeout=3600)
        )


@receiver(post_delete, sender=Video)
def remove_video_files(sender: type[Video], instance: Video, **kwargs) -> None:
    """Delete the original file, the thumbnail and all HLS files of a deleted video."""
    delete_video_files(instance)
