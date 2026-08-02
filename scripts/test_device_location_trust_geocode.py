import os
import sys
import unittest
from unittest import mock

from flask import Blueprint, Flask, request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from routes.miniapp import device_state
from services import amap_geocode


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _make_app() -> Flask:
    app = Flask(__name__)

    @app.before_request
    def _attach_device():
        request.environ["miniapp_panel_payload"] = {"device_id": "device-1"}

    bp = Blueprint("location_test", __name__)
    device_state.register_routes(bp)
    app.register_blueprint(bp, url_prefix="/miniapp-api")
    return app


class DeviceLocationTrustTest(unittest.TestCase):
    def setUp(self):
        device_state._REPORT_DEDUPE_CACHE.clear()
        self.app = _make_app()
        self.client = self.app.test_client()
        self.base_payload = {
            "lat": 30.0,
            "lng": 120.0,
            "accuracy": 20,
            "precision": "fine",
            "age_ms": 1000,
            "is_mock": False,
            "coordinate_system": "WGS84",
            "trusted": True,
        }

    def test_each_untrusted_condition_skips_before_write(self):
        cases = (
            ("not_trusted", {"trusted": False}),
            ("precision_not_fine", {"precision": "coarse"}),
            ("mock_location", {"is_mock": True}),
            ("accuracy_too_low", {"accuracy": 150.01}),
            ("location_too_old", {"age_ms": 600001}),
        )
        with (
            mock.patch.object(device_state.r2_store, "is_device_reporting_bucket_enabled", return_value=True),
            mock.patch.object(device_state.r2_store, "merge_and_save_sense_bucket") as save,
            mock.patch.object(device_state.r2_store, "get_sense_latest") as load_latest,
            mock.patch.object(amap_geocode, "enrich_location_patch_with_amap_address") as enrich,
        ):
            for expected_reason, changed in cases:
                with self.subTest(expected_reason=expected_reason):
                    payload = dict(self.base_payload)
                    payload.update(changed)
                    response = self.client.post("/miniapp-api/device-state/location", json=payload)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(
                        response.get_json(),
                        {
                            "ok": True,
                            "bucket": "location",
                            "device_id": "device-1",
                            "skipped": True,
                            "reason": expected_reason,
                        },
                    )
            save.assert_not_called()
            load_latest.assert_not_called()
            enrich.assert_not_called()

    def test_trusted_threshold_boundary_saves_precision_metadata(self):
        payload = dict(self.base_payload, accuracy=150, age_ms=600000)
        saved = {}

        def _save(bucket, patch):
            saved["bucket"] = bucket
            saved["patch"] = dict(patch)
            return True

        with (
            mock.patch.object(device_state.r2_store, "is_device_reporting_bucket_enabled", return_value=True),
            mock.patch.object(device_state.r2_store, "get_sense_latest", return_value={"location": {}}),
            mock.patch.object(device_state.r2_store, "merge_and_save_sense_bucket", side_effect=_save),
            mock.patch.object(
                amap_geocode,
                "enrich_location_patch_with_amap_address",
                side_effect=lambda patch, **_: dict(patch),
            ),
        ):
            response = self.client.post("/miniapp-api/device-state/location", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])
        self.assertEqual(saved["bucket"], "location")
        patch = saved["patch"]
        self.assertEqual(patch["lat"], 30.0)
        self.assertEqual(patch["lng"], 120.0)
        self.assertEqual(patch["wgs84_lat"], 30.0)
        self.assertEqual(patch["wgs84_lng"], 120.0)
        self.assertEqual(patch["precision"], "fine")
        self.assertEqual(patch["age_ms"], 600000)
        self.assertIs(patch["is_mock"], False)
        self.assertEqual(patch["coordinate_system"], "WGS84")
        self.assertIs(patch["trusted"], True)


class AmapLocationEnrichmentTest(unittest.TestCase):
    def test_wgs84_is_converted_before_reverse_geocode(self):
        responses = [
            _FakeResponse({"status": "1", "locations": "120.006,30.006"}),
            _FakeResponse({"status": "1", "regeocode": {"formatted_address": "杭州市测试地址"}}),
        ]
        with (
            mock.patch.object(amap_geocode, "AMAP_API_KEY", "test-key"),
            mock.patch.object(amap_geocode.requests, "get", side_effect=responses) as get,
        ):
            result = amap_geocode.enrich_location_patch_with_amap_address(
                {"lat": 30.0, "lng": 120.0},
                current_time="2026-07-30T12:00:00+08:00",
            )

        self.assertEqual(get.call_count, 2)
        convert_call, regeo_call = get.call_args_list
        self.assertEqual(convert_call.args[0], amap_geocode._CONVERT_URL)
        self.assertEqual(
            convert_call.kwargs["params"],
            {
                "key": "test-key",
                "locations": "120.0,30.0",
                "coordsys": "gps",
            },
        )
        self.assertEqual(regeo_call.args[0], amap_geocode._REGEO_URL)
        self.assertEqual(regeo_call.kwargs["params"]["location"], "120.006,30.006")
        self.assertEqual(result["lat"], 30.0)
        self.assertEqual(result["lng"], 120.0)
        self.assertEqual(result["wgs84_lat"], 30.0)
        self.assertEqual(result["wgs84_lng"], 120.0)
        self.assertEqual(result["gcj02_lat"], 30.006)
        self.assertEqual(result["gcj02_lng"], 120.006)
        self.assertEqual(result["address"], "杭州市测试地址")
        self.assertEqual(result["address_resolution_status"], "resolved")

    def test_amap_failure_preserves_previous_trusted_address(self):
        previous = {
            "lat": 30.0,
            "lng": 120.0,
            "wgs84_lat": 30.0,
            "wgs84_lng": 120.0,
            "address": "原可信地址",
            "address_resolved_at": "2026-07-30T10:00:00+08:00",
        }
        responses = [
            _FakeResponse({"status": "1", "locations": "120.106,30.106"}),
            RuntimeError("amap timeout"),
        ]
        with (
            mock.patch.object(amap_geocode, "AMAP_API_KEY", "test-key"),
            mock.patch.object(amap_geocode.requests, "get", side_effect=responses),
        ):
            result = amap_geocode.enrich_location_patch_with_amap_address(
                {"lat": 30.1, "lng": 120.1},
                previous_location=previous,
                current_time="2026-07-30T12:00:00+08:00",
            )

        self.assertEqual(result["address"], "原可信地址")
        self.assertEqual(result["address_resolved_at"], "2026-07-30T10:00:00+08:00")
        self.assertEqual(result["address_resolution_status"], "failed")
        self.assertEqual(result["address_resolution_failed_at"], "2026-07-30T12:00:00+08:00")
        self.assertEqual(result["gcj02_lat"], 30.106)
        self.assertEqual(result["gcj02_lng"], 120.106)

    def test_nearby_persisted_location_reuses_address_without_regeo(self):
        previous = {
            "lat": 30.0,
            "lng": 120.0,
            "wgs84_lat": 30.0,
            "wgs84_lng": 120.0,
            "address": "缓存地址",
            "address_resolved_at": "2026-07-30T12:00:00+08:00",
        }
        with (
            mock.patch.object(amap_geocode, "AMAP_API_KEY", "test-key"),
            mock.patch.object(
                amap_geocode.requests,
                "get",
                return_value=_FakeResponse({"status": "1", "locations": "120.0065,30.0065"}),
            ) as get,
        ):
            result = amap_geocode.enrich_location_patch_with_amap_address(
                {"lat": 30.0005, "lng": 120.0005},
                previous_location=previous,
                current_time="2026-07-30T12:10:00+08:00",
            )

        self.assertEqual(get.call_count, 1)
        self.assertEqual(get.call_args.args[0], amap_geocode._CONVERT_URL)
        self.assertEqual(result["address"], "缓存地址")
        self.assertEqual(result["address_resolved_at"], "2026-07-30T12:00:00+08:00")
        self.assertEqual(result["address_resolution_status"], "cached")


if __name__ == "__main__":
    unittest.main()
