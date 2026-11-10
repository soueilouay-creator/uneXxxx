from __future__ import annotations

import http.client
import json
import tempfile
import threading
import unittest
from unittest.mock import patch

from unexpected_runtime.coordinator import Coordinator
from unexpected_runtime.http_api import create_server
from unexpected_runtime.providers import DeterministicMockProvider


class FakeCinematicCreator:
    def __init__(self):
        self.quote_payload = None
        self.submit_payload = None
        self.job_id = "a" * 32

    def status(self):
        return {"provider": "fal.ai", "model": "seedance-test", "configured": False,
                "ready": False, "paid_generation_started": False, "publishing": False}

    def quote(self, payload):
        self.quote_payload = payload
        return {"quote_id": "q1", "quote_token": "signed-quote", "estimated_cost_usd": 1.08,
                "scene_count": 1, "total_seconds": 5, "requires_explicit_approval": True,
                "paid_generation_started": False}

    def submit(self, payload):
        self.submit_payload = payload
        return {"job_id": self.job_id, "status": "queued", "scenes": [{"status": "queued"}],
                "estimated_cost_usd": 1.08, "publishing_performed": False}

    def get_job(self, job_id):
        return {"job_id": job_id, "status": "completed", "scenes": [{"status": "downloaded"}],
                "master": {"byte_size": 9, "sha256": "a" * 64}, "qa": {"status": "passed"}}

    def read_video(self, job_id):
        return b"verified-mp4"


class CinematicVideoAPITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.coordinator = Coordinator(state_dir=self.tmp.name, provider=DeterministicMockProvider(),
                                       max_workers=2, max_retries=0)
        self.token = "cinematic-api-test-token-" + "x" * 32
        self.server = create_server(coordinator=self.coordinator, api_token=self.token,
                                    host="127.0.0.1", port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.coordinator.close()
        self.tmp.cleanup()

    def request(self, method, path, body=None, auth=True):
        conn = http.client.HTTPConnection(self.host, self.port, timeout=8)
        headers = {}
        if auth:
            headers["Authorization"] = "Bearer " + self.token
        if body is not None:
            headers["Content-Type"] = "application/json"
        conn.request(method, path, json.dumps(body) if body is not None else None, headers)
        response = conn.getresponse()
        raw = response.read()
        content_type = response.getheader("Content-Type", "")
        conn.close()
        return response.status, json.loads(raw) if raw and "application/json" in content_type else raw

    def test_cinematic_routes_require_runtime_authentication(self):
        fake = FakeCinematicCreator()
        with patch("unexpected_runtime.cinematic_video.CinematicVideoCreator.from_environment",
                   return_value=fake):
            self.assertEqual(self.request("GET", "/v1/creator/cinematic/status", auth=False)[0], 401)
            self.assertEqual(self.request("POST", "/v1/creator/cinematic/quote", {}, auth=False)[0], 401)
            self.assertEqual(self.request("POST", "/v1/creator/cinematic/jobs", {}, auth=False)[0], 401)
            self.assertEqual(self.request("GET", "/v1/creator/cinematic/jobs/" + fake.job_id, auth=False)[0], 401)

    def test_quote_is_non_spending_and_jobs_require_exact_explicit_approval_fields(self):
        fake = FakeCinematicCreator()
        brief = {"title": "Original fantasy short", "character_bible": "A young heroine in a blue cloak.",
                 "resolution": "480p", "scenes": [{"scene_id": "scene-01", "prompt": "A heroine crosses a castle hall.",
                 "caption": "The castle was not empty.", "duration_seconds": 5}]}
        with patch("unexpected_runtime.cinematic_video.CinematicVideoCreator.from_environment",
                   return_value=fake):
            status, quote = self.request("POST", "/v1/creator/cinematic/quote", brief)
            self.assertEqual(status, 200)
            self.assertFalse(quote["quote"]["paid_generation_started"])
            self.assertEqual(fake.quote_payload, brief)
            self.assertIsNone(fake.submit_payload)
            self.assertEqual(self.request("POST", "/v1/creator/cinematic/jobs",
                                          {"quote_token": "signed-quote", "approved_max_usd": 1.08, "publish": True})[0], 400)
            status, submitted = self.request("POST", "/v1/creator/cinematic/jobs",
                                              {"quote_token": "signed-quote", "approved_max_usd": 1.08})
            self.assertEqual(status, 202)
            self.assertEqual(fake.submit_payload, {"quote_token": "signed-quote", "approved_max_usd": 1.08})
            status, detail = self.request("GET", "/v1/creator/cinematic/jobs/" + fake.job_id)
            self.assertEqual(status, 200)
            self.assertEqual(detail["job"]["status"], "completed")
            status, media = self.request("GET", "/v1/creator/cinematic/jobs/" + fake.job_id + "/file")
            self.assertEqual(status, 200)
            self.assertEqual(media, b"verified-mp4")


if __name__ == "__main__":
    unittest.main(verbosity=2)
