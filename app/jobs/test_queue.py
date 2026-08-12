import unittest

from app.db import init_db
from app.jobs import queue
from app.repositories import organizations


class TestJobQueue(unittest.TestCase):
    def setUp(self):
        self.conn = init_db(":memory:")
        self.org = organizations.create(self.conn, "Acme Corp")

    def test_enqueue_stores_organization_id_in_payload(self):
        job_id = queue.enqueue(self.conn, "noop", self.org.id, payload={"foo": "bar"})
        job = queue.get_by_id(self.conn, job_id)

        self.assertEqual(job.status, "pending")
        self.assertEqual(job.organization_id, self.org.id)
        self.assertIn(f'"organization_id": {self.org.id}', job.payload)
        self.assertIn('"foo": "bar"', job.payload)

    def test_run_pending_marks_succeeded_and_stores_result(self):
        def handler(scope, payload):
            return {"seen_org": payload["organization_id"]}

        job_id = queue.enqueue(self.conn, "noop", self.org.id)
        results = queue.run_pending(self.conn, handlers={"noop": handler})

        self.assertEqual(results, [{"job_id": job_id, "status": "succeeded"}])
        job = queue.get_by_id(self.conn, job_id)
        self.assertEqual(job.status, "succeeded")
        self.assertIn(str(self.org.id), job.result)

    def test_handler_exception_marks_job_failed_without_crashing_batch(self):
        def boom(scope, payload):
            raise RuntimeError("handler blew up")

        def ok(scope, payload):
            return {"ok": True}

        failing_job_id = queue.enqueue(self.conn, "boom", self.org.id)
        ok_job_id = queue.enqueue(self.conn, "ok", self.org.id)

        results = queue.run_pending(self.conn, handlers={"boom": boom, "ok": ok})

        by_id = {r["job_id"]: r["status"] for r in results}
        self.assertEqual(by_id[failing_job_id], "failed")
        self.assertEqual(by_id[ok_job_id], "succeeded")

        failed_job = queue.get_by_id(self.conn, failing_job_id)
        self.assertEqual(failed_job.error, "handler blew up")

    def test_unknown_job_type_marks_failed(self):
        job_id = queue.enqueue(self.conn, "mystery", self.org.id)
        results = queue.run_pending(self.conn, handlers={})

        self.assertEqual(results, [{"job_id": job_id, "status": "failed"}])
        job = queue.get_by_id(self.conn, job_id)
        self.assertIn("no handler registered", job.error)

    def test_scheduled_for_future_is_not_run_yet(self):
        queue.enqueue(self.conn, "noop", self.org.id, scheduled_for="2099-01-01T00:00:00+00:00")
        results = queue.run_pending(self.conn, handlers={"noop": lambda scope, payload: {}}, now="2026-01-01T00:00:00+00:00")
        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
