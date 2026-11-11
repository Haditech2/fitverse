"""FASHN virtual try-on.

Two transports are supported:

* The official FASHN API (``https://api.fashn.ai/v1``) whenever
  ``FASHN_API_KEY`` is configured. This is the production path: submit a
  prediction, poll it, then store the finished image locally.
* The public Hugging Face demo Space as a keyless fallback, so the app still
  works for someone who has not bought API credits.

Both return a site-relative ``/media/tryons/<uuid>.png`` URL.
"""

import base64
import json
import mimetypes
import shutil
import tempfile
import time
from functools import lru_cache
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

from django.conf import settings

DEFAULT_API_URL = 'https://api.fashn.ai/v1'
DEFAULT_MODEL = 'tryon-v1.6'
POLL_INTERVAL = 2.0
POLL_TIMEOUT = 180.0
MAX_OUTPUT_BYTES = 25 * 1024 * 1024
SUPPORTED_CATEGORIES = {'tops', 'bottoms', 'one-pieces'}
SUPPORTED_PHOTO_TYPES = {'model', 'flat-lay'}


class FashnVtonError(Exception):
    """Raised when FASHN cannot produce a try-on result."""


# ---------------------------------------------------------------------------
# Official FASHN API
# ---------------------------------------------------------------------------

def get_api_key():
    """The FASHN API key from settings/env. Empty means "use the free Space"."""
    return (getattr(settings, 'FASHN_API_KEY', '') or '').strip()


def _api_base():
    base = getattr(settings, 'FASHN_API_URL', DEFAULT_API_URL) or DEFAULT_API_URL
    return base.rstrip('/')


def _http_error(exc):
    detail = ''
    try:
        detail = exc.read().decode('utf-8', errors='replace')[:400]
    except Exception:
        detail = ''

    name = ''
    message = ''
    try:
        payload = json.loads(detail)
        if isinstance(payload, dict):
            name = str(payload.get('error') or '')
            message = str(payload.get('message') or '')
    except ValueError:
        message = detail.strip()

    haystack = f'{name} {message}'.lower()
    if exc.code in (401, 403):
        return FashnVtonError(
            'FASHN rejected the API key. Check FASHN_API_KEY in .env.'
        )
    if exc.code == 429:
        if 'credits' in haystack:
            return FashnVtonError(
                'The FASHN API credits are used up. Top up at app.fashn.ai/billing.'
            )
        if 'concurrency' in haystack:
            return FashnVtonError(
                'FASHN is busy with other try-ons. Wait a moment and try again.'
            )
        return FashnVtonError('FASHN is rate-limiting us. Try again in a minute.')
    if exc.code == 400:
        return FashnVtonError(
            'FASHN could not accept this request'
            + (f': {message}' if message else '.')
        )
    if exc.code >= 500:
        return FashnVtonError('The FASHN service had a server error. Try again.')
    return FashnVtonError(
        f'FASHN request failed (HTTP {exc.code})' + (f': {message}' if message else '.')
    )


def _api_request(path, *, key, payload=None, timeout=40):
    """POST when ``payload`` is given, otherwise GET. Returns parsed JSON."""
    url = _api_base() + path
    data = None
    method = 'GET'
    headers = {
        'Authorization': f'Bearer {key}',
        'Accept': 'application/json',
    }
    if payload is not None:
        data = json.dumps(payload).encode('utf-8')
        method = 'POST'
        headers['Content-Type'] = 'application/json'

    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode('utf-8'))
    except HTTPError as exc:
        raise _http_error(exc) from exc
    except (URLError, TimeoutError) as exc:
        raise FashnVtonError('Could not reach the FASHN API. Check the network connection.') from exc
    except ValueError as exc:
        raise FashnVtonError('FASHN returned an unreadable response.') from exc


def _runtime_error_message(error):
    if isinstance(error, dict):
        name = str(error.get('name') or '').strip()
        message = str(error.get('message') or '').strip()
    else:
        name, message = '', str(error or '').strip()

    if name == 'PoseError' or 'pose' in message.lower():
        return (
            'FASHN could not detect a full-body pose. Use a clear, upright photo '
            'of the whole body with the person facing the camera.'
        )
    if name == 'ContentModerationError':
        return 'FASHN blocked one of the images under its content policy.'
    if message:
        return f'FASHN could not finish the try-on: {message}'
    return 'FASHN could not finish the try-on. Try different photos.'


def _image_data_uri(image):
    """Turn an uploaded file, a local path, or a URL into something FASHN reads.

    Browser uploads and site-relative ``/static`` and ``/media`` files are
    inlined as base64 data URIs because FASHN's servers cannot reach this
    machine. Public ``http(s)`` URLs and data URIs pass through untouched.
    """
    if hasattr(image, 'read'):
        data = image.read()
        if hasattr(image, 'seek'):
            image.seek(0)
        name = getattr(image, 'name', '') or ''
        content_type = getattr(image, 'content_type', '') or ''
        if not content_type:
            content_type = mimetypes.guess_type(name)[0] or 'image/jpeg'
        if not content_type.startswith('image/'):
            content_type = 'image/jpeg'
        if not data:
            raise FashnVtonError('One of the photos is empty. Choose it again.')
        return f'data:{content_type};base64,{base64.b64encode(data).decode("ascii")}'

    source = str(image or '').strip()
    if not source:
        raise FashnVtonError('A person photo and a garment image are required.')
    if source.startswith(('http://', 'https://', 'data:')):
        return source

    local = _local_file_path(source)
    if local is None:
        raise FashnVtonError('The garment image could not be found for the try-on.')
    content_type = mimetypes.guess_type(str(local))[0] or 'image/jpeg'
    if not content_type.startswith('image/'):
        content_type = 'image/jpeg'
    try:
        data = local.read_bytes()
    except OSError as exc:
        raise FashnVtonError('The garment image could not be read.') from exc
    if not data:
        raise FashnVtonError('The garment image is empty.')
    return f'data:{content_type};base64,{base64.b64encode(data).decode("ascii")}'


def _local_file_path(url):
    """Map a site-relative ``/static/…`` or ``/media/…`` URL to a real file."""
    path = urlparse(url).path
    static_url = getattr(settings, 'STATIC_URL', 'static/').lstrip('/')
    media_url = getattr(settings, 'MEDIA_URL', 'media/').lstrip('/')

    if path.startswith('/' + static_url):
        relative = path[len(static_url) + 1:]
        for static_dir in getattr(settings, 'STATICFILES_DIRS', []) or []:
            base = Path(static_dir).resolve()
            candidate = (base / relative).resolve()
            if _inside(candidate, base) and candidate.is_file():
                return candidate
        return None
    if path.startswith('/' + media_url):
        base = Path(getattr(settings, 'MEDIA_ROOT', '')).resolve()
        candidate = (base / path[len(media_url) + 1:]).resolve()
        return candidate if _inside(candidate, base) and candidate.is_file() else None
    return None


def _inside(candidate, base):
    try:
        candidate.relative_to(base)
        return True
    except ValueError:
        return False


def _download_output(output):
    """Fetch a finished image (CDN URL or data URI) and return its bytes."""
    if output.startswith('data:'):
        header, _, encoded = output.partition(',')
        if ';base64' not in header:
            raise FashnVtonError('FASHN returned an invalid image result.')
        try:
            blob = base64.b64decode(encoded)
        except ValueError as exc:
            raise FashnVtonError('FASHN returned an invalid image result.') from exc
    else:
        try:
            with urlopen(output, timeout=90) as response:
                blob = response.read(MAX_OUTPUT_BYTES + 1)
        except (HTTPError, URLError, TimeoutError) as exc:
            raise FashnVtonError('The finished try-on could not be downloaded.') from exc

    if not blob:
        raise FashnVtonError('FASHN returned an empty image.')
    if len(blob) > MAX_OUTPUT_BYTES:
        raise FashnVtonError('The finished try-on is larger than 25 MB.')
    return blob


def _save_output(blob):
    output_dir = Path(settings.MEDIA_ROOT) / 'tryons'
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f'{uuid4().hex}.png'
    output_path.write_bytes(blob)
    return f'{settings.MEDIA_URL}tryons/{output_path.name}'


def _generate_via_api(
    *,
    person_image,
    garment_image,
    category,
    garment_photo_type,
    mode,
    seed,
    segmentation_free,
):
    key = get_api_key()
    payload = {
        'model_name': getattr(settings, 'FASHN_MODEL', DEFAULT_MODEL) or DEFAULT_MODEL,
        'inputs': {
            'model_image': _image_data_uri(person_image),
            'garment_image': _image_data_uri(garment_image),
            'category': category,
            'garment_photo_type': garment_photo_type
            if garment_photo_type in SUPPORTED_PHOTO_TYPES
            else 'auto',
            'segmentation_free': bool(segmentation_free),
            'mode': mode,
            'seed': int(seed),
            'output_format': 'png',
        },
    }

    response = _api_request('/run', key=key, payload=payload)
    prediction_id = response.get('id') if isinstance(response, dict) else None
    if not prediction_id:
        raise FashnVtonError('FASHN did not return a prediction id.')

    deadline = time.monotonic() + POLL_TIMEOUT
    while time.monotonic() < deadline:
        time.sleep(POLL_INTERVAL)
        status = _api_request(
            f'/status/{quote(str(prediction_id), safe="")}', key=key
        )
        state = status.get('status') if isinstance(status, dict) else None
        if state == 'completed':
            outputs = status.get('output') or []
            if not outputs:
                raise FashnVtonError('FASHN finished without returning an image.')
            return _save_output(_download_output(str(outputs[0])))
        if state == 'failed':
            raise FashnVtonError(_runtime_error_message(status.get('error')))

    raise FashnVtonError(
        'FASHN is taking longer than expected. Check app.fashn.ai for the result.'
    )


# ---------------------------------------------------------------------------
# Public Hugging Face Space (keyless fallback)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _client():
    try:
        from gradio_client import Client
    except ImportError as exc:
        raise FashnVtonError(
            'The FASHN client is not installed. Run `python -m pip install -r requirements.txt`.'
        ) from exc

    space = getattr(settings, 'FASHN_VTON_SPACE', 'fashn-ai/fashn-vton-1.5')
    token = getattr(settings, 'HF_TOKEN', '') or None
    try:
        return Client(space, hf_token=token, verbose=False)
    except Exception as exc:
        raise FashnVtonError('Could not connect to the FASHN VTON Hugging Face Space.') from exc


def _input(value):
    from gradio_client import handle_file

    if hasattr(value, 'temporary_file_path'):
        return handle_file(value.temporary_file_path())
    return handle_file(str(value))


def _uploaded_file_path(uploaded_file):
    if hasattr(uploaded_file, 'temporary_file_path'):
        return uploaded_file.temporary_file_path(), None

    temporary_file = tempfile.NamedTemporaryFile(
        prefix='fitverse-vton-',
        suffix=Path(uploaded_file.name).suffix,
        delete=False,
    )
    for chunk in uploaded_file.chunks():
        temporary_file.write(chunk)
    temporary_file.close()
    return temporary_file.name, temporary_file.name


def _generate_via_space(
    *,
    person_image,
    garment_image,
    category,
    garment_photo_type,
    num_timesteps,
    guidance_scale,
    seed,
    segmentation_free,
):
    temporary_paths = []
    try:
        if hasattr(person_image, 'read'):
            person_image, temporary_path = _uploaded_file_path(person_image)
            if temporary_path:
                temporary_paths.append(temporary_path)
        if hasattr(garment_image, 'read'):
            garment_image, temporary_path = _uploaded_file_path(garment_image)
            if temporary_path:
                temporary_paths.append(temporary_path)

        result = _client().predict(
            person_image=_input(person_image),
            garment_image=_input(garment_image),
            category=category,
            garment_photo_type=garment_photo_type,
            num_timesteps=num_timesteps,
            guidance_scale=guidance_scale,
            seed=seed,
            segmentation_free=segmentation_free,
            api_name='/try_on',
        )
    except Exception as exc:
        raise FashnVtonError('FASHN VTON inference failed. Please try again.') from exc
    finally:
        for temporary_path in temporary_paths:
            Path(temporary_path).unlink(missing_ok=True)

    result_path = result.get('path') if isinstance(result, dict) else result
    if not result_path or not Path(result_path).is_file():
        raise FashnVtonError('FASHN VTON returned an invalid image result.')

    output_dir = Path(settings.MEDIA_ROOT) / 'tryons'
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f'{uuid4().hex}.png'
    shutil.copyfile(result_path, output_path)
    return f'{settings.MEDIA_URL}tryons/{output_path.name}'


def generate_try_on(
    *,
    person_image,
    garment_image,
    category,
    garment_photo_type='model',
    num_timesteps=30,
    guidance_scale=1.5,
    seed=42,
    segmentation_free=True,
    mode='balanced',
):
    """Render a try-on and return a site-relative image URL.

    ``num_timesteps`` and ``guidance_scale`` only apply to the keyless Space;
    the official API uses ``mode`` (performance | balanced | quality).
    """
    if category not in SUPPORTED_CATEGORIES:
        raise FashnVtonError('Unsupported garment category.')
    if garment_photo_type not in SUPPORTED_PHOTO_TYPES | {'auto'}:
        raise FashnVtonError('Unsupported garment photo type.')

    if get_api_key():
        return _generate_via_api(
            person_image=person_image,
            garment_image=garment_image,
            category=category,
            garment_photo_type=garment_photo_type,
            mode=mode if mode in {'performance', 'balanced', 'quality'} else 'balanced',
            seed=seed,
            segmentation_free=segmentation_free,
        )

    return _generate_via_space(
        person_image=person_image,
        garment_image=garment_image,
        category=category,
        garment_photo_type=garment_photo_type,
        num_timesteps=num_timesteps,
        guidance_scale=guidance_scale,
        seed=seed,
        segmentation_free=segmentation_free,
    )
