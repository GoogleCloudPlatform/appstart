# Copyright 2015 Google Inc. All Rights Reserved.
"""Unit tests for ContainerSandbox."""
# This file conforms to the external style guide
# pylint: disable=bad-indentation, g-bad-import-order

import logging
import os
import unittest

import docker
import mox

from appstart import sandbox
from appstart import utils

from fakes import fake_docker


class TestBase(unittest.TestCase):

    def setUp(self):
        self.old_docker_client = docker.Client
        docker.Client = fake_docker.FakeDockerClient

        test_directory = os.path.dirname(os.path.realpath(__file__))
        conf_file = os.path.join('./tests/test_data/fake_app', 'app.yaml')

        self.sandbox = sandbox.container_sandbox.ContainerSandbox(conf_file)
        self.mocker = mox.Mox()
        fake_docker.reset()

    def tearDown(self):
        """Restore docker.Client and requests.get."""
        self.mocker.VerifyAll()
        self.mocker.UnsetStubs()
        docker.Client = self.old_docker_client


# pylint: disable=too-many-public-methods
class CreateContainersTest(TestBase):
    """Test the creation of containers."""

    def setUp(self):
        super(CreateContainersTest, self).setUp()
        self.old_ping = (
            sandbox.container.PingerContainer.ping_application_container)
        sandbox.container.PingerContainer.ping_application_container = (
            lambda self: True)

        self.old_logs = sandbox.container.Container.stream_logs
        sandbox.container.Container.stream_logs = (
            lambda unused_self, unused_stream=True: None)

    def test_create_and_run_containers(self):
        """Test ContainerSandbox.create_and_run_containers."""
        self.sandbox.create_and_run_containers()

    def tearDown(self):
        sandbox.container.PingerContainer.ping_application_container = (
            self.old_ping)
        sandbox.container.Container.stream_logs = self.old_logs


class BadVersionTest(unittest.TestCase):

    def setUp(self):
        fake_docker.reset()

    def test_bad_version(self):
        """Test ContainerSandbox.create_and_run_containers.

        With a bad version, construction of the sandbox should fail.
        """
        docker.Client.version = lambda _: {'Version': '1.6.0'}
        with self.assertRaises(utils.AppstartAbort):
            _ = sandbox.container_sandbox.ContainerSandbox(image_name='temp')


class ExitTest(TestBase):
    """Ensure the ContainerSandbox exits properly."""

    def setUp(self):
        """Populate the sandbox fake containers.

        This simulates the scenario where create_and_run_containers() has
        just run successfully.
        """
        super(ExitTest, self).setUp()

        # Also add the containers to the sandbox
        self.sandbox.app_container = (
            self.mocker.CreateMock(sandbox.container.ApplicationContainer))

        self.sandbox.devappserver_container = (
            self.mocker.CreateMock(sandbox.container.Container))

        self.sandbox.pinger_container = (
            self.mocker.CreateMock(sandbox.container.PingerContainer))

        self.sandbox.app_container.running().AndReturn(True)
        self.sandbox.app_container.get_id().AndReturn('456')
        self.sandbox.app_container.kill()
        self.sandbox.app_container.remove()

        self.sandbox.devappserver_container.running().AndReturn(True)
        self.sandbox.devappserver_container.get_id().AndReturn('123')
        self.sandbox.devappserver_container.kill()
        self.sandbox.devappserver_container.remove()

        self.sandbox.pinger_container.running().AndReturn(True)
        self.sandbox.pinger_container.get_id().AndReturn('123')
        self.sandbox.pinger_container.kill()
        self.sandbox.pinger_container.remove()
        self.mocker.ReplayAll()

    def test_stop(self):
        self.sandbox.stop()

    def test_exception_handling(self):
        """Test the case where an exception was raised in __enter__."""
        def excep_func():
            """Simulate arbitrary exception."""
            raise Exception()
        self.sandbox.create_and_run_containers = excep_func

        with self.assertRaises(Exception):
            self.sandbox.start()


class StaticTest(TestBase):

    def test_get_web_xml(self):
        self.assertEqual(self.sandbox.get_web_xml('/conf/appengine-web.xml'),
                         '/conf/web.xml',
                         'web.xml must be in same folder as appengine-web.xml')

    def test_app_directory_from_config(self):
        self.assertEqual(
            self.sandbox.app_directory_from_config('/app/blah/app-web.xml'),
            '/app')

        self.assertEqual(
            self.sandbox.app_directory_from_config('/app/app.yaml'),
            '/app')

if __name__ == '__main__':
    logging.basicConfig(level=logging.CRITICAL)
    unittest.main()
