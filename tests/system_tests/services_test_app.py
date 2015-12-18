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

"""App that tests api server to see if services are connected.

Each endpoint tests a different service. An endpoints respond with 200
if it is working, and 500 if there are any exceptions
"""
# This file conforms to the external style guide
# pylint: disable=bad-indentation

import sys
import logging
import socket
import threading

import webapp2

from google.appengine.api import memcache
from google.appengine.api.logservice import logservice
from google.appengine.ext import ndb


def respond_with_error(func):
    """Wraps func so that it writes all Exceptions to response."""
    def get_func(self):
        """Handle a get request respond with 500 status code on error."""
        try:
            func(self)
        except Exception as excep:  # pylint: disable=broad-except
            self.response.set_status(500)
            self.response.write(str(excep))
    return get_func


# pylint: disable=no-member
class Message(ndb.Model):  # pylint: disable=too-few-public-methods
    """Models a simple message."""
    content = ndb.StringProperty()


# pylint: disable=no-self-use
class DataStoreTest(webapp2.RequestHandler):
    """Test that the datastore is connected."""

    @respond_with_error
    def get(self):
        """Ensure that the datastore works."""
        Message(content='Hi', parent=ndb.Key(Message, 'test')).put()

        msg = Message.query(ancestor=ndb.Key(Message, 'test')).get()
        assert msg.content == 'Hi', ('\"%s\" is not \"%s\"' %
                                     (msg.content, 'Hi'))


class LoggingTest(webapp2.RequestHandler):
    """Test that logservice is connected."""

    @respond_with_error
    def get(self):
        """Ensure that the log service works."""
        logservice.write('Hi')
        logservice.flush()


class MemcacheTest(webapp2.RequestHandler):
    """Test that memcache is connected."""

    @respond_with_error
    def get(self):
        """Ensure that memcache works."""
        memcache.set('test', 'hi')
        assert memcache.get('test') == 'hi', 'Memcache failure'


def socket_thread():
    # Function that runs a little server on port 1000 that just echoes back
    # the first chunk of data that it receives.
    logging.info('In socket thread')
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
    s.bind(('', 1000))
    s.listen(5)
    while True:
        c, addr = s.accept()
        data = c.recv(1024)
        c.send(data)
        c.close()


class OpenPort(webapp2.RequestHandler):
    """Open port 1000."""

    def get(self):
        logging.info('Starting socket thread')
        threading.Thread(target=socket_thread).start()
        self.content_type = 'text/plain'
        self.response.write('started thread.')


# pylint: disable=invalid-name
urls = [('/datastore', DataStoreTest),
        ('/logging', LoggingTest),
        ('/memcache', MemcacheTest),
        ('/openport', OpenPort)]

app = webapp2.WSGIApplication(urls, debug=True)
