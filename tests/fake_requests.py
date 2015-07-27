# Copyright 2015 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
