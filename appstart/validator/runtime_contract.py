# Copyright 2015 Google Inc. All Rights Reserved.

"""The runtime contract is a set of requirements on GAE app containers."""

# This file conforms to the external style guide.
# see: https://www.python.org/dev/peps/pep-0008/.
# pylint: disable=bad-indentation, g-bad-import-order

import json
import os
import re
import requests

import contract

# Fields that diagnostic log entries are required to have.
_DIAGNOSTIC_FIELDS = ['timestamp', 'severity', 'thread', 'message']

# Absolute path to directory where the application is expected to write logs.
_LOG_LOCATION = '/var/log/app_engine'

# Diagnostic log location
_DLOG_LOCATION = os.path.join(_LOG_LOCATION, 'app.log.json')

# Access log location
_ALOG_LOCATION = os.path.join(_LOG_LOCATION, 'request.log')

# Custom log directory
_CLOG_LOCATION = os.path.join(_LOG_LOCATION, 'custom_logs')


class HealthClause(contract.ContractClause):
    """Validate that the application responds to '_ah/health' endpoint."""

    title = 'Health checking'
    description = 'Endpoint /_ah/health must respond with status code 200'
    lifecyle_point = contract.POST_START
    error_level = contract.FATAL

    def evaluate_clause(self, app_container):
        url = 'http://{0}:{1}/_ah/health'.format(app_container.host,
                                                 8080)
        rep = requests.get(url)
        self.assertEqual(rep.status_code,
                         200,
                         'the container did not '
                         'properly respond to '
                         'health checks.')


class AccessLogLocationClause(contract.ContractClause):
    """Validate that the application writes access logs to correct location.

    Access logs should be written to _ALOG_LOCATION.
    """

    title = 'Access log location'
    description = ('Container should write access logs to '
                   '{0}'.format(_ALOG_LOCATION))
    lifecyle_point = contract.POST_START
    error_level = contract.UNUSED

    def evaluate_clause(self, app_container):
        try:
            _ = app_container.extract_tar(_ALOG_LOCATION)
        except IOError:
            self.fail('No log file found at {0}'.format(_ALOG_LOCATION))


class AccessLogFormatClause(contract.ContractClause):
    """Validate that the application writes access logs in the correct format.

    Logs must be in Common Log Format or Extended Format.

    Common Log Format: http://httpd.apache.org/docs/1.3/logs.html#common
    Extended Format: http://www.w3.org/TR/WD-logfile.html
    """

    title = 'Access log format'
    description = 'Access logs should be in Common or Extended formats'
    lifecyle_point = contract.POST_START
    error_level = contract.WARNING
    dependencies = [AccessLogLocationClause]

    def evaluate_clause(self, app_container):
        common_log_format = re.compile(r'(\S*) '
                                       r'(\S*) '
                                       r'(\S*) '
                                       r'\[([^]]*)\] '
                                       r'"([^"]*)" '
                                       r'(\S*) '
                                       r'(\S*)')

        logfile_tar = app_container.extract_tar(_ALOG_LOCATION)
        logfile = logfile_tar.get_file(os.path.basename(_ALOG_LOCATION))

        full_line = False
        for line in logfile:
            if line:
                full_line = True
                match = common_log_format.match(line)
                if not match:
                    self.fail('Improperly formatted line:"{0}"'.format(line))
        if not full_line:
            self.fail('No access logs found in log file.')


class CustomLogLocationClause(contract.ContractClause):
    """Validate that the application writes custom logs in correct location.

    The application should write custom logs to the directory _CLOG_LOCATION.
    """

    title = 'Custom log location'
    description = 'Custom logs can be written to {0}'.format(_CLOG_LOCATION)
    lifecyle_point = contract.POST_START
    error_level = contract.UNUSED

    def evaluate_clause(self, app_container):
        try:
            _ = app_container.extract_tar(_CLOG_LOCATION)
        except IOError:
            self.fail('Custom logs directory not found at '
                      '{0}'.format(_CLOG_LOCATION))


class CustomLogExtensionClause(contract.ContractClause):
    """Custom logs must have either .log or .log.json extensions."""

    title = 'Custom log extension'
    description = 'Custom log files must end with .log or .log.json'
    lifecyle_point = contract.POST_START
    error_level = contract.WARNING
    dependencies = [CustomLogLocationClause]

    def evaluate_clause(self, app_container):
        custom_logs_tar = app_container.extract_tar(_CLOG_LOCATION)
        files, dirs = custom_logs_tar.list(os.path.basename(_CLOG_LOCATION))

        for f in files:
            self.assertTrue(f.endswith('.log') or f.endswith('.log.json'),
                            'File "{0}" does not end in .log or '
                            '.log.json'.format(f))
        self.assertEqual(
            len(dirs),
            0,
            ('{0} should only have log files ending '
             'in .log or .log.json.').format(_CLOG_LOCATION))


class DiagnosticLogLocationClause(contract.ContractClause):
    """Validate that the application writes diagnostic log to correct location.

    App must write diagnostic logs to _DLOG_LOCATION.
    """

    title = 'Diagnostic log location'
    description = ('Container should write diagnostic logs to '
                   '{0}'.format(_DLOG_LOCATION))
    error_level = contract.UNUSED
    lifecyle_point = contract.POST_START

    def evaluate_clause(self, app_container):
        try:
            _ = app_container.extract_tar(_DLOG_LOCATION)
        except (ValueError, IOError):
            self.fail('Could not find log file at {0}'.format(_DLOG_LOCATION))


class DiagnosticLogFormatClause(contract.ContractClause):
    """Validate that the application writes diagnostic logs in correct format.

    There must be one json object per line. Furthermore, all log entries must
    have the following fields:

          - timestamp
          - severity
          - thread
          - message
    """
    title = 'Diagnostic log format'
    description = ('Logs must be in json format and have "timestamp", '
                   '"thread", "severity" and "message" fields.')
    lifecyle_point = contract.POST_START
    error_level = contract.WARNING
    dependencies = [DiagnosticLogLocationClause]

    def evaluate_clause(self, app_container):
        logfile_tar = app_container.extract_tar(_DLOG_LOCATION)
        logfile = logfile_tar.get_file(os.path.basename(_DLOG_LOCATION))

        for line in logfile:
            if line:
                try:
                    logmsg = json.loads(line)
                except ValueError:
                    self.fail('Improperly formatted line: "{0}"'.format(line))

                for field in _DIAGNOSTIC_FIELDS:
                    self.assertIn(field,
                                  logmsg,
                                  'Log message missing'
                                  ' "{0}" field: {1}'.format(field,
                                                             line))


class HostnameClause(contract.ContractClause):
    """Validate that container executes /bin/hostname cleanly."""

    title = 'Hostname'
    description = 'Container must make hostname available through /bin/hostname'
    error_level = contract.WARNING
    lifecyle_point = contract.PRE_START

    def evaluate_clause(self, app_container):
        res = app_container.execute('/bin/hostname')
        self.assertEqual(res['ExitCode'],
                         0,
                         'Error while executing /bin/hostname')


class StartClause(contract.ContractClause):
    """Validate that the application responds correctly to _ah/start.

    The application shouldn't respond with status code 500 but all other
    status codes are fine.
    """

    title = 'Start request'
    description = 'Container must respond 200 OK on _ah/start endpoint'
    lifecyle_point = contract.START
    error_level = contract.FATAL

    def evaluate_clause(self, app_container):
        url = 'http://{0}:{1}/_ah/start'.format(app_container.host,
                                                8080)
        r = requests.get(url)
        self.assertNotEqual(r.status_code, 500, 'Request to _ah/start failed.')


class StopClause(contract.ContractClause):
    """Validate that the application responds correctly to _ah/stop.

    The application shouldn't respond with status code 500 but all other
    status codes are fine.
    """

    title = 'Stop request'
    description = 'Send a request to _ah/stop.'
    lifecyle_point = contract.STOP
    error_level = contract.WARNING

    def evaluate_clause(self, app_container):
        """Ensure that the status code is not 500."""
        url = 'http://{0}:{1}/_ah/stop'.format(app_container.host, 8080)
        r = requests.get(url)
        self.assertNotEqual(r.status_code, 500, 'Request to _ah/stop failed.')
