# Copyright 2015 Google Inc. All Rights Reserved.

"""Wrapper around docker.Client to create semblance of container."""

# This file conforms to the external style guide.
# pylint: disable=bad-indentation

import httplib
import signal
import socket
import StringIO
import subprocess
import tarfile
import urlparse

import docker

import utils


_EXITING = False


def sig_handler(unused_signo, unused_frame):
    global _EXITING
    _EXITING = True


class Container(object):
    """Wrapper around docker container."""

    def __init__(self, dclient, **docker_kwargs):
        """Initializer for Container.

        Args:
            dclient: (docker.Client) The docker client that is managing
                the container.
            **docker_kwargs: (dict) Keyword arguments that can be supplied
                to docker.Client.create_container.
        """
        self.__container_id = None

        # Anticipate the possibility of SIGINT during construction.
        # Note that graceful behavior is guaranteed only for SIGINT.
        try:
            self.__dclient = dclient

            # Set handler
            prev = signal.signal(signal.SIGINT, sig_handler)
            self.__container_id = (
                self.__dclient.create_container(**docker_kwargs).get('Id'))

            # Restore previous handler
            signal.signal(signal.SIGINT, prev)

            # If _EXITING is True, then the signal handler was called.
            if _EXITING:
                raise KeyboardInterrupt

            self.host = urlparse.urlparse(self.__dclient.base_url).hostname
        except KeyboardInterrupt:
            self.remove()
            raise

    def kill(self):
        """Kill the underlying container."""

        # "removed" container is occasionally killed in ContainerSandbox.
        # Stay silent about this scenario.
        if self.__container_id:
            self.__dclient.kill(self.__container_id)

    def remove(self):
        """Remove the underlying container."""

        # Containers are occasionally removed twice in ContainerSandbox.
        # Stay silent about this scenario.
        if self.__container_id:
            self.__dclient.remove_container(self.__container_id)
            self.__container_id = None

    def start(self, **start_kwargs):
        """Start the container.

        Args:
            **start_kwargs: (dict) Additional kwargs to be supplied to
                docker.Client.start.
        """
        self.__dclient.start(self.__container_id, **start_kwargs)

    def stream_logs(self):
        """Print the container's stdout/stderr if necessary."""

        # docker.Client.logs seems to be broken, so use CLI instead :(
        # TODO(gouzenko): Fix capture of stdout, stderr
        subprocess.Popen('docker logs -f {0}'.format(self.__container_id),
                         shell=True)

    def get_id(self):
        return self.__container_id

    def ping(self, port=8080):
        """Check if container is listening on the specified port.

        Args:
            port: (int) The port to ping. This defaults to 8080 because
                application containers are required (at a minimum) to have
                a service listening on 8080.

        Returns:
            (bool) Whether or not the container is listening on the specified
                port.
        """

        con = None
        try:
            con = httplib.HTTPConnection(self.host, port)
            con.connect()
            return True
        except (socket.error, httplib.HTTPException):
            return False
        finally:
            if con:
                con.close()

    def execute(self, cmd, **create_kwargs):
        """Execute the command specified by cmd inside the container.

        Args:
            cmd: (basestring) The command to execute.
            **create_kwargs: (dict) Arguments that can be supplied to
                docker.Client.exec_create.

        Returns:
            (dict) A dict of values as returned by docker.Client.exec_inspect.
        """
        exec_id = self.__dclient.exec_create(container=self.__container_id,
                                             cmd=cmd,
                                             **create_kwargs).get('Id')
        self.__dclient.exec_start(exec_id)
        return self.__dclient.exec_inspect(exec_id)

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
            reply = self.__dclient.copy(self.__container_id, path)
        except docker.errors.APIError:
            raise IOError('File could not be found at {0}.'.format(path))

        fileobj = StringIO.StringIO(reply.read())

        # Wrap the TarFile for more user-friendliness
        return utils.TarWrapper(tarfile.open(fileobj=fileobj))


class ApplicationContainer(Container):
    """Explicitly give the application container a configuration file.

    This will be useful for validation.
    """

    def __init__(self, app_config, *args, **kwargs):
        super(ApplicationContainer, self).__init__(*args, **kwargs)
        self.configuration = app_config
