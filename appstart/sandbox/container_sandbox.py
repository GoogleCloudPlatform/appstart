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
import os
import sys
import time

import docker

import configuration
import container
from .. import utils
from ..utils import get_logger


# Devappserver base image name
DEVAPPSERVER_IMAGE = 'appstart_devappserver_base'

# Pinger image name
PINGER = 'appstart_pinger'

# Maximum attempts to health check application container.
MAX_ATTEMPTS = 30

# Default port that the application is expected to listen on inside
# the application container.
DEFAULT_APPLICATION_PORT = 8080

# Time format for naming images/containers
TIME_FMT = '%Y.%m.%d_%H.%M.%S'

# Java offset for the xml file's location, relative to the root
# diretory of the WAR archive
JAVA_OFFSET = 'WEB-INF/'


class ContainerSandbox(object):
    """Sandbox to manage the user application & devappserver containers.

    This sandbox aims to leave the docker container space untouched.
    Proper usage ensures that application & devappserver containers will
    be created, started, stopped, and destroyed. For proper usage, the
    ContainerSandbox should be used as a context manager (inside a "with"
    statement), or the start and stop functions should be invoked from
    within a try-finally context.
    """
    # pylint: disable=too-many-instance-attributes
    # pylint: disable=too-many-arguments

    def __init__(self,
                 config_file=None,
                 image_name=None,
                 application_id=None,
                 application_port=8080,
                 admin_port=8000,
                 internal_admin_port=32768,
                 internal_api_port=32769,
                 internal_proxy_port=32770,
                 log_path=None,
                 run_api_server=True,
                 storage_path='/tmp/app_engine/storage',
                 nocache=False,
                 timeout=MAX_ATTEMPTS,
                 force_version=False):
        """Get the sandbox ready to construct and run the containers.

        Args:
            config_file: (basestring or None) The relative or full path
                to the config_file of the application. At least one of
                image_name and config_file must be specified. If image_name is
                not specified, this path will be used to help find the
                Dockerfile and build the application container.
                Therefore, if image_name is not specified, there should
                be a Dockerfile in the correct location:

                Non-java apps (apps that use .yaml files)
                1) The .yaml file must be in the root of the app
                   directory.
                2) The Dockerfile must be in the root of the app
                   directory.

                Java apps (apps that are built off java-compat):
                1) The appengine-web.xml file must be in
                   <root>/WEB-INF/ (where <root> is the root
                   directory of the WAR archive.)
                2) The Dockerfile must be in the root of the WAR
                   archive.
                3) There must be a web.xml file in the same
                   directory as the appengine-web.xml file.
            image_name: (basestring or None) If specified, the sandbox
                will run the image associated with image_name instead of
                building an image from the specified application_directory.
            application_id: (basestring) The application ID is
                the unique "appengine application ID" that the app is
                identified by, and can be found in the developer's
                console. While for deployment purposes, this ID is
                important, it's not as important in development. This
                ID only controls which datastore, blobstore, etc the
                sandbox will use. If the sandbox is run consecutively
                with the same application_id, (and of course, the same
                storage_path) the datastore, blobstore, taskqueue, etc
                will persist assuming their data has not been deleted.
            application_port: (int) The port on the docker host that should be
                mapped to the application. The application will be
                accessible through this port.
            admin_port: (int) The port on the docker server host that
                should be mapped to the admin server, which runs inside
                the devappserver container. The admin panel will be
                accessible through this port.
            internal_admin_port: (int) The port INSIDE the devappserver
                container that the admin panel binds to. Because this
                is internal to the container, it can be defaulted.
                In fact, you shouldn't change it from the default unless
                you have a reason to.
            internal_api_port: (int) The port INSIDE the devappserver
                container that the api server should bind to.
                ~Same disclaimer as the one for internal_admin_port.~
            internal_proxy_port: (int) The port INSIDE the devappserver
                container that the proxy should bind to.
                ~Same disclaimer as the one for internal_admin_port.~
            log_path: (basestring or None) The path where the application's
                logs should be collected. Note that the application's logs
                will be collected EXTERNALLY (ie they will collect in the
                docker host's file system) and log_path specifies where
                these logs should go. If log_path is None, a timestamped
                name will be generated for the log directory.
            run_api_server: (bool) Whether or not to run the api server.
                If this argument is set to false, the sandbox won't start
                a devappserver.
            storage_path: (basestring) The path (external to the
                containers) where the data associated with the api
                server's services - datastore, blobstore, etc - should
                collect. Note that this path defaults to
                /tmp/appengine/storage, so it should be changed if the data
                is intended to persist.
            nocache: (bool) Whether or not to use the cache when building
                images.
            timeout: (int) How many seconds to wait for the application
                container to start.
            force_version: (bool) Whether or not to continue in the case
                of mismatched docker versions.
        """
        self.cur_time = time.strftime(TIME_FMT)
        self.app_id = (application_id or
                       time.strftime('%s'))
        self.internal_api_port = internal_api_port
        self.internal_proxy_port = internal_proxy_port
        self.internal_admin_port = internal_admin_port
        self.port = application_port
        self.storage_path = storage_path
        self.log_path = (
            log_path or self.make_timestamped_name(
                '/tmp/log/app_engine/app_logs',
                self.cur_time))
        self.image_name = image_name
        self.admin_port = admin_port
        self.dclient = utils.get_docker_client()
        self.devappserver_container = None
        self.app_container = None
        self.pinger_container = None
        self.nocache = nocache
        self.run_devappserver = run_api_server
        self.timeout = timeout

        if config_file:
            self.conf_path = os.path.abspath(config_file)
            self.app_dir = (self.app_directory_from_config(self.conf_path)
                            if not image_name else None)
        else:
            if not image_name:
                raise utils.AppstartAbort('At least one of config_file and '
                                          'image_name must be specified.')
            self.conf_path = os.path.join(os.path.dirname(__file__),
                                          'app.yaml')
        self.application_configuration = (
            configuration.ApplicationConfiguration(self.conf_path))

        # For Java apps, the xml file must be offset by WEB-INF.
        # Otherwise, devappserver will think that it's a non-java app.
        self.das_offset = (JAVA_OFFSET if
                           self.application_configuration.is_java else '')

        if not force_version:
            utils.check_docker_version(self.dclient)

    def __enter__(self):
        self.start()
        return self

    def start(self):
        """Start the sandbox."""
        try:
            self.create_and_run_containers()
        except:  # pylint: disable=bare-except
            self.stop()
            raise

    def create_and_run_containers(self):
        """Creates and runs app and (optionally) devappserver containers.

        This includes the creation of a new devappserver image, unless
        self.run_devappserver is False. If image_name isn't specified, an
        image is created for the application as well. Newly made containers
        are cleaned up, but newly made images are not.
        """

        if self.run_devappserver:
            # Devappserver must know APP_ID to properly interface with
            # services like datastore, blobstore, etc. It also needs
            # to know where to find the config file, which port to
            # run the proxy on, and which port to run the api server on.
            das_env = {'APP_ID': self.app_id,
                       'PROXY_PORT': self.internal_proxy_port,
                       'API_PORT': self.internal_api_port,
                       'ADMIN_PORT': self.internal_admin_port,
                       'CONFIG_FILE': os.path.join(
                           self.das_offset,
                           os.path.basename(self.conf_path))}
            devappserver_image = self.build_devappserver_image()
            devappserver_container_name = (
                self.make_timestamped_name('devappserver',
                                           self.cur_time))

            # The host_config specifies port bindings and volume bindings.
            # /storage is bound to the storage_path. Internally, the
            # devappserver writes all the db files to /storage. The mapping
            # thus allows these files to appear on the host machine. As for
            # port mappings, we only want to expose the application (via the
            # proxy), and the admin panel.
            devappserver_hconf = docker.utils.create_host_config(
                port_bindings={
                    DEFAULT_APPLICATION_PORT: self.port,
                    self.internal_admin_port: self.admin_port,
                },
                binds={
                    self.storage_path: {'bind': '/storage'},
                }
            )

            self.devappserver_container = container.Container(self.dclient)
            self.devappserver_container.create(
                name=devappserver_container_name,
                image=devappserver_image,
                ports=[DEFAULT_APPLICATION_PORT, self.internal_admin_port],
                volumes=['/storage'],
                host_config=devappserver_hconf,
                environment=das_env)

            self.devappserver_container.start()
            get_logger().info('Starting container: %s',
                              devappserver_container_name)

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
        #     app directory
        app_env = {'API_HOST': '0.0.0.0',
                   'API_PORT': self.internal_api_port,
                   'GAE_LONG_APP_ID': self.app_id,
                   'GAE_PARTITION': 'dev',
                   'GAE_MODULE_INSTANCE': '0',
                   'MODULE_YAML_PATH': os.path.basename(self.conf_path),
                   'GAE_MODULE_NAME': 'default',
                   'GAE_MODULE_VERSION': '1',
                   'GAE_SERVER_PORT': '8080',
                   'USE_MVM_AGENT': 'true'}

        # Build from the application directory iff image_name is not
        # specified.
        app_image = self.image_name or self.build_app_image()
        app_container_name = self.make_timestamped_name('test_app',
                                                        self.cur_time)

        # If devappserver is running, hook up the app to it.
        if self.run_devappserver:
            network_mode = ('container:%s' %
                            self.devappserver_container.get_id())
            ports = port_bindings = None
        else:
            port_bindings = {DEFAULT_APPLICATION_PORT: self.port}
            ports = [DEFAULT_APPLICATION_PORT]
            network_mode = None

        app_hconf = docker.utils.create_host_config(
            port_bindings=port_bindings,
            binds={
                self.log_path: {'bind': '/var/log/app_engine'}
            },

        )

        self.app_container = container.ApplicationContainer(
            self.application_configuration,
            self.dclient)
        self.app_container.create(
            name=app_container_name,
            image=app_image,
            ports=ports,
            volumes=['/var/log/app_engine'],
            host_config=app_hconf,
            environment=app_env)

        # Start as a shared network container, putting the application
        # on devappserver's network stack. (If devappserver is not
        # running, network_mode is None).
        self.app_container.start(network_mode=network_mode)
        get_logger().info('Starting container: %s', app_container_name)

        # Construct a pinger container and bind it to the application's network
        # stack. This will allow the pinger to attempt to connect to the
        # application's ports.
        pinger_name = self.make_timestamped_name('pinger', self.cur_time)
        self.pinger_container = container.PingerContainer(self.dclient)
        self.pinger_container.create(name=pinger_name, image=PINGER)
        get_logger().info('Starting container: {0}'.format(pinger_name))

        self.pinger_container.start(
            network_mode='container:{0}'.format(self.app_container.get_id()))

        self.wait_for_start()
        self.app_container.stream_logs()

    def stop(self):
        """Remove containers to clean up the environment."""
        self.stop_and_remove_containers()

    def __exit__(self, etype, value, traceback):
        self.stop()

    def stop_and_remove_containers(self):
        """Stop and remove application containers."""
        containers_to_remove = [self.app_container,
                                self.devappserver_container,
                                self.pinger_container]
        for cont in containers_to_remove:
            if cont and cont.running():
                cont_id = cont.get_id()
                get_logger().info('Stopping %s', cont_id)
                cont.kill()

                get_logger().info('Removing %s', cont_id)
                cont.remove()

    def wait_for_start(self):
        """Wait for the app container to start.

        Raises:
            utils.AppstartAbort: If the application server doesn't
                start after timeout reach it on 8080.
        """
        host = self.pinger_container.host

        get_logger().info('Waiting for application to listen on port 8080')
        attempt = 1
        graphical = sys.stdout.isatty()

        def print_if_graphical(message):
            if graphical:
                sys.stdout.write(message)
                sys.stdout.flush()

        def exit_loop_with_error(error):
            print_if_graphical('\n')
            raise utils.AppstartAbort(error)

        print_if_graphical('Waiting ')
        while True:
            if attempt > self.timeout:
                exit_loop_with_error('The application server timed out.')

            if (self.run_devappserver and
                not self.devappserver_container.running()):
                # There's been a problem with devappserver, so dump its logs
                self.devappserver_container.stream_logs(stream=False)
                exit_loop_with_error('Devappserver stopped prematurely')

            if attempt % 4 == 0:
                # \033[3D moves the cursor left 3 times. \033[K clears to the
                # end of the line. So, every 4th ping, clear the dots.
                print_if_graphical('\033[3D\033[K')
            else:
                print_if_graphical('.')

            if self.pinger_container.ping_application_container():
                print_if_graphical('\n')
                break

            attempt += 1
            time.sleep(1)

        get_logger().info('Your application is live. '
                          'Access it at: {0}:{1}'.format(host, str(self.port)))

    def build_app_image(self):
        """Build the app image from the Dockerfile in app_dir.

        Returns:
            (basestring) The name of the new app image.
        """
        name = self.make_timestamped_name('app_image', self.cur_time)
        utils.build_from_directory(self.app_dir, name)
        return name

    def build_devappserver_image(self):
        """Build a layer over devappserver to include application files.

        The new image contains the user's config files.

        Returns:
            (basestring) The name of the new devappserver image.
        """
        # pylint: disable=too-many-locals, unused-variable
        # Collect the files that should be added to the docker build
        # context.
        files_to_add = {self.conf_path: None}
        if self.application_configuration.is_java:
            files_to_add[self.get_web_xml(self.conf_path)] = None

        # The Dockerfile should add the config files to
        # the /app folder in devappserver's container.
        dockerfile = """
        FROM %(das_repo)s
        ADD %(path)s/* %(dest)s
        """ %{'das_repo': DEVAPPSERVER_IMAGE,
              'path': os.path.dirname(self.conf_path),
              'dest': os.path.join('/app', self.das_offset)}

        # Construct a file-like object from the Dockerfile.
        dockerfile_obj = io.BytesIO(dockerfile.encode('utf-8'))
        build_context = utils.make_tar_build_context(dockerfile_obj,
                                                     files_to_add)
        image_name = self.make_timestamped_name('devappserver_image',
                                                self.cur_time)

        # Build the devappserver image.
        res = self.dclient.build(fileobj=build_context,
                                 custom_context=True,
                                 rm=True,
                                 nocache=self.nocache,
                                 tag=image_name)

        # Log the output of the build.
        utils.log_and_check_build_results(res, image_name)
        return image_name

    @staticmethod
    def get_web_xml(full_config_file_path):
        """Get (what should be) the path of the web.xml file.

        Args:
            full_config_file_path: (basestring) The absolute path to a
                .xml config file.

        Returns:
            (basestring) The full path to the web.xml file.
        """
        return os.path.join(os.path.dirname(full_config_file_path),
                            'web.xml')

    @staticmethod
    def app_directory_from_config(full_config_file_path):
        """Get the application root directory based on the config file.

        Args:
            full_config_file_path: (basestring) The absolute path to a
                config file.

        Returns:
            (basestring): The application's root directory.
        """
        conf_file_dir = os.path.dirname(full_config_file_path)
        if full_config_file_path.endswith('.yaml'):
            return conf_file_dir
        else:
            return os.path.dirname(conf_file_dir)

    @staticmethod
    def make_timestamped_name(base, time_str):
        """Construct a name for an image or container.

        Note that naming is functionally unimportant and
        serves only to make the output of 'docker images'
        and 'docker ps' look cleaner.

        Args:
            base: (basestring) The prefix of the name.
            time_str: (basestring) The name's timestamp.
        Returns:
            (basestring) The name of the image or container.
        """
        return '%s.%s' % (base, time_str)
