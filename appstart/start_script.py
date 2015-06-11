#!/usr/bin/python
# Copyright 2015 Google Inc. All Rights Reserved.
"""A python wrapper to start devappserver and a managed vm application.

Both the devappserver and the application will run in their respective
containers.
"""
# This file conforms to the external style guide
# pylint: disable=bad-indentation

import argparse
import logging
import time

from appstart import container_sandbox


def main():
    """Run devappserver and the user's application in separate containers.

    The application must be started with the proper environment variables,
    port bindings, and volume bindings. The devappserver image runs a
    standalone api server.
    """
    logging.basicConfig(
        format='%(levelname)-8s %(asctime)s '
        '%(filename)s:%(lineno)s] %(message)s')
    logging.getLogger('appstart').setLevel(logging.INFO)
    
    args = make_parser().parse_args()
    try:
        with container_sandbox.ContainerSandbox(**vars(args)):
            while True:
                time.sleep(10000)
    except KeyboardInterrupt:
        logging.info('Appstart terminated by user.')


def make_parser():
    """Make an argument parser to take in command line arguments.

    Returns:
        (argparse.ArgumentParser) the parser
    """
    parser = argparse.ArgumentParser(
        description='Wrapper to run a managed vm container')
    parser.add_argument('--image_name',
                        default=None,
                        help='The name of the docker image to run. '
                        'If the docker image is specified, no '
                        'new docker image will be built from the '
                        'application\'s Dockerfile.')
    parser.add_argument('--app_port',
                        default=8080,
                        type=int,
                        help='The port where the application should be '
                        'reached externally.')
    parser.add_argument('--admin_port',
                        default='8000',
                        type=int,
                        help='The port where the admin panel should be '
                        'reached externally. ')
    parser.add_argument('--application_id',
                        default='temp',
                        help='The id of the application.'
                        'This id will determine what datastore '
                        'the application will have access to '
                        'and should be the same as the Google '
                        'App Engine id, which can be found on the '
                        'developers\' console.')
    parser.add_argument('--storage_path',
                        default='/tmp/appengine/storage',
                        help='The directory where the application '
                        'files should get stored. This includes '
                        'the Datastore, logservice files, Google Cloud '
                        'Storage files, etc. ')
    parser.add_argument('--config_file_name',
                        default='app.yaml',
                        help='The name of the application\'s config file. '
                        'Non-Java applications should have a yaml config '
                        'file in the application\'s root directory. Java '
                        'applications that are built on the java-compat '
                        'docker image should have an xml file in the '
                        'WEB-INF directory, which resides in the root '
                        'of the WAR archive. ')

    # The port that the proxy should bind to inside the container.
    parser.add_argument('--internal_proxy_port',
                        type=int,
                        default=20000,
                        help=argparse.SUPPRESS)

    # The port that the api server should bind to inside the container.
    parser.add_argument('--internal_api_port',
                        type=int,
                        default=10000,
                        help=argparse.SUPPRESS)
    parser.add_argument('--log_path',
                        default='/tmp/log/appengine',
                        help='The location where this container will '
                        'output logs.')
    parser.add_argument('--use-cache',
                        choices=['True', 'true', 'False', 'false'],
                        nargs=1,
                        default='True',
                        action=BoolAction,
                        help='If false, docker will not use '
                        'the cache during image builds.')
    parser.add_argument('application_directory',
                        help='The root directory of the application. '
                        'This directory should contain a Dockerfile '
                        'if image_name is not specified.')
    return parser


# pylint: disable=too-few-public-methods
class BoolAction(argparse.Action):
    """Action to parse boolean values."""

    def __init__(self, option_strings, dest, nargs=None, **kwargs):
        """Call constructor of arpargse.Action."""
        super(BoolAction, self).__init__(option_strings, dest, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        """Parse boolean arguments and populate namespace."""
        if values in ['True', 'true']:
            setattr(namespace, self.dest, True)
        elif values in ['False', 'false']:
            setattr(namespace, self.dest, False)

if __name__ == '__main__':
    main()
