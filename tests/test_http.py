import os
import sys
import unittest

os.environ["API_SECRET_KEY"] = "unit-test-secret"
os.environ["CHATGPT_COOKIES_NETSCAPE"] = ""
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi.testclient import TestClient
import main
main.API_SECRET_KEY = "unit-test-secret"
app = main.app


class HttpTests(unittest.TestCase):
    def test_health_and_authentication_states(self):
        with TestClient(app) as client:
            health = client.get("/health")
            self.assertIn(health.status_code, (200, 503))
            self.assertEqual(client.get("/v1/models").status_code, 401)
            models = client.get("/v1/models", headers={"Authorization": "Bearer unit-test-secret"})
            self.assertEqual(models.status_code, 200)
            invalid = client.post("/v1/chat/completions", headers={"Authorization": "Bearer unit-test-secret"}, json={})
            self.assertEqual(invalid.status_code, 400)


if __name__ == "__main__":
    unittest.main()
