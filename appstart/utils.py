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

"""Helper functions for components of appstart."""

# This file follows the external style guide.
# pylint: disable=bad-indentation, g-bad-import-order

import logging
import io
import json
import os
import re
import requests
import socket
import ssl
import sys
import tarfile
import tempfile

import docker


# HTTP timeout for docker client
TIMEOUT_SECS = 60

# Default docker host if user isn't using boot2docker
LINUX_DOCKER_HOST = '/var/run/docker.sock'

# Supported docker versions
DOCKER_API_VERSION = '1.17'
DOCKER_SERVER_VERSION = '1.5.0'

# Logger that is shared accross all components of appstart
_logger = None

# Logging format
FMT = '[%(levelname).1s: %(asctime)s] %(message)s'
DATE_FMT = '%H:%M:%S'

INT_RX = re.compile(r'\d+')


class AppstartAbort(Exception):
    pass


def get_logger():
    """Configures the appstart logger if it doesn't exist yet.

    Returns:
        (logging.Logger) a logger used to log messages on behalf of
        appstart.
    """
    global _logger
    if _logger is None:
        _logger = logging.getLogger('appstart')
        _logger.setLevel(logging.DEBUG)
        sh = logging.StreamHandler()
        sh.setLevel(logging.DEBUG)
        formatter = logging.Formatter(fmt=FMT, datefmt=DATE_FMT)
        sh.setFormatter(formatter)
        _logger.addHandler(sh)
    return _logger


def _soft_int(val):
    """Convert strings to integers without dying on non-integer values."""
    m = INT_RX.match(val)
    if m:
        return int(m.group())
    else:
        return 0


def check_docker_version(dclient):
    """Check version of docker server and log errors if it's too old/new.

    The currently supported versions of docker are 1.5.0 to 1.8.x

    Args:
        dclient: (docker.Client) The docker client to use to connect to the
            docker server.

    Raises:
        AppstartAbort: If user's docker server version is not correct.
    """
    version = dclient.version()
    server_version = [_soft_int(x) for x in version.get('Version').split('.')]
    if server_version < [1, 5, 0] or server_version > [1, 8, 1000]:
        raise AppstartAbort('Expected docker server version {0}. '
                            'Found server version {1}. Use --force_version '
                            'flag to run Appstart '
                            'anyway'.format(DOCKER_SERVER_VERSION,
                                            server_version))

# TODO(mmuller): "ClientWrapper" is a pretty horrible kludge.  Rewrite it so
# that it doesn't indiscriminately reconnect every time an attribute is
# accessed.


class ClientWrapper(object):

    def __init__(self, **params):
        self.__params = params

    def __getattr__(self, attrname):
        return getattr(docker.Client(**self.__params), attrname)


def get_docker_client():
    """Get the user's docker client.

    Raises:
        AppstartAbort: If there was an error in connecting to the
            Docker Daemon.

    Returns:
        (docker.Client) a docker client that can be used to manage
        containers and images.
    """
    host = os.environ.get('DOCKER_HOST')
    cert_path = os.environ.get('DOCKER_CERT_PATH')
    tls_verify = int(os.environ.get('DOCKER_TLS_VERIFY', 0))

    params = {}
    if host:
        params['base_url'] = (host.replace('tcp://', 'https://')
                              if tls_verify else host)
    elif sys.platform.startswith('linux'):
        # if this is a linux user, the default value of DOCKER_HOST
        # should be the unix socket.  first check if the socket is
        # valid to give a better feedback to the user.
        if os.path.exists(LINUX_DOCKER_HOST):
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                sock.connect(LINUX_DOCKER_HOST)
                params['base_url'] = 'unix://' + LINUX_DOCKER_HOST
            except socket.error:
                get_logger().warning('Found a stale '
                                     '/var/run/docker.sock, '
                                     'did you forget to start '
                                     'your docker daemon?')
            finally:
                sock.close()

    if tls_verify and cert_path:
        # assert_hostname=False is needed for boot2docker to work with
        # our custom registry.
        params['tls'] = docker.tls.TLSConfig(
            client_cert=(os.path.join(cert_path, 'cert.pem'),
                         os.path.join(cert_path, 'key.pem')),
            ca_cert=os.path.join(cert_path, 'ca.pem'),
            verify=True,
            ssl_version=ssl.PROTOCOL_TLSv1,
            assert_hostname=False)

    # pylint: disable=star-args
    client = ClientWrapper(version=DOCKER_API_VERSION,
                           timeout=TIMEOUT_SECS,
                           **params)
    try:
        client.ping()
    except requests.exceptions.ConnectionError as excep:
        raise AppstartAbort('Failed to connect to Docker '
                            'Daemon due to: {0}'.format(excep.message))
    return client


def build_from_directory(dirname, image_name, nocache=False):
    """Builds devappserver base image from source using a Dockerfile."""
    dclient = get_docker_client()

    res = dclient.build(path=dirname,
                        rm=True,
                        nocache=nocache,
                        tag=image_name)

    try:
        log_and_check_build_results(res, image_name)
    except docker.errors.DockerException as err:
        raise AppstartAbort(err.message)


def make_tar_build_context(dockerfile, context_files):
    """Compose tar file for the new devappserver layer's build context.

    Args:
        dockerfile: (io.BytesIO or file) a file-like object
            representing the Dockerfile.
        context_files: ({basestring: basestring, ...}) a dictionary
            mapping absolute filepaths to their destination name in
            the tar build context. This is used to specify other files
            that should be added to the build context.

    Returns:
        (tempfile.NamedTemporaryFile) a temporary tarfile
        representing the docker build context.
    """

    f = tempfile.NamedTemporaryFile()
    t = tarfile.open(mode='w', fileobj=f)

    # Add dockerfile to top level under the name "Dockerfile"
    if isinstance(dockerfile, io.BytesIO):
        dfinfo = tarfile.TarInfo('Dockerfile')
        dfinfo.size = len(dockerfile.getvalue())
        dockerfile.seek(0)
    else:
        dfinfo = t.gettarinfo(fileobj=dockerfile, arcname='Dockerfile')
    t.addfile(dfinfo, dockerfile)

    # Open all of the context files and add them to the tarfile.
    for path in context_files:
        with open(path) as file_object:
            file_info = t.gettarinfo(fileobj=file_object,
                                     arcname=context_files[path])
            t.addfile(file_info, file_object)

    t.close()
    f.seek(0)
    return f


class TarWrapper(object):
    """A convenience wrapper around a tar archive.

    Helps to list contents of directories and read contents of files.
    """

    def __init__(self, tar_file):
        """Initializer for TarWrapper."""
        self.tarfile = tar_file

    def list(self, path):
        """Return the contents of dir_path as a list of file/directory names.

        Args:
            path: (basestring) The path to the directory,
                relative to the root of the tar archive.

        Raises:
            ValueError: If dir_path resolves to something other than
                a directory.
            KeyError: If path cannot be found.

        Returns:
            ([basestring, ...], [basestring, ...])
            A tuple of two lists, collectively representing the files and
            directories contained within the directory specified by dir_path.
            The first element of the tuple is a list of files and the second
            a list of directories.
        """
        tinfo = self.tarfile.getmember(path.lstrip('/'))
        if not tinfo.isdir():
            raise ValueError('"{0}" is not a directory.'.format(path))

        if not path.endswith('/'):
            path += '/'

        files = []
        dirs = []

        # Find all files rooted at path.
        names = [n for n in self.tarfile.getnames() if n.startswith(path)]

        # Calculate the number of components in the path.
        path_len = len(path.strip(os.sep).split(os.sep))

        for name in names:
            # If the name is one component longer, it must be directly inside
            # the directory specified by path (as opposed to being inside a
            # hierarchy of subdirectories that begin at path).
            if len(name.split(os.sep)) - path_len == 1:
                if self.tarfile.getmember(name).isfile():
                    files.append(os.path.basename(name))
                elif self.tarfile.getmember(name).isdir():
                    dirs.append(os.path.basename(name))

        return files, dirs

    def get_file(self, path):
        """Return a file-like object from within the tar archive.

        Args:
            path: (basestring) The path to the file, relative to
                the root of the tar archive.

        Raises:
            ValueError: If path resolves to something other than
                a file.
            KeyError: If path cannot be found.

        Returns:
            (basestring) The contents of the file.
        """
        tinfo = self.tarfile.getmember(path)
        if not tinfo.isfile():
            raise ValueError('"{0}" is not a file.'.format(path))
        return self.tarfile.extractfile(tinfo)


def find_image(image_name):
    dclient = get_docker_client()
    for image in dclient.images():
        if image_name in image['RepoTags']:
            return True
    return False


def log_and_check_build_results(build_res, image_name):
        """Log the results of a docker build.

        Args:
            build_res: ([basestring, ...]) a generator of build results,
                as returned by docker.Client.build
            image_name: (basestring) the name of the image associated
                with the build results (for logging purposes only)

        Raises:
            AppstartAbort: if the build failed.
        """
        get_logger().info('  BUILDING IMAGE  '.center(80, '-'))
        get_logger().info('IMAGE  : %s', image_name)

        success = True
        try:
            for chunk in build_res:
                if not chunk:
                    continue
                line = json.loads(chunk)
                if 'stream' in line:
                    logmsg = line['stream'].strip()
                    get_logger().info(logmsg)
                elif 'error' in line:
                    success = False
                    logmsg = line['error'].strip()
                    get_logger().error(logmsg)
                elif 'errorDetail' in line:
                    success = False
                    logmsg = line['errorDetail']['message'].strip()
                    get_logger().error(logmsg)
        finally:
            get_logger().info('-' * 80)

        # Docker build doesn't raise exceptions, so raise one here if the
        # build was not successful.
        if not success:
            raise AppstartAbort('Image build failed.')
