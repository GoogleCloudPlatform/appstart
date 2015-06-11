# Copyright 2015 Google Inc. All Rights Reserved.
"""A ContainerSandbox manages the application and devappserver containers.

This includes their creation, termination, and destruction.
ContainerSandbox is intended to be used inside a "with" statement. Inside
the interior of the "with" statement, the user interact with the containers
via the docker api. It may also be beneficial for the user to perform
system tests in this manner.
"""
# This file conforms to the external style guide
# pylint: disable=bad-indentation, g-bad-import-order

import io
import json
import logging
import os
import requests
import socket
import ssl
import sys
import tarfile
import tempfile
import time
import urlparse

import docker


# HTTP timeout for docker client
TIMEOUT_SECS = 60

# Repo where the devappserver base image can be found (change this later)
DEVAPPSERVER_IMAGE = 'gouzenko/devappserver'

# Default docker host if user isn't using boot2docker
LINUX_DOCKER_HOST = '/var/run/docker.sock'

# Maximum attempts to health check application container.
MAX_ATTEMPTS = 30

# Yaml file error message
YAML_MSG = 'The yaml file must be in the application\'s root directory.'

# XML file error message
XML_MSG = 'The xml file must be in the WEB-INF directory.'

# Java offset for the xml file's location, relative to the root
# diretory of the WAR archive
JAVA_OFFSET = 'WEB-INF'


_logger = None


def get_logger():
    global _logger
    if _logger is None:
        _logger = logging.getLogger('appstart')
        sh = logging.StreamHandler()
        sh.setLevel(logging.INFO)
        _logger.addHandler(sh)
    return _logger


class ContainerSandbox(object):
    """Sandbox to manage the user application & devappserver containers.

    This sandbox aims to leave the docker container space untouched.
    The application & devappserver containers should be created, started,
    stopped, and destroyed before the script terminates.
    """
    # pylint: disable=too-many-instance-attributes
    # pylint: disable=too-many-arguments

    def __init__(self,
                 application_directory,
                 admin_port=8000,
                 application_id='temp',
                 app_port=8080,
                 config_file_name='app.yaml',
                 image_name=None,
                 internal_api_port=10000,
                 internal_proxy_port=20000,
                 log_path='/tmp/log/appengine',
                 storage_path='/tmp/appengine/storage',
                 use_cache=True):
        """Get the sandbox ready to construct and run the containers.

        Args:
            application_directory: (basestring) the relative or full path
                to the directory of the application that should be run.
                This path will be used to build the application container.
                Therefore, the application_directory should have a
                Dockerfile. If it doesn't, image_name should be specified.
            admin_port: (int) the port on the docker server host that
                should be mapped to the admin server, which runs inside
                the devappserver container. The admin panel will be
                accessible through this port.
            application_id: (basestring) The application's id. This is
                the unique "appengine application ID" that the app is
                identified by, and can be found in the developer's
                console. While for deployment purposes, this ID is
                important, it's not as important in development. This
                ID only controls which datastore, blobstore, etc the
                sandbox will use. If the sandbox is run consecutively
                with the same application_id, (and of course, the same
                storage_path) the datastore, blobstore, taskqueue, etc
                will persist assuming their data has not been deleted.
            app_port: (int) the port on the docker host that should be
                mapped to the application. The application will be
                accessible through this port.
            config_file_name: (basestring) the name of the application's
                yaml or xml file. If using a yaml file, the yaml file
                should be in the root of the application directory. If
                using an xml file (javascript only), the xml file should
                be in WEB-INF, a folder in the root directory of the
                WAR.
            image_name: (basestring or None) if specified, the sandbox
                will run the image associated with image_name instead of
                building an image from the specified application_directory.
            internal_api_port: (int) the port INSIDE the devappserver
                container that the api server should bind to. Because this
                is internal to the container, it doesn't need to be
                changed. In fact, you shouldn't change it unless you have
                a reason to and know what you're doing.
            internal_proxy_port: (int) the port INSIDE the devappserver
                container that the proxy should bind to. Because this is
                internal to the container, it doesn't need to be changed.
                ~Same disclaimer as the one for internal_api_port.~
            log_path: (basetring) the path where the application's
                logs should be collected. Note that the application's logs
                will be collected EXTERNALLY (ie they will collect in the
                docker host's file system) and log_path specifies where
                these logs should go.
            storage_path: (basestring) the path (external to the
                containers) where the data associated with the api
                server's services - datastore, blobstore, etc - should
                collect. Note that this path defaults to
                /tmp/appengine/storage, so it should be changed if the data
                is intended to persist.
            use_cache: (bool) whether or not to use the cache when building
                images.
        """
        self.devappserver_container = None
        self.app_container = None
        self.app_id = application_id
        self.internal_api_port = internal_api_port
        self.app_directory = application_directory
        self.internal_proxy_port = internal_proxy_port
        self.port = app_port
        self.storage_path = storage_path
        self.log_path = log_path
        self.image_name = image_name
        self.admin_port = admin_port
        self.dclient = ContainerSandbox.get_docker_client()
        self.nocache = not use_cache
        self.app_path, self.config_file_relative_path = (
            ContainerSandbox.parse_directory_structure(
                config_file_name,
                application_directory))

    def __enter__(self):
        self.start()
        return self

    def start(self):
        try:
            self.create_and_run_containers()
        except KeyboardInterrupt:  # pylint: disable=bare-except
            self.stop()
            get_logger().warning('Caught SIGINT when the sandbox '
                                 'was being set up. The environment was '
                                 'successfully cleaned up.')
            sys.exit(0)
        except:
            self.stop()
            get_logger().warning('An error was detected when the sandbox '
                                 'was being set up. The environment was '
                                 'successfully cleaned up.')
            raise

    def create_and_run_containers(self):
        """Creates and runs application and devappserver containers.

        This includes the creation of a new devappserver image. An image
        is created for the application as well. Newly made containers are
        cleaned up, but newly made images are not. Images are named based
        on the folder they're located in.
        """

        # Devappserver must know APP_ID to properly interface with
        # services like datastore, blobstore, etc. It also needs
        # to know where to find the config file, which port to
        # run the proxy on, and which port to run the api server on.
        das_env = {'APP_ID': self.app_id,
                   'PROXY_PORT': self.internal_proxy_port,
                   'API_PORT': self.internal_api_port,
                   'APP_YAML_FILE': self.config_file_relative_path}

        devappserver_image = self.build_devappserver_image()
        devappserver_container_name = self.make_devappserver_container_name()

        # The host_config specifies port bindings and volume bindings.
        # /storage is bound to the storage_path. Internally, the
        # devappserver writes all the db files to /storage. The mapping
        # thus allows these files to appear on the host machine. As for
        # port mappings, we only want to expose the application (via the
        # proxy), and the admin panel.
        devappserver_hconf = docker.utils.create_host_config(
            binds={
                self.storage_path: {'bind': '/storage'},
            },
            port_bindings={
                self.internal_proxy_port: self.port,
                8000: self.admin_port,
            }
        )

        self.devappserver_container = self.dclient.create_container(
            name=devappserver_container_name,
            ports=[self.internal_proxy_port, 8000],
            image=devappserver_image,
            volumes=['/storage'],
            environment=das_env,
            host_config=devappserver_hconf
        )

        self.dclient.start(self.devappserver_container.get('Id'))
        get_logger().info('Starting container: %s', devappserver_container_name)

        # The application container needs several environment variables
        # in order to start up the application properly, as well as
        # look for the api server in the correct place. Notes:
        #
        # GAE_PARTITION is always dev for development modules.
        # GAE_LONG_APP_ID is the "application ID". When devappserver
        #     is invoked, it can be passed a "--application" flag. This
        #     application must be consistent with GAE_LONG_APP_ID.
        # API_HOST is 0.0.0.0 because application container runs on the
        #     same network stack as devappserver.
        # MODULE_YAML_PATH specifies the path to the app from the
        #     app_directory
        app_env = {'API_HOST': '0.0.0.0',
                   'API_PORT': self.internal_api_port,
                   'GAE_LONG_APP_ID': self.app_id,
                   'GAE_PARTITION': 'dev',
                   'GAE_MODULE_INSTANCE': '0',
                   'MODULE_YAML_PATH': self.config_file_relative_path,
                   'GAE_MODULE_NAME': 'default',
                   'GAE_MODULE_VERSION': '1',
                   'GAE_SERVER_PORT': '8080',
                   'USE_MVM_AGENT': 'true'}

        # Build from the application directory iff image_name is not
        # specified.
        app_image = self.image_name or self.build_app_image()
        app_container_name = self.make_app_container_name()

        app_hconf = docker.utils.create_host_config(
            binds={
                self.log_path: {'bind': '/var/log/app_engine'}
            },
        )

        self.app_container = self.dclient.create_container(
            name=app_container_name,
            volumes=['/var/log/app_engine'],
            image=app_image,
            host_config=app_hconf,
            environment=app_env,
        )

        # Start as a shared network container, putting the application
        # on devappserver's network stack.
        self.dclient.start(self.app_container.get('Id'),
                           network_mode='container:%s'
                           % self.devappserver_container.get('Id'))

        get_logger().info('Starting container: %s', app_container_name)
        self.wait_for_start()
        get_logger().info('Your application is live. Access it at: %s:%s',
                          self.get_docker_host(),
                          str(self.port))

    def stop(self):
        """Call __exit__() to clean up the environment."""
        self.stop_and_remove_containers([self.app_container,
                                         self.devappserver_container])

    def __exit__(self, etype, value, traceback):
        """Stop and remove containers to clean up the environment.

        Args:
            etype: (type) the type of exception
            value: (Exception) an instance of the exception raised
            traceback: (traceback) an instance of the current traceback
        Returns:
            True if the sandbox was exited normally (ie exiting the with
            block or KeyboardInterrupt).
        """
        self.stop()

    def stop_and_remove_containers(self, cont_list):
        """Stop and remove application containers.

        Args:
            cont_list: ([{basestring:basestring, ...}, ...]) a list of
                containers that should be stopped and removed. Each
                container is a dictionary (as returned by
                docker.Client.create_container)
        """
        for cont in cont_list:
            if cont:
                cont_id = cont.get('Id')
                get_logger().info('Stopping %s', cont_id)
                self.dclient.kill(cont_id)

                get_logger().info('Removing %s', cont_id)
                self.dclient.remove_container(cont_id)

    def get_docker_host(self):
        """Get hostname of machine where the docker client is running."""
        return urlparse.urlparse(self.dclient.base_url).hostname

    def wait_for_start(self):
        """Wait for the app container to start."""
        attempt = 1
        while True:
            try:
                time.sleep(1)
                get_logger().info('Checking if server running: attempt #%i',
                                  attempt)
                attempt += 1
                rep = requests.get('http://%s:%s/_ah/health' %
                                   (self.get_docker_host(), self.port))
                if rep.status_code == 200:
                    break
                if attempt > MAX_ATTEMPTS:
                    raise RuntimeError('The application server timed out.')
            except requests.exceptions.ConnectionError:
                pass

    def build_app_image(self):
        """Build the app image from the Dockerfile in app_directory.

        Returns:
            (basestring) the name of the new application image.

        """
        image_name = ContainerSandbox.make_app_image_name()
        res = self.dclient.build(path=self.app_path,
                                 rm=True,
                                 nocache=self.nocache,
                                 quiet=False,
                                 tag=image_name)
        ContainerSandbox.log_and_check_build_results(res, image_name)
        return image_name

    def build_devappserver_image(self):
        """Build a layer over devappserver to include application files.

        The new image contains the user's application (including the app.yaml)
        files.

        Returns:
            the name of the new devappserver image.

        Raises:
            Exception: if the app directory or yaml file cannot be found.
        """
        # pylint: disable=too-many-locals, unused-variable
        # Collect the files that should be added to the docker build
        # context.
        files_to_add = []
        for root, dirs, files in os.walk(self.app_path, topdown=False):
            for name in files:
                files_to_add.append(os.path.join(root, name))

        # The Dockerfile should add everything inside the application
        # directory to the /app folder in devappserver's container.
        dockerfile = """
        FROM %(das_repo)s
        ADD %(path)s /app
        """ %{'das_repo': DEVAPPSERVER_IMAGE,
              'path': self.app_path}

        # Construct a file-like object from the Dockerfile.
        dockerfile_obj = io.BytesIO(dockerfile.encode('utf-8'))
        build_context = self.make_tar_build_context(dockerfile_obj,
                                                    files_to_add)
        image_name = ContainerSandbox.make_devappserver_image_name()

        # Build the devappserver image.
        res = self.dclient.build(fileobj=build_context,
                                 custom_context=True,
                                 rm=True,
                                 nocache=self.nocache,
                                 tag=image_name)

        # Log the output of the build.
        ContainerSandbox.log_and_check_build_results(res, image_name)
        return image_name

    @staticmethod
    def parse_directory_structure(config_file_name, app_directory):
        """Verify a correct directory structure.

        There are a few things that constitute a "proper" directory
        structure, and this varies between Java apps and all other
        apps:
            Non-java apps (apps that use .yaml files)
                1) The .yaml file must be in the root of the app
                   directory.
                2) The Dockerfile (if the sandbox is supposed to build
                   the application image) must be in the root of the app
                   directory.
            Java apps (apps that are built off java-compat):
                1) The .xml file must be in /WEB-INF/ (relative to the
                   root directory of the WAR archive.)
                2) The Dockerfile (if the sandbox is supposed to build
                   the application image) must be in the root of the WAR
                   archive.

        Args:
            config_file_name: (basestring) the name of the configuration
                file (must be a yaml or xml file).
            app_directory: (basestring) the root directory of the
                application.

        Returns:
            (basestring, basestring): a tuple where the first element is
            the absolute path to the application root directory, and
            the second element is the relative path to the config
            file. For non-Java applications, the relative path to the
            config file should just be the name of the yaml file
            (since the yaml file) should be in the root directory.
            For Java applications, the relative path should be the
            name of the xml file, prefixed with JAVA_OFFSET.

        Raises:
            ValueError: if one of the following 4 things happens:
                1) The path to the directory doesn't exist.
                2) The config_file_name is actually a path.
                3) The config file is not an xml or yaml file.
                4) The config file could not be found where it should be.
        """
        # Ensure that the application directory exists.
        if os.path.exists(app_directory):
            app_path = os.path.abspath(app_directory)
        else:
            raise ValueError('The path \"%s\" could not be resolved.' %
                             app_directory)

        # Ensure that the config_file_name is a file name and not a path
        if os.path.basename(config_file_name) != config_file_name:
            raise ValueError('config_file_name must be a name, not a path')

        is_yaml_file = True
        if config_file_name.endswith('.yaml'):
            config_file_relative_path = config_file_name
        elif config_file_name.endswith('.xml'):
            is_yaml_file = False
            config_file_relative_path = os.path.join(JAVA_OFFSET,
                                                     config_file_name)
        else:
            raise ValueError('config_file_name is not a valid '
                             'configuration file. Use either a .yaml '
                             'file or .xml file')

        full_conf_path = os.path.join(app_path, config_file_relative_path)
        if not os.path.isfile(full_conf_path):
            raise ValueError('Could not find the application\'s '
                             'config file at %(path)s. %(errormsg)s'
                             % {'path': full_conf_path,
                                'errormsg': (YAML_MSG if is_yaml_file
                                             else XML_MSG)
                               })

        return app_path, config_file_relative_path

    @staticmethod
    def log_and_check_build_results(build_res, image_name):
        """Log the results of a docker build.

        Args:
            build_res: ([basestring, ...]) a generator of build results,
                as returned by docker.Client.build
            image_name: (basestring) the name of the image associated
                with the build results (for logging purposes only)
        Raises:
            docker.errors.DockerException: if the build failed.
        """
        get_logger().info('-' * 20 + '  BUILDING IMAGE  ' + '-' * 20)
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
            get_logger().info('-' * 58)

        if not success:
            raise docker.errors.DockerException('Image build failed.')

    @staticmethod
    def get_docker_client():
        """Get the user's docker client."""
        host = os.environ.get('DOCKER_HOST')
        cert_path = os.environ.get('DOCKER_CERT_PATH')
        tls_verify = os.environ.get('DOCKER_TLS_VERIFY')

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
        client = docker.Client(version='auto',
                               timeout=TIMEOUT_SECS,
                               **params)
        try:
            client.ping()
        except requests.exceptions.ConnectionError as excep:
            get_logger().error('Failed to connect to Docker '
                               'Daemon due to: %s', excep)
            raise
        return client

    @staticmethod
    def make_app_container_name():
        """Construct a name for the app container.

        Returns:
            (basestring) the name of the app container
        """
        return 'test_app.' + str(time.strftime('%Y.%m.%d_%H.%M.%S'))

    # pylint: disable=invalid-name
    @staticmethod
    def make_devappserver_container_name():
        """Construct a name for the devappserver container.

        Returns:
            (basestring) the name of the devappserver container
        """
        return 'devappserver.' + str(time.strftime('%Y.%m.%d_%H.%M.%S'))

    @staticmethod
    def make_app_image_name():
        """Construct a name for the application image.

        The image name is based on the application directory, with
        the assumption that the directory's name somehow describes
        the application. Note that naming is totally unimportant and
        serves only to make the output of 'docker images' look cleaner.

        Returns:
            (basestring) the name of the app image
        """
        return 'application_image'

    @staticmethod
    def make_devappserver_image_name():
        """Construct a name for the new devappserver image.

        Returns:
            (basestring) the name of the devappserver image
        """
        return 'devappserver_image'

    @staticmethod
    def make_tar_build_context(dockerfile, context_files):
        """Compose tar file for the new devappserver layer's build context.

        Args:
            dockerfile: (io.BytesIO) a file-like buffer representing the
                Dockerfile.
            context_files: ([basestring, ...]) a list of absolute filepaths
                for other files that should be added to the build context.

        Returns:
            (TarFile) a temporary tarfile representing the docker build
            context
        """
        f = tempfile.NamedTemporaryFile()
        t = tarfile.open(mode='w', fileobj=f)

        # Add dockerfile to top level under the name "Dockerfile"
        dfinfo = tarfile.TarInfo('Dockerfile')
        dfinfo.size = len(dockerfile.getvalue())
        dockerfile.seek(0)
        t.addfile(dfinfo, dockerfile)

        # Open all of the context files and add them to the tarfile.
        for file_name in context_files:
            with open(file_name) as file_object:
                file_info = t.gettarinfo(fileobj=file_object)
                t.addfile(file_info, file_object)

        t.close()
        f.seek(0)
        return f
