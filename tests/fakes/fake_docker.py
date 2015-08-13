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

"""An imitation of docker.Client.

This class is used for unit testing ContainerSandbox.
"""
# This file conforms to the external style guide.
# pylint: disable=bad-indentation

import requests
import stubout
import unittest
import uuid

import docker

from appstart.sandbox import container_sandbox


DEFAULT_IMAGES = [container_sandbox.DEVAPPSERVER_IMAGE,
                  container_sandbox.PINGER]
images = list(DEFAULT_IMAGES)
containers = []
removed_containers = []


def reset():
    global containers, images, removed_containers
    containers = []
    images = list(DEFAULT_IMAGES)
    removed_containers = []


# Fake build results, mimicking those that appear from docker.Client.build
BUILD_RES = [
    '{"stream":"Step 1 : MAINTAINER first last, name@example.com\\n"}',
    '{"stream":" ---\\u003e Running in 08787d0ee8b1\\n"}',
    '{"stream":" ---\\u003e 23e5e66a4494\\n"}',
    '{"stream":"Removing intermediate container 08787d0ee8b1\\n"}',
    '{"stream":"Step 2 : VOLUME /data\\n"}',
    '{"stream":" ---\\u003e Running in abdc1e6896c6\\n"}',
    '{"stream":" ---\\u003e 713bca62012e\\n"}',
    '{"stream":"Removing intermediate container abdc1e6896c6\\n"}',
    '{"stream":"Step 3 : CMD [\\"/bin/sh\\"]\\n"}',
    '{"stream":" ---\\u003e Running in dba30f2a1a7e\\n"}',
    '{"stream":" ---\\u003e 032b8b2855fc\\n"}',
    '{"stream":"Removing intermediate container dba30f2a1a7e\\n"}',
    '{"stream":"Successfully built 032b8b2855fc\\n"}']

FAILED_BUILD_RES = [
    '{"stream":"Step 1 : MAINTAINER first last, name@example.com\\n"}',
    '{"stream":" ---\\u003e Running in 08787d0ee8b1\\n"}',
    '{"stream":" ---\\u003e 23e5e66a4494\\n"}',
    '{"stream":"Removing intermediate container 08787d0ee8b1\\n"}',
    '{"stream":"Step 2 : VOLUME /data\\n"}',
    '{"stream":" ---\\u003e Running in abdc1e6896c6\\n"}',
    '{"stream":" ---\\u003e 713bca62012e\\n"}',
    '{"stream":"Removing intermediate container abdc1e6896c6\\n"}',
    '{"stream":"Step 3 : CMD [\\"/bin/sh\\"]\\n"}',
    '{"stream":" ---\\u003e Running in dba30f2a1a7e\\n"}',
    '{"stream":" ---\\u003e 032b8b2855fc\\n"}',
    '{"stream":"Removing intermediate container dba30f2a1a7e\\n"}',
    '{"error":"Could not build 032b8b2855fc\\n"}']


class FakeDockerClient(object):
    """Fake the functionality of docker.Client."""

    def __init__(self, **kwargs):  # pylint: disable=unused-argument
        """Keep lists for images, containers, and removed containers."""
        self.base_url = 'http://0.0.0.0:1234'
        self.kwargs = kwargs

    def version(self):
        return {'Version': '1.5.0'}

    def ping(self):
        """Do nothing."""
        pass

    def build(self, **kwargs):
        """Imitate docker.Client.build."""
        if 'custom_context' in kwargs and 'fileobj' not in kwargs:
            raise TypeError('fileobj must be passed with custom_context.')
        if 'tag' not in kwargs:
            raise KeyError('tag must be specified in docker build.')
        if 'nocache' not in kwargs:
            raise KeyError('appstart must specify nocache in builds.')

        # "Store" the newly "built" image
        images.append(kwargs['tag'])
        return BUILD_RES

    def inspect_container(self, container_id):
        cont = find_container(container_id)
        return {'Name': cont['Name'],
                'Id': cont['Id'],
                'State': {'Running': cont['Running']}}

    def create_container(self, **kwargs):
        """Imitiate docker.Client.create_container."""
        if 'image' not in kwargs:
            raise KeyError('image was not specified.')
        if 'name' not in kwargs:
            raise KeyError('appstart should not make unnamed containers.')
        if kwargs['image'] not in images:
            raise docker.errors.APIError('the specified image does not exist.',
                                         requests.Response())

        # Create a unique id for the container.
        container_id = str(uuid.uuid4())

        # Create a new container and append it to the list of containers.
        new_container = {'Id': container_id,
                         'Running': False,
                         'Options': kwargs,
                         'Name': kwargs['name']}
        containers.append(new_container)
        return {'Id': container_id, 'Warnings': None}

    def kill(self, cont_id):
        """Imitate docker.Client.kill."""
        cont_to_kill = find_container(cont_id)
        cont_to_kill['Running'] = False

    def remove_container(self, cont_id):
        """Imitate docker.Client.remove_container."""
        cont_to_rm = find_container(cont_id)
        if cont_to_rm['Running']:
            raise RuntimeError('tried to remove a running container.')
        removed_containers.append(cont_to_rm)
        containers.remove(cont_to_rm)

    def start(self, cont_id, **kwargs):  # pylint: disable=unused-argument
        """Imitate docker.Client.start."""
        cont_to_start = find_container(cont_id)
        cont_to_start['Running'] = True


def find_container(cont_id):
    """Helper function to find a container based on id."""
    for cont in containers:
        if cont['Id'] == cont_id:
            return cont
    raise docker.errors.APIError('container was not found.', requests.Response())


class FakeDockerTestBase(unittest.TestCase):

    def setUp(self):
        self.stubs = stubout.StubOutForTesting()
        self.stubs.Set(docker, 'Client', FakeDockerClient)
        reset()

    def tearDown(self):
        """Restore docker.Client and requests.get."""
        reset()
        self.stubs.UnsetAll()
