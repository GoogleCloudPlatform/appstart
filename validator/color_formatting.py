# Copyright 2015 Google Inc. All Rights Reserved.

"""Color formatting for the validator's logging stream handlers."""

# This file conforms to the external style guide.
# see: https://www.python.org/dev/peps/pep-0008/.
# pylint: disable=bad-indentation, g-bad-import-order

import logging

# Color escapes.
GREEN = '\033[92m'
RED = '\033[91m'
WARN = '\033[93m'
END = '\033[0m'
BOLD = '\033[1m'


class ColorFormatter(logging.Formatter):
    """Formats log messages with or without colors."""

    def __init__(self, tty=True, **kwargs):
        super(ColorFormatter, self).__init__(**kwargs)
        self.tty = tty

    def format(self, record):
        # Let the base Formatter do all of the heavy lifting.
        message = super(ColorFormatter, self).format(record)

        # If the destination is a tty, replace all the color replacement fields
        # with the appropriate ansi escape pattern.
        if self.tty:
            return message.format(red=RED,
                                  green=GREEN,
                                  warn=WARN,
                                  end=END,
                                  bold=BOLD)

        # Otherwise (if we're printing to a log file) eliminate the colors.
        else:
            return message.format(red='', green='', warn='', end='', bold='')
