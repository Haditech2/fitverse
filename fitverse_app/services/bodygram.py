import base64
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from django.conf import settings


class BodygramError(Exception):
    """Raised when Bodygram cannot produce or return a measurement scan."""


# UserMeasurement field -> Bodygram measurement names, in order of preference.
FIELD_SOURCES = {
    'chest': ('bustGirth',),
    'waist': ('waistGirth',),
    'hips': ('hipGirth',),
    'shoulder': ('acrossBackShoulderWidth',),
    'sleeve': ('outerArmLengthR', 'backNeckPointToWristLengthR'),
    'inseam': ('insideLegLengthR', 'insideLegHeight'),
    'neck': ('neckGirth', 'neckBaseGirth'),
}

# Friendly names for every measurement the Platform API can return.
MEASUREMENT_LABELS = {
    'acrossBackShoulderWidth': 'Shoulder width (across back)',
    'backNeckHeight': 'Back neck height',
    'backNeckPointToGroundContoured': 'Back neck to ground (contoured)',
    'backNeckPointToWaist': 'Back neck to waist',
    'backNeckPointToWristLengthR': 'Back neck to right wrist',
    'bellyWaistDepth': 'Belly waist depth',
    'bellyWaistGirth': 'Belly waist circumference',
    'bellyWaistHeight': 'Belly waist height',
    'bellyWaistWidth': 'Belly waist width',
    'bustGirth': 'Bust',
    'bustHeight': 'Bust height',
    'calfGirthR': 'Right calf',
    'forearmGirthR': 'Right forearm',
    'hipGirth': 'Hip',
    'hipHeight': 'Hip height',
    'insideLegHeight': 'Inside leg height',
    'insideLegLengthR': 'Right inside leg length',
    'kneeGirthR': 'Right knee',
    'kneeHeightR': 'Right knee height',
    'midThighGirthR': 'Right mid-thigh',
    'neckBaseGirth': 'Neck base',
    'neckGirth': 'Neck',
    'outerAnkleHeightR': 'Right outer ankle height',
    'outerArmLengthR': 'Right outer arm length',
    'outseamR': 'Right outseam',
    'outsideLegLengthR': 'Right outside leg length',
    'shoulderToElbowR': 'Right shoulder to elbow',
    'thighGirthR': 'Right thigh',
    'topHipGirth': 'Top hip',
    'topHipHeight': 'Top hip height',
    'underBustGirth': 'Under-bust',
    'upperArmGirthR': 'Right upper arm',
    'waistGirth': 'Waist',
    'waistHeight': 'Waist height',
    'wristGirthR': 'Right wrist',
}

GROUP_ORDER = ('Circumferences', 'Widths & depths', 'Lengths', 'Heights', 'Other')


def _config():
    org_id = getattr(settings, 'BODYGRAM_ORG_ID', '').strip()
    api_key = getattr(settings, 'BODYGRAM_API_KEY', '').strip()
    base_url = getattr(settings, 'BODYGRAM_API_URL', 'https://platform.bodygram.com/api/orgs').strip()
    if not org_id or not api_key:
        raise BodygramError(
            "Bodygram is not configured. Add BODYGRAM_ORG_ID and BODYGRAM_API_KEY to .env."
        )
    return org_id, api_key, base_url.rstrip('/')


def _http_error(exc):
    detail = ''
    try:
        detail = exc.read().decode('utf-8', errors='replace')[:300]
    except Exception:
        detail = ''
    if exc.code in (401, 403):
        return BodygramError(
            "Bodygram rejected the credentials. Check BODYGRAM_ORG_ID and BODYGRAM_API_KEY."
        )
    if exc.code == 404:
        return BodygramError("That Bodygram scan could not be found on this account.")
    if exc.code == 429:
        return BodygramError("Bodygram scan quota is exhausted for this account.")
    if exc.code == 422:
        return BodygramError(
            "Bodygram could not analyse these photos. Use a clear front and right-side photo of the full body."
        )
    return BodygramError(f"Bodygram request failed (HTTP {exc.code}). {detail}".strip())


def _send(request):
    try:
        with urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode('utf-8'))
    except HTTPError as exc:
        raise _http_error(exc) from exc
    except URLError as exc:
        raise BodygramError("Could not reach the Bodygram API. Check the network connection.") from exc
    except ValueError as exc:
        raise BodygramError("Bodygram returned an unreadable response.") from exc


def _post(url, api_key, payload):
    request = Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Authorization': api_key,
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        },
        method='POST',
    )
    return _send(request)


def _get(url, api_key):
    request = Request(
        url,
        headers={'Authorization': api_key, 'Accept': 'application/json'},
        method='GET',
    )
    return _send(request)


def _measurements_cm(entries):
    """Convert Bodygram's measurement list to a name -> centimetres map."""
    by_name = {}
    for item in entries or []:
        name = item.get('name')
        value = item.get('value')
        if not name or value is None:
            continue
        unit = (item.get('unit') or 'mm').lower()
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        if unit == 'mm':
            by_name[name] = value / 10.0
        elif unit == 'cm':
            by_name[name] = value
        elif unit == 'in':
            by_name[name] = value * 2.54
    return by_name


def _label_for(name):
    if name in MEASUREMENT_LABELS:
        return MEASUREMENT_LABELS[name]
    spaced = re.sub(r'(?<!^)(?=[A-Z])', ' ', name)
    return spaced.replace(' R', ' (right)').strip()


def _group_for(name):
    # Names ending in "R" are right-side measurements (calfGirthR); classify the base name.
    base = name[:-1] if name.endswith('R') and len(name) > 1 and name[-2].islower() else name
    if base.endswith('Girth'):
        return 'Circumferences'
    if base.endswith(('Width', 'Depth')):
        return 'Widths & depths'
    if base.endswith('Height'):
        return 'Heights'
    if base.lower().endswith(('length', 'contoured', 'waist', 'wrist', 'elbow', 'outseam')):
        return 'Lengths'
    return 'Other'


def _failure_reason(entry):
    error = entry.get('error') or {}
    return error.get('code') or entry.get('failureReason') or entry.get('message') or ''


def _entry_to_result(entry):
    """Normalise one Bodygram ``entry`` into Fitverse's result shape."""
    entry = entry or {}
    if entry.get('status') != 'success':
        reason = _failure_reason(entry)
        hint = " Try clearer front and right-side photos."
        raise BodygramError(
            "Bodygram could not estimate measurements from these photos."
            + (f" ({reason})" if reason else hint)
        )

    by_name = _measurements_cm(entry.get('measurements'))

    measurements = {}
    profile_fields = {}
    for field, sources in FIELD_SOURCES.items():
        for source in sources:
            if source in by_name:
                measurements[field] = round(by_name[source], 1)
                profile_fields[source] = field
                break

    if not measurements:
        raise BodygramError("Bodygram returned no usable measurements.")

    all_measurements = [
        {
            'name': name,
            'label': _label_for(name),
            'group': _group_for(name),
            'value': round(value, 1),
            'profile_field': profile_fields.get(name, ''),
        }
        for name, value in by_name.items()
    ]
    all_measurements.sort(
        key=lambda item: (GROUP_ORDER.index(item['group']), item['label'].lower())
    )

    return {
        'scan_id': entry.get('id', ''),
        'measurements': measurements,
        'all_measurements': all_measurements,
        'body_composition': entry.get('bodyComposition') or None,
        'posture': entry.get('posture') or None,
        'avatar_obj': _avatar_bytes(entry.get('avatar')),
        'stats': _stats_from_input(entry.get('input')),
    }


def _avatar_bytes(avatar):
    """Decode Bodygram's base64 ``.obj`` avatar, returning ``None`` if absent."""
    if not avatar or avatar.get('format') != 'obj':
        return None
    data = avatar.get('data') or ''
    if not data:
        return None
    try:
        return base64.b64decode(data)
    except (ValueError, TypeError):
        return None


def _stats_from_input(input_data):
    """Extract the age/gender/height/weight a scan was created with.

    ``GET /scans/{SCAN_ID}`` echoes the original input in millimetres/grams,
    which lets a saved profile be refreshed without re-asking the user.
    """
    input_data = input_data or {}
    scan_input = input_data.get('photoScan') or input_data.get('statsEstimations') or {}
    stats = {}
    if scan_input.get('age') is not None:
        stats['age'] = int(scan_input['age'])
    if scan_input.get('gender') in {'male', 'female'}:
        stats['gender'] = scan_input['gender']
    if scan_input.get('height') is not None:
        stats['height_cm'] = round(float(scan_input['height']) / 10.0, 1)
    if scan_input.get('weight') is not None:
        stats['weight_kg'] = round(float(scan_input['weight']) / 1000.0, 2)
    return stats


def _photo_payload(front_photo, right_photo, age, gender, height_cm, weight_kg):
    return {
        'photoScan': {
            'age': int(age),
            'gender': gender,
            'height': int(round(float(height_cm) * 10)),
            'weight': int(round(float(weight_kg) * 1000)),
            'frontPhoto': base64.b64encode(front_photo).decode('ascii'),
            'rightPhoto': base64.b64encode(right_photo).decode('ascii'),
        }
    }


def estimate_measurements(*, front_photo, right_photo, age, gender, height_cm, weight_kg):
    """Run a Bodygram photo scan and return measurements in centimetres.

    ``front_photo`` and ``right_photo`` are raw image bytes; ``height_cm`` and
    ``weight_kg`` are converted to the millimetres/grams Bodygram expects.
    """
    if gender not in {'male', 'female'}:
        raise BodygramError("Select a valid gender for the Bodygram scan.")
    if not front_photo or not right_photo:
        raise BodygramError("Upload both a front photo and a right-side photo.")

    org_id, api_key, base_url = _config()
    payload = _photo_payload(front_photo, right_photo, age, gender, height_cm, weight_kg)

    data = _post(f"{base_url}/{org_id}/scans", api_key, payload)
    return _entry_to_result(data.get('entry'))


def fetch_scan(scan_id):
    """Return a previously created scan with its full results.

    Reading a scan is free — it does not consume Bodygram quota — so saved
    profile measurements can be refreshed without a new scan.
    """
    if not scan_id:
        raise BodygramError("A Bodygram scan ID is required.")
    org_id, api_key, base_url = _config()
    url = f"{base_url}/{org_id}/scans/{quote(scan_id, safe='')}"
    data = _get(url, api_key)
    return _entry_to_result(data.get('entry'))
