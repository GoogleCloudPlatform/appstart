# Copyright 2015 Google Inc. All Rights Reserved.
"""Imitate the functionality of requests.get.

Used for unit testing.
"""
# This file conforms to the external style guide.
# pylint: disable=bad-indentation


# pylint: disable=too-few-public-methods, unused-argument
class FakeResponse(object):
    """Fake response that mimicks a successful health check."""

    def __init__(self):
        """Add the necessary components of a successful health check."""
        self.text = 'ok'
        self.status_code = 200


def fake_get(url):
    """Create and return response that mimicks successful health check."""
    return FakeResponse()
