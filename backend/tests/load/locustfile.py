"""
Locust load test for the Production RAG API.

Usage:
  # Interactive web UI → http://localhost:8089
  locust -f backend/tests/load/locustfile.py --host http://localhost:8000

  # Headless with HTML report
  locust -f backend/tests/load/locustfile.py \\
    --headless --host http://localhost:8000 \\
    --users 50 --spawn-rate 5 --run-time 5m \\
    --html backend/tests/load/report.html \\
    --csv backend/tests/load/results

Target SLOs under 50 concurrent users:
  - GET /v1/health         P95 < 50ms
  - POST /v1/sessions      P95 < 500ms
  - POST /v1/query (SSE)   P95 < 30s   (LLM-bound)
  - Overall error rate     < 1%
"""
import uuid

from locust import HttpUser, LoadTestShape, between, task


SAMPLE_QUESTION = "What is the refund policy for products purchased online?"
SAMPLE_DOCUMENT = b"Acme Corp offers a 30-day money-back guarantee on all products. Contact support@acme.example for returns."


class RAGUser(HttpUser):
    """Simulates a real user: register → create session → query / upload."""
    wait_time = between(1, 3)

    def on_start(self) -> None:
        """Called once per virtual user at spawn time."""
        suffix = uuid.uuid4().hex[:10]
        self._email    = f"loadtest_{suffix}@example.com"
        self._username = f"loadtest_{suffix}"
        self._token: str = ""
        self._session_id: str = ""
        self._doc_uploaded: bool = False

        # Register
        reg = self.client.post("/v1/auth/register", json={
            "username": self._username,
            "email":    self._email,
            "password": "Loadtest1234!",
        }, name="/v1/auth/register")
        if reg.status_code != 201:
            return

        self._token = reg.json().get("access_token", "")

        # Create initial session
        sess = self.client.post(
            "/v1/sessions",
            headers=self._auth(),
            name="/v1/sessions [create]",
        )
        if sess.status_code == 201:
            self._session_id = sess.json().get("session_id", "")

    def _auth(self) -> dict:
        return {"Authorization": f"Bearer {self._token}"}

    # ── Tasks (higher weight = more frequent) ────────────────────────────────

    @task(10)
    def query_rag(self) -> None:
        """Primary load: stream a RAG query and drain the SSE response."""
        if not self._session_id:
            return
        with self.client.post(
            "/v1/query",
            json={"session_id": self._session_id, "question": SAMPLE_QUESTION},
            headers=self._auth(),
            stream=True,
            catch_response=True,
            name="/v1/query [stream]",
        ) as resp:
            if resp.status_code == 200:
                for _ in resp.iter_lines():
                    pass
                resp.success()
            else:
                resp.failure(f"status={resp.status_code}")

    @task(3)
    def upload_document(self) -> None:
        """Upload a small synthetic document (once per user)."""
        if self._doc_uploaded:
            return
        resp = self.client.post(
            "/v1/documents",
            files={"file": ("sample.txt", SAMPLE_DOCUMENT, "text/plain")},
            headers=self._auth(),
            name="/v1/documents [upload]",
        )
        if resp.status_code == 202:
            self._doc_uploaded = True

    @task(2)
    def list_sessions(self) -> None:
        self.client.get(
            "/v1/sessions",
            headers=self._auth(),
            name="/v1/sessions [list]",
        )

    @task(1)
    def health_check(self) -> None:
        self.client.get("/v1/health", name="/v1/health")

    @task(1)
    def rotate_session(self) -> None:
        """Close current session and open a fresh one."""
        if self._session_id:
            self.client.delete(
                f"/v1/sessions/{self._session_id}",
                headers=self._auth(),
                name="/v1/sessions [delete]",
            )
        resp = self.client.post(
            "/v1/sessions",
            headers=self._auth(),
            name="/v1/sessions [create]",
        )
        if resp.status_code == 201:
            self._session_id = resp.json().get("session_id", "")


class StepLoadShape(LoadTestShape):
    """
    Ramp users in 4 stages:
      0–60s:   warm-up  to 10 users
      60–120s: ramp     to 25 users
      120–180s: ramp    to 50 users
      180–240s: hold    at 50 users (peak steady-state)
    """
    stages = [
        {"duration": 60,  "users": 10, "spawn_rate": 2},
        {"duration": 120, "users": 25, "spawn_rate": 3},
        {"duration": 180, "users": 50, "spawn_rate": 5},
        {"duration": 240, "users": 50, "spawn_rate": 0},
    ]

    def tick(self):
        run_time = self.get_run_time()
        for stage in self.stages:
            if run_time < stage["duration"]:
                return stage["users"], stage["spawn_rate"]
        return None
