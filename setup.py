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

"""A setuptools based setup module.

See:
https://packaging.python.org/en/latest/distributing.html
https://github.com/pypa/sampleproject
"""

# This file conforms to the external style guide.
# pylint: disable=bad-indentation

import codecs
import os
import setuptools


here = os.path.abspath(os.path.dirname(__file__))

with codecs.open(os.path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setuptools.setup(
    name='appstart',
    version='0.8',
    description='A utility to start GAE Managed VMs in containers.',
    long_description=long_description,
    url='https://github.com/GoogleCloudPlatform/appstart',
    author='Mitchell Gouzenko',
    author_email='mgouzenko@gmail.com',
    license='APACHE',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Development Tools',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.2',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
    ],
    keywords='GAE Google App Engine appengine development docker',
    packages=setuptools.find_packages(exclude='tests'),
    package_data={'appstart.devappserver_init': ['Dockerfile', 'das.sh'],
                  'appstart.pinger': ['Dockerfile'],
                  'appstart.sandbox': ['app.yaml']},
    install_requires=[
        'backports.ssl-match-hostname==3.4.0.2',
        'docker-py==1.5.0',
        'mox==0.5.3',
        'PyYAML==3.11',
        'requests==2.8.1',
        'six==1.10.0',
        'websocket-client==0.32.0',
        'wheel==0.24.0',
    ],
    entry_points={
        'console_scripts': [
            'appstart=appstart.cli.start_script:main',
        ],
    },
)
