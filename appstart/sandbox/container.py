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

"""Wrapper around docker.Client to create semblance of a container."""

# This file conforms to the external style guide.
# pylint: disable=bad-indentation, g-bad-import-order

import requests
import signal
import StringIO
import tarfile
import threading
import urlparse

import docker

from .. import utils


_EXITING = False


def sig_handler(unused_signo, unused_frame):
    global _EXITING
    _EXITING = True


class Container(object):
    """Wrapper around docker container."""

    def __init__(self, dclient):
        """Initializer for Container.

        Args:
            dclient: (docker.Client) The docker client that is managing
                the container.
        """
        self._container_id = None
        self._dclient = dclient
        res = urlparse.urlparse(self._dclient.base_url)
        self.host = (res.hostname if res.hostname != 'localunixsocket'
                     else 'localhost')
        self.name = None

    def create(self, **docker_kwargs):
        """Do the work of calling docker.Client.create_container.

        The purpose of separating this functionality from __init__ is to be
        safe from the race condition (as documented below).

        Args:
            **docker_kwargs: (dict) Keyword arguments that can be supplied
                to docker.Client.create_container.

        Raises:
            KeyboardInterrupt: If SIGINT is caught during
                docker.client.create_container.
        """
        # Anticipate the possibility of SIGINT during construction.
        # Note that graceful behavior is guaranteed only for SIGINT.
        prev = signal.signal(signal.SIGINT, sig_handler)

        # Protecting create_container in this manner ensures that there
        # is GUARANTEED to be a container_id after this call. Then,
        # if there was a KeyboardInterrupt, it'll bubble up to higher
        # level error handling, which should remove the container.
        # This solves the problem where create_container gets interrupted
        # AFTER the container is created but BEFORE a result is returned.
        try:
            self._container_id = (
                self._dclient.create_container(**docker_kwargs).get('Id'))
        except docker.errors.APIError as err:
            raise utils.AppstartAbort('Could not create container because: '
                                      '{0}'.format(err))

        # Restore previous handler
        signal.signal(signal.SIGINT, prev)

        # If _EXITING is True, then the signal handler was called.
        if _EXITING:
            raise KeyboardInterrupt

        self.name = docker_kwargs.get('name')

    def kill(self):
        """Kill the underlying container."""

        # "removed" container is occasionally killed in ContainerSandbox.
        # Stay silent about this scenario.
        if self._container_id:
            self._dclient.kill(self._container_id)

    def remove(self):
        """Remove the underlying container."""

        # Containers are occasionally removed twice in ContainerSandbox.
        # Stay silent about this scenario.
        if self._container_id:
            self._dclient.remove_container(self._container_id)
            self._container_id = None

    def start(self, **start_kwargs):
        """Start the container.

        Args:
            **start_kwargs: (dict) Additional kwargs to be supplied to
                docker.Client.start.
        """
        try:
            self._dclient.start(self._container_id, **start_kwargs)
            utils.get_logger().info('Starting container: {0}'.format(self.name))
        except docker.errors.APIError as err:
            raise utils.AppstartAbort('Docker error: {0}'.format(err))

    def stream_logs(self, stream=True):
        """Print the container's stdout/stderr.

        Args:
            stream: (bool) Whether or not to continue streaming stdout/stderr.
                If False, only the current stdout/stderr buffer will be
                collected from the container. If True, stdout/stderr collection
                will continue as a subprocess.
        """

        def log_streamer():
            # This loop tackles the problem of request timeouts. When the
            # docker client is created, it establishes a timeout. The
            # default is 60 seconds. If docker.Client.logs hangs for
            # more than 60 seconds, this is considered a "timeout".
            name = (self._dclient.inspect_container(self._container_id)
                    .get('Name'))
            while True:
                try:
                    # If a timeout happens, an error will be raise from inside
                    # the log generator.
                    logs = self._dclient.logs(container=self._container_id,
                                              stream=True)
                    for line in logs:
                        utils.get_logger().debug('{0}: {1}'.format(
                            name, line.strip()))

                # In the case of a timeout, try to start collecting logs again.
                except requests.exceptions.ReadTimeout:
                    pass

                # An APIError occurs if the container doesn't exist anymore.
                # This indicates that we're shutting down, so we can break
                # and terminate the thread.
                except docker.errors.APIError:
                    break

        if stream:
            # If we want to stream the log output of the container,
            # start another thread. There's no need to join this thread,
            # because it's supposed to live until the container is removed.
            thread = threading.Thread(target=log_streamer)
            thread.start()
        else:
            logs = self._dclient.logs(container=self._container_id,
                                      stream=False)
            for line in logs.split('\n'):
                utils.get_logger().debug(line.strip())

    def running(self):
        """Check if the container is still running.

        Returns:
            (bool) Whether or not the container is running.
        """
        if not self._container_id:
            return False
        res = self._dclient.inspect_container(self._container_id)
        return res['State']['Running']

    def get_id(self):
        return self._container_id

    def execute(self, cmd, **create_kwargs):
        """Execute the command specified by cmd inside the container.

        Args:
            cmd: (basestring) The command to execute.
            **create_kwargs: (dict) Arguments that can be supplied to
                docker.Client.exec_create.

        Returns:
            (dict) A dict of values as returned by docker.Client.exec_inspect.
        """
        exec_id = self._dclient.exec_create(container=self._container_id,
                                            cmd=cmd,
                                            **create_kwargs).get('Id')
        self._dclient.exec_start(exec_id)
        return self._dclient.exec_inspect(exec_id)

    def extract_tar(self, path):
        """Extract the file/directory specified by path as a TarWrapper object.

        Args:
            path: (basestring) The path (within the container)
                to the file/directory to extract.

        Raises:
            IOError: If path cannot be resolved within the container.

        Returns:
            (utils.TarWrapper) The tar archive.
        """
        try:
            reply = self._dclient.copy(self._container_id, path)
        except docker.errors.APIError:
            raise IOError('File could not be found at {0}.'.format(path))

        fileobj = StringIO.StringIO(reply.read())

        # Wrap the TarFile for more user-friendliness
        return utils.TarWrapper(tarfile.open(fileobj=fileobj))


class PingerContainer(Container):
    """Give devappserver the ability to ping the application.

    Relies on container having a pinger.py in the root directory.
    """

    def ping_application_container(self):
        """Return True iff the application is listening on port 8080."""
        return self.execute('python /pinger.py')['ExitCode'] == 0


class ApplicationContainer(Container):
    """Explicitly give the application container a configuration file.

    This will be useful for validation.
    """

    def __init__(self, app_config, *args, **kwargs):
        super(ApplicationContainer, self).__init__(*args, **kwargs)
        self.configuration = app_config
