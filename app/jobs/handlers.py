"""Registry mapping job_type -> handler function.

This registry centralizes exactly one thing: which function runs for which
job_type. It does NOT centralize or enforce anything about which
organization a job is allowed to touch — there is no shared "current org"
context here. Each handler receives its full JSON payload (which always
contains organization_id, see app/jobs/queue.py:enqueue) and is
individually responsible for reading that value and using it to scope its
own database access. A future handler that forgets to do so would not be
caught by anything in this module.
"""

HANDLERS = {}


def register(job_type, handler):
    HANDLERS[job_type] = handler
