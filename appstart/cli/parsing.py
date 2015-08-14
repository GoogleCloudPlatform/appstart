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
from ..validator import contract


def make_appstart_parser():
    """Make an argument parser to take in command line arguments.

    Returns:
        (argparse.ArgumentParser) the parser.
    """
    parser = argparse.ArgumentParser(
        description='Wrapper to run a managed vm container. If '
        'using for the first time, run \'appstart init\' '
        'to generate a devappserver base image.')
    subparsers = parser.add_subparsers(dest='parser_type')

    run_parser = subparsers.add_parser('run',
                                       help='Run a Managed VM application')
    add_appstart_args(run_parser)

    init_parser = subparsers.add_parser('init',
                                        help='Initialize the Docker '
                                        'environment for Appstart. Must be '
                                        'run before the first use of '
                                        '"appstart run"')
    add_init_args(init_parser)

    validate_parser = subparsers.add_parser('validate')
    validate_parser.set_defaults(parser_type='validate')
    add_validate_args(validate_parser)
    add_appstart_args(validate_parser)
    return parser


def add_validate_args(parser):
    """Adds command line arguments for the validator.

    Args:
       parser: the argparse.ArgumentParser to add the args to.
    """
    parser.add_argument('--log_file',
                        default=None,
                        help='Logfile to collect validation results.')

    parser.add_argument('--threshold',
                        default='WARNING',
                        choices=[name for _, name in
                                 contract.LEVEL_NAMES_TO_NUMBERS.iteritems()],
                        help='The threshold at which validation should fail.')
    parser.add_argument('--tags',
                        nargs='*',
                        help='Tag names of the tests to run')
    parser.add_argument('--verbose',
                        action='store_true',
                        dest='verbose',
                        help='Whether to emit verbose output to stdout.')
    parser.set_defaults(verbose=False)

    parser.add_argument('--list',
                        action='store_true',
                        dest='list_clauses',
                        help='List the clauses available to the validator.')
    parser.set_defaults(list_clauses=False)


def add_init_args(parser):
    parser.add_argument('--use_cache',
                        action='store_false',
                        dest='nocache',
                        help='Flag to enable usage of cache during init.')
    parser.set_defaults(nocache=True)


def add_appstart_args(parser):
    """Add Appstart's command line options to the parser."""
    parser.add_argument('--image_name',
                        default=None,
                        help='The name of the docker image to run. '
                        'If no image is specified, one will be '
                        "built from the application's Dockerfile.")
    parser.add_argument('--application_port',
                        default=8080,
                        type=int,
                        help='The port on the Docker host machine where '
                        'the application should be reached. Defaults to '
                        '8080.')
    parser.add_argument('--admin_port',
                        default='8000',
                        type=int,
                        help='The port on the Docker host machine where '
                        'the admin panel should be reached. Defaults to '
                        '8000.')
    parser.add_argument('--application_id',
                        default=None,
                        help='The api server uses this ID to maintain an '
                        'isolated state for each application. Thus, the '
                        'Application ID determines which Datastore '
                        'the application container has access to. '
                        'In theory, the ID should be the same as the Google '
                        'App Engine ID found in the Google Developers '
                        'Console. However, in practice, an arbitrary ID can '
                        'be chosen during development. By default, if the ID '
                        'is not specified, Appstart chooses a new, '
                        'timestamped ID for every invocation.')
    parser.add_argument('--storage_path',
                        default='/tmp/appengine/storage',
                        help='The api server creates files to store the '
                        "state of the application's datastore, taskqueue, "
                        'etc. By default, these files are stored in '
                        '/tmp/app_engine/storage on the docker host. '
                        'An alternative storage path can be specified with '
                        'this flag. A good use of this flag is to maintain '
                        'multiple sets of test data.')

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
                        help='Managed VM application containers are expected '
                        'to write logs to /var/log/app_engine. Appstart binds '
                        'the /var/log/app_engine directory inside the '
                        'application container to a directory in the Docker '
                        'host machine. This option specifies which directory '
                        'on the host machine to use for the binding. Defaults '
                        'to a timestamped directory inside '
                        '/tmp/log/app_engine.')
    parser.add_argument('--timeout',
                        type=int,
                        default=30,
                        help='How many seconds to wait for the application '
                        'to start listening on port 8080. Defaults to 30 '
                        'seconds.')
    parser.add_argument('config_file',
                        nargs='?',
                        default=None,
                        help='The relative or absolute path to the '
                        "application\'s .yaml or .xml file.")

    ################################ Flags ###############################
    parser.add_argument('--no_cache',
                        action='store_true',
                        dest='nocache',
                        help="Stop Appstart from using Docker's cache during "
                        'image builds.')
    parser.set_defaults(nocache=False)

    parser.add_argument('--no_api_server',
                        action='store_false',
                        dest='run_api_server',
                        help='Stop Appstart from running an API server. '
                        'You do not need one if you do not consume '
                        'standard Google services such as taskqueue, '
                        'datastore, logging, etc.')
    parser.set_defaults(run_api_server=True)

    parser.add_argument('--force_version',
                        action='store_true',
                        dest='force_version',
                        help='Force Appstart to run with mismatched Docker '
                        'version.')
    parser.set_defaults(force_version=False)

    parser.add_argument('--clear_datastore',
                        action='store_true',
                        dest='clear_datastore',
                        help='Clear the contents of the datastore before '
                        'running the application.')
    parser.set_defaults(clear_datastore=False)
