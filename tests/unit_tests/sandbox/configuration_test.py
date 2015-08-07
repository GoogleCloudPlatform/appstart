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

"""Unit tests for sandbox.configuration."""

# This file conforms to the external style guide.
# pylint: disable=bad-indentation, g-bad-import-order

import os
import tempfile
import textwrap
import unittest

from appstart.sandbox import configuration
from appstart import utils


class ConfigurationTest(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def _make_xml_configs(self, xml_config_file):
        """Make an xml config file and web.xml file in self.temp_dir.

        Args:
            xml_config_file: (basestring) The string contents of the
                xml file.

        Returns:
            (basestring) The path to the appengine-web.xml file.
        """
        conf_file_name = os.path.join(self.temp_dir, 'appengine-web.xml')
        web_xml_name = os.path.join(self.temp_dir, 'web.xml')

        conf_file = open(conf_file_name, 'w')
        conf_file.write(xml_config_file)
        conf_file.close()

        web_xml = open(web_xml_name, 'w')
        web_xml.close()

        return conf_file_name

    def _make_yaml_config(self, yaml_config_file):
        """Make a yaml config file in self.temp_dir.

        Args:
            yaml_config_file: (basestring) The string contents of the yaml file.

        Returns:
            (basestring) The path to the app.yaml file.
        """
        conf_file_name = os.path.join(self.temp_dir, 'app.yaml')

        conf_file = open(conf_file_name, 'w')
        conf_file.write(yaml_config_file)
        conf_file.close()

        return conf_file_name

    def test_init_from_xml_health_checks_on(self):
        xml_files = [textwrap.dedent("""\
                        <appengine-web-app xmlns="http://appengine.google.com/ns/1.0">
                             <vm>true</vm>
                             <health-check>
                                 <enable-health-check>true</enable-health-check>
                             </health-check>
                        </appengine-web-app>"""),
                     textwrap.dedent("""\
                        <appengine-web-app xmlns="http://appengine.google.com/ns/1.0">
                             <vm>true</vm>
                             <health-check>
                                 <enable-health-check></enable-health-check>
                             </health-check>
                        </appengine-web-app>"""),
                     textwrap.dedent("""\
                        <appengine-web-app xmlns="http://appengine.google.com/ns/1.0">
                                 <vm>true</vm>
                        </appengine-web-app>""")]

        for xml_file in xml_files:
            conf_file_name = self._make_xml_configs(xml_file)
            conf = configuration.ApplicationConfiguration(conf_file_name)
            self.assertTrue(conf.health_checks_enabled,
                            'Health checks should be '
                            'enabled in file:\n{0}'.format(xml_file))

    def test_init_from_xml_health_checks_off(self):
        xml_file = textwrap.dedent("""\
                       <appengine-web-app xmlns="http://appengine.google.com/ns/1.0">
                           <vm>true</vm>
                           <health-check>
                               <enable-health-check>false</enable-health-check>
                           </health-check>
                       </appengine-web-app>""")

        conf_file_name = self._make_xml_configs(xml_file)
        conf = configuration.ApplicationConfiguration(conf_file_name)
        self.assertFalse(conf.health_checks_enabled)

    def test_init_from_xml_vm_false(self):
        xml_files = [textwrap.dedent("""\
                        <appengine-web-app xmlns="http://appengine.google.com/ns/1.0">
                        </appengine-web-app>"""),
                     textwrap.dedent("""\
                        <appengine-web-app xmlns="http://appengine.google.com/ns/1.0">
                             <vm></vm>
                        </appengine-web-app>"""),
                     textwrap.dedent("""\
                        <appengine-web-app xmlns="http://appengine.google.com/ns/1.0">
                                 <vm>false</vm>
                        </appengine-web-app>""")]

        for xml_file in xml_files:
            conf_file_name = self._make_xml_configs(xml_file)
            with self.assertRaises(utils.AppstartAbort):
                configuration.ApplicationConfiguration(conf_file_name)

    def test_malformed_xml(self):
        xml_file = 'malformed xml file'
        conf_file_name = self._make_xml_configs(xml_file)
        with self.assertRaises(utils.AppstartAbort):
            configuration.ApplicationConfiguration(conf_file_name)

    def test_init_from_yaml_health_checks_on(self):
        yaml_files = [textwrap.dedent("""\
                          vm: true
                          health_check:
                              enable_health_check: True
                              check_interval_sec: 5
                              timeout_sec: 4
                              unhealthy_threshold: 2
                              healthy_threshold: 2
                              restart_threshold: 60"""),
                      textwrap.dedent("""vm: true""")]

        for yaml_file in yaml_files:
            conf_file_name = self._make_yaml_config(yaml_file)
            conf = configuration.ApplicationConfiguration(conf_file_name)
            self.assertTrue(conf.health_checks_enabled)

    def test_init_from_yaml_health_checks_off(self):
        yaml_file = textwrap.dedent("""\
                        vm: true
                        health_check:
                            enable_health_check: False""")

        conf_file_name = self._make_yaml_config(yaml_file)
        conf = configuration.ApplicationConfiguration(conf_file_name)
        self.assertFalse(conf.health_checks_enabled)

    def test_init_from_yaml_vm_false(self):
        yaml_files = [textwrap.dedent("""\
                          health_check:
                              enable_health_check: True
                              check_interval_sec: 5
                              timeout_sec: 4
                              unhealthy_threshold: 2
                              healthy_threshold: 2
                              restart_threshold: 60"""),
                      textwrap.dedent("""vm: false""")]

        for yaml_file in yaml_files:
            conf_file_name = self._make_yaml_config(yaml_file)
            with self.assertRaises(utils.AppstartAbort):
                configuration.ApplicationConfiguration(conf_file_name)

    def test_malformed_yaml(self):
        yaml_file = 'malformed yaml file'
        conf_file_name = self._make_yaml_config(yaml_file)
        with self.assertRaises(utils.AppstartAbort):
            configuration.ApplicationConfiguration(conf_file_name)
