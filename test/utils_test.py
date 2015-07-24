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

"""Unit tests for appstart.utils."""

# This file conforms to the external style guide.
# pylint: disable=bad-indentation, g-bad-import-order

import io
import logging
import tarfile
import tempfile
import unittest

import appstart
import fake_docker


class DockerBuildResultsTest(unittest.TestCase):
    """Test error detection in Docker build results."""

    def test_failed_build(self):
        bad_build_res = fake_docker.FAILED_BUILD_RES
        with self.assertRaises(appstart.utils.AppstartAbort):
            appstart.utils.log_and_check_build_results(bad_build_res, 'temp')

    def test_successful_build(self):
        good_build_res = fake_docker.BUILD_RES
        appstart.utils.log_and_check_build_results(good_build_res, 'temp')


class TarTest(unittest.TestCase):
    """Test the feature in appstart.utils that deal with tarfiles."""

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

        context = appstart.utils.make_tar_build_context(dockerfile,
                                                        context_files)
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

        wrapped_tar = appstart.utils.TarWrapper(tarfile.open(mode='r',
                                                             fileobj=temp))
        self.assertEqual(wrapped_tar.read_file('root/bar.txt'), 'bar')
        self.assertEqual(wrapped_tar.read_file('root/baz/foo.txt'), 'foo')
        with self.assertRaises(ValueError):
            wrapped_tar.read_file('root')

        files, dirs = wrapped_tar.list('root')
        self.assertEqual(files, ['bar.txt'])
        self.assertEqual(dirs, ['baz'])
        with self.assertRaises(ValueError):
            wrapped_tar.list('root/bar.txt')


class LoggerTest(unittest.TestCase):

    def test_get_logger(self):
        logger = appstart.utils.get_logger()
        self.assertIsInstance(logger, logging.Logger)

if __name__ == '__main__':
    unittest.main()
