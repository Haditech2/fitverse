import json
import tempfile
from pathlib import Path
from urllib.request import urlopen
from uuid import uuid4

from django.conf import settings


class GeminiError(Exception):
    """Raised when Gemini cannot produce the requested result."""


def _client():
    api_key = getattr(settings, "GEMINI_API_KEY", "")
    if not api_key:
        raise GeminiError("Gemini is not configured. Add GEMINI_API_KEY to .env.")
    try:
        from google import genai
        from google.genai import types
        return genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=60000),
        )
    except ImportError as exc:
        raise GeminiError(
            "The Gemini client is not installed. Run `python -m pip install -r requirements.txt`."
        ) from exc
    except Exception as exc:
        raise GeminiError("Could not initialize the Gemini client.") from exc


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
    try:
        response = _client().models.generate_content(
            model=getattr(settings, "GEMINI_TEXT_MODEL", "gemini-2.5-flash"),
            contents=prompt,
        )
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
    except Exception as exc:
        raise GeminiError("Gemini stylist request failed. Please try again.") from exc


def _image_bytes(value):
    if hasattr(value, "read"):
        value.seek(0)
        return value.read(), getattr(value, "content_type", "image/jpeg")
    try:
        with urlopen(str(value), timeout=20) as response:
            return response.read(), response.headers.get_content_type()
    except Exception as exc:
        raise GeminiError("Could not read the garment image.") from exc


def generate_try_on(*, person_image, garment_image, category):
    person_bytes, person_mime = _image_bytes(person_image)
    garment_bytes, garment_mime = _image_bytes(garment_image)
    prompt = (
        "Create a realistic virtual try-on image. Put the garment from the second "
        "image onto the person in the first image. Preserve the person's face, pose, "
        "body proportions, background, and lighting. Show the complete outfit clearly. "
        f"Garment category: {category}. Do not add text, logos, or extra people."
    )
    try:
        from google.genai import types

        response = _client().models.generate_content(
            model=getattr(settings, "GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image"),
            contents=[
                types.Part.from_bytes(data=person_bytes, mime_type=person_mime),
                types.Part.from_bytes(data=garment_bytes, mime_type=garment_mime),
                prompt,
            ],
            config=types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
        )
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
        raise GeminiError("Gemini try-on generation failed. Please try again.") from exc
