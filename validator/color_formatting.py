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
            return message % {'red': RED,
                              'green': GREEN,
                              'warn': WARN,
                              'end': END,
                              'bold': BOLD}

        # Otherwise (if we're printing to a log file) eliminate the colors.
        else:
            return message % {'red': '',
                              'green': '',
                              'warn': '',
                              'end': '',
                              'bold': ''}
