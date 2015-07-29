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

"""Contains helper functions for constructing a devappserver base image."""

# This file follows the external style guide.
# pylint: disable=bad-indentation, g-bad-import-order

import os
from appstart.container_sandbox import DEVAPPSERVER_IMAGE

import appstart


def base_image_from_dockerfile():
    """Builds devappserver base image from source using a Dockerfile."""
    dclient = appstart.utils.get_docker_client()

    # Since the devappserver base image should be built once, we should
    # have no need to use the cache.
    res = dclient.build(path=os.path.dirname(__file__),
                        rm=True,
                        nocache=True,
                        tag=DEVAPPSERVER_IMAGE)

    appstart.utils.log_and_check_build_results(res, DEVAPPSERVER_IMAGE)
