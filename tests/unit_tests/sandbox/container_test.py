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

"""Unit tests for appstart.sandbox.container."""

# This file conforms to the external style guide.
# pylint: disable=bad-indentation, g-bad-import-order

import unittest

from appstart.sandbox import container
from fakes import fake_docker


class TestContainerExit(fake_docker.FakeDockerTestBase):

    def setUp(self):
        # Simulate that a SIGINT was caught by setting global _EXITING var
        super(TestContainerExit, self).setUp()
        self.stubs.Set(container, '_EXITING', True)

        # Pretend that we've created an image called 'temp'
        fake_docker.images.append('temp')

    def test_exit_from_create(self):
        dclient = fake_docker.FakeDockerClient()

        # container should detect that a KeyboardInterrupt was raised and
        # manually raise it again.
        cont = container.Container(dclient)
        with self.assertRaises(KeyboardInterrupt):
            cont.create(name='temp', image='temp')
        self.assertIsNotNone(cont._container_id)


class TestContainer(fake_docker.FakeDockerTestBase):

    def setUp(self):
        super(TestContainer, self).setUp()
        self.dclient = fake_docker.FakeDockerClient()
        fake_docker.images.append('temp')
        self.cont = container.Container(self.dclient)
        self.cont.create(name='temp',
                         image='temp')

    def test_create(self):
        # Ensure that only one container was created.
        self.assertEqual(len(fake_docker.containers),
                         1,
                         'Too many containers')

        created_container = fake_docker.containers[0]

        # Ensure that Container used the name supplied to it.
        self.assertEqual(created_container['Name'],
                         'temp',
                         'Container name did not match.')

        # Ensure that the Container is not yet running.
        self.assertFalse(created_container['Running'],
                         '__init__ should not start container')

        # Ensure the correct host. (Note that the host is a result of
        # hardcoding the base_url in fake_docker.py
        self.assertEqual(self.cont.host,
                         '0.0.0.0',
                         'Hosts do not match.')

    def test_kill(self):
        # Ensure that the container stops running in response to 'kill'
        fake_docker.containers[0]['Running'] = True
        self.cont.kill()
        self.assertFalse(self.cont.running(),
                         'Container believes itself to be running')
        self.assertFalse(fake_docker.containers[0]['Running'],
                         'Container was left running')

        # Containers can be more than once, so this should pass without error
        self.cont.kill()

    def test_remove(self):
        # Ensure that the container is removed when 'remove' is called.
        self.cont.remove()
        self.assertEqual(len(fake_docker.containers),
                         0,
                         'Container was not removed')

        # Containers can be removed more than once
        self.cont.remove()

    def test_start(self):
        self.cont.start()
        self.assertTrue(self.cont.running(),
                        'Container does not think itself to be running')
        self.assertTrue(fake_docker.containers[0]['Running'],
                        'Container is not running')

    def test_get_id(self):
        self.assertEqual(self.cont.get_id(),
                         fake_docker.containers[0]['Id'],
                         'Container IDs do not match')

if __name__ == '__main__':
    unittest.main()
