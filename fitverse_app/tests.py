import base64
import json
import shutil
import tempfile
from io import BytesIO
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from PIL import Image

from . import views
from .models import Category, Design, UserMeasurement, WardrobeItem
from .services import bodygram, fashn_vton, gemini_ai, look360, wardrobe


class FabricDesignChatTests(SimpleTestCase):
    @override_settings(FASHN_API_KEY='test-key')
    def test_fashn_agent_receives_fabric_reference_and_design_brief(self):
        directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        result = {'status': 'completed', 'predictions': [
            {'status': 'completed', 'results': ['data:image/png;base64,cG5n']}
        ]}
        with override_settings(MEDIA_ROOT=directory), mock.patch.object(
            fashn_vton, '_api_request', return_value=result
        ) as request, mock.patch.object(fashn_vton, '_download_output', return_value=b'png'):
            image = fashn_vton.generate_fabric_design(
                fabric_bytes=b'jpeg', prompt='Long sleeve gown', occasion='wedding', style='ankara'
            )
        self.assertTrue(image.startswith('/media/designs/'))
        self.assertEqual(request.call_args.args[0], '/agent/images')
        payload = request.call_args.kwargs['payload']
        self.assertIn('Long sleeve gown', payload['prompt'])
        self.assertEqual(payload['images'], ['data:image/jpeg;base64,anBlZw=='])
        self.assertEqual(payload['generation_mode'], 'fast')

    def test_uploaded_fabric_and_brief_reach_design_generator(self):
        photo = BytesIO()
        Image.new('RGB', (80, 80), '#9a2444').save(photo, format='PNG')
        upload = SimpleUploadedFile('fabric.png', photo.getvalue(), content_type='image/png')
        with mock.patch.object(views, 'generate_fabric_design', return_value='/media/designs/new.png') as generate:
            response = self.client.post('/api/stylist/design/', {
                'fabric': upload,
                'message': 'Long sleeve wedding gown',
                'occasion': 'wedding',
                'style': 'ankara',
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['image'], '/media/designs/new.png')
        self.assertEqual(generate.call_args.kwargs['prompt'], 'Long sleeve wedding gown')
        self.assertTrue(generate.call_args.kwargs['fabric_bytes'].startswith(b'\xff\xd8'))

    def test_design_requires_fabric(self):
        response = self.client.post('/api/stylist/design/', {'message': 'A gown'})
        self.assertEqual(response.status_code, 400)


class TryOnFallbackTests(SimpleTestCase):
    """Provider selection and fallback behaviour for _generate_try_on."""

    def setUp(self):
        self.person = BytesIO(b"person-bytes")
        self.garment = BytesIO(b"garment-bytes")

    def _call(self):
        return views._generate_try_on(
            person_image=self.person,
            garment_image=self.garment,
            category="one-pieces",
            garment_photo_type="model",
        )

    @override_settings(AI_PROVIDER="gemini", TRYON_PROVIDER="", GEMINI_API_KEY="test-key")
    def test_gemini_result_is_used_when_available(self):
        with mock.patch.object(
            views, "generate_gemini_try_on", return_value="/media/tryons/gemini.png"
        ) as gemini, mock.patch.object(views, "generate_try_on") as fashn:
            result = self._call()

        self.assertEqual(result, ("/media/tryons/gemini.png", "gemini"))
        gemini.assert_called_once()
        fashn.assert_not_called()

    @override_settings(AI_PROVIDER="gemini", TRYON_PROVIDER="", GEMINI_API_KEY="test-key")
    def test_gemini_failure_falls_back_to_fashn(self):
        with mock.patch.object(
            views, "generate_gemini_try_on", side_effect=views.GeminiError("quota exhausted")
        ), mock.patch.object(
            views, "generate_try_on", return_value="/media/tryons/fashn.png"
        ) as fashn:
            result = self._call()

        self.assertEqual(result, ("/media/tryons/fashn.png", "fashn"))
        fashn.assert_called_once()

    @override_settings(AI_PROVIDER="gemini", TRYON_PROVIDER="", GEMINI_API_KEY="test-key")
    def test_uploads_are_rewound_before_fallback(self):
        # Gemini consumes the upload streams, so the fallback must still receive full bytes.
        def consume(**kwargs):
            kwargs["person_image"].read()
            kwargs["garment_image"].read()
            raise views.GeminiError("quota exhausted")

        captured = {}

        def capture(**kwargs):
            captured["person"] = kwargs["person_image"].read()
            captured["garment"] = kwargs["garment_image"].read()
            return "/media/tryons/fashn.png"

        with mock.patch.object(views, "generate_gemini_try_on", side_effect=consume), \
                mock.patch.object(views, "generate_try_on", side_effect=capture):
            self._call()

        self.assertEqual(captured["person"], b"person-bytes")
        self.assertEqual(captured["garment"], b"garment-bytes")

    @override_settings(AI_PROVIDER="fashn", GEMINI_API_KEY="test-key")
    def test_explicit_fashn_provider_skips_gemini(self):
        with mock.patch.object(views, "generate_gemini_try_on") as gemini, \
                mock.patch.object(views, "generate_try_on", return_value="/media/tryons/fashn.png"):
            result = self._call()

        self.assertEqual(result, ("/media/tryons/fashn.png", "fashn"))
        gemini.assert_not_called()

    @override_settings(AI_PROVIDER="gemini", TRYON_PROVIDER="fashn", GEMINI_API_KEY="test-key")
    def test_try_on_provider_overrides_the_stylist_provider(self):
        with mock.patch.object(views, "generate_gemini_try_on") as gemini, \
                mock.patch.object(views, "generate_try_on", return_value="/media/tryons/fashn.png"):
            result = self._call()

        self.assertEqual(result, ("/media/tryons/fashn.png", "fashn"))
        gemini.assert_not_called()

    @override_settings(AI_PROVIDER="gemini", GEMINI_API_KEY="")
    def test_missing_gemini_key_uses_fashn(self):
        with mock.patch.object(views, "generate_gemini_try_on") as gemini, \
                mock.patch.object(views, "generate_try_on", return_value="/media/tryons/fashn.png"):
            result = self._call()

        self.assertEqual(result, ("/media/tryons/fashn.png", "fashn"))
        gemini.assert_not_called()

    @override_settings(AI_PROVIDER="gemini", TRYON_PROVIDER="", GEMINI_API_KEY="test-key")
    def test_both_providers_failing_raises_try_on_error(self):
        with mock.patch.object(
            views, "generate_gemini_try_on", side_effect=views.GeminiError("quota exhausted")
        ), mock.patch.object(
            views, "generate_try_on", side_effect=views.FashnVtonError("space offline")
        ):
            with self.assertRaises(views.TryOnError) as caught:
                self._call()

        message = str(caught.exception)
        self.assertIn("quota exhausted", message)
        self.assertIn("space offline", message)


class TryOnApiTests(TestCase):
    """The JSON contract the frontend relies on."""

    def _post(self):
        person = SimpleUploadedFile("person.png", b"fake-image-bytes", content_type="image/png")
        return self.client.post(
            "/api/vton/tryon/",
            {
                "person_image": person,
                "garment_image_url": "https://example.com/garment.jpg",
                "category": "one-pieces",
                "model_preset": "custom",
            },
        )

    def test_success_response_includes_provider(self):
        with mock.patch.object(
            views, "_generate_try_on", return_value=("/media/tryons/out.png", "fashn")
        ):
            response = self._post()

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertEqual(payload["result_image"], "/media/tryons/out.png")
        self.assertEqual(payload["provider"], "fashn")

    def test_provider_failure_returns_503_with_message(self):
        with mock.patch.object(
            views, "_generate_try_on", side_effect=views.TryOnError("Gemini: quota exhausted | FASHN VTON: offline")
        ):
            response = self._post()

        self.assertEqual(response.status_code, 503)
        self.assertIn("quota exhausted", json.loads(response.content)["error"])

    def test_missing_person_image_returns_400(self):
        response = self.client.post(
            "/api/vton/tryon/",
            {
                "garment_image_url": "https://example.com/garment.jpg",
                "category": "one-pieces",
            },
        )

        self.assertEqual(response.status_code, 400)


class Look360ApiTests(TestCase):
    """The image-to-3D relay keeps the key private and never duplicates a task."""

    def setUp(self):
        media_root = tempfile.mkdtemp(prefix="fitverse-look360-")
        self.media_root = Path(media_root)
        self.addCleanup(shutil.rmtree, media_root, True)
        self.media_override = override_settings(MEDIA_ROOT=media_root)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        cache.clear()
        self.addCleanup(cache.clear)

        category = Category.objects.create(name="Test", slug="test")
        self.design = Design.objects.create(
            title="Test Design",
            slug="test-design",
            category=category,
            image_url="https://example.com/design.webp",
            description="A test design.",
        )
        self.url = "/api/look360/designs/test-design/"

    def _post(self, payload=None):
        return self.client.post(
            self.url,
            data=json.dumps(payload or {}),
            content_type="application/json",
        )

    def test_missing_key_returns_clearly_labelled_demo(self):
        with mock.patch.object(look360, "get_api_key", return_value=""):
            response = self._post()

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["state"], "ready")
        self.assertTrue(payload["demo"])
        self.assertEqual(payload["model_url"], look360.DEMO_MODEL_URL)

    def test_pending_task_is_reused_after_cache_reset(self):
        pending = {"status": "PENDING", "progress": 12}
        with mock.patch.object(look360, "get_api_key", return_value="key"), \
                mock.patch.object(look360, "create_task", return_value="task-123") as create, \
                mock.patch.object(look360, "get_task", return_value=pending):
            first = self._post().json()
            cache.clear()  # simulate an autoreload/new worker
            second = self._post().json()

        self.assertEqual(first["task_id"], "task-123")
        self.assertEqual(second["task_id"], "task-123")
        create.assert_called_once()

    def test_successful_model_is_saved_under_media(self):
        complete = {
            "status": "SUCCEEDED",
            "progress": 100,
            "model_urls": {"glb": "https://example.com/model.glb"},
        }
        model_bytes = b"glTF" + (b"\x00" * 32)
        with mock.patch.object(look360, "get_api_key", return_value="key"), \
                mock.patch.object(look360, "create_task", return_value="task-456"), \
                mock.patch.object(look360, "get_task", return_value=complete), \
                mock.patch.object(look360, "download_model", return_value=model_bytes):
            response = self._post()

        payload = response.json()
        self.assertEqual(payload["state"], "ready")
        self.assertFalse(payload["demo"])
        self.assertEqual(payload["model_url"], "/media/look360/test-design.glb")
        self.assertTrue((self.media_root / "look360" / "test-design.glb").is_file())


class GeminiServiceTests(SimpleTestCase):
    """Model fallback and input handling for the Gemini client."""

    class _Response:
        text = '{"advice": "Wear the senator set.", "recommended_ids": ["1"]}'

    class _Models:
        def __init__(self, failing):
            self.calls = []
            self.failing = failing

        def generate_content(self, *, model, contents, config=None):
            self.calls.append(model)
            if model in self.failing:
                raise RuntimeError(self.failing[model])
            return GeminiServiceTests._Response()

    class _Client:
        def __init__(self, failing):
            self.models = GeminiServiceTests._Models(failing)

    catalog = [{"id": "1", "title": "Modern Senator Set"}]

    def _stylist(self):
        return gemini_ai.generate_stylist_response(
            message="wedding outfit",
            occasion="wedding",
            style="traditional",
            budget=50000,
            catalog=self.catalog,
        )

    @override_settings(
        GEMINI_TEXT_MODEL="primary-model",
        GEMINI_TEXT_FALLBACKS=("backup-model",),
    )
    def test_overloaded_primary_model_falls_back(self):
        client = self._Client({"primary-model": "503 UNAVAILABLE. This model is currently experiencing high demand."})
        with mock.patch.object(gemini_ai, "_client", return_value=client):
            advice, looks = self._stylist()

        self.assertEqual(client.models.calls, ["primary-model", "backup-model"])
        self.assertIn("senator", advice.lower())
        self.assertEqual([item["id"] for item in looks], ["1"])

    @override_settings(
        GEMINI_TEXT_MODEL="retired-model",
        GEMINI_TEXT_FALLBACKS=("backup-model",),
    )
    def test_unknown_primary_model_does_not_fall_back(self):
        client = self._Client({"retired-model": "404 NOT_FOUND. This model is no longer available to new users."})
        with mock.patch.object(gemini_ai, "_client", return_value=client):
            with self.assertRaises(gemini_ai.GeminiError) as caught:
                self._stylist()

        self.assertEqual(client.models.calls, ["retired-model"])
        self.assertIn("unavailable", str(caught.exception).lower())

    def test_local_image_path_is_read(self):
        directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        path = Path(directory) / "person.png"
        path.write_bytes(b"png-bytes")

        data, mime_type = gemini_ai._image_bytes(str(path), label="person")

        self.assertEqual(data, b"png-bytes")
        self.assertEqual(mime_type, "image/png")

    @override_settings(GEMINI_IMAGE_MODEL="image-model")
    def test_image_quota_message_explains_free_tier(self):
        client = self._Client({"image-model": "429 RESOURCE_EXHAUSTED. quota exceeded, limit: 0"})
        with mock.patch.object(gemini_ai, "_client", return_value=client):
            with self.assertRaises(gemini_ai.GeminiError) as caught:
                gemini_ai.generate_try_on(
                    person_image=BytesIO(b"person"),
                    garment_image=BytesIO(b"garment"),
                    category="one-pieces",
                )

        self.assertIn("free tier", str(caught.exception).lower())


class BodygramServiceTests(SimpleTestCase):
    """Bodygram payload shape and measurement mapping."""

    ENTRY = {
        "id": "scan_1",
        "status": "success",
        "measurements": [
            {"name": "bustGirth", "unit": "mm", "value": 965},
            {"name": "waistGirth", "unit": "mm", "value": 821},
            {"name": "hipGirth", "unit": "mm", "value": 1004},
            {"name": "acrossBackShoulderWidth", "unit": "mm", "value": 461},
            {"name": "outerArmLengthR", "unit": "mm", "value": 643},
            {"name": "insideLegLengthR", "unit": "mm", "value": 812},
            {"name": "neckGirth", "unit": "mm", "value": 392},
        ],
        "bodyComposition": {"bodyFatPercentage": 20.0, "skeletalMuscleMass": 30000},
        "input": {"photoScan": {"age": 29, "gender": "male", "height": 1800, "weight": 75000}},
        "avatar": {
            "format": "obj",
            "type": "highResolution",
            "data": base64.b64encode(b"v 0 0 0\n").decode("ascii"),
        },
        "posture": {
            "front": {"angles": [{"name": "shoulder", "unit": "degrees", "value": -1.5}], "lines": []},
            "right": {"angles": [{"name": "bodyLine", "unit": "degrees", "angles": [0.5, 1.0, 2.0, 3.0]}], "lines": []},
        },
    }

    def _estimate(self):
        return bodygram.estimate_measurements(
            front_photo=b"front-bytes",
            right_photo=b"right-bytes",
            age=29,
            gender="male",
            height_cm=180,
            weight_kg=75,
        )

    @override_settings(BODYGRAM_ORG_ID="org", BODYGRAM_API_KEY="key")
    def test_maps_vendor_measurements_to_profile_fields(self):
        with mock.patch.object(bodygram, "_post", return_value={"entry": self.ENTRY}) as post:
            result = self._estimate()

        self.assertEqual(result["measurements"], {
            "chest": 96.5,
            "waist": 82.1,
            "hips": 100.4,
            "shoulder": 46.1,
            "sleeve": 64.3,
            "inseam": 81.2,
            "neck": 39.2,
        })
        self.assertEqual(result["scan_id"], "scan_1")
        self.assertEqual(result["body_composition"], self.ENTRY["bodyComposition"])

        by_name = {item["name"]: item for item in result["all_measurements"]}
        self.assertEqual(len(result["all_measurements"]), 7)
        self.assertEqual(by_name["bustGirth"]["value"], 96.5)
        self.assertEqual(by_name["bustGirth"]["label"], "Bust")
        self.assertEqual(by_name["bustGirth"]["group"], "Circumferences")
        self.assertEqual(by_name["bustGirth"]["profile_field"], "chest")
        self.assertEqual(by_name["acrossBackShoulderWidth"]["group"], "Widths & depths")
        self.assertEqual(by_name["outerArmLengthR"]["group"], "Lengths")
        self.assertEqual(by_name["insideLegLengthR"]["group"], "Lengths")

        url, api_key, payload = post.call_args.args
        self.assertEqual(url, "https://platform.bodygram.com/api/orgs/org/scans")
        self.assertEqual(api_key, "key")
        self.assertEqual(payload["photoScan"]["height"], 1800)   # cm -> mm
        self.assertEqual(payload["photoScan"]["weight"], 75000)  # kg -> g
        self.assertEqual(payload["photoScan"]["frontPhoto"], "ZnJvbnQtYnl0ZXM=")

    @override_settings(BODYGRAM_ORG_ID="org", BODYGRAM_API_KEY="key")
    def test_failed_scan_raises_bodygram_error(self):
        with mock.patch.object(bodygram, "_post", return_value={"entry": {"status": "failure"}}):
            with self.assertRaisesMessage(bodygram.BodygramError, "could not estimate"):
                self._estimate()

    def test_normalize_photo_crops_landscape_to_9x16(self):
        data = bodygram.normalize_photo(self._photo(1600, 900))
        with Image.open(BytesIO(data)) as image:
            self.assertEqual(image.size, (1080, 1920))

    def test_normalize_photo_trims_images_taller_than_9x16(self):
        data = bodygram.normalize_photo(self._photo(800, 2000))
        with Image.open(BytesIO(data)) as image:
            self.assertEqual(image.size, (1080, 1920))

    def test_normalize_photo_keeps_exact_9x16(self):
        data = bodygram.normalize_photo(self._photo(1080, 1920))
        with Image.open(BytesIO(data)) as image:
            self.assertEqual(image.size, (1080, 1920))

    def test_normalize_photo_returns_none_for_unknown_bytes(self):
        self.assertIsNone(bodygram.normalize_photo(b"not-an-image"))

    @staticmethod
    def _photo(width, height):
        buffer = BytesIO()
        Image.new("RGB", (width, height), (90, 100, 110)).save(buffer, format="PNG")
        return buffer.getvalue()

    @override_settings(BODYGRAM_ORG_ID="", BODYGRAM_API_KEY="")
    def test_missing_credentials_raises_clear_error(self):
        with self.assertRaisesMessage(bodygram.BodygramError, "not configured"):
            self._estimate()

    @override_settings(BODYGRAM_ORG_ID="org", BODYGRAM_API_KEY="key")
    def test_skips_missing_measurements(self):
        entry = {"id": "scan_2", "status": "success", "measurements": [
            {"name": "waistGirth", "unit": "mm", "value": 800},
        ]}
        with mock.patch.object(bodygram, "_post", return_value={"entry": entry}):
            result = self._estimate()

        self.assertEqual(result["measurements"], {"waist": 80.0})

    @override_settings(BODYGRAM_ORG_ID="org", BODYGRAM_API_KEY="key")
    def test_right_side_measurements_group_by_base_name(self):
        entry = {"id": "scan_3", "status": "success", "measurements": [
            {"name": "waistGirth", "unit": "mm", "value": 800},
            {"name": "calfGirthR", "unit": "mm", "value": 350},
            {"name": "kneeHeightR", "unit": "mm", "value": 440},
            {"name": "outseamR", "unit": "mm", "value": 980},
        ]}
        with mock.patch.object(bodygram, "_post", return_value={"entry": entry}):
            result = self._estimate()

        groups = {item["name"]: item["group"] for item in result["all_measurements"]}
        self.assertEqual(groups["calfGirthR"], "Circumferences")
        self.assertEqual(groups["kneeHeightR"], "Heights")
        self.assertEqual(groups["outseamR"], "Lengths")

    @override_settings(BODYGRAM_ORG_ID="org", BODYGRAM_API_KEY="key")
    def test_fetch_scan_reads_existing_scan_without_creating(self):
        with mock.patch.object(bodygram, "_get", return_value={"entry": self.ENTRY}) as get:
            result = bodygram.fetch_scan("scan_1")

        url, api_key = get.call_args.args
        self.assertEqual(url, "https://platform.bodygram.com/api/orgs/org/scans/scan_1")
        self.assertEqual(api_key, "key")
        self.assertEqual(result["scan_id"], "scan_1")
        self.assertEqual(len(result["all_measurements"]), 7)
        self.assertEqual(result["stats"], {
            "age": 29,
            "gender": "male",
            "height_cm": 180.0,
            "weight_kg": 75.0,
        })
        self.assertEqual(result["avatar_obj"], b"v 0 0 0\n")
        self.assertEqual(result["posture"]["front"]["angles"][0]["name"], "shoulder")

    @override_settings(BODYGRAM_ORG_ID="org", BODYGRAM_API_KEY="key")
    def test_fetch_scan_encodes_the_scan_id(self):
        with mock.patch.object(bodygram, "_get", return_value={"entry": self.ENTRY}) as get:
            bodygram.fetch_scan("scan/1")

        self.assertTrue(get.call_args.args[0].endswith("/scans/scan%2F1"))


class BodygramEndpointTests(TestCase):
    def setUp(self):
        media_root = tempfile.mkdtemp(prefix="fitverse-bodygram-")
        self.addCleanup(shutil.rmtree, media_root, True)
        self.media_override = override_settings(MEDIA_ROOT=media_root)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)

    def _post(self, **overrides):
        data = {
            "front_photo": SimpleUploadedFile("front.jpg", b"front-bytes", content_type="image/jpeg"),
            "right_photo": SimpleUploadedFile("right.jpg", b"right-bytes", content_type="image/jpeg"),
            "age": "29",
            "gender": "male",
            "height": "180",
            "weight": "75",
        }
        data.update(overrides)
        return self.client.post("/api/measurements/bodygram/", data)

    def test_scan_saves_measurements_to_profile(self):
        result = {
            "scan_id": "scan_1",
            "measurements": {"chest": 101.2, "waist": 88.4},
            "all_measurements": [
                {"name": "bustGirth", "label": "Bust", "group": "Circumferences",
                 "value": 101.2, "profile_field": "chest"},
                {"name": "waistGirth", "label": "Waist", "group": "Circumferences",
                 "value": 88.4, "profile_field": "waist"},
                {"name": "calfGirthR", "label": "Right calf", "group": "Circumferences",
                 "value": 35.0, "profile_field": ""},
            ],
            "body_composition": {"bodyFatPercentage": 24.3, "skeletalMuscleMass": 30000},
            "posture": {
                "front": {"angles": [{"name": "shoulder", "unit": "degrees", "value": -1.5}]},
                "right": {"angles": [{"name": "bodyLine", "unit": "degrees", "angles": [0.5, 1.0, 2.0, 3.0]}]},
            },
            "avatar_obj": b"v 0 0 0\n",
        }
        with mock.patch.object(views, "estimate_measurements", return_value=result):
            response = self._post()

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertEqual(payload["measurements"]["chest"], 101.2)
        self.assertEqual(payload["scan_id"], "scan_1")
        self.assertEqual(len(payload["all_measurements"]), 3)
        self.assertTrue(payload["avatar_url"].endswith("scan_1.obj"))
        self.assertEqual(payload["height_cm"], 180.0)
        self.assertTrue(payload["front_photo_url"].endswith("scan_1-front.jpg"))
        self.assertTrue(payload["right_photo_url"].endswith("scan_1-right.jpg"))
        self.assertEqual(payload["posture"]["front"]["angles"][0]["name"], "shoulder")

        saved = UserMeasurement.objects.get()
        self.assertEqual(saved.chest, 101.2)
        self.assertEqual(saved.waist, 88.4)
        self.assertEqual(saved.age, 29)
        self.assertEqual(saved.gender, "male")
        self.assertEqual(saved.height_cm, 180.0)
        self.assertEqual(saved.weight_kg, 75.0)
        self.assertEqual(saved.unit, "cm")
        self.assertEqual(saved.bodygram_scan_id, "scan_1")
        self.assertEqual(len(saved.bodygram_measurements), 3)
        self.assertEqual(saved.bodygram_measurements[2]["label"], "Right calf")
        self.assertEqual(saved.body_composition["bodyFatPercentage"], 24.3)
        self.assertEqual(saved.bodygram_posture["front"]["angles"][0]["name"], "shoulder")
        self.assertTrue(saved.bodygram_avatar.name.endswith("scan_1.obj"))
        self.assertTrue(saved.bodygram_front_photo.name.endswith("scan_1-front.jpg"))
        self.assertTrue(saved.bodygram_right_photo.name.endswith("scan_1-right.jpg"))
        self.assertTrue(saved.bodygram_avatar.storage.exists(saved.bodygram_avatar.name))
        self.assertIsNotNone(saved.bodygram_scanned_at)

    def test_delete_photos_removes_stored_files(self):
        result = {
            "scan_id": "scan_del",
            "measurements": {"chest": 100.0},
            "all_measurements": [],
            "body_composition": None,
            "posture": None,
            "avatar_obj": None,
        }
        with mock.patch.object(views, "estimate_measurements", return_value=result):
            self._post()

        saved = UserMeasurement.objects.get()
        storage = saved.bodygram_front_photo.storage
        front_name = saved.bodygram_front_photo.name
        self.assertTrue(storage.exists(front_name))

        response = self.client.post("/api/measurements/bodygram/photos/delete/")

        self.assertEqual(response.status_code, 200)
        saved.refresh_from_db()
        self.assertFalse(saved.bodygram_front_photo)
        self.assertFalse(saved.bodygram_right_photo)
        self.assertFalse(storage.exists(front_name))

    def test_avatar_is_stored_once_per_scan(self):
        result = {
            "scan_id": "scan_shared",
            "measurements": {"chest": 100.0},
            "all_measurements": [],
            "body_composition": None,
            "posture": None,
            "avatar_obj": b"v 0 0 0\n",
        }
        with mock.patch.object(views, "estimate_measurements", return_value=result):
            self._post()
            self._post()

        saved = UserMeasurement.objects.get()
        storage = saved.bodygram_avatar.storage
        folder = saved.bodygram_avatar.name.rsplit("/", 1)[0]
        self.assertEqual(storage.listdir(folder)[1], ["scan_shared.obj"])

    def test_measurements_page_shows_saved_bodygram_results(self):
        self.client.get("/measurements/")
        saved = UserMeasurement.objects.get()
        saved.bodygram_scan_id = "scan_saved"
        saved.bodygram_measurements = [
            {"name": "bustGirth", "label": "Bust", "group": "Circumferences",
             "value": 96.5, "profile_field": "chest"},
        ]
        saved.body_composition = {"bodyFatPercentage": 25.5}
        saved.bodygram_posture = {"front": {"angles": [{"name": "shoulder", "value": -1.5}]}}
        saved.bodygram_avatar.save("scan_saved.obj", ContentFile(b"v 0 0 0\n"), save=False)
        saved.bodygram_front_photo.save("scan_saved-front.jpg", ContentFile(b"front"), save=False)
        saved.bodygram_scanned_at = timezone.now()
        saved.save()

        response = self.client.get("/measurements/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "bodygram-all")
        self.assertContains(response, "bodygram-cards")
        self.assertContains(response, "bodygram-visuals")
        self.assertContains(response, "bodygram-posture")
        self.assertContains(response, "bodygram-posture-front")
        self.assertContains(response, "bodygram-posture-side")
        self.assertContains(response, "scan_saved")
        self.assertContains(response, "shoulder")
        self.assertContains(response, "height_cm")

    def test_missing_photo_returns_400(self):
        response = self.client.post("/api/measurements/bodygram/", {"age": "29", "gender": "male", "height": "180", "weight": "75"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("front photo", json.loads(response.content)["error"])

    def test_vendor_failure_returns_503(self):
        with mock.patch.object(
            views, "estimate_measurements", side_effect=bodygram.BodygramError("quota exhausted")
        ):
            response = self._post()

        self.assertEqual(response.status_code, 503)
        self.assertIn("quota exhausted", json.loads(response.content)["error"])

    def test_invalid_stats_return_400(self):
        response = self._post(age="5")
        self.assertEqual(response.status_code, 400)
        self.assertIn("age", json.loads(response.content)["error"])

    def test_landscape_upload_is_normalized_before_bodygram(self):
        result = {
            "scan_id": "scan_ratio",
            "measurements": {"chest": 100.0},
            "all_measurements": [],
            "body_composition": None,
            "posture": None,
            "avatar_obj": None,
        }
        with mock.patch.object(views, "estimate_measurements", return_value=result) as estimate:
            response = self._post(
                front_photo=SimpleUploadedFile(
                    "front.png", self._photo(1200, 900), content_type="image/png"
                ),
                right_photo=SimpleUploadedFile(
                    "right.png", self._photo(900, 900), content_type="image/png"
                ),
            )

        self.assertEqual(response.status_code, 200)
        for key in ("front_photo", "right_photo"):
            with Image.open(BytesIO(estimate.call_args.kwargs[key])) as image:
                self.assertEqual(image.size, (1080, 1920))
                self.assertEqual(image.format, "JPEG")

        saved = UserMeasurement.objects.get()
        self.assertTrue(saved.bodygram_front_photo.name.endswith(".jpg"))
        self.assertTrue(saved.bodygram_right_photo.name.endswith(".jpg"))

    @staticmethod
    def _photo(width, height):
        buffer = BytesIO()
        Image.new("RGB", (width, height), (120, 110, 100)).save(buffer, format="PNG")
        return buffer.getvalue()


class FashnApiTests(SimpleTestCase):
    """Official FASHN API transport (used whenever FASHN_API_KEY is set)."""

    def setUp(self):
        media_root = tempfile.mkdtemp(prefix="fitverse-fashn-")
        self.addCleanup(shutil.rmtree, media_root, True)
        self.media_override = override_settings(MEDIA_ROOT=media_root)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)

        self.person = SimpleUploadedFile(
            "person.jpg", b"person-bytes", content_type="image/jpeg"
        )
        self.garment = SimpleUploadedFile(
            "garment.jpg", b"garment-bytes", content_type="image/jpeg"
        )

    def _call(self, **overrides):
        kwargs = {
            "person_image": self.person,
            "garment_image": self.garment,
            "category": "tops",
        }
        kwargs.update(overrides)
        return fashn_vton.generate_try_on(**kwargs)

    @override_settings(FASHN_API_KEY="test-key")
    def test_payload_uses_data_uris_and_saves_the_result(self):
        responses = [
            {"id": "pred_1"},
            {"status": "processing", "error": None},
            {"status": "completed", "output": ["https://cdn.fashn.ai/pred_1/output_0.png"]},
        ]
        with mock.patch.object(
            fashn_vton, "_api_request", side_effect=responses
        ) as api, mock.patch.object(
            fashn_vton, "_download_output", return_value=b"png-bytes"
        ) as download, mock.patch.object(fashn_vton.time, "sleep"):
            url = self._call()

        payload = api.call_args_list[0].kwargs["payload"]
        self.assertEqual(payload["model_name"], "tryon-v1.6")
        inputs = payload["inputs"]
        self.assertTrue(inputs["model_image"].startswith("data:image/jpeg;base64,"))
        self.assertTrue(inputs["garment_image"].startswith("data:image/jpeg;base64,"))
        self.assertEqual(inputs["category"], "tops")
        self.assertEqual(inputs["output_format"], "png")
        self.assertTrue(inputs["return_base64"])
        self.assertEqual(api.call_args_list[1].args[0], "/status/pred_1")

        download.assert_called_once_with("https://cdn.fashn.ai/pred_1/output_0.png")
        self.assertTrue(url.startswith("/media/tryons/"))
        saved = Path(self.media_override.options["MEDIA_ROOT"], "tryons", url.rsplit("/", 1)[1])
        self.assertEqual(saved.read_bytes(), b"png-bytes")

    @override_settings(FASHN_API_KEY="test-key")
    def test_runtime_pose_error_has_a_clear_message(self):
        responses = [
            {"id": "pred_2"},
            {"status": "failed", "error": {"name": "PoseError", "message": "No pose detected"}},
        ]
        with mock.patch.object(fashn_vton, "_api_request", side_effect=responses), mock.patch.object(
            fashn_vton.time, "sleep"
        ):
            with self.assertRaisesMessage(fashn_vton.FashnVtonError, "full-body pose"):
                self._call()

    def test_invalid_key_is_reported_clearly(self):
        error = HTTPError(
            "https://api.fashn.ai/v1/run",
            401,
            "Unauthorized",
            {},
            BytesIO(b'{"error":"UnauthorizedAccess","message":"Unauthorized: Invalid token"}'),
        )
        self.assertIn("API key", str(fashn_vton._http_error(error)))

    def test_out_of_credits_is_reported_clearly(self):
        error = HTTPError(
            "https://api.fashn.ai/v1/run",
            429,
            "Too Many Requests",
            {},
            BytesIO(b'{"error":"OutOfCredits","message":"No API credits remaining"}'),
        )
        self.assertIn("credits are used up", str(fashn_vton._http_error(error)))

    def test_base64_output_is_decoded(self):
        data_uri = "data:image/png;base64," + base64.b64encode(b"png-bytes").decode("ascii")
        self.assertEqual(fashn_vton._download_output(data_uri), b"png-bytes")

    @override_settings(FASHN_API_KEY="")
    def test_without_a_key_the_free_space_is_used(self):
        with mock.patch.object(
            fashn_vton, "_generate_via_space", return_value="/media/tryons/space.png"
        ) as space:
            url = self._call(garment_photo_type="flat-lay")

        self.assertEqual(url, "/media/tryons/space.png")
        space.assert_called_once()
        self.assertFalse(fashn_vton.get_api_key())


class WardrobeServiceTests(SimpleTestCase):
    """Photo normalisation for personal wardrobe uploads."""

    def _image_bytes(self, size=(320, 400), colour=(190, 40, 45), fmt="JPEG"):
        buffer = BytesIO()
        Image.new("RGB", size, colour).save(buffer, format=fmt)
        return buffer.getvalue()

    def test_prepare_photo_returns_full_photo_thumbnail_and_colour(self):
        prepared = wardrobe.prepare_photo(self._image_bytes())

        self.assertTrue(prepared.full.startswith(b"\xff\xd8"))
        self.assertTrue(prepared.thumb.startswith(b"\xff\xd8"))
        self.assertLess(len(prepared.thumb), len(prepared.full))
        self.assertEqual(prepared.colour, "red")

        with Image.open(BytesIO(prepared.full)) as full, Image.open(BytesIO(prepared.thumb)) as thumb:
            self.assertLessEqual(max(full.size), wardrobe.MAX_EDGE)
            self.assertLessEqual(max(thumb.size), wardrobe.THUMB_EDGE)

    def test_large_photo_is_scaled_down(self):
        prepared = wardrobe.prepare_photo(self._image_bytes(size=(2400, 3200)))
        with Image.open(BytesIO(prepared.full)) as image:
            self.assertEqual(max(image.size), wardrobe.MAX_EDGE)

    def test_unreadable_file_is_rejected(self):
        with self.assertRaisesMessage(wardrobe.WardrobeImageError, "not a photo"):
            wardrobe.prepare_photo(b"definitely not an image")

    def test_tiny_photo_is_rejected(self):
        with self.assertRaisesMessage(wardrobe.WardrobeImageError, "too small"):
            wardrobe.prepare_photo(self._image_bytes(size=(20, 20)))

    def test_empty_upload_is_rejected(self):
        with self.assertRaises(wardrobe.WardrobeImageError):
            wardrobe.prepare_photo(b"")

    def test_fenced_json_from_the_ai_is_parsed(self):
        fenced = '```json\r\n{"outfits": [{"title": "Work"}]}\r\n```'
        self.assertEqual(gemini_ai._parse_json(fenced), {"outfits": [{"title": "Work"}]})
        self.assertEqual(gemini_ai._parse_json('{"name": "shirt"}'), {"name": "shirt"})


class WardrobeApiTests(TestCase):
    """Private closet: upload, tag, edit, wear, delete, and outfit ideas."""

    def setUp(self):
        self.tempdir = tempfile.mkdtemp(prefix="fitverse-wardrobe-")
        self.root_override = override_settings(WARDROBE_ROOT=Path(self.tempdir))
        self.root_override.enable()
        self.addCleanup(shutil.rmtree, self.tempdir, True)
        self.addCleanup(self.root_override.disable)
        # Establish the browser session so every test owns what it uploads.
        self.client.get("/wardrobe/")

    def _photo(self, name="shirt.jpg", size=(320, 400), colour=(190, 40, 45)):
        buffer = BytesIO()
        Image.new("RGB", size, colour).save(buffer, format="JPEG")
        return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")

    def _upload(self, count=1):
        files = [self._photo(name=f"piece-{index}.jpg") for index in range(count)]
        return self.client.post("/api/wardrobe/upload/", {"photos": files})

    def _item(self, **overrides):
        data = {
            "session_key": self.client.session.session_key or "",
            "name": "Navy shirt",
            "category": "top",
            "colours": ["navy"],
            "tagged": True,
        }
        data.update(overrides)
        item = WardrobeItem(**data)
        item.image.save("seed.jpg", ContentFile(self._photo().read()), save=False)
        item.thumb.save("seed-thumb.jpg", ContentFile(self._photo().read()), save=False)
        item.save()
        return item

    def _session_item(self):
        response = self._upload(1)
        self.assertEqual(response.status_code, 200)
        return WardrobeItem.objects.get(pk=response.json()["items"][0]["id"])

    def test_upload_normalises_and_keeps_photos_private(self):
        response = self._upload(2)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["items"]), 2)
        self.assertEqual(payload["errors"], [])
        self.assertNotIn("image", payload["items"][0])

        for item in WardrobeItem.objects.all():
            self.assertTrue(item.image.name.endswith(".jpg"))
            self.assertTrue(item.thumb.name.endswith(".jpg"))
            self.assertTrue(
                str(item.image.path).startswith(self.tempdir),
                f"{item.image.path!r} should live under {self.tempdir!r}",
            )
            self.assertFalse(item.tagged)
            self.assertEqual(item.colours, ["red"])

        first = payload["items"][0]
        self.assertEqual(first["thumb_url"], f"/wardrobe/items/{first['id']}/thumb/")

    def test_upload_rejects_a_file_that_is_not_a_photo(self):
        bad = SimpleUploadedFile("notes.jpg", b"not an image", content_type="image/jpeg")
        response = self.client.post("/api/wardrobe/upload/", {"photos": bad})

        self.assertEqual(response.status_code, 400)
        self.assertIn("not a photo", response.json()["error"])
        self.assertFalse(WardrobeItem.objects.exists())

    def test_upload_rejects_a_disallowed_file_type(self):
        bad = SimpleUploadedFile("notes.gif", b"GIF89a", content_type="image/gif")
        response = self.client.post("/api/wardrobe/upload/", {"photos": bad})

        self.assertEqual(response.status_code, 400)
        self.assertIn("JPEG", response.json()["error"])

    def test_upload_respects_the_wardrobe_limit(self):
        with override_settings(WARDROBE_MAX_ITEMS=1):
            first = self._upload(1)
            second = self._upload(1)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 400)
        self.assertEqual(WardrobeItem.objects.count(), 1)

    def test_tagging_stores_the_ai_metadata(self):
        item = self._session_item()
        tags = {
            "name": "Navy linen shirt",
            "category": "top",
            "colours": ["navy", "white"],
            "pattern": "plain",
            "formality": "smart-casual",
            "seasons": ["hot", "mild"],
            "style_tags": ["linen", "breathable"],
        }

        with mock.patch.object(views, "tag_wardrobe_image", return_value=tags) as tag:
            response = self.client.post(f"/api/wardrobe/items/{item.id}/tag/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["item"]["name"], "Navy linen shirt")
        tag.assert_called_once()
        item.refresh_from_db()
        self.assertTrue(item.tagged)
        self.assertEqual(item.category, "top")
        self.assertEqual(item.colours, ["navy", "white"])
        self.assertEqual(item.seasons, ["hot", "mild"])
        self.assertEqual(item.style_tags, ["linen", "breathable"])

    def test_tagging_failure_keeps_the_piece_and_flags_fallback(self):
        item = self._session_item()

        with mock.patch.object(
            views, "tag_wardrobe_image", side_effect=gemini_ai.GeminiError("AI is resting")
        ):
            response = self.client.post(f"/api/wardrobe/items/{item.id}/tag/")

        self.assertEqual(response.status_code, 503)
        self.assertTrue(response.json()["fallback"])
        item.refresh_from_db()
        self.assertFalse(item.tagged)

    def test_already_tagged_item_is_not_sent_to_the_ai_again(self):
        item = self._item()

        with mock.patch.object(views, "tag_wardrobe_image") as tag:
            response = self.client.post(f"/api/wardrobe/items/{item.id}/tag/")

        self.assertEqual(response.status_code, 200)
        tag.assert_not_called()

    def test_user_can_correct_the_ai_tags(self):
        item = self._item(category="top")

        response = self.client.post(
            f"/api/wardrobe/items/{item.id}/update/",
            data=json.dumps({"name": "  Navy  shirt  ", "category": "outerwear", "notes": "Wear open"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.name, "Navy shirt")
        self.assertEqual(item.category, "outerwear")
        self.assertEqual(item.notes, "Wear open")

    def test_invalid_category_update_is_ignored(self):
        item = self._item(category="top")

        self.client.post(
            f"/api/wardrobe/items/{item.id}/update/",
            data=json.dumps({"category": "spacesuit"}),
            content_type="application/json",
        )

        item.refresh_from_db()
        self.assertEqual(item.category, "top")

    def test_photo_is_only_served_to_its_owner(self):
        own = self._session_item()
        foreign = WardrobeItem(session_key="someone-elses-browser", name="Not yours")
        foreign.image.save("foreign.jpg", ContentFile(self._photo().read()), save=False)
        foreign.save()

        self.assertEqual(self.client.get(f"/wardrobe/items/{foreign.id}/photo/").status_code, 404)
        self.assertEqual(self.client.get(f"/wardrobe/items/{foreign.id}/thumb/").status_code, 404)

        response = self.client.get(f"/wardrobe/items/{own.id}/photo/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/jpeg")
        self.assertIn("private", response["Cache-Control"])

    def test_wear_history_only_touches_owned_pieces(self):
        own = self._session_item()
        foreign = WardrobeItem(session_key="someone-else", name="Not yours")
        foreign.save()

        response = self.client.post(
            "/api/wardrobe/worn/",
            data=json.dumps({"item_ids": [own.id, foreign.id]}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["updated"], 1)
        own.refresh_from_db()
        foreign.refresh_from_db()
        self.assertEqual(own.wear_count, 1)
        self.assertIsNotNone(own.last_worn)
        self.assertEqual(foreign.wear_count, 0)

    def test_worn_requires_at_least_one_piece(self):
        response = self.client.post(
            "/api/wardrobe/worn/", data=json.dumps({"item_ids": []}), content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)

    def test_delete_removes_the_database_row_and_the_files(self):
        item = self._session_item()
        image_path = Path(item.image.path)
        thumb_path = Path(item.thumb.path)
        self.assertTrue(image_path.exists())

        response = self.client.post(f"/api/wardrobe/items/{item.id}/delete/")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(WardrobeItem.objects.filter(pk=item.id).exists())
        self.assertFalse(image_path.exists())
        self.assertFalse(thumb_path.exists())

    def test_other_visitors_cannot_delete_your_piece(self):
        foreign = WardrobeItem(session_key="someone-else", name="Not yours")
        foreign.save()

        response = self.client.post(f"/api/wardrobe/items/{foreign.id}/delete/")

        self.assertEqual(response.status_code, 404)
        self.assertTrue(WardrobeItem.objects.filter(pk=foreign.id).exists())

    def test_recommendations_resolve_ids_and_send_only_metadata(self):
        shirt = self._item(name="White shirt")
        trousers = self._item(name="Wide trousers", category="bottom", colours=["cream"])
        captured = {}

        def fake_recommend(**kwargs):
            captured.update(kwargs)
            return [
                {
                    "title": "Easy office",
                    "item_ids": [str(shirt.id), str(trousers.id), "999999"],
                    "why": "Clean and light.",
                    "tip": "Add a brown belt.",
                }
            ]

        with mock.patch.object(views, "recommend_wardrobe_outfits", side_effect=fake_recommend):
            response = self.client.post(
                "/api/wardrobe/recommend/",
                data=json.dumps({"occasion": "work", "weather": "hot", "note": "keep it simple"}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        outfits = response.json()["outfits"]
        self.assertEqual(len(outfits), 1)
        self.assertEqual([piece["id"] for piece in outfits[0]["items"]], [shirt.id, trousers.id])
        self.assertEqual(outfits[0]["title"], "Easy office")
        self.assertEqual(captured["occasion"], "work")

        for piece in captured["items"]:
            self.assertNotIn("image", piece)
            self.assertNotIn("thumb_url", piece)
            self.assertNotIn("photo_url", piece)

    def test_recommendations_need_at_least_two_pieces(self):
        self._item()

        with mock.patch.object(views, "recommend_wardrobe_outfits") as recommend:
            response = self.client.post(
                "/api/wardrobe/recommend/",
                data=json.dumps({}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 400)
        recommend.assert_not_called()

    def test_recommendation_failure_has_a_friendly_message(self):
        self._item()
        self._item(name="Second piece")

        with mock.patch.object(
            views, "recommend_wardrobe_outfits", side_effect=gemini_ai.GeminiError("No outfits")
        ):
            response = self.client.post(
                "/api/wardrobe/recommend/",
                data=json.dumps({}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"], "No outfits")

    def test_wardrobe_page_renders_the_private_closet(self):
        shirt = self._item(name="White shirt")

        response = self.client.get("/wardrobe/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "White shirt")
        self.assertContains(response, "My clothes (1)")
        self.assertContains(response, "photos stay private")
        self.assertContains(response, f"/wardrobe/items/{shirt.id}/thumb/")
