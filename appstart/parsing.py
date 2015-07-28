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


"""Command line argument parsers for appstart."""

# This file conforms to the external style guide.
# pylint: disable=bad-indentation

import argparse


def make_appstart_parser():
    """Make an argument parser to take in command line arguments.

    Returns:
        (argparse.ArgumentParser) the parser.
    """
    parser = argparse.ArgumentParser(
        description='Wrapper to run a managed vm container. If '
        'using for the first time, run \'appstart init\' '
        'to generate a devappserver base image.')
    subparsers = parser.add_subparsers()
    run_parser = subparsers.add_parser('run')
    run_parser.set_defaults(parser_type='run')
    init_parser = subparsers.add_parser('init')
    init_parser.set_defaults(parser_type='init')
    add_appstart_args(run_parser)
    return parser


def add_appstart_args(parser):
    """Add Appstart's command line options to the parser."""
    parser.add_argument('--image_name',
                        default=None,
                        help='The name of the docker image to run. '
                        'If no image is specified, one will be '
                        "built from the application's Dockerfile.")
    parser.add_argument('--run_api_server',
                        choices=['True', 'true', 'False', 'false'],
                        nargs=1,
                        default='True',
                        action=BoolAction,
                        help='Specifies whether to run an api server. '
                        'You do not need one if you do not consume '
                        'standard Google services such as taskqueue, '
                        'datastore, logging, etc.')
    parser.add_argument('--application_port',
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
                        default=None,
                        help='The ID determines the Datastore '
                        'the application has access to. '
                        'This should be the same as the Google '
                        'App Engine ID found on the '
                        'Google Developers Console.')
    parser.add_argument('--storage_path',
                        default='/tmp/appengine/storage',
                        help='The directory where the application '
                        'files should get stored. This includes '
                        'the Datastore, Log Service files, Google Cloud '
                        'Storage files, etc. ')

    # The port that the admin panel should bind to inside the container.
    parser.add_argument('--internal_admin_port',
                        type=int,
                        default=32768,
                        help=argparse.SUPPRESS)

    # The port that the api server should bind to inside the container.
    parser.add_argument('--internal_api_port',
                        type=int,
                        default=32769,
                        help=argparse.SUPPRESS)

    # The port that the proxy should bind to inside the container.
    parser.add_argument('--internal_proxy_port',
                        type=int,
                        default=32770,
                        help=argparse.SUPPRESS)

    parser.add_argument('--log_path',
                        default=None,
                        help='The location where this container will '
                        'output logs.')
    parser.add_argument('--use-cache',
                        choices=['True', 'true', 'False', 'false'],
                        nargs=1,
                        default='True',
                        action=BoolAction,
                        help='If false, docker will not use '
                        'the cache during image builds.')
    parser.add_argument('--timeout',
                        type=int,
                        default=30,
                        help='How many seconds to wait for the application '
                        'to start listening on port 8080.')
    parser.add_argument('config_file',
                        nargs='?',
                        default=None,
                        help='The relative or absolute path to the '
                        "application\'s .yaml or .xml file.")


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
