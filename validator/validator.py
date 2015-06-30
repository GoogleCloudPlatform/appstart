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
    sandbox_kwargs = vars(parsing.make_appstart_parser().parse_args())

    validator = contract.ContractValidator(sandbox_kwargs,
                                           runtime_contract.get_contract())

    result = validator.validate(contract.WARNING)
    if not result:
        sys.exit('Validation failed')


if __name__ == '__main__':
    main()
