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

"""Unit tests for utils."""

# This file conforms to the external style guide.
# pylint: disable=bad-indentation, g-bad-import-order

import io
import logging
import os
import tarfile
import tempfile
import unittest

import docker

from fakes import fake_docker
from appstart import utils


CERT_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                         'test_data/certs')
APP_DIR = os.path.join(os.path.dirname(__file__), 'system_tests')


class DockerTest(fake_docker.FakeDockerTestBase):
    """Test error detection in Docker build results."""

    def test_get_docker_client(self):
        os.environ['DOCKER_HOST'] = 'tcp://192.168.59.103:2376'
        os.environ['DOCKER_TLS_VERIFY'] = '1'
        os.environ['DOCKER_CERT_PATH'] = CERT_PATH

        dclient = utils.get_docker_client()
        self.assertIn('tls', dclient.kwargs)
        self.assertIn('base_url', dclient.kwargs)

    def test_build_from_directory(self):
        utils.build_from_directory(APP_DIR, 'test')
        self.assertEqual(len(fake_docker.images),
                         1 + len(fake_docker.DEFAULT_IMAGES))
        self.assertIn('test', fake_docker.images)

    def test_failed_build(self):
        bad_build_res = fake_docker.FAILED_BUILD_RES
        with self.assertRaises(utils.AppstartAbort):
            utils.log_and_check_build_results(bad_build_res, 'temp')

    def test_successful_build(self):
        good_build_res = fake_docker.BUILD_RES
        utils.log_and_check_build_results(good_build_res, 'temp')

    def test_good_version(self):
        dclient = fake_docker.FakeDockerClient()
        utils.check_docker_version(dclient)

    def test_bad_version(self):
        dclient = fake_docker.FakeDockerClient()
        dclient.version = lambda: {'Version': '1.6.0'}
        with self.assertRaises(utils.AppstartAbort):
            utils.check_docker_version(dclient)

    def test_find_image(self):
        dclient = fake_docker.FakeDockerClient()
        fake_docker.images.append('test')
        self.assertTrue(utils.find_image('test'))


class TarTest(unittest.TestCase):
    """Test the feature in utils that deal with tarfiles."""

    def setUp(self):
        self.tempfile1 = tempfile.NamedTemporaryFile()
        self.tempfile1.write('foo')
        self.tempfile1.seek(0)

        self.tempfile2 = tempfile.NamedTemporaryFile()
        self.tempfile2.write('bar')
        self.tempfile2.seek(0)

    def test_make_build_context(self):
        dockerfile = io.BytesIO('FROM debian'.encode('utf-8'))
        context_files = {self.tempfile1.name: 'foo.txt',
                         self.tempfile2.name: '/baz/bar.txt'}

        context = utils.make_tar_build_context(dockerfile, context_files)
        tar = tarfile.TarFile(fileobj=context)

        self.assertEqual(tar.extractfile('foo.txt').read(), 'foo')
        self.assertEqual(tar.extractfile('baz/bar.txt').read(), 'bar')

    def test_tar_wrapper(self):
        temp = tempfile.NamedTemporaryFile()
        tar = tarfile.open(mode='w', fileobj=temp)

        tinfo1 = tar.gettarinfo(fileobj=self.tempfile1,
                                arcname='/root/baz/foo.txt')
        tar.addfile(tinfo1, self.tempfile1)

        tinfo2 = tar.gettarinfo(fileobj=self.tempfile2,
                                arcname='/root/bar.txt')
        tar.addfile(tinfo2, self.tempfile2)

        fake_root = tarfile.TarInfo('root')
        fake_root.type = tarfile.DIRTYPE
        tar.addfile(fake_root)

        fake_baz = tarfile.TarInfo('root/baz')
        fake_baz.type = tarfile.DIRTYPE
        tar.addfile(fake_baz)

        tar.close()
        temp.seek(0)

        wrapped_tar = utils.TarWrapper(tarfile.open(mode='r', fileobj=temp))
        self.assertEqual(wrapped_tar.get_file('root/bar.txt').read(), 'bar')
        self.assertEqual(wrapped_tar.get_file('root/baz/foo.txt').read(), 'foo')
        with self.assertRaises(ValueError):
            wrapped_tar.get_file('root')

        files, dirs = wrapped_tar.list('root')
        self.assertEqual(files, ['bar.txt'])
        self.assertEqual(dirs, ['baz'])
        with self.assertRaises(ValueError):
            wrapped_tar.list('root/bar.txt')


class LoggerTest(unittest.TestCase):

    def test_get_logger(self):
        logger = utils.get_logger()
        self.assertIsInstance(logger, logging.Logger)

if __name__ == '__main__':
    unittest.main()
