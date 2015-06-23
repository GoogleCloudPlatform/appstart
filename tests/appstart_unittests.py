# Copyright 2015 Google Inc. All Rights Reserved.
"""Unit tests for ContainerSandbox."""
# This file conforms to the external style guide
# pylint: disable=bad-indentation, g-bad-import-order

import logging
import os
import requests
import unittest

import docker

from appstart import container_sandbox
from appstart import utils

import fake_docker
import fake_requests


class TestBase(unittest.TestCase):

    def setUp(self):
        """Monkey patch docker.Client and requests.get."""
        self.old_docker_client = docker.Client
        self.old_requests_get = requests.get
        docker.Client = fake_docker.FakeDockerClient
        requests.get = fake_requests.fake_get
        test_directory = os.path.dirname(os.path.realpath(__file__))
        conf_file = os.path.join(test_directory, 'app.yaml')
        self.sandbox = container_sandbox.ContainerSandbox(conf_file)

    def tearDown(self):
        """Restore docker.Client and requests.get."""
        docker.Client = self.old_docker_client
        requests.get = self.old_requests_get


# pylint: disable=too-many-public-methods
class CreateContainersTest(TestBase):
    """Test the creation of containers."""

    def test_create_and_run_containers(self):
        """Test ContainerSandbox.create_and_run_containers."""
        self.sandbox.create_and_run_containers()

        # Ensure that no containers have been removed
        num_cont_rm = len(self.sandbox.dclient.removed_containers)
        self.assertEqual(num_cont_rm, 0, 'containers were prematurely removed')

        # Ensure that all containers are running
        containers = self.sandbox.dclient.containers
        num_cont_running = 0
        for cont in containers:
            if cont['Running']:
                num_cont_running += 1
        self.assertEqual(num_cont_running,
                         len(containers),
                         'containers were prematurely stopped')

    def test_failed_build_logs(self):
        """Test behavior in the case of a failed build."""
        bad_build_res = fake_docker.FAILED_BUILD_RES
        with self.assertRaises(docker.errors.DockerException):
            utils.log_and_check_build_results(bad_build_res, 't')


class ExitTests(TestBase):
    """Ensure the ContainerSandbox exits properly."""

    def setUp(self):
        """Populate the sandbox and client with fake containers.

        This simulates the scenario where create_and_run_containers() has
        just run successfully.
        """
        super(ExitTests, self).setUp()

        # Create containers and add them to the docker client.
        self.container1 = {'Id': '1', 'Running': True}
        self.container2 = {'Id': '2', 'Running': True}
        self.sandbox.dclient.containers.extend([self.container1,
                                                self.container2])

        # Also add the containers to the sandbox
        self.sandbox.app_container = {'Id': self.container1['Id']}
        self.sandbox.devappserver_container = {'Id': self.container2['Id']}

    def test_sigint_handling(self):
        """Test the case where user pressed ctrl-c in __enter__."""

        # Patch create_and_run_containers so that it simply raises
        # a KeyboardInterrupt
        def sigint_func():
            """Simulate sigint (ctrl-c)."""
            raise KeyboardInterrupt()
        self.sandbox.create_and_run_containers = sigint_func

        # Ensure that __enter__ exits normally
        with self.assertRaises(SystemExit):
            self.sandbox.__enter__()

    def test_exception_handling(self):
        """Test the case where an exception was raised in __enter__."""
        def excep_func():
            """Simulate arbitrary exception."""
            raise Exception()
        self.sandbox.create_and_run_containers = excep_func

        with self.assertRaises(Exception):
            self.sandbox.__enter__()

    def tearDown(self):
        """Make sure that the containers have been removed."""
        self.assertEqual(len(self.sandbox.dclient.containers), 0,
                         'not all containers were removed.')
        super(ExitTests, self).tearDown()

if __name__ == '__main__':
    logging.basicConfig(level=logging.CRITICAL)
    unittest.main()
