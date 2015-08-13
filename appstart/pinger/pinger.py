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

"""Pings the application by trying to establish a socket on the specified port.

When Appstart actually starts the application container, it exposes port 8080
on the container by mapping some port X on the Docker host to 8080 within the
application, where X is determined at runtime. For proper behavior, the
application needs to actually be listening on port 8080. To determine if the
application is in fact listening on the port, it's not enough to simply
establish a connection with port X on the Docker host. Due to the way port
mappings are done, a connection can always be established with port X, even if
there's nothing listening on 8080 inside the container. To bypass this issue,
the pinger tries to establish a socket on 8080 from INSIDE the same network
stack as the application.

The alternative is simply to send an actual request to port X. Due to the port
mapping, docker would attempt to forward the request to 8080 inside the
container. The response can then be examined to see if a service is listening.
The problem with this approach is that the request may actually cause the
container to change state in an unpredictable way.

To actually run the pinger, a container is created and put on the same network
stack as the application container. It's then possible to run the pinger via
docker exec and see its exit status.
"""

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
