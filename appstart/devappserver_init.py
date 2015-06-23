# Copyright 2015 Google Inc. All Rights Reserved.
"""Contains helper functions for constructing a devappserver base image."""
# This file follows the external style guide.
# pylint: disable=bad-indentation, g-bad-import-order

import logging
import os

from appstart import utils
from appstart.container_sandbox import DEVAPPSERVER_IMAGE


# Devappserver relative path from google-cloud-sdk/bin.
DAS_REL_PATH = '../platform/google_appengine/dev_appserver.py'

# The name of the gcloud executable
GCLOUD_NAME = 'gcloud'

# Directories needed for devappserver build (speeds up build context)
# Paths are relative to the sdk root.
TARGET_DIRS = ['platform/google_appengine', 'lib/docker']


def base_image_from_root():
    """Builds devappserver base image from local copy of gcloud."""

    # Get path to the gcloud sdk's root.
    sdk_path = sdk_path_from_env()

    dclient = utils.get_docker_client()

    # Map out which files to add to the build context.
    files_to_add = {}
    for relpath in TARGET_DIRS:
        target_dir_root = os.path.join(sdk_path, relpath)

        # Add each file in the target dir to the build context
        # pylint: disable=unused-variable
        for root, dirs, files, in os.walk(target_dir_root):
            for name in files:
                full_path = os.path.join(root, name)
                prefix_len = len(sdk_path)
                dest_name = full_path[prefix_len:]
                files_to_add[full_path] = dest_name

    # Locate the dockerfile and open it. Then use it to make the build
    # context, along with the other necessary files.
    dockerfile = os.path.join(os.path.dirname(__file__), 'Dockerfile')
    with open(dockerfile) as dfile:
        context = utils.make_tar_build_context(dfile, files_to_add)

    # Since the devappserver base image should be built once, we should
    # have no need to use the cache.
    res = dclient.build(fileobj=context,
                        custom_context=True,
                        rm=True,
                        nocache=True,
                        tag=DEVAPPSERVER_IMAGE)

    utils.log_and_check_build_results(res, DEVAPPSERVER_IMAGE)


def sdk_path_from_env():
    """Get the gcloud sdk root from the PATH environment variable.

    Returns:
        (basestring) the absolute path to the sdk root.
    """
    paths = os.environ['PATH'].split(os.pathsep)

    sdk_path = None
    for path in paths:
        is_sdk = (os.path.exists(os.path.join(path, GCLOUD_NAME)) and
                  os.path.basename(path) == 'bin' and
                  os.path.exists(os.path.join(path, DAS_REL_PATH)))
        if is_sdk:
            sdk_path = os.path.abspath(os.path.join(path, '..'))
            break

    if sdk_path is None:
        logging.error('Could not find gcloud sdk path.')

    return sdk_path
