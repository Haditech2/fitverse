"""Image preparation for personal wardrobe uploads.

Photos come straight from a phone camera: huge, sometimes rotated, often
HEIC-named but JPEG-encoded. Everything is normalised to RGB JPEG here before
it is stored, and a grid-sized thumbnail is produced at the same time.
"""

import io
from dataclasses import dataclass

from PIL import Image, ImageOps

MAX_EDGE = 1600
THUMB_EDGE = 520
JPEG_QUALITY = 88
THUMB_QUALITY = 82

# Small named palette used for a sensible colour tag when AI tagging is
# unavailable, and as a fallback label the user can correct later.
PALETTE = {
    'black': (24, 24, 24),
    'charcoal': (62, 66, 64),
    'grey': (135, 135, 130),
    'white': (246, 246, 240),
    'cream': (232, 223, 200),
    'beige': (203, 181, 148),
    'brown': (116, 78, 50),
    'tan': (176, 128, 82),
    'navy': (28, 40, 74),
    'blue': (54, 96, 160),
    'sky blue': (134, 176, 216),
    'teal': (30, 122, 118),
    'green': (56, 118, 70),
    'olive': (104, 112, 62),
    'lime': (168, 196, 68),
    'gold': (203, 155, 20),
    'yellow': (226, 200, 76),
    'orange': (214, 126, 46),
    'red': (178, 44, 44),
    'wine': (110, 30, 54),
    'pink': (214, 140, 160),
    'purple': (110, 70, 140),
}


class WardrobeImageError(Exception):
    """Raised when an upload is not a readable image."""


@dataclass
class PreparedPhoto:
    full: bytes
    thumb: bytes
    colour: str


def prepare_photo(data):
    """Return normalised full-size JPEG, thumbnail JPEG, and a colour name."""
    if not data:
        raise WardrobeImageError('That photo is empty. Choose it again.')

    try:
        with Image.open(io.BytesIO(data)) as source:
            source.load()
            image = ImageOps.exif_transpose(source).convert('RGB')
    except Exception as exc:
        raise WardrobeImageError('That file is not a photo we can read.') from exc

    if min(image.size) < 64:
        raise WardrobeImageError('That photo is too small. Use one at least 64 px wide.')

    return PreparedPhoto(
        full=_jpeg(image, MAX_EDGE, JPEG_QUALITY),
        thumb=_jpeg(image, THUMB_EDGE, THUMB_QUALITY),
        colour=dominant_colour(image),
    )


def _jpeg(image, max_edge, quality):
    copy = image.copy()
    copy.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    copy.save(buffer, format='JPEG', quality=quality, optimize=True)
    return buffer.getvalue()


def dominant_colour(image):
    """Nearest palette name to the most common colour in the photo."""
    sample = image.copy()
    sample.thumbnail((48, 48), Image.Resampling.LANCZOS)
    quantized = sample.quantize(colors=8, method=Image.Quantize.MEDIANCUT)
    palette = quantized.getpalette() or []
    counts = sorted(quantized.getcolors() or [], reverse=True)
    if not counts:
        return ''

    _, index = counts[0]
    rgb = tuple(palette[index * 3:index * 3 + 3])
    if len(rgb) < 3:
        return ''
    return min(PALETTE, key=lambda name: _distance(PALETTE[name], rgb))


def _distance(left, right):
    return sum((a - b) ** 2 for a, b in zip(left, right))
