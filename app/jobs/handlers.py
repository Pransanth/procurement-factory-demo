"""Registry mapping job_type -> handler function.

This registry centralizes exactly one thing: which function runs for which
job_type. It does not itself enforce anything about which organization a
job is allowed to touch — that is the job of app/jobs/scoped_repositories.py
and app/jobs/queue.py:run_pending, which construct a ScopedRepositories
instance for each job and call `handler(scope, payload)`. A registered
handler's signature is therefore `handle(scope, payload)`, not
`handle(conn, payload)`: it receives a tenant-bound facade, not a raw
database connection, so it has no parameter through which it could
address a different organization.
"""

HANDLERS = {}


def register(job_type, handler):
    HANDLERS[job_type] = handler
