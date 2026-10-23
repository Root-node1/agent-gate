"""Request identifiers for logs and API error envelopes."""

from uuid import uuid4


class RequestIdMiddleware:
    """Attach a server-generated request id to every request and response."""

    header = "X-Request-Id"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.request_id = uuid4().hex
        response = self.get_response(request)
        response[self.header] = request.request_id
        return response
