#!/usr/bin/python
# Copyright 2015 Google Inc. All Rights Reserved.

"""The script that drives validation."""

# This file conforms to the external style guide.
# see: https://www.python.org/dev/peps/pep-0008/.
# pylint: disable=bad-indentation, g-bad-import-order

import logging
import sys

from appstart import parsing

import contract
import runtime_contract


def main():
    """Perform validation."""
    logging.getLogger('appstart').setLevel(logging.INFO)
    parser = parsing.make_appstart_parser()
    parser.add_argument('--log_file',
                        default=None,
                        help='Logfile to collect validation results.')
    args = vars(parser.parse_args())
    logfile = args.get('log_file')
    args.pop('log_file', None)
    validator = contract.ContractValidator(args, runtime_contract)

    result = validator.validate(contract.FATAL, logfile)
    if not result:
        sys.exit('Validation failed')

if __name__ == '__main__':
    main()
