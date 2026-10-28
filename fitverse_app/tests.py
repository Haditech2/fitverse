import base64
import json
import shutil
import tempfile
from io import BytesIO
from unittest import mock

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from . import views
from .models import UserMeasurement
from .services import bodygram


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

    @override_settings(AI_PROVIDER="gemini", GEMINI_API_KEY="test-key")
    def test_gemini_result_is_used_when_available(self):
        with mock.patch.object(
            views, "generate_gemini_try_on", return_value="/media/tryons/gemini.png"
        ) as gemini, mock.patch.object(views, "generate_try_on") as fashn:
            result = self._call()

        self.assertEqual(result, ("/media/tryons/gemini.png", "gemini"))
        gemini.assert_called_once()
        fashn.assert_not_called()

    @override_settings(AI_PROVIDER="gemini", GEMINI_API_KEY="test-key")
    def test_gemini_failure_falls_back_to_fashn(self):
        with mock.patch.object(
            views, "generate_gemini_try_on", side_effect=views.GeminiError("quota exhausted")
        ), mock.patch.object(
            views, "generate_try_on", return_value="/media/tryons/fashn.png"
        ) as fashn:
            result = self._call()

        self.assertEqual(result, ("/media/tryons/fashn.png", "fashn"))
        fashn.assert_called_once()

    @override_settings(AI_PROVIDER="gemini", GEMINI_API_KEY="test-key")
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

    @override_settings(AI_PROVIDER="gemini", GEMINI_API_KEY="")
    def test_missing_gemini_key_uses_fashn(self):
        with mock.patch.object(views, "generate_gemini_try_on") as gemini, \
                mock.patch.object(views, "generate_try_on", return_value="/media/tryons/fashn.png"):
            result = self._call()

        self.assertEqual(result, ("/media/tryons/fashn.png", "fashn"))
        gemini.assert_not_called()

    @override_settings(AI_PROVIDER="gemini", GEMINI_API_KEY="test-key")
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
