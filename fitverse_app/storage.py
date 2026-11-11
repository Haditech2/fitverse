"""Private storage for personal wardrobe photos.

Files live outside ``MEDIA_ROOT`` so the normal media URL never exposes them.
They are streamed back through an ownership-checked view instead.
"""

import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage


class WardrobeStorage(FileSystemStorage):
    """File storage whose folder follows ``settings.WARDROBE_ROOT`` at runtime.

    Both ``base_location`` and ``location`` are plain properties. Django caches
    ``FileSystemStorage.location`` and only clears that cache for ``MEDIA_ROOT``
    changes, which would leave tests (and any runtime override of
    ``WARDROBE_ROOT``) pointing at the first folder ever used.
    """

    @property
    def base_location(self):
        return settings.WARDROBE_ROOT

    @property
    def location(self):
        return os.path.abspath(self.base_location)
