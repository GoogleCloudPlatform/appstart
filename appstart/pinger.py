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

# This file conforms to the external style guide.
# pylint: disable=bad-indentation

"""'Pings' the application by attempting to establish a socket on port 8080."""

import httplib
import logging
import socket
import sys


def ping():
    """Check if container is listening on the specified port."""
    try:
        host = sys.argv[1]
        port = int(sys.argv[2])
    except (IndexError, ValueError):
        host = '0.0.0.0'
        port = 8080

    con = None
    success = True
    try:
        con = httplib.HTTPConnection(host, port)
        con.connect()
    except (socket.error, httplib.HTTPException):
        success = False
    finally:
        if con:
            con.close()
    if success:
        logging.info('success')
        sys.exit(0)
    logging.info('failure')
    sys.exit(1)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    ping()
