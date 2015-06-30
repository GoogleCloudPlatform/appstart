# Copyright 2015 Google Inc. All Rights Reserved.

"""This file contains the classes that form a framework for validation.

The validation framework is based on the python unittest framework.
"""

# This file conforms to the external style guide.
# see: https://www.python.org/dev/peps/pep-0008/.
# pylint: disable=bad-indentation, g-bad-import-order

import collections
import logging
import time
import unittest

import appstart


# Error levels
FATAL = 20
WARNING = 10
_LEVELS = {20: 'FATAL',
           10: 'WARNING'}

# Lifecycle timeline
POST_STOP = 30
POST_START = 20
PRE_START = 10
_TIMELINE = collections.OrderedDict({30: 'Post Stop',
                                     20: 'Post Start',
                                     10: 'Pre Start'})

# Color escapes.
GREEN = '\033[92m'
RED = '\033[91m'
WARN = '\033[93m'
END = '\033[0m'


class ContractTestResult(unittest.TextTestResult):
    """Collect and report test results."""

    def __init__(self, threshold, stream, description, verbosity):
        """Create a ContractTestResult.

        Args:
            threshold: (int) One of the error levels in _LEVELS.keys().
                Validation will result in failure if and only if a
                test with an error_level greater than threshold fails.
            stream: (file-like object) Any object which has both a "write"
                function and an "isatty" function. Test results will be
                recorded by writing to the stream.
            description: (bool) Toggles whether or not test descriptions
                will be written in output.
            verbosity: (int) Sets the level of output verbosity.
        """
        super(ContractTestResult, self).__init__(stream,
                                                 description,
                                                 verbosity)

        # Assume that the tests will be successful
        self.success = True
        self.__threshold = threshold

        # A list of successful tests.
        self.success_list = []

        # { error_level -> error_count } A breakdown of error
        # frequency by level.
        self.error_stats = {}

        self.__is_tty = stream.isatty()

    def addSuccess(self, test):
        """Wrapper around TestResult's addSuccess.

        In addition to what the parent function does,
        add the current test to the list of successful tests.

        Args:
            test: (ContractClause) A contract clause that has
                succeeded.
        """
        unittest.TestResult.addSuccess(self, test)
        self.success_list.append(test)

    def __update_error_stats(self, test):
        """Update the appropriate error level in self.error_stats.

        Args:
            test: (ContractClause) A contract clause that has
                failed.
        """

        # If this level of test is not yet in the error_stats,
        # initialize it to 0.
        self.error_stats.setdefault(test.error_level, 0)
        self.error_stats[test.error_level] += 1
        if test.error_level >= self.__threshold:
            self.success = False

    def addError(self, test, err):
        """Wrapper around parent's addError.

        In addition, update the error stats and success flag.

        Args:
            test: (ContractClause) A contract clause that has
                failed.
            err: (type, value, traceback) A tuple as returned by sys.exc_info
        """
        unittest.TestResult.addError(self, test, err)
        self.__update_error_stats(test)

    def addFailure(self, test, err):
        """Modified version of parent's addFailure.

        In addition, update the error stats, and success flag.

        Args:
            test: (ContractClause) A contract clause that has
                failed.
            err: (type, value, traceback) A tuple as returned by sys.exc_info
        """
        unittest.TestResult.addFailure(self, test, err)
        self.__update_error_stats(test)

        test.failure_message = err[1] or test.shortDescription()

    def getDescription(self, test):
        """Get the description of a test.

        Args:
            test: (ContractClause) The clause whose description
                to get.

        Returns:
            (basestring) The description of the test.
        """
        return test.shortDescription()

    def print_successes(self):
        """Write successes to the stream."""
        green, end = (GREEN, END) if self.__is_tty else ('', '')

        for test in self.success_list:
            self.stream.writeln('%s[PASSED]%s %s' % (green, end, test.title))

    def printErrorList(self, flavor, errors):
        """Helper function to write failures and errors to the stream."""
        red, warn, end = (RED, WARN, END) if self.__is_tty else ('', '', '')

        for test, err in errors:
            self.stream.writeln(
                '{c}[{flavor} ({level})]{end} {title}: {msg}'.format(
                    c=red if test.error_level > self.__threshold else warn,
                    flavor=flavor,
                    level=_LEVELS[test.error_level],
                    end=end,
                    title=test.title,
                    msg=getattr(test, 'failure_message', err)))


class ContractTestRunner(unittest.TextTestRunner):
    """Test runner for a single suite of runtime contract clauses.

    There is one suite per point in _TIMELINE, so each instance of
    ContractTestRunner corresponds to a single _TIMELINE point.
    """

    def __init__(self, threshold):
        """Create a ContractTestRunner.

        Args:
            threshold: (int) One of the error levels as specified above
                in the _LEVELS global var. Validation will result in
                failure if and only if a test with an error_level greater
                than threshold fails.
        """
        super(ContractTestRunner, self).__init__()
        self.__threshold = threshold

    def _makeResult(self):
        """Make a ContractTestResult to capture the test results.

        Returns:
            (ContractTestResult) the test result object.
        """
        return ContractTestResult(self.__threshold,
                                  self.stream,
                                  self.descriptions,
                                  self.verbosity)

    def run(self, test, point):
        """Run the test suite.

        This should be called once per point in _TIMELINE. This function
        is almost the same as unittest.TestSuite.run, differing minorly
        in formatting.

        Args:
            test: (unittest.TestSuite) a suite of ContractClauses,
                corresponding to a point in _TIMELINE.
            point: (basestring) the name of the point in _TIMELINE.

        Returns:
            (ContractTestResult) The result of the tests.
        """
        self.stream.writeln('\nRunning tests: %s' % point)
        result = self._makeResult()
        unittest.signals.registerResult(result)
        result.failfast = self.failfast
        result.buffer = self.buffer
        start_time = time.time()
        start_test_run = getattr(result, 'startTestRun', None)
        if start_test_run is not None:
            start_test_run()
        try:
            test(result)
        finally:
            stop_test_run = getattr(result, 'stopTestRun', None)
            if stop_test_run is not None:
                stop_test_run()
        stop_time = time.time()
        time_taken = stop_time - start_time
        result.print_successes()
        result.printErrors()
        run = result.testsRun
        self.stream.writeln('Ran %d test%s in %.3fs' %
                            (run, run != 1 and 's' or '', time_taken))
        self.stream.writeln()

        expected_fails = unexpected_successes = skipped = 0
        try:
            results = map(len, (result.expected_failures,
                                result.unexpected_successes,
                                result.skipped))
        except AttributeError:
            pass
        else:
            expected_fails, unexpected_successes, skipped = results

        infos = []

        # Put together an error summary from error_stats
        if not result.wasSuccessful():
            self.stream.write('Error Summary')
            for level in result.error_stats.keys():
                infos.append('%s=%i' %
                             (_LEVELS[level], result.error_stats[level]))
        else:
            self.stream.write('OK')
        if skipped:
            infos.append('skipped=%d' % skipped)
        if expected_fails:
            infos.append('expected failures=%d' % expected_fails)
        if unexpected_successes:
            infos.append('unexpected successes=%d' % unexpected_successes)
        if infos:
            self.stream.writeln(' (%s)' % (', '.join(infos),))
        else:
            self.stream.write('\n')
        self.stream.writeln(result.separator1)
        return result


class ContractClause(unittest.TestCase):
    """A single clause of the contract.

    Each clause represents a functionally independent condition
    that the container is supposed to fulfill.
    """

    def __init__(self,
                 title,
                 description,
                 lifecyle_point,
                 error_level=WARNING):
        # Register the function 'run_test' to be executed as the
        # test driver.
        super(ContractClause, self).__init__('run_test')

        # Ensure a valid lifecycle_point.
        if lifecyle_point not in _TIMELINE.keys():
            raise KeyError('This clause does not have '
                           'a valid lifecycle point.')

        # Ensure a valid error_level
        if error_level not in _LEVELS.keys():
            raise KeyError('This clause does not have '
                           'a valid error level.')
        self.title = title
        self.description = description
        self.lifecyle_point = lifecyle_point
        self.error_level = error_level
        self.__sandbox = None

    def shortDescription(self):
        """Return a short description of the clause."""
        return '%s: %s' % (self.title, self.description)

    def inject_sandbox(self, sandbox):
        """Set the clause's sandbox before calling run_test.

        Args:
            sandbox: (appstart.ContainerSandbox) A sandbox that manages
                the container that should be tested.
        """
        self.__sandbox = sandbox

    def run_test(self):
        """Entrypoint for clause evaluation.

        This is necessary because unittest calls the test method with
        no arguments, so run_test must wrap evaluate_clause.

        Raises:
            ValueError: If the sandbox has not yet been injected.
        """
        if self.__sandbox is None:
            raise ValueError('Must inject sandbox before running test.')
        self.evaluate_clause(self.__sandbox)

    def evaluate_clause(self, sandbox):
        """A test that checks if the container is fulfilling the clause.

        This function must be overridden.

        Args:
            sandbox: (container.ContainerSandbox) A sandbox that manages
                the container to be tested.
        """
        raise NotImplementedError('ContractClauses must have an '
                                  'evaluate_clause function.')


class ContractValidator(object):
    """Coordinates the evaluation of multiple contract clauses."""

    def __init__(self, sandbox_kwargs, contract=None):
        self.contract = {}
        self.sandbox = appstart.ContainerSandbox(**sandbox_kwargs)
        self.logger = logging.getLogger('validator')
        self.logger.setLevel(logging.INFO)
        sh = logging.StreamHandler()
        sh.setLevel(logging.INFO)
        self.logger.addHandler(sh)
        self.logger.propagate = False

        for point in _TIMELINE.keys():
            self.contract[point] = []

        if contract:
            for clause in contract:
                self.add_clause(clause)

    def add_clause(self, clause):
        """Add a clause to the validator.

        Args:
            clause: (ContractClause) a clause that the
                container is expected to fulfill.
        """

        # Inject the sandbox into the clause so that we can evaluate it.
        clause.inject_sandbox(self.sandbox)

        # Add the clause to the appropriate list.
        self.contract.get(clause.lifecyle_point).append(clause)

    def validate(self, threshold=WARNING):
        """Evaluate all clauses.

        Args:
            threshold: (int) One of the error levels as specified above
                in the _LEVELS global var. Validation will result in
                failure if and only if a test with an error_level greater
                than threshold fails.

        Returns:
            (bool) True if validation was successful. False otherwise.
        """
        test_runner = ContractTestRunner(threshold=threshold)
        validation_passed = True
        try:
            self.sandbox.start()
            for point in _TIMELINE.keys():
                suite = unittest.TestSuite(self.contract.get(point))
                res = test_runner.run(suite, _TIMELINE[point])
                validation_passed = validation_passed and res.success
        finally:
            self.sandbox.stop()

        return validation_passed


class Contract(object):
    """A grouping of clauses that collectively form a contract."""

    def __init__(self):
        self.timeline_clauses = {}
        self.other_clauses = []


