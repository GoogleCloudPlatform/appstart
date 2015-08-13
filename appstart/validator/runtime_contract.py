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

# Fields that a diagnostic log's timestamp are supposed to have.
_TIMESTAMP_FIELDS = ['seconds', 'nanos']

# Absolute path to directory where the application is expected to write logs.
_LOG_LOCATION = '/var/log/app_engine'

# Diagnostic log location
_DLOG_LOCATION = os.path.join(_LOG_LOCATION, 'app.log.json')

# Access log location
_ALOG_LOCATION = os.path.join(_LOG_LOCATION, 'request.log')

# Custom log directory
_CLOG_LOCATION = os.path.join(_LOG_LOCATION, 'custom_logs')

# Permissible status codes for a container to return from _ah/start
_STATUS_CODES = [200, 202, 404, 503]


class LogFormatChecker(object):
    """Class to give clauses the ability to check the format of logs.


    For json logs, there must be one json object per line. Furthermore, all
    entries must have the following fields:

          - timestamp
                - seconds
                - nanos
          - severity
          - thread
          - message

    For access logs, it seems that they're supposed to be
    in Common Log or Extended format. It's not immediately clear if or how
    this is enforced.
    """

    def check_json_log_format(self, logfile):
        """Check if a log file conforms to the proper json format.

        Args:
            logfile: (file-like object) The log file to be checked.
        """
        for line in logfile:
            if line:
                try:
                    logmsg = json.loads(line)
                except ValueError:
                    self.fail('Improperly formatted line: "{0}"'.format(line))

                for field in _DIAGNOSTIC_FIELDS:
                    self.assertIn(
                        field,
                        logmsg,
                        'Log message missing "{0}" field: {1}'.format(field,
                                                                      line))

                ts = logmsg['timestamp']
                if not isinstance(ts, dict) or ts.keys() != _TIMESTAMP_FIELDS:
                    self.fail('{0}\nTimestamps must have fields: '
                              '"{1}"'.format(line, _TIMESTAMP_FIELDS))

    def check_access_log_format(self, logfile):
        """Check if a log file conforms to the Common Log or Extended formats.

        (Currently not implemented)

        Args:
            logfile: (file-like object) The log file to be checked.
        """

        # TODO(gouzenko): *ACTUALLY* figure out how to do this in the best way
        common_log_format = re.compile(r'(\S*) '
                                       r'(\S*) '
                                       r'(\S*) '
                                       r'\[([^]]*)\] '
                                       r'"([^"]*)" '
                                       r'(\S*) '
                                       r'(\S*)')
        full_line = False
        for line in logfile:
            if line:
                full_line = True
                match = common_log_format.match(line)
                if not match:
                    self.fail('Improperly formatted line:"{0}"'.format(line))
        if not full_line:
            self.fail('No access logs found in log file.')


class HealthChecksEnabledClause(contract.ContractClause):
    """Validate that health checking is turned on."""
    title = 'Health checking enabled'
    description = 'Container can enable health checks in configuration'
    lifecycle_point = contract.PRE_START
    error_level = contract.UNUSED
    tags = {'health'}

    def evaluate_clause(self, app_container):
        self.assertTrue(app_container.configuration.health_checks_enabled)


class HealthCheckClause(contract.ContractClause):
    """Validate that the application responds to '_ah/health' endpoint."""

    title = 'Health checking'
    description = 'Endpoint /_ah/health must respond with status code 200'
    lifecycle_point = contract.POST_START
    error_level = contract.FATAL
    dependencies = {HealthChecksEnabledClause}
    tags = {'health'}

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
    lifecycle_point = contract.POST_START
    error_level = contract.UNUSED
    tags = {'logging'}

    def evaluate_clause(self, app_container):
        try:
            _ = app_container.extract_tar(_ALOG_LOCATION)
        except IOError:
            self.fail('No log file found at {0}'.format(_ALOG_LOCATION))


class AccessLogFormatClause(contract.ContractClause, LogFormatChecker):
    """Validate that the application writes access logs in the correct format.

    Logs must be in Common Log Format or Extended Format.

    Common Log Format: http://httpd.apache.org/docs/1.3/logs.html#common
    Extended Format: http://www.w3.org/TR/WD-logfile.html
    """

    title = 'Access log format'
    description = 'Access logs should be in Common or Extended formats'
    lifecycle_point = contract.POST_START
    error_level = contract.WARNING
    dependencies = {AccessLogLocationClause}
    tags = {'logging'}

    def evaluate_clause(self, app_container):
        logfile_tar = app_container.extract_tar(_ALOG_LOCATION)
        logfile = logfile_tar.get_file(os.path.basename(_ALOG_LOCATION))
        self.check_access_log_format(logfile)


class CustomLogLocationClause(contract.ContractClause):
    """Validate that the application writes custom logs in correct location.

    The application should write custom logs to the directory _CLOG_LOCATION.
    """

    title = 'Custom log location'
    description = 'Custom logs can be written to {0}'.format(_CLOG_LOCATION)
    lifecycle_point = contract.POST_START
    error_level = contract.UNUSED
    tags = {'logging'}

    def evaluate_clause(self, app_container):
        try:
            _ = app_container.extract_tar(_CLOG_LOCATION)
        except IOError:
            self.fail('Custom logs directory not found at '
                      '{0}'.format(_CLOG_LOCATION))


class CustomLogFormatClause(contract.ContractClause, LogFormatChecker):
    """Custom logs must have either .log or .log.json extensions."""

    title = 'Custom log format'
    description = ('Json logs must have "timestamp", '
                   '"thread", "severity" and "message" fields. Other logs '
                   'can be plain text.')
    lifecycle_point = contract.POST_START
    error_level = contract.WARNING
    dependencies = {CustomLogLocationClause}
    tags = {'logging'}

    def evaluate_clause(self, app_container):
        custom_logs_tar = app_container.extract_tar(_CLOG_LOCATION)
        custom_logs_root = os.path.basename(_CLOG_LOCATION)
        files, dirs = custom_logs_tar.list(custom_logs_root)

        for f in files:
            if f.endswith('.log.json'):
                logfile = custom_logs_tar.get_file(
                    os.path.join(custom_logs_root, f))
                self.check_json_log_format(logfile)

            elif not f.endswith('.log'):
                self.fail('File "{0}" does not end in .log or '
                          '.log.json'.format(f))

        self.assertEqual(
            len(dirs),
            0,
            ('Directories inside {0} will not have their logs '
             'ingested.').format(_CLOG_LOCATION))


class DiagnosticLogLocationClause(contract.ContractClause):
    """Validate that the application writes diagnostic log to correct location.

    App must write diagnostic logs to _DLOG_LOCATION.
    """

    title = 'Diagnostic log location'
    description = ('Container should write diagnostic logs to '
                   '{0}'.format(_DLOG_LOCATION))
    error_level = contract.UNUSED
    lifecycle_point = contract.POST_START
    tags = {'logging'}

    def evaluate_clause(self, app_container):
        try:
            _ = app_container.extract_tar(_DLOG_LOCATION)
        except (ValueError, IOError):
            self.fail('Could not find log file at {0}'.format(_DLOG_LOCATION))


class DiagnosticLogFormatClause(contract.ContractClause, LogFormatChecker):
    """Validate that the application writes diagnostic logs correctly."""
    title = 'Diagnostic log format'
    description = ('Json logs must have "timestamp", '
                   '"thread", "severity" and "message" fields.')
    lifecycle_point = contract.POST_START
    error_level = contract.WARNING
    dependencies = {DiagnosticLogLocationClause}
    tags = {'logging'}

    def evaluate_clause(self, app_container):
        logfile_tar = app_container.extract_tar(_DLOG_LOCATION)
        logfile = logfile_tar.get_file(os.path.basename(_DLOG_LOCATION))
        self.check_json_log_format(logfile)


class HostnameClause(contract.ContractClause):
    """Validate that container executes /bin/hostname cleanly."""

    title = 'Hostname'
    description = 'Container must make hostname available through /bin/hostname'
    error_level = contract.WARNING
    lifecycle_point = contract.PRE_START

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
    lifecycle_point = contract.START
    error_level = contract.FATAL

    def evaluate_clause(self, app_container):
        url = 'http://{0}:{1}/_ah/start'.format(app_container.host,
                                                8080)
        r = requests.get(url)
        self.assertIn(r.status_code,
                      _STATUS_CODES,
                      'Request to _ah/start failed.')


class StopClause(contract.ContractClause):
    """Validate that the application responds correctly to _ah/stop.

    The application shouldn't respond with status code 500 but all other
    status codes are fine.
    """

    title = 'Stop request'
    description = 'Send a request to _ah/stop.'
    lifecycle_point = contract.STOP
    error_level = contract.WARNING

    def evaluate_clause(self, app_container):
        """Ensure that the status code is not 500."""
        url = 'http://{0}:{1}/_ah/stop'.format(app_container.host, 8080)
        r = requests.get(url)
        self.assertIn(r.status_code,
                      _STATUS_CODES,
                      'Request to _ah/stop failed.')
