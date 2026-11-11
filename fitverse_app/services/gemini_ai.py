import json
import mimetypes
from functools import lru_cache
from pathlib import Path
from urllib.request import urlopen
from uuid import uuid4

from django.conf import settings


class GeminiError(Exception):
    """Raised when Gemini cannot produce the requested result."""


TRANSIENT_MARKERS = (
    "503",
    "UNAVAILABLE",
    "high demand",
    "overloaded",
    "504",
    "DEADLINE_EXCEEDED",
    "timed out",
    "timeout",
    "500",
    "INTERNAL",
)


def _request_error(exc):
    message = str(exc)
    lowered = message.lower()
    if "RESOURCE_EXHAUSTED" in message or "quota" in lowered:
        return "Gemini quota is exhausted for this key. Check billing or use a key with Gemini image quota enabled."
    if "503" in message or "high demand" in lowered or "overloaded" in lowered:
        return "Gemini is busy right now (high demand). Please try again in a moment."
    if "DEADLINE_EXCEEDED" in message or "504" in message or "timed out" in lowered:
        return "Gemini timed out while processing the request. Please try again."
    if "not found" in lowered or "no longer available" in lowered:
        return "The configured Gemini model is unavailable for this API key. Update the model in .env."
    if "client has been closed" in lowered:
        return "The Gemini client closed before the request finished. Please try again."
    return "Gemini request failed. Check the API key, model access, and network connection."


def _image_error(exc):
    message = str(exc)
    if "RESOURCE_EXHAUSTED" in message or "quota" in message.lower():
        return (
            "Gemini image generation is not included in this key's free tier "
            "(quota limit: 0). Enable billing on the Google AI Studio project, "
            "or keep AI_PROVIDER=fashn for virtual try-on."
        )
    return _request_error(exc)


def _is_transient(exc):
    message = str(exc)
    return any(marker in message for marker in TRANSIENT_MARKERS)


@lru_cache(maxsize=2)
def _client(timeout_ms=60000):
    api_key = getattr(settings, "GEMINI_API_KEY", "")
    if not api_key:
        raise GeminiError("Gemini is not configured. Add GEMINI_API_KEY to .env.")
    try:
        from google import genai
        from google.genai import types
        return genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=timeout_ms),
        )
    except ImportError as exc:
        raise GeminiError(
            "The Gemini client is not installed. Run `python -m pip install -r requirements.txt`."
        ) from exc
    except Exception as exc:
        raise GeminiError("Could not initialize the Gemini client.") from exc


def _model_chain(configured, fallbacks):
    chain = []
    for model in (configured, *fallbacks):
        model = (model or "").strip()
        if model and model not in chain:
            chain.append(model)
    return chain


def _generate_content(contents, models, timeout_ms=60000, config=None):
    """Try each model in turn, skipping over temporarily overloaded ones."""
    last_error = None
    for index, model in enumerate(models):
        try:
            response = _client(timeout_ms).models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
            return response, model
        except Exception as exc:
            last_error = exc
            if index == len(models) - 1 or not _is_transient(exc):
                raise
    raise last_error


def generate_stylist_response(*, message, occasion, style, budget, catalog):
    catalog_text = json.dumps(catalog, ensure_ascii=False)
    prompt = f"""
You are Fitverse AI, an expert Nigerian and African fashion stylist.
Answer the user's request with practical, culturally respectful styling advice.
Only recommend items from the provided catalog. Return valid JSON only, with this shape:
{{"advice": "short helpful answer", "recommended_ids": ["catalog id"]}}
Choose up to two recommended IDs.
User request: {message}
Occasion: {occasion}
Style direction: {style}
Budget in NGN: {budget}
Catalog: {catalog_text}
"""
    models = _model_chain(
        getattr(settings, "GEMINI_TEXT_MODEL", "gemini-3.8-flash"),
        getattr(settings, "GEMINI_TEXT_FALLBACKS", ("gemini-3.6-flash", "gemini-3.5-flash")),
    )
    try:
        response = _generate_content(prompt, models, timeout_ms=30000)[0]
        raw = (response.text or "").strip()
        if raw.startswith("```"):
            raw = raw.strip("`").replace("json\n", "", 1).strip()
        parsed = json.loads(raw)
        advice = str(parsed.get("advice", "")).strip()
        ids = {str(item) for item in parsed.get("recommended_ids", [])}
        looks = [item for item in catalog if str(item["id"]) in ids][:2]
        if not advice or not looks:
            raise GeminiError("Gemini returned an incomplete stylist response.")
        return advice, looks
    except GeminiError:
        raise
    except json.JSONDecodeError as exc:
        raise GeminiError("Gemini replied with an unreadable stylist response. Please try again.") from exc
    except Exception as exc:
        raise GeminiError(_request_error(exc)) from exc


def _image_bytes(value, label="image"):
    if hasattr(value, "read"):
        value.seek(0)
        return value.read(), getattr(value, "content_type", "image/jpeg")

    text = str(value or "").strip()
    if not text:
        raise GeminiError(f"Could not read the {label} image.")

    path = Path(text)
    if path.is_file():
        mime_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
        return path.read_bytes(), mime_type

    try:
        with urlopen(text, timeout=20) as response:
            return response.read(), response.headers.get_content_type()
    except Exception as exc:
        raise GeminiError(f"Could not read the {label} image.") from exc


def generate_try_on(*, person_image, garment_image, category):
    person_bytes, person_mime = _image_bytes(person_image, label="person")
    garment_bytes, garment_mime = _image_bytes(garment_image, label="garment")
    prompt = (
        "Create a realistic virtual try-on image. Put the garment from the second "
        "image onto the person in the first image. Preserve the person's face, pose, "
        "body proportions, background, and lighting. Show the complete outfit clearly. "
        f"Garment category: {category}. Do not add text, logos, or extra people."
    )
    models = _model_chain(
        getattr(settings, "GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image"),
        getattr(settings, "GEMINI_IMAGE_FALLBACKS", ()),
    )
    try:
        from google.genai import types

        response = _generate_content(
            [
                types.Part.from_bytes(data=person_bytes, mime_type=person_mime),
                types.Part.from_bytes(data=garment_bytes, mime_type=garment_mime),
                prompt,
            ],
            models,
            timeout_ms=180000,
            config=types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
        )[0]
        for candidate in response.candidates or []:
            for part in candidate.content.parts or []:
                if part.inline_data and part.inline_data.data:
                    output_dir = Path(settings.MEDIA_ROOT) / "tryons"
                    output_dir.mkdir(parents=True, exist_ok=True)
                    output_path = output_dir / f"{uuid4().hex}.png"
                    output_path.write_bytes(part.inline_data.data)
                    return f"{settings.MEDIA_URL}tryons/{output_path.name}"
        raise GeminiError("Gemini did not return an image result.")
    except GeminiError:
        raise
    except Exception as exc:
        raise GeminiError(_image_error(exc)) from exc


# ---------------------------------------------------------------------------
# Personal wardrobe: tag each photo, then build outfits from the collection.
# ---------------------------------------------------------------------------

WARDROBE_CATEGORIES = {
    'top', 'bottom', 'dress', 'outerwear', 'shoes', 'accessory', 'other',
}
WARDROBE_FORMALITY = {'casual', 'smart-casual', 'formal'}
WARDROBE_SEASONS = {'hot', 'mild', 'cold', 'all'}


def _parse_json(raw):
    raw = (raw or '').strip()
    if raw.startswith('```'):
        raw = raw[3:]
        if raw.lstrip().lower().startswith('json'):
            raw = raw.lstrip()[4:]
        raw = raw.strip()
        if raw.endswith('```'):
            raw = raw[:-3].strip()
    return json.loads(raw)


def _clean_text(value, *, limit=60):
    return ' '.join(str(value or '').split())[:limit]


def _clean_list(value, *, allowed=None, limit=5):
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        return []
    cleaned = []
    for entry in value:
        item = _clean_text(entry, limit=40).lower()
        if not item:
            continue
        if allowed is not None and item not in allowed:
            continue
        if item not in cleaned:
            cleaned.append(item)
        if len(cleaned) >= limit:
            break
    return cleaned


def tag_wardrobe_image(image_bytes, mime_type='image/jpeg', filename=''):
    """Read one clothing photo and return structured wardrobe tags."""
    prompt = f"""
You are Fitverse AI, tagging a photo from a user's own wardrobe.
Look at the garment and return valid JSON only, with this exact shape:
{{"name": "short 2-4 word name", "category": "top|bottom|dress|outerwear|shoes|accessory|other",
  "colours": ["main colour", "other colour"], "pattern": "plain|striped|checked|floral|print|textured|other",
  "formality": "casual|smart-casual|formal", "seasons": ["hot|mild|cold|all"],
  "style_tags": ["short descriptors"]}}
Rules: use lower-case words, at most 3 colours and 4 style tags, never invent details
you cannot see, and keep the item type honest (a shirt is a top, not a dress).
File name hint: {_clean_text(filename, limit=80) or 'none'}
"""
    models = _model_chain(
        getattr(settings, "GEMINI_TEXT_MODEL", "gemini-3.6-flash"),
        getattr(settings, "GEMINI_TEXT_FALLBACKS", ("gemini-3.5-flash", "gemini-3.8-flash")),
    )
    try:
        from google.genai import types

        response = _generate_content(
            [
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                prompt,
            ],
            models,
            timeout_ms=45000,
        )[0]
        parsed = _parse_json(response.text)
    except GeminiError:
        raise
    except json.JSONDecodeError as exc:
        raise GeminiError("The fashion AI could not read this photo's tags. Try again.") from exc
    except Exception as exc:
        raise GeminiError(_request_error(exc)) from exc

    if not isinstance(parsed, dict):
        raise GeminiError("The fashion AI returned incomplete tags. Try again.")

    category = _clean_text(parsed.get('category'), limit=20).lower()
    formality = _clean_text(parsed.get('formality'), limit=20).lower()
    return {
        'name': _clean_text(parsed.get('name'), limit=60) or _clean_text(filename, limit=60),
        'category': category if category in WARDROBE_CATEGORIES else 'other',
        'colours': _clean_list(parsed.get('colours'), limit=3),
        'pattern': _clean_text(parsed.get('pattern'), limit=30).lower(),
        'formality': formality if formality in WARDROBE_FORMALITY else '',
        'seasons': _clean_list(parsed.get('seasons'), allowed=WARDROBE_SEASONS, limit=3),
        'style_tags': _clean_list(parsed.get('style_tags'), limit=4),
    }


def recommend_wardrobe_outfits(*, items, occasion='', weather='', note='', profile=None):
    """Pick 2-3 outfits from the user's own wardrobe.

    ``items`` is a list of dicts with id/name/category/colours/pattern/
    formality/seasons and optional wear history. Only metadata is sent, so this
    is one cheap text call and no image-generation credits.
    """
    if len(items) < 2:
        raise GeminiError('Add at least two pieces to your wardrobe first.')

    catalog = json.dumps(items, ensure_ascii=False)
    profile_text = ''
    if profile:
        profile_text = ', '.join(f'{key}: {value}' for key, value in profile.items() if value)

    prompt = f"""
You are Fitverse AI, a Nigerian and African fashion stylist building outfits from
a real person's own wardrobe. Use ONLY the item ids in the wardrobe below and
never invent clothing that is not listed.
Return valid JSON only, with this exact shape:
{{"outfits": [{{"title": "short outfit name", "item_ids": [1, 2],
  "why": "one or two sentences on why this works for the occasion and colours",
  "tip": "one practical styling tip"}}]}}
Give 2 or 3 complete outfits. A complete outfit must cover the body: at least a
top and a bottom, or a dress. Shoes and accessories are optional extras. Prefer
pieces that have not been worn recently when they suit the occasion.
Occasion: {occasion or 'not specified'}
Weather / temperature: {weather or 'not specified'}
Extra context from the user: {note or 'none'}
Body profile: {profile_text or 'not shared'}
Wardrobe: {catalog}
"""
    models = _model_chain(
        getattr(settings, "GEMINI_TEXT_MODEL", "gemini-3.6-flash"),
        getattr(settings, "GEMINI_TEXT_FALLBACKS", ("gemini-3.5-flash", "gemini-3.8-flash")),
    )
    try:
        response = _generate_content(prompt, models, timeout_ms=45000)[0]
        parsed = _parse_json(response.text)
    except GeminiError:
        raise
    except json.JSONDecodeError as exc:
        raise GeminiError("The fashion AI replied with an unreadable outfit. Try again.") from exc
    except Exception as exc:
        raise GeminiError(_request_error(exc)) from exc

    valid_ids = {str(item['id']) for item in items}
    outfits = []
    for entry in (parsed.get('outfits') if isinstance(parsed, dict) else None) or []:
        if not isinstance(entry, dict):
            continue
        chosen = []
        for raw_id in entry.get('item_ids') or []:
            item_id = str(raw_id)
            if item_id in valid_ids and item_id not in chosen:
                chosen.append(item_id)
        if not chosen:
            continue
        outfits.append({
            'title': _clean_text(entry.get('title'), limit=60) or 'Outfit idea',
            'item_ids': chosen,
            'why': _clean_text(entry.get('why'), limit=280),
            'tip': _clean_text(entry.get('tip'), limit=200),
        })
        if len(outfits) == 3:
            break

    if not outfits:
        raise GeminiError(
            'The fashion AI could not build an outfit from these pieces. '
            'Add a few more tops, bottoms, or a dress and try again.'
        )
    return outfits
