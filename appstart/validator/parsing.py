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


"""Command line argument parsers for validator."""

# This file conforms to the external style guide.
# pylint: disable=bad-indentation, g-bad-import-order

import argparse

import appstart
import contract


def make_validator_parser():
    parser = argparse.ArgumentParser(
        description='Utility to validate whether or not a docker image '
        'fulfills the runtime contract specified by the Google Cloud '
        'Platform.')
    add_validate_args(parser)
    appstart.parsing.add_appstart_args(parser)
    return parser


def add_validate_args(parser):
    parser.add_argument('--log_file',
                        default=None,
                        help='Logfile to collect validation results.')
    parser.add_argument('--threshold',
                        default='WARNING',
                        choices=[name for _, name in
                                 contract.LEVEL_NAMES.iteritems()],
                        help='The threshold at which validation should fail.')
