# Copyright 2015 Google Inc. All Rights Reserved.
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

from appstart import container_sandbox

import services_test_app


# pylint: disable=too-many-public-methods
class SystemTests(unittest.TestCase):
    """Probe endpoints on a running application container."""

    @classmethod
    def setUpClass(cls):
        """Create an actual sandbox.

        This depends on a properly set up docker environment.
        """
        test_directory = os.path.dirname(os.path.realpath(__file__))
        conf_file = os.path.join(test_directory, 'app.yaml')

        # Use temporary storage, generating unique name with a timestamp.
        temp_storage_path = '/tmp/storage/%s' % str(time.time())
        cls.sandbox = container_sandbox.ContainerSandbox(
            conf_file,
            storage_path=temp_storage_path)

        # Set up the containers
        cls.sandbox.start()

    @classmethod
    def tearDownClass(cls):
        """Clean up the docker environment."""
        cls.sandbox.stop()


def make_endpoint_test(endpoint, handler):
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
                           (self.sandbox.get_docker_host(),
                            self.sandbox.port,
                            endpoint))
        self.assertEqual(res.status_code,
                         200,
                         '%s failed with error \"%s\"' %
                         (handler.__name__, res.text))
    _endpoint_test.__name__ = 'test_%s_endpoint' % endpoint.strip('/')
    return _endpoint_test


if __name__ == '__main__':
    logging.getLogger('appstart').setLevel(logging.INFO)
    # Get all the endpoints from the test app and turn them into tests.
    for ep, handlr in services_test_app.urls:
        endpoint_test = make_endpoint_test(ep, handlr)
        setattr(SystemTests, endpoint_test.__name__, endpoint_test)
    unittest.main()
