#!/usr/bin/python
# Copyright 2015 Google Inc. All Rights Reserved.
"""A python wrapper to start devappserver and a managed vm application.

Both the devappserver and the application will run in their respective
containers.
"""
# This file conforms to the external style guide
# pylint: disable=bad-indentation

import logging
import sys
import time

from appstart import container_sandbox
from appstart import devappserver_init
from appstart import parsing


def main():
    """Run devappserver and the user's application in separate containers.

    The application must be started with the proper environment variables,
    port bindings, and volume bindings. The devappserver image runs a
    standalone api server.
    """
    logging.getLogger('appstart').setLevel(logging.INFO)
    if 'init' in sys.argv:
        args = vars(parsing.make_init_parser().parse_args(sys.argv[2:]))
        devappserver_init.base_image_from_root(**args)
    else:
        args = parsing.make_appstart_parser().parse_args()
        try:
            with container_sandbox.ContainerSandbox(**vars(args)):
                while True:
                    time.sleep(10000)
        except KeyboardInterrupt:
            logging.info('Appstart terminated by user.')


if __name__ == '__main__':
    main()
