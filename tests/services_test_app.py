# Copyright 2015 Google Inc. All Rights Reserved.
"""App that tests api server to see if services are connected.

Each endpoint tests a different service. An endpoints respond with 200
if it is working, and 500 if there are any exceptions
"""
# This file conforms to the external style guide
# pylint: disable=bad-indentation

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


# pylint: disable=invalid-name
urls = [('/datastore', DataStoreTest),
        ('/logging', LoggingTest),
        ('/memcache', MemcacheTest)]

app = webapp2.WSGIApplication(urls, debug=True)
