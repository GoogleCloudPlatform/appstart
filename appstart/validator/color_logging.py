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

"""Color logging for the validator."""

# This file conforms to the external style guide.
# see: https://www.python.org/dev/peps/pep-0008/.
# pylint: disable=bad-indentation, g-bad-import-order

import logging

import color_formatting


class LogfileHandler(logging.FileHandler):

    def emit(self, record):
        # Only emit the record if it wasn't an empty string or separator.
        if str(record.msg).replace('=', ''):
            super(LogfileHandler, self).emit(record)


class LoggingStream(object):
    """A fake 'stream' to be used for logging in tests."""

    def __init__(self, logfile, verbose_printing, formatter=None):
        self.__logger = logging.getLogger('validator')
        self.__logger.setLevel(logging.DEBUG)

        # Don't send messages to root logger.
        self.__logger.propagate = False

        # Stream handler prints to console.
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(logging.DEBUG if verbose_printing
                                else logging.INFO)

        # Color formatter replaces colors (like {red}, {warn}, etc) with ansi
        # escape sequences.
        stream_handler.setFormatter(fmt=formatter or
                                    color_formatting.ColorFormatter())
        self.__logger.addHandler(stream_handler)

        if logfile:
            # This special logfile handler doesn't emit empty records.
            logfile_handler = LogfileHandler(logfile)
            logfile_handler.setLevel(logging.DEBUG)

            # Use a colorless formatter since this handler logs to a file.
            logfile_handler.setFormatter(
                fmt=color_formatting.ColorFormatter(tty=False))
            self.__logger.addHandler(logfile_handler)

    def writeln(self, message=None, lvl=logging.INFO):
        """Write logs, but do proper formatting first.

        Args:
            message: (basestring) A message that may or may not contain.
                unformatted replacement fields.
            lvl: (int) The logging level.
        """
        if message is None:
            message = ''

        self.__logger.log(lvl, msg=message)
