"""Look 360 — turn a design photo into a real, draggable 3D view.

Uses the Meshy image-to-3D API (free tier) as the 3D provider. The renderer
itself is Google's open-source ``<model-viewer>`` web component, loaded on
demand in the browser, so nothing here changes the design page's base cost.

This module is deliberately tiny and key-safe: the browser never sees the
Meshy key; Django relays create/status calls and hands back only the public
model URL. When no key is configured we serve a clearly-labelled demo model
instead of pretending a real 360 view was generated.
"""

import base64
import json
import os
import mimetypes
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from django.conf import settings

MESHY_ENDPOINT = 'https://api.meshy.ai/openapi/v1/image-to-3d'

# Public sample asset from modelviewer.dev — only used when no 3D API key is
# configured, and always flagged ``demo=true`` in the API response.
DEMO_MODEL_URL = 'https://modelviewer.dev/shared-assets/models/Astronaut.glb'

MAX_IMAGE_BYTES = 20 * 1024 * 1024  # Meshy limit: JPG/PNG/WebP <= 20 MB
MAX_MODEL_BYTES = 100 * 1024 * 1024


class Look360Error(Exception):
    """Raised when a 3D task cannot be created or polled."""


def get_api_key():
    """The Meshy key, from env (or Django settings override). Empty = demo mode."""
    key = getattr(settings, 'LOOK360_API_KEY', '') or os.environ.get('FITVERSE_3D_API_KEY', '')
    return key.strip()


def _post(path_suffix='', payload=None, headers=None, timeout=25):
    request = Request(
        MESHY_ENDPOINT + path_suffix,
        data=json.dumps(payload or {}).encode('utf-8') if payload is not None else None,
        headers={'Content-Type': 'application/json', **(headers or {})},
        method='POST' if payload is not None else 'GET',
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode('utf-8'))


def create_task(image_url):
    """Start an image-to-3D task and return the Meshy task id.

    The image is always sent as a base64 data URI: wikimedia/CDN links go
    stale, and local ``/media/`` or ``/static/`` images are simply not
    reachable by Meshy's servers, so this works everywhere.
    """
    key = get_api_key()
    if not key:
        raise Look360Error('No 3D API key configured.')

    data_uri = _image_data_uri(image_url)
    try:
        payload = _post(
            headers={'Authorization': f'Bearer {key}'},
            payload={'image_url': data_uri, 'target_formats': ['glb']},
        )
    except HTTPError as exc:
        if exc.code == 402:
            raise Look360Error('The free 3D credits are used up this month.') from exc
        if exc.code == 429:
            raise Look360Error('The 3D service is rate-limiting us. Try again in a minute.') from exc
        raise Look360Error(f'3D service refused the task (HTTP {exc.code}).') from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise Look360Error('Could not reach the 3D service.') from exc

    task_id = payload.get('result')
    if not task_id:
        raise Look360Error('3D service returned no task id.')
    return task_id


def get_task(task_id):
    """Poll a task. Returns Meshy's status payload dict (status, progress, model_urls)."""
    key = get_api_key()
    if not key:
        raise Look360Error('No 3D API key configured.')
    try:
        return _post(
            path_suffix=f'/{quote(str(task_id), safe="")}',
            headers={'Authorization': f'Bearer {key}'},
        )
    except HTTPError as exc:
        raise Look360Error(f'3D task lookup failed (HTTP {exc.code}).') from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise Look360Error('Could not reach the 3D service.') from exc


def download_model(model_url):
    """Download a completed GLB so Fitverse is not tied to an expiring URL."""
    try:
        with urlopen(model_url, timeout=90) as response:
            blob = response.read(MAX_MODEL_BYTES + 1)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise Look360Error('The finished 3D model could not be downloaded.') from exc

    if len(blob) > MAX_MODEL_BYTES:
        raise Look360Error('The finished 3D model is larger than 100 MB.')
    if len(blob) < 12 or blob[:4] != b'glTF':
        raise Look360Error('The 3D service returned an invalid GLB model.')
    return blob


def _image_data_uri(image_url):
    """Resolve any design image source we can reach into a ``data:`` URI."""
    image_url = (image_url or '').strip()
    if not image_url:
        raise Look360Error('This design has no image to convert.')

    if image_url.startswith(('http://', 'https://')):
        try:
            with urlopen(image_url, timeout=20) as response:
                content_type = response.headers.get_content_type()
                blob = response.read(MAX_IMAGE_BYTES + 1)
        except (HTTPError, URLError, TimeoutError) as exc:
            raise Look360Error('The design image could not be fetched to convert.') from exc
    else:
        local = _local_file_path(image_url)
        if not local:
            raise Look360Error('This design image has no local or public source.')
        content_type = mimetypes.guess_type(str(local))[0] or 'image/webp'
        try:
            blob = Path(local).read_bytes()[: MAX_IMAGE_BYTES + 1]
        except OSError as exc:
            raise Look360Error('The design image file could not be read.') from exc

    if len(blob) > MAX_IMAGE_BYTES:
        raise Look360Error('The design image is larger than the 3D service allows (20 MB).')
    if not content_type.startswith('image/'):
        raise Look360Error('The design image is not an image file the 3D service accepts.')

    return f'data:{content_type};base64,{base64.b64encode(blob).decode("ascii")}'


def _local_file_path(url):
    """Map a site-relative ``/static/…`` or ``/media/…`` URL to a real file."""
    path = urlparse(url).path
    static_url = getattr(settings, 'STATIC_URL', 'static/').lstrip('/')
    media_url = getattr(settings, 'MEDIA_URL', 'media/').lstrip('/')
    if path.startswith('/' + static_url):
        static_dirs = getattr(settings, 'STATICFILES_DIRS', []) or []
        for static_dir in static_dirs:
            base = Path(static_dir).resolve()
            candidate = (base / path[len(static_url) + 1:]).resolve()
            if _inside(candidate, base) and candidate.is_file():
                return candidate
        return None
    if path.startswith('/' + media_url):
        base = Path(getattr(settings, 'MEDIA_ROOT', '')).resolve()
        candidate = (base / path[len(media_url) + 1:]).resolve()
        return candidate if _inside(candidate, base) and candidate.is_file() else None
    return None


def _inside(candidate, base):
    """Reject ``../`` escapes when resolving a site-relative image path."""
    try:
        candidate.relative_to(base)
        return True
    except ValueError:
        return False
