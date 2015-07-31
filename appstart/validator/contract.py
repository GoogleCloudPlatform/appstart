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

"""This file contains the classes that form a framework for validation.

The validation framework is based on the python unittest framework.
"""

# This file conforms to the external style guide.
# see: https://www.python.org/dev/peps/pep-0008/.
# pylint: disable=bad-indentation, g-bad-import-order

import inspect
import logging
import time
import unittest

from ..sandbox import container_sandbox

import color_logging

################################################################################
# Error level descriptions                                                     #
################################################################################
# FATAL: If the container fails a clause marked as FATAL, the container will
#     absolutely not work. FATAL errors include not listening
#     on 8080, not responding properly to health checks, etc.
# WARNING: If the container fails a clause marked as WARNING,
#     it will possibly exhibit unexpected behavior. WARNING errors include
#     not writing access logs in the correct format, turning off health
#     checking while implementing an _ah/health endpoint, etc.
# UNUSED: If the container does not pass a clause marked as UNUSED, no real
#     error has occurred. It just means that the container isn't taking full
#     advantage of the runtime contract. UNUSED level errors include not writing
#     access or diagnostic logs. Other errors (namely WARNING errors) might be
#     dependent on info-level clauses. For instance, logging format is
#     contingent on the existence of logs in the proper location.
################################################################################

FATAL = 30
WARNING = 20
UNUSED = 10
LEVEL_NAMES = {FATAL: 'FATAL',
               WARNING: 'WARNING',
               UNUSED: 'UNUSED'}

# Lifecycle timeline
POST_STOP = 50
STOP = 40
POST_START = 30
START = 20
PRE_START = 10

# Tests will be executed in the order of lifecyle points.
_TIMELINE = [PRE_START, START, POST_START, STOP, POST_STOP]

# Singular points are lifecycle points that allow only one test.
_SINGULAR_POINTS = [START, STOP]

_TIMELINE_NAMES = {POST_STOP: 'Post Stop',
                   STOP: 'Stop',
                   POST_START: 'Post Start',
                   START: 'Start',
                   PRE_START: 'Pre Start'}


class ContractTestResult(unittest.TextTestResult):
    """Collect and report test results.

    This class is used to collect test results from ContractClauses.
    """

    # Possible test outcomes
    ERROR = 3
    FAIL = 2
    SKIP = 1
    PASS = 0

    def __init__(self,
                 success_set,
                 threshold,
                 *test_result_args,
                 **test_result_kwargs):
        """Initializer for ContractTestResult.

        Args:
            success_set: (set) A set of test classes that have succeeded thus
                far. Upon success, the class should be added to this set.
            threshold: (int) One of the error levels in LEVEL_NAMES.keys().
                Validation will result in failure if and only if a
                test with an error_level greater than threshold fails.
            *test_result_args: (list) Arguments to be passed to the
                constructor for TextTestResult.
            **test_result_kwargs: (dict) Keyword arguments to be passed to the
                constructor for TextTestResult.
        """
        super(ContractTestResult, self).__init__(*test_result_args,
                                                 **test_result_kwargs)

        # Assume that the tests will be successful
        self.success = True
        self.__threshold = threshold
        self.__success_set = success_set

        # A list of successful tests.
        self.success_list = []

        # { error_level -> error_count } A breakdown of error
        # frequency by level.
        self.error_stats = {}

    def addSuccess(self, test):
        """Wrapper around TestResult's addSuccess.

        In addition to what the parent function does,
        add the current test to the list of successful tests.

        Args:
            test: (ContractClause) A contract clause that has
                succeeded.
        """
        unittest.TestResult.addSuccess(self, test)
        self.__success_set.add(test.__class__)
        self.success_list.append(test)
        message = self.__make_message(test, self.PASS)
        self.stream.writeln(message)

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

    def addSkip(self, test, reason):
        unittest.TestResult.addSkip(self, test, reason)
        message = self.__make_message(test, self.SKIP)
        self.stream.writeln(message, lvl=logging.DEBUG)

    def addError(self, test, err):
        """Wrapper around grandparent's addError.

        In addition, update the error stats and success flag.

        Args:
            test: (ContractClause) A contract clause that has
                failed.
            err: (type, value, traceback) A tuple as returned by sys.exc_info
        """
        unittest.TestResult.addError(self, test, err)
        self.__update_error_stats(test)
        message = self.__make_message(test, self.ERROR)
        self.stream.writeln(message)

    def addFailure(self, test, err):
        """Modified version of grandparent's addFailure.

        In addition, update the error stats, and success flag.

        Args:
            test: (ContractClause) A contract clause that has
                failed.
            err: (type, value, traceback) A tuple as returned by sys.exc_info
        """
        unittest.TestResult.addFailure(self, test, err)
        self.__update_error_stats(test)

        # Collect the failure message for nicer format.
        test.failure_message = str(err[1])
        message = self.__make_message(test, self.FAIL)
        self.stream.writeln(message)

    def getDescription(self, test):
        """Get the description of a test."""
        return test.shortDescription()

    def __make_message(self, test, outcome, short=True):
        """Does the work of creating a description for the test and its result.

        Args:
            test: (ContractClause) The test for which to make a description.
            outcome: (int) One of the four possible test outcomes, enumerated
                as class variables. The type of outcome will determine
                formatting.
            short: (bool) Whether to print the shorter version of the
                description.

        Returns:
            (basestring) The description of the test result.
        """
        if outcome == self.PASS:
            color = 'green'
            outcome_type = 'PASSED'
        elif outcome == self.SKIP:
            color = None
            outcome_type = 'SKIP'
        elif outcome == self.FAIL:
            outcome_type = 'FAILED'
            if test.error_level == UNUSED:
                color = None
                outcome_type = 'UNUSED'
            elif test.error_level >= self.__threshold:
                color = 'red'
            else:
                color = 'warn'
        elif outcome == self.ERROR:
            color = 'red'
            outcome_type = 'ERROR'

        if short:
            prefix = '[{0: >6}]'.format(outcome_type)
        else:
            prefix = '[{0} ({1})]'.format(outcome_type,
                                          LEVEL_NAMES.get(test.error_level))

        if color:
            prefix = '%({0})s{1}%(end)s'.format(color, prefix)
        return '{0} {1}'.format(prefix, test.shortDescription())

    def print_errors(self):
        """Write failures and errors to the stream after tests."""
        if not (self.failures or self.errors):
            return

        self.stream.writeln(
            ' %(bold)s Failure Details %(end)s '.center(100, '-'),
            lvl=logging.DEBUG if self.success else logging.INFO)

        for test, _ in self.failures:
            # Log at the debug level by default. Debug logs will not be
            # printed to console but WILL be collected in the log.
            lvl = logging.DEBUG

            # Only log at the info level (to console) when for tests that
            # cause validation to fail.
            if test.error_level >= self.__threshold:
                lvl = logging.INFO
            message = self.__make_message(test, self.FAIL, short=False)
            self.stream.writeln(message, lvl=lvl)
            self.stream.writeln(test.failure_message, lvl=lvl)
            self.stream.writeln(lvl=lvl)

        for test, err in self.errors:
            message = self.__make_message(test, self.ERROR, short=False)
            self.stream.writeln(message)
            self.stream.writeln(err)

    def print_skips(self):
        self.stream.writeln(' %(bold)s Skip Details %(end)s '.center(100, '-'),
                            lvl=logging.DEBUG)
        for test, reason in self.skipped:
            message = self.__make_message(test, self.SKIP, short=False)
            self.stream.writeln(message, lvl=logging.DEBUG)
            self.stream.writeln('Reason: {0}'.format(reason),
                                lvl=logging.DEBUG)

            self.stream.writeln(lvl=logging.DEBUG)


class ContractTestRunner(unittest.TextTestRunner):
    """Test runner for a single suite of runtime contract clauses.

    There is one suite per point in _TIMELINE, so each instance of
    ContractTestRunner corresponds to a single _TIMELINE point.
    """

    def __init__(self, success_set, threshold, logfile, verbose_printing):
        """Create a ContractTestRunner.

        Args:
            success_set: (set) An empty set. Test classes that have succeeded
                should be added to this set.
            threshold: (int) One of the error levels as specified above
                in the LEVEL_NAMES global var. Validation will result in
                failure if and only if a test with an error_level greater
                than threshold fails.
            logfile: (basestring) The logfile to append messages to.
            verbose_printing: (bool) Whether or not to create a verbose
                LoggingStream (one that prints to console verbosely).
        """
        super(ContractTestRunner, self).__init__()
        self.__threshold = threshold
        self.stream = color_logging.LoggingStream(logfile, verbose_printing)
        self.__success_set = success_set

    def _makeResult(self):
        """Make a ContractTestResult to capture the test results.

        Returns:
            (ContractTestResult) the test result object.
        """
        return ContractTestResult(self.__success_set,
                                  self.__threshold,
                                  self.stream,
                                  self.descriptions,
                                  self.verbosity)

    def run(self, tests, point):
        """Run the test suite.

        This should be called once per point in _TIMELINE. This function
        is almost the same as unittest.TestSuite.run, differing minorly
        in formatting.

        Args:
            tests: (unittest.TestSuite) a suite of ContractClauses,
                corresponding to a point in _TIMELINE.
            point: (basestring) the name of the point in _TIMELINE.

        Returns:
            (ContractTestResult) The result of the tests.
        """
        self.stream.writeln()
        self.stream.writeln('%(bold)sRunning tests: {0} %(end)s'.format(point))
        result = self._makeResult()
        unittest.signals.registerResult(result)
        result.failfast = self.failfast
        result.buffer = self.buffer
        start_time = time.time()
        start_test_run = getattr(result, 'startTestRun', None)
        if start_test_run is not None:
            start_test_run()
        try:
            tests(result)
        finally:
            stop_test_run = getattr(result, 'stopTestRun', None)
            if stop_test_run is not None:
                stop_test_run()
        stop_time = time.time()
        time_taken = stop_time - start_time

        self.stream.writeln()

        result.print_errors()
        result.print_skips()

        # Find out how many tests ran
        run = result.testsRun

        # Put together an error summary from error_stats, success_list
        # skipped.
        infos = []
        if result.success_list:
            infos.append('PASSED=%d' % len(result.success_list))
        for level in result.error_stats.keys():
            infos.append('%s=%i' %
                         (LEVEL_NAMES[level], result.error_stats[level]))
        if result.skipped:
            infos.append('SKIPPED=%d' % len(result.skipped))

        time_str = ('Ran %d test%s in %.3fs' %
                    (run, '' if run == 1 else 's', time_taken))
        self.stream.writeln('%s (%s)' % (time_str, ', '.join(infos),))
        self.stream.writeln('=' * 100)
        return result


class ContractClause(unittest.TestCase):
    """A single clause of the contract.

    Each clause represents a functionally independent condition
    that the container is supposed to fulfill.
    """

    # lifecyle_point: (int) A point corresponding to a time period
    #     in _TIMELINE. This determines in which time period the clause
    #     will be evaluated.
    # error_level: (int) A number corresponding to an
    #     error level in LEVEL_NAMES. This indicates the severity of
    #     the error that would occur in production, should the container
    #     not fulfill the clause. Clauses that assert conditions
    #     that are essential to the operation of a container should
    #     have a higher level than clauses that assert trivial
    #     conditions.
    # tags: ([basestring, ...]) Tags are a list of string identifiers
    #     associated with the ContractClause. They allow a subset of
    #     ContractClauses from a module to be run; the runner of validator
    #     can pass a list of tags, and the ContractClause will only be
    #     evaluated if one of its tags appears in the list. By default,
    #     a clause will be tagged with its own class name.
    # dependencies: ([class, ...]) A list of classes that inherit
    #     from ContractClause. A clause will be evaluated if and only
    #     if the clauses in this list pass.

    lifecyle_point = None
    error_level = UNUSED
    dependencies = []
    description = None
    tags = None
    title = None

    def __init__(self, sandbox):
        """Initializer for ContractClause.

        Args:
            sandbox: (sandbox.container_sandbox.ContainerSandbox)
                A sandbox that manages the container to be tested.
        Raises:
            KeyError: If lifecyle_point is not a valid lifecyle point or
                if error_level is not a valid error level.
            AttributeError: If the clause does not have the attributes
                enumerated in _REQUIRED_ATTRIBUTES.
            ValueError: If the clause's 'tags' attribute is not a list.
        """
        for attr in ['lifecyle_point', 'title', 'description']:
            if not getattr(self, attr, None):
                raise AttributeError('{0} must have attribute: '
                                     '{1}'.format(self.__class__.__name__,
                                                  attr))

        # Ensure a valid lifecycle_point.
        if self.lifecyle_point not in _TIMELINE:
            raise KeyError('{0} does not have a valid lifecycle '
                           'point.'.format(self.__class__.__name__))

        # Ensure a valid error_level
        if self.error_level not in LEVEL_NAMES.keys():
            raise KeyError('{0} does not have a valid error '
                           'level.'.format(self.__class__.__name__))

        self.tags = self.tags or []
        if not isinstance(self.tags, list):
            raise ValueError('"tags" attribute must be a list')

        self.tags.append(self.__class__.__name__)

        # Register the function 'run_test' to be executed as the
        # test driver.
        super(ContractClause, self).__init__('run_test')

        self.__sandbox = sandbox

    def shortDescription(self):
        """Return a short description of the clause."""
        return '%s: %s' % (self.title, self.description)

    def run_test(self):
        self.evaluate_clause(self.__sandbox.app_container)

    def evaluate_clause(self, app_container):
        """A test that checks if the container is fulfilling the clause.

        Args:
            app_container: (sandbox.container.Container) The container
                to be tested
        """
        raise NotImplementedError('evaluate_clause must be implemented '
                                  'by classes that extend ContractClause')


class ContractValidator(object):
    """Coordinates the evaluation of multiple contract clauses."""

    def __init__(self, sandbox_kwargs, contract_module):
        """Initializer for ContractValidator.

        Args:
            sandbox_kwargs: (dict) Keyword args for the ContainerSandbox.
            contract_module: (module) A module that contains classes that
                inherit from ContractClause. These classes will
                be used to make the contract.
        """
        self.contract = {}
        self.sandbox = container_sandbox.ContainerSandbox(
            **sandbox_kwargs)

        # Set of clauses that have been added to the contract.
        self.__added_clauses = set()

        # Set of clauses that have succeeded.
        self.__success_set = set()

        self.__construct_contract(contract_module)
        self._tags = []

    def __construct_contract(self, module):
        """Recursively add clauses to the contract."""

        # Iterate over all of the module's attributes.
        for attr in [module.__dict__.get(name) for name in dir(module)]:
            # Add the attribute to the contract if it's a ContractClause
            if inspect.isclass(attr) and issubclass(attr, ContractClause):
                self.__add_clause(attr, set(), [])

    def display_loop(self, stack, cls):
        """Display the loop in the dependency graph.

        Args:
            stack: ([class, ...]) A list of ContractClause classes,
                corresponding to the path taken in the DFS of the test
                dependencies.
            cls: (class) The ContractClause class that demarks the beginning
                of the cycle.

        Returns:
            (basestring) The message indicating where the loop was.
        """
        # Get the index of the first occurence of cls
        first = stack.index(cls)

        # Start iterating over the stack, beginning with the first occurence of
        # cls.
        msg = ''
        for item in stack[first:]:
            msg = '{0}{1}->'.format(msg, item.__name__)
        msg += cls.__name__
        return msg

    def __add_clause(self, clause_class, visited_classes, recursion_stack):
        """Add a clause to the validator.

        Ensure that no dependency cycles occur.

        Args:
            clause_class: (ContractClause) A clause that the
                container is expected to fulfill.
            visited_classes: (set) A set of classes that have been
                visited so far in the recursive traversal.
            recursion_stack: ([ContractClause, ...] A list of ContractClauses,
                representing the exact path that has been traversed
                recursively so far. This is only used to print the loop, if
                a loop is even found.

        Raises:
            RuntimeError: If a circular dependency is detected.
            ValueError: If a clause has an earlier lifecyle_point than
                another clause that it depends on OR if more than one
                clause with a lifecyle_point in _SINGULAR_POINTS is
                added.
        """
        # Base case: the clause has been added already.
        if clause_class in self.__added_clauses:
            return

        # If we've visited this class, there's a loop in the dependency
        # structure.
        if clause_class in visited_classes:

            # In the case of a loop, print where it occurs so that the person
            # writing the contract knows to get rid of it.
            message = self.display_loop(recursion_stack, clause_class)
            raise RuntimeError('Circular dependency '
                               'was detected: {0}'.format(message))

        # Mark that we've visited the clause already. If we come back to
        # the same clause later, we'll know that a cycle has occured.
        visited_classes.add(clause_class)
        recursion_stack.append(clause_class)

        for dep in clause_class.dependencies:
            # A clause must have either the same lifecycle point or a later one
            # than all of the clauses it depends on.
            if dep.lifecyle_point > clause_class.lifecyle_point:
                raise ValueError('{0}->{1}: Clause cannot have earlier '
                                 'lifecyle_point than a clause it depends '
                                 'on.'.format(clause_class.__name__,
                                              dep.__name__))

            # Recur on all clauses that this clause depends on. We want to add
            # these clauses to the contract before we add the current one.
            # That's because the clauses upon which the current clause depends
            # should be evaluated first.
            self.__add_clause(dep, visited_classes, recursion_stack)

        # At this point, we've finished recurring and need to prepare to return
        # and take a step backward in our DFS traversal. Therefore, remove the
        # current clause from the set of visited clauses and pop the stack.
        visited_classes.remove(clause_class)
        recursion_stack.pop()

        # Construct an actual instance of this clause with the sandbox.
        clause = clause_class(self.sandbox)

        # Add the clause to the appropriate list. Note that the list may not yet
        # exist.
        self.contract.setdefault(clause.lifecyle_point, [])
        clause_list = self.contract.get(clause.lifecyle_point)

        # Singular points are those for which only ONE clause can be present.
        if clause.lifecyle_point in _SINGULAR_POINTS and len(clause_list):
            raise ValueError(
                'Cannot add more than one "{0}" '
                'clause'.format(_TIMELINE_NAMES[clause.lifecyle_point]))

        clause.evaluate_clause = self.patch_clause(clause,
                                                   clause.evaluate_clause)
        clause_list.append(clause)
        self.__added_clauses.add(clause_class)

    def patch_clause(self, clause, func):
        def _wrapper(*args, **kwargs):
            for dependency_class in clause.dependencies:
                if dependency_class not in self.__success_set:
                    raise unittest.SkipTest(
                        '"{0}" did not pass'.format(dependency_class.title))
            if self._tags:
                for tag in clause.tags:
                    if tag in self._tags:
                        return func(*args, **kwargs)
                raise unittest.SkipTest('Clause is tagged with: {0}. '
                                        'Currently running: '
                                        '{1}'.format(clause.tags, self._tags))
            else:
                return func(*args, **kwargs)

        return _wrapper

    def validate(self, tags, threshold='WARNING', logfile=None, verbose=False):
        """Evaluate all clauses.

        Args:
            tags: ([basestring, ...]) A list of tags to identify the
                desired tests to run. A clause will only be evaluated if
                it contains a tag that appears in this list.
            threshold: (int) One of the error levels as specified above
                in the LEVEL_NAMES global var. Validation will result in
                failure if and only if a test with an error_level greater
                than threshold fails.
            logfile: (basestring or None) The name of the log file to append
                to.
            verbose: (bool) Whether or not to run tests verbosely. If False,
                some non-essential information is ommitted from the output
                printed to stdout. Note that ALL information is logged to
                the logfile, if one is specified.

        Returns:
            (bool) True if validation was successful. False otherwise.
        """
        self._tags.extend(tags or [])
        for level, name in LEVEL_NAMES.iteritems():
            if name == threshold:
                threshold = level
                break

        test_runner = ContractTestRunner(self.__success_set,
                                         threshold=threshold,
                                         logfile=logfile,
                                         verbose_printing=verbose)
        validation_passed = True
        try:
            self.sandbox.start()
            for point in _TIMELINE:
                if point not in self.contract: continue
                suite = unittest.TestSuite(self.contract.get(point))
                res = test_runner.run(suite, _TIMELINE_NAMES[point])
                validation_passed = validation_passed and res.success
        finally:
            self.sandbox.stop()

        return validation_passed
