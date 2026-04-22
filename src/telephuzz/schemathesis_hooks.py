"""File for schemathesis hooks."""

import schemathesis
from schemathesis.generation.case import Case

from telephuzz.http_message import HTTPMethod, Request


@schemathesis.hook
def before_call(context, case: Case, response):
    """Schemathesis hook for obtaining generated request."""
    Request(
        headers=case.headers,
        body=case.body,
        content_type=case.media_type,
        method=HTTPMethod(case.method),
        path=case.path,
        path_parameters=case.path_parameters,
        query_parameters=case.query,
    )
    # TODO save
