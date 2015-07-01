# Copyright 2015 Google Inc. All Rights Reserved.

"""Color logging for the validator."""

# This file conforms to the external style guide.
# see: https://www.python.org/dev/peps/pep-0008/.
# pylint: disable=bad-indentation, g-bad-import-order

import logging
import string

import color_formatting


class LogfileHandler(logging.FileHandler):

    def emit(self, record):
        # Only emit the record if it wasn't an empty string or separator.
        if str(record.msg).replace('=', ''):
            super(LogfileHandler, self).emit(record)


class StringFormatDict(dict):
    """Wrapper around dict.

    Instead of raising KeyError, this returns missing keys surrounded in "{}".
    """

    def __missing__(self, key):
        return '{{{key}}}'.format(key=key)


class LoggingStream(object):
    """A fake 'stream' to be used for logging in tests."""

    def __init__(self, logfile, formatter=None):
        self.__logger = logging.getLogger('validator')
        self.__logger.setLevel(logging.DEBUG)

        # Don't send messages to root logger.
        self.__logger.propagate = False

        # Stream handler prints to console.
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(logging.INFO)

        # Color formatter replaces colors (like {red}, {warn}, etc) with ansi
        # escape sequences.
        stream_handler.setFormatter(fmt=formatter or
                                    color_formatting.ColorFormatter())
        self.__logger.addHandler(stream_handler)

        if logfile:
            # Logfile handler doesn't emit empty records.
            logfile_handler = LogfileHandler(logfile)
            logfile_handler.setLevel(logging.DEBUG)

            # Eliminate colors if writing to a log file.
            logfile_handler.setFormatter(
                fmt=color_formatting.ColorFormatter(tty=False))
            self.__logger.addHandler(logfile_handler)

    def writeln(self, message=None, lvl=logging.INFO, **fmt_kwargs):
        """Write logs, but do proper formatting first.

        Args:
            message: (basestring) A message that may or may not contain.
                unformatted replacement fields.
            lvl: (int) The logging level.
            **fmt_kwargs: (dict) Args used to partially format the message
                by filling in some of the replacement fields.
        """
        if message is None:
            message = ''

        formatter = string.Formatter()

        # The message might have color formatting that we're not ready to
        # replace just yet. This customized dict leaves replacement fields
        # untouched if there is no argument to perform a replacement.
        name_mapping = StringFormatDict(fmt_kwargs)
        formatted_message = formatter.vformat(message, (), name_mapping)

        # The formatter attached to the log handlers will finish formatting
        # by filling the color replacement fields.
        self.__logger.log(lvl, msg=formatted_message)
