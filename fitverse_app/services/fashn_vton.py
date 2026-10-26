import shutil
import tempfile
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

from django.conf import settings


class FashnVtonError(Exception):
    """Raised when the FASHN VTON Space cannot produce a result."""


@lru_cache(maxsize=1)
def _client():
    try:
        from gradio_client import Client
    except ImportError as exc:
        raise FashnVtonError(
            "The FASHN client is not installed. Run `python -m pip install -r requirements.txt`."
        ) from exc

    space = getattr(settings, "FASHN_VTON_SPACE", "fashn-ai/fashn-vton-1.5")
    token = getattr(settings, "HF_TOKEN", "") or None
    try:
        return Client(space, hf_token=token, verbose=False)
    except Exception as exc:
        raise FashnVtonError("Could not connect to the FASHN VTON Hugging Face Space.") from exc


def _input(value):
    from gradio_client import handle_file

    if hasattr(value, "temporary_file_path"):
        return handle_file(value.temporary_file_path())
    return handle_file(str(value))


def _uploaded_file_path(uploaded_file):
    if hasattr(uploaded_file, "temporary_file_path"):
        return uploaded_file.temporary_file_path(), None

    temporary_file = tempfile.NamedTemporaryFile(
        prefix="fitverse-vton-",
        suffix=Path(uploaded_file.name).suffix,
        delete=False,
    )
    for chunk in uploaded_file.chunks():
        temporary_file.write(chunk)
    temporary_file.close()
    return temporary_file.name, temporary_file.name


def generate_try_on(
    *,
    person_image,
    garment_image,
    category,
    garment_photo_type="model",
    num_timesteps=30,
    guidance_scale=1.5,
    seed=42,
    segmentation_free=True,
):
    if category not in {"tops", "bottoms", "one-pieces"}:
        raise FashnVtonError("Unsupported garment category.")
    if garment_photo_type not in {"model", "flat-lay"}:
        raise FashnVtonError("Unsupported garment photo type.")

    temporary_paths = []
    try:
        if hasattr(person_image, "read"):
            person_image, temporary_path = _uploaded_file_path(person_image)
            if temporary_path:
                temporary_paths.append(temporary_path)
        if hasattr(garment_image, "read"):
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
            api_name="/try_on",
        )
    except Exception as exc:
        raise FashnVtonError("FASHN VTON inference failed. Please try again.") from exc
    finally:
        for temporary_path in temporary_paths:
            Path(temporary_path).unlink(missing_ok=True)

    result_path = result.get("path") if isinstance(result, dict) else result
    if not result_path or not Path(result_path).is_file():
        raise FashnVtonError("FASHN VTON returned an invalid image result.")

    output_dir = Path(settings.MEDIA_ROOT) / "tryons"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{uuid4().hex}.png"
    shutil.copyfile(result_path, output_path)
    return f"{settings.MEDIA_URL}tryons/{output_path.name}"
