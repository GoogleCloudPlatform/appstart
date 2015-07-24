# Copyright 2015 Google Inc. All Rights Reserved.
"""Unit tests for ContainerSandbox."""
# This file conforms to the external style guide
# pylint: disable=bad-indentation, g-bad-import-order

import logging
import os
import unittest

import docker
import mox

import appstart

import fake_docker


class TestBase(unittest.TestCase):

    def setUp(self):
        self.old_docker_client = docker.Client
        docker.Client = fake_docker.FakeDockerClient

        test_directory = os.path.dirname(os.path.realpath(__file__))
        conf_file = os.path.join(test_directory, 'app.yaml')

        self.sandbox = appstart.container_sandbox.ContainerSandbox(conf_file)
        self.mocker = mox.Mox()

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

        # Since we test containers elsewhere, stub them out here.
        self.mocker.StubOutClassWithMocks(appstart.container,
                                          'DevappserverContainer')
        self.mocker.StubOutClassWithMocks(appstart.container,
                                          'ApplicationContainer')

        # Ensure that a devappserver container was created with the proper args.
        # Most importantly, the environment needs to be set up properly, so that
        # devappserver can be successfully invoked.
        devappserver_container = appstart.container.DevappserverContainer(
            mox.IsA(docker.Client))
        devappserver_container.create(
            name=mox.IsA(str),
            image=mox.IsA(str),
            ports=mox.IsA(list),
            volumes=mox.IsA(list),
            host_config=mox.IgnoreArg(),
            environment=mox.And(
                mox.In('APP_ID'),
                mox.In('PROXY_PORT'),
                mox.In('API_PORT'),
                mox.In('CONFIG_FILE')))

        # Give the devappserver a host
        devappserver_container.host = '0.0.0.0'
        devappserver_container.start()
        devappserver_container.get_id()

        # Check arguments for application container's constructor.
        # The most important argument is the environment; this is what
        # allows the application container to go through the bootstrapping
        # process to start serving.
        application_container = appstart.container.ApplicationContainer(
            mox.IsA(appstart.configuration.ApplicationConfiguration),
            mox.IsA(docker.Client))
        application_container.create(
            name=mox.IsA(str),
            image=mox.IsA(str),
            ports=mox.Or(mox.IsA(list), mox.IsA(None)),
            volumes=mox.IsA(list),
            host_config=mox.IgnoreArg(),
            environment=mox.And(
                mox.In('API_HOST'),
                mox.In('API_PORT'),
                mox.In('GAE_LONG_APP_ID'),
                mox.In('GAE_PARTITION'),
                mox.In('GAE_MODULE_INSTANCE'),
                mox.In('MODULE_YAML_PATH'),
                mox.In('GAE_MODULE_NAME'),
                mox.In('GAE_MODULE_VERSION'),
                mox.In('GAE_SERVER_PORT'),
                mox.In('USE_MVM_AGENT')))
        devappserver_container.host = '0.0.0.0'
        application_container.start(network_mode=mox.IgnoreArg())
        devappserver_container.is_running().AndReturn(True)
        devappserver_container.ping_application_container().AndReturn(True)
        application_container.stream_logs()
        self.mocker.ReplayAll()

        # Internal devappserver offset is initialized before creating and
        # running the containers.
        self.sandbox.das_offset = ''

        self.sandbox.application_configuration = self.mocker.CreateMock(
            appstart.configuration.ApplicationConfiguration)

        self.sandbox.application_configuration.is_java = False

    def test_create_and_run_containers(self):
        """Test ContainerSandbox.create_and_run_containers."""
        self.sandbox.create_and_run_containers()


class BadVersionTest(unittest.TestCase):

    def test_bad_version(self):
        """Test ContainerSandbox.create_and_run_containers.

        With a bad version, construction of the sandbox should fail.
        """
        docker.Client.version = lambda _: {'Version': '1.6.0'}
        with self.assertRaises(appstart.utils.AppstartAbort):
            _ = appstart.ContainerSandbox(image_name='temp')


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
            self.mocker.CreateMock(appstart.container.Container))

        self.sandbox.devappserver_container = (
            self.mocker.CreateMock(appstart.container.Container))

        self.sandbox.app_container.is_running().AndReturn(True)
        self.sandbox.app_container.get_id().AndReturn('456')
        self.sandbox.app_container.kill()
        self.sandbox.app_container.remove()

        self.sandbox.devappserver_container.is_running().AndReturn(True)
        self.sandbox.devappserver_container.get_id().AndReturn('123')
        self.sandbox.devappserver_container.kill()
        self.sandbox.devappserver_container.remove()
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
