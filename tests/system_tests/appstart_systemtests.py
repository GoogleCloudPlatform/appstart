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

"""Set up real application and devappserver containers.

All endpoints of the application are probed. The application
respond with 200 OK if the endpoint is healthy, and any other
status code if the endpoint is broken.
"""
# This file conforms to the external style guide
# pylint: disable=bad-indentation, g-bad-import-order

import logging
import os
import requests
import time
import unittest
from appstart import utils, devappserver_init

from appstart.sandbox import container_sandbox

APPSTART_BASE_IMAGE = "appstart_systemtest_devappserver"

# pylint: disable=too-many-public-methods
class SystemTests(unittest.TestCase):
    """Probe endpoints on a running application container."""

    @classmethod
    def setUpClass(cls):
        """Create an actual sandbox.

        This depends on a properly set up docker environment.
        """
        
        utils.build_from_directory(os.path.dirname(devappserver_init.__file__),
                                   APPSTART_BASE_IMAGE,
                                   nocache=True)

        test_directory = os.path.dirname(os.path.realpath(__file__))
        cls.conf_file = os.path.join(test_directory, 'app.yaml')

        # Use temporary storage, generating unique name with a timestamp.
        temp_storage_path = '/tmp/storage/%s' % str(time.time())
        cls.sandbox = container_sandbox.ContainerSandbox(
            cls.conf_file,
            storage_path=temp_storage_path,
            devbase_image=APPSTART_BASE_IMAGE,
            force_version=True)

        # Set up the containers
        cls.sandbox.start()

    @classmethod
    def tearDownClass(cls):
        """Clean up the docker environment."""
        cls.sandbox.stop()

def make_endpoint_test(endpoint):
    """Create and return a function that tests the endpoint.

    Args:
        endpoint: (basestring) the endpoint to be tested (starting with /)
        handler: (webapp2.RequestHandler) the handler (from the test
            application) that services endpoint.

    Returns:
        (callable()) a function to test the endpoint.
    """
    def _endpoint_test(self):
        """Hit the endpoint and assert that it responds with 200 OK."""
        res = requests.get('http://%s:%i%s' %
                           (self.sandbox.devappserver_container.host,
                            self.sandbox.port,
                            endpoint))
        self.assertEqual(res.status_code,
                         200,
                         '%s failed with error \"%s\"' %
                         (endpoint, res.text))
    _endpoint_test.__name__ = 'test_%s_endpoint' % endpoint.strip('/')
    return _endpoint_test


if __name__ == '__main__':
    logging.getLogger('appstart').setLevel(logging.INFO)

    # Sync with urls in services_test_app.py
    # Keeping handler as None for later on customizing of tests
    urls = [
         '/datastore',
         '/logging', 
         '/memcache'
    ]

    
    # Get all the endpoints from the test app and turn them into tests.
    for ep in urls:
        endpoint_test = make_endpoint_test(ep)
        setattr(SystemTests, endpoint_test.__name__, endpoint_test)
    unittest.main()
