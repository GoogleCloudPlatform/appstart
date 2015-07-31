# Copyright 2015 Google Inc. All Rights Reserved.

"""Parser of application configuration files.

These include appengine-web.xml files and *.yaml files.
"""

# This file conforms to the external style guide.
# pylint: disable=bad-indentation, g-bad-import-order

import os
import xml.dom.minidom
import yaml

from .. import utils


class ApplicationConfiguration(object):
    """Class to parse an xml or yaml config file.

    Extract the necessary configuration details. Currently, only health
    check information is required.
    """

    def __init__(self, config_file):
        """Initializer for ApplicationConfiguration.

        Args:
            config_file: (basestring) The absolute path to the configuration
                file.

        Raises:
            utils.AppstartAbort: If the config file neither ends with .yaml
                nor is an appengine-web.xml file.
        """
        self.verify_structure(config_file)
        if config_file.endswith('.yaml'):
            self.__init_from_yaml_config(config_file)
            self.is_java = False
        elif os.path.basename(config_file) == 'appengine-web.xml':
            self.__init_from_xml_config(config_file)
            self.is_java = True
        else:
            raise utils.AppstartAbort('{0} is not a valid '
                                      'configuration file. Use either a .yaml '
                                      'file or .xml file.'.format(config_file))

    def __init_from_xml_config(self, xml_config):
        """Initialize from an xml file.

        Args:
            xml_config: (basestring) The absolute path to an appengine-web.xml
                file.

        Raises:
            utils.AppstartAbort: If "<vm>true</vm>" is not set in the
                configuration.
        """
        root = xml.dom.minidom.parse(xml_config).firstChild
        try:
            vm = root.getElementsByTagName('vm')[0]
            assert vm.firstChild.nodeValue == 'true'
        except (IndexError, AttributeError, AssertionError):
            raise utils.AppstartAbort(
                '"<vm>true</vm>" must be set in '
                '{0}'.format(os.path.basename(xml_config)))

        # Assume that health checks are enabled.
        self.health_checks_enabled = True
        health = root.getElementsByTagName('health-check')
        if health:
            checks = health[0].getElementsByTagName('enable-health-check')
            if checks:
                value = checks[0].firstChild
                if value and value.nodeValue != 'true':
                    self.health_checks_enabled = False

    def __init_from_yaml_config(self, yaml_config):
        """Initialize from a yaml file.

        Args:
            yaml_config: (basestring) The absolute path to a *.yaml
                file.

        Raises:
            utils.AppstartAbort: if "vm: true" is not set in the configuration.
        """
        yaml_dict = yaml.load(open(yaml_config))
        if not yaml_dict.get('vm'):
            raise utils.AppstartAbort(
                '"vm: true" must be set in '
                '{0}'.format(os.path.basename(yaml_config)))
        hc_options = yaml_dict.get('health_check')
        if hc_options and not hc_options.get('enable_health_check', True):
            self.health_checks_enabled = False
        else:
            self.health_checks_enabled = True

    @staticmethod
    def verify_structure(full_config_file_path):
        """Verify the existence of the configuration files.

        If the config file is an xml file, there also
        needs to be a web.xml file in the same directory.

        Args:
            full_config_file_path: (basestring) The absolute path to a
                .xml or .yaml config file.

        Raises:
            utils.AppstartAbort: If the application is a Java app, and
                the web.xml file cannot be found, or the config
                file cannot be found.
        """
        if not os.path.exists(full_config_file_path):
            raise utils.AppstartAbort('The path %s could not be resolved.' %
                                      full_config_file_path)

        if full_config_file_path.endswith('.xml'):
            webxml = os.path.join(os.path.dirname(full_config_file_path),
                                  'web.xml')
            if not os.path.exists(webxml):
                raise utils.AppstartAbort('Could not find web.xml at: '
                                          '{}'.format(webxml))
