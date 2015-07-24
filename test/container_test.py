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

"""Unit tests for appstart.container."""

# This file conforms to the external style guide.
# pylint: disable=bad-indentation, g-bad-import-order

import unittest

import appstart
import fake_docker


class TestContainerInitExit(unittest.TestCase):

    def setUp(self):
        # Simulate that a SIGINT was caught by setting global _EXITING var
        appstart.container._EXITING = True
        self.dclient = fake_docker.FakeDockerClient()

        # Pretend that we've created an image called 'temp'
        self.dclient.images.append('temp')

    def test_exit_from_init(self):
        # container should detect that a KeyboardInterrupt was raised and
        # manually raise it again.
        with self.assertRaises(KeyboardInterrupt):
            container = appstart.container.Container(self.dclient)
            container.create(name='temp', image='temp')

    def tearDown(self):
        appstart.container._EXITING = False


class TestContainer(unittest.TestCase):

    def setUp(self):
        self.dclient = fake_docker.FakeDockerClient()
        self.dclient.images.append('temp')
        self.cont = appstart.container.Container(self.dclient)
        self.cont.create(name='temp',
                         image='temp')

    def test_init(self):
        # Ensure that only one container was created.
        self.assertEqual(len(self.dclient.containers),
                         1,
                         'Too many containers')

        created_container = self.dclient.containers[0]

        # Ensure that Container used the name supplied to it.
        self.assertEqual(created_container['Name'],
                         'temp',
                         'Container name did not match.')

        # Ensure that the Container is not yet running.
        self.assertFalse(created_container['Running'],
                         '__init__ should not start container')

        # Ensure the correct host.
        self.assertEqual(self.cont.host,
                         '0.0.0.0',
                         'Hosts do not match.')

    def test_kill(self):
        self.dclient.containers[0]['Running'] = True
        self.cont.kill()
        self.assertFalse(self.dclient.containers[0]['Running'],
                         'Container was left running')

    def test_remove(self):
        self.cont.remove()
        self.assertEqual(len(self.dclient.containers),
                         0,
                         'Container was not removed')

    def test_start(self):
        self.cont.start()
        self.assertTrue(self.dclient.containers[0]['Running'],
                        'Container is not running')

    def test_get_id(self):
        self.assertEqual(self.cont.get_id(),
                         self.dclient.containers[0]['Id'],
                         'Container IDs do not match')

if __name__ == '__main__':
    unittest.main()
