#!/usr/bin/python
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

"""The script that drives validation."""

# This file conforms to the external style guide.
# see: https://www.python.org/dev/peps/pep-0008/.
# pylint: disable=bad-indentation, g-bad-import-order

import logging
import sys
import warnings

import appstart

import contract
import parsing
import runtime_contract


def main():
    """Perform validation."""
    logging.getLogger('appstart').setLevel(logging.INFO)
    parser = parsing.make_validator_parser()
    args = vars(parser.parse_args())
    logfile = args.pop('log_file')
    threshold = args.pop('threshold')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            validator = contract.ContractValidator(args, runtime_contract)
            success = validator.validate(threshold, logfile)
    except KeyboardInterrupt:
        appstart.utils.get_logger().info('Exiting')
        success = False
    except appstart.utils.AppstartAbort as err:
        if err.message:
            appstart.utils.get_logger().warning(err.message)
        success = False
    if success:
        sys.exit(0)
    sys.exit('Validation failed')


if __name__ == '__main__':
    main()
