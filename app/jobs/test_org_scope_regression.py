"""Red regression test for factory/findings/P1-DEMO-1.md.

This test demonstrates the Root Cause described in P1-DEMO-1 using ONLY
the production API that exists today: app.db.init_db, app.repositories.*,
and app.jobs.queue (enqueue / run_pending / get_by_id). It does not
reference any not-yet-built class (no ScopedRepositories, no AST guard) —
per the build order (factory/build-orders/P1-DEMO-1.md), that
infrastructure must not exist yet when this test is written.

It simulates a job enqueued for Organization A whose handler is
deliberately buggy: instead of using the organization_id the queue gave
it, it acts on a different organization_id (Organization B) — exactly the
kind of mistake P1-DEMO-1 warns a future handler could make. Today,
nothing in app/jobs/queue.py or app/repositories/*.py stops this.

The final assertion encodes the SECURITY EXPECTATION ("a job scoped to
Organization A must never change Organization B's data"), not the current
behavior. That is why this test is expected to FAIL (red) against today's
code: the failure is the proof that the vulnerability described in
P1-DEMO-1 is real, not a mistake in this test. Do not "fix" this test by
weakening or removing that assertion — it must turn green only as a
consequence of the runtime security boundary described in the build
order being implemented.
"""

import unittest

from app.db import init_db
from app.jobs import queue
from app.repositories import organizations, procurement_requests, suppliers, users


def _buggy_handler_ignores_its_own_job_org(conn, payload):
    """Stand-in for a future developer mistake.

    A correct handler would use payload["organization_id"] (the org the
    queue actually enqueued this job for). This handler instead acts on
    payload["acts_on_organization_id"], representing a wrong-variable /
    copy-paste bug. Nothing in the current job infrastructure or
    repository layer notices or prevents the mismatch.
    """
    wrong_org_id = payload["acts_on_organization_id"]
    target_request_id = payload["target_request_id"]
    procurement_requests.update_status(conn, wrong_org_id, target_request_id, "approved")
    return {"updated_request_id": target_request_id}


class TestOrgScopeRegressionP1Demo1(unittest.TestCase):
    def setUp(self):
        self.conn = init_db(":memory:")

        self.org_a = organizations.create(self.conn, "Org A")
        self.org_b = organizations.create(self.conn, "Org B")

        user_b = users.create(self.conn, self.org_b.id, "bob@b.example", "Bob", "member")
        supplier_b = suppliers.create(self.conn, self.org_b.id, "B Supplies")
        self.request_b = procurement_requests.create(
            self.conn, self.org_b.id, user_b.id, supplier_b.id, "B's laptops", 200_000
        )
        procurement_requests.update_status(self.conn, self.org_b.id, self.request_b.id, "submitted")

    def test_job_scoped_to_org_a_must_not_be_able_to_mutate_org_b_data(self):
        # A job is enqueued for Organization A. The job infrastructure accepts
        # this without question and files it under Organization A.
        job_id = queue.enqueue(
            self.conn,
            "buggy_reminder_job",
            self.org_a.id,
            payload={
                "acts_on_organization_id": self.org_b.id,
                "target_request_id": self.request_b.id,
            },
        )
        job_before = queue.get_by_id(self.conn, job_id)
        self.assertEqual(
            job_before.organization_id, self.org_a.id,
            "job infrastructure did not accept the job under Organization A as expected",
        )

        # The buggy handler runs. Nothing in run_pending() checks that the
        # organization_id the handler actually used matches the job's own
        # organization_id.
        results = queue.run_pending(
            self.conn, handlers={"buggy_reminder_job": _buggy_handler_ignores_its_own_job_org}
        )
        self.assertEqual(
            results, [{"job_id": job_id, "status": "succeeded"}],
            "the queue did not even detect anything was wrong: the buggy handler "
            "completed successfully",
        )

        # SECURITY EXPECTATION: a job that the queue itself filed under
        # Organization A must never be able to change Organization B's data.
        # This is the assertion that SHOULD hold. It does not, with today's
        # code — that is the proven vulnerability, and why this test is red.
        request_b_after = procurement_requests.get_by_id(self.conn, self.org_b.id, self.request_b.id)
        self.assertEqual(
            request_b_after.status,
            "submitted",
            "SECURITY: a background job enqueued for Organization A was able to change "
            "Organization B's procurement request status from 'submitted' to "
            f"'{request_b_after.status}'. There is no central technical boundary in "
            "app/jobs/queue.py or app/repositories/procurement_requests.py that prevents "
            "a handler from acting on a different organization than the one its job "
            "belongs to.",
        )


if __name__ == "__main__":
    unittest.main()
