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

"""This file contains the classes that form the notion of a contract.

The information flow is as follows:

1) A contract is specified as a series of ContractClauses*. A clause is
a functionally independent condition that a container is supposed to satisfy.
These clauses can specify ordering and dependencies on other ContractClauses.

2) The contract is presented to the ContractValidator. The ContractValidator
will generate "hook clauses"** and throw them into the mix. Then, the
ContractValidator will arrange clauses in the correct chronological order and
check that there are no dependency loops.

3) The ContractValidator runs the clauses using the ContractTestRunner. The
test runner is based on python's unittest.TextTestRunner.

4) The ContractTestRunner collects the results of each clause in a
ContractTestResult. The ContractTestResult simultaneously collects results and
reports. At the end of validation, the ContractTestRunner makes a cumulative,
more detailed report, using the ContractTestResult.

* ContractClauses must define an 'evaluate_clause' method, which verifies the
actual thing that the clause is supposed to check. For instance, a clause that
checks if the container responds favorably on _ah/health must send an HTTP
request to the container's _ah/health endpoint in the evaluate_clause method.

** Hook clauses are custom scripts defined by the user. Hook clauses are added
at runtime. See README.md for more info.
"""

# TODO: see if we can simplify the way that dependencies and lifecycle points
# work.

# This file conforms to the external style guide.
# see: https://www.python.org/dev/peps/pep-0008/.
# pylint: disable=bad-indentation, g-bad-import-order

import copy
import inspect
import logging
import os
import subprocess
import tempfile
import time
import unittest
import yaml

from ..sandbox import container_sandbox
from .. import utils

import errors
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
LEVEL_NUMBERS_TO_NAMES = {FATAL: 'FATAL',
                          WARNING: 'WARNING',
                          UNUSED: 'UNUSED'}

LEVEL_NAMES_TO_NUMBERS = {name: val for val, name
                          in LEVEL_NUMBERS_TO_NAMES.iteritems()}

# Lifecycle timeline
POST_STOP = 50
STOP = 40
POST_START = 30
START = 20
PRE_START = 10

# Tests will be executed in the order of lifecycle points.
_TIMELINE = [PRE_START, START, POST_START, STOP, POST_STOP]

# Singular points are lifecycle points that allow only one test.
_SINGULAR_POINTS = [START, STOP]

_TIMELINE_NUMBERS_TO_NAMES = {POST_STOP: 'Post Stop',
                              STOP: 'Stop',
                              POST_START: 'Post Start',
                              START: 'Start',
                              PRE_START: 'Pre Start'}

_TIMELINE_NAMES_TO_NUMBERS = {name.upper().replace(' ', '_'): val for val, name
                              in _TIMELINE_NUMBERS_TO_NAMES.iteritems()}


# Hook config extension. This determines what the extension of config files for
# hooks should be.
_HOOK_CONF_EXTENSION = '.conf.yaml'

# Name of the directory where validator is supposed to find hook tests
HOOK_DIRECTORY = 'validator_tests'

# Attributes for a ContractClause
_REQUIRED_ATTRS = ['lifecycle_point', 'title', 'description']

_DEFAULT_ATTRS = {'dependencies': set(),
                  'dependents': set(),
                  'before': set(),
                  'after': set(),
                  'tags': set(),
                  'error_level': UNUSED,
                  '_unresolved_before': set(),
                  '_unresolved_after': set(),
                  '_unresolved_dependents': set(),
                  '_unresolved_dependencies': set(),
                  '_conf_file': None}

# Keys for a yaml test configuration
_REQUIRED_YAML_ATTRS = ['name'] + _REQUIRED_ATTRS
_DEFAULT_YAML_ATTRS = {'dependencies': [],
                       'dependents': [],
                       'before': [],
                       'after': [],
                       'tags': [],
                       'error_level': 'UNUSED'}


class ContractTestResult(unittest.TextTestResult):
    """Collect and report test results.

    This class is used to collect test results from ContractClauses.
    """

    # Possible test outcomes
    ERROR = 3
    FAIL = 2
    SKIP = 1
    PASS = 0

    def __init__(self, success_set, threshold, *result_args, **result_kwargs):
        """Initializer for ContractTestResult.

        Args:
            success_set: (set) A set of test classes that have succeeded thus
                far. Upon success, the class should be added to this set.
            threshold: (int) One of the error levels in
                LEVEL_NUMBERS_TO_NAMES.keys(). Validation will result in
                failure if and only if a test with an error_level greater than
                threshold fails.
            *result_args: (list) Arguments to be passed to the
                constructor for TextTestResult.
            **result_kwargs: (dict) Keyword arguments to be passed to the
                constructor for TextTestResult.
        """
        super(ContractTestResult, self).__init__(*result_args, **result_kwargs)

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
            prefix = '[{0} ({1})]'.format(
                outcome_type,
                LEVEL_NUMBERS_TO_NAMES.get(test.error_level))

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

            # Sanitize the input to the logger by replacing % with %%.
            # This is necessary because the custom formatter operates on
            # % placeholders. Since this place deals with external input,
            # make sure that there are no stray %'s.
            self.stream.writeln(test.failure_message.replace('%', '%%'),
                                lvl=lvl)
            self.stream.writeln(lvl=lvl)

        for test, err in self.errors:
            message = self.__make_message(test, self.ERROR, short=False)
            self.stream.writeln(message)

            # Same sanitization as above.
            self.stream.writeln(err.replace('%', '%%'))

    def print_skips(self):
        if self.skipped:
            self.stream.writeln(
                ' %(bold)s Skip Details %(end)s '.center(100, '-'),
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
                in the LEVEL_NUMBERS_TO_NAMES global var. Validation will
                result in failure if and only if a test with an error_level
                greater than threshold fails.
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
                         (LEVEL_NUMBERS_TO_NAMES[level],
                          result.error_stats[level]))
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

    Clauses should define the following class variables:

    Optional:
        error_level: (int) A number corresponding to an
            error level in LEVEL_NUMBERS_TO_NAMES. Defaults to UNUSED. This
            indicates the severity of the error that would occur in production,
            should the container not fulfill the clause. Clauses that assert
            conditions that are essential to the operation of a container
            should have a higher level than clauses that assert trivial
            conditions.
        tags: {[basestring, ...]} Tags are a set of string identifiers
            associated with the ContractClause. They allow a subset of
            ContractClauses from a module to be run; the runner of validator
            can pass a list of tags, and the ContractClause will only be
            evaluated if one of its tags appears in the list. By default, a
            clause will be tagged with its own class name in addition to any
            tags specified.
        dependencies: {[class, ...]} A set of clause classes that inherit
            from ContractClause. A clause will be evaluated if and only
            if the clauses in this set pass.
        before: {[class, ...]} A set of clauses (ContractClause classes)
            to evaluate BEFORE the current clause.
        dependents: {[class, ...]} A set of classes that inherit from
            ContractClause. This clause will be added to the dependency sets 
            of all dependents. In other words, the dependents are to depend on
            this clause.
        after: {[class, ...]} A set of clauses (ContractClause classes)
            to evaluate AFTER the current clause.

        The point of 'after' and 'dependents' is to allow hook clauses to
        place themselves before a default clause of the runtime contract. 
        However, the code for the default clauses is not to be modified.
        Implementing 'dependents' and 'afters' is a good workaround.

    Required:
        lifecycle_point: (int) A point corresponding to a time period
            in _TIMELINE. This determines in which time period the clause
            will be evaluated.
        title: (basestring) The title of the clause, displayed in validation
            results.
        description: (basestring) The description, elaborating what the clause
            is validating. This description is also presented in the validation
            results.
    """

    class __metaclass__(type):  # pylint: disable=invalid-name
        """Checks attributes of any class derived from ContractClause.

        The metaclass is invoked when the class is defined, so this is a
        great way to check very early that the clause is valid.
        """

        def __init__(cls, name, bases, dct):
            """Ensure cls has the required attributes, and set the default ones.

            Args:
                name: (basestring) The name of the class being initialized.
                bases: ([class, ...]) A list of classes that cls inherits from.
                dct: (dict) A dictionary mapping names->attributes/methods of
                    cls.

            Raises:
                KeyError: If lifecycle_point is not a valid lifecycle point or
                    if error_level is not a valid error level.
                AttributeError: If the clause does not have the attributes
                    enumerated in _REQUIRED_ATTRIBUTES.
            """
            type.__init__(cls, name, bases, dct)

            # String by which to identify the clause, for the purpose of
            # error reporting.
            identifier = getattr(cls, '_conf_file', name)

            def set_default_attr(obj, attr, value):
                if not hasattr(obj, attr):
                    # Copy so that we don't use the same sets for all of
                    # the clauses.
                    setattr(obj, attr, copy.copy(value))

            def ensure_proper_type(obj, attr, attr_type):
                if type(getattr(obj, attr)) != attr_type:
                    raise errors.ContractAttributeError(
                        '{0}: {1} should be of type '
                        '"{2}"'.format(identifier, attr, attr_type))

            def assert_attrs_exist(cls, attrs):
                for attr in attrs:
                    if not hasattr(cls, attr):
                        raise errors.ContractAttributeError(
                            '{0} must have attribute: {1}'.format(identifier,
                                                                  attr))

            # These defaults should only be set if the class being
            # initialized is not a ContractClause. Same goes for asserting
            # that the required attributes exist.
            if name != 'ContractClause':
                for attr, val in _DEFAULT_ATTRS.iteritems():
                    set_default_attr(cls, attr, val)
                    if val is not None:
                        ensure_proper_type(cls, attr, type(val))

                assert_attrs_exist(cls, _REQUIRED_ATTRS)

                # Ensure a valid lifecycle point.
                if cls.lifecycle_point not in _TIMELINE:
                    raise errors.ContractAttributeError(
                        '{0} does not have a valid lifecycle '
                        'point'.format(identifier))

                # Ensure a valid error_level.
                if cls.error_level not in LEVEL_NUMBERS_TO_NAMES.keys():
                    raise errors.ContractAttributeError(
                        '{0} does not have a valid error '
                        'level'.format(identifier))

                # Tag the clause with its own name.
                cls.tags.add(name)

    def __init__(self, sandbox):
        """Initializer for ContractClause.

        Args:
            sandbox: (sandbox.container_sandbox.ContainerSandbox)
                A sandbox that manages the container to be tested.
        """

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

    def __init__(self, contract_module, **sandbox_kwargs):
        """Initializer for ContractValidator.

        Args:
            contract_module: (module) A module that contains classes that
                inherit from ContractClause. These classes will
                be used to make the contract.
            **sandbox_kwargs: (dict) Keyword args for the ContainerSandbox.
        """
        self.contract = {}
        self.sandbox = container_sandbox.ContainerSandbox(
            **sandbox_kwargs)

        # Set of clauses that have been added to the contract.
        self.__added_clauses = set()

        # Set of clauses that have succeeded.
        self.__success_set = set()

        # Dict of clauses to add to the contract.
        self._clause_dict = {c.__name__: c
                             for c in self._extract_clauses(contract_module)}

        # Make the "hook" clauses and add them to the clause list. See
        # README.md to find out more about hook clauses.
        for hook in self._make_hook_clauses():
            if hook.__name__ in self._clause_dict:
                raise utils.AppstartAbort('Cannot use same clause name twice: '
                                          '{0}'.format(hook.__name__))
            self._clause_dict[hook.__name__] = hook

        # Normalize the dependency structure of the clauses
        self._normalize_clause_dict(self._clause_dict)

        # Construct the contract. This involves a depth-first traversal of
        # the clauses in self._clause_list.
        self._construct_contract()

        # Tags identifying the clauses to be validated.
        self._tags = set()

    @staticmethod
    def _extract_clauses(module):
        clause_list = []

        # Iterate over all of the module's attributes.
        for attr in [module.__dict__.get(name) for name in dir(module)]:
            # Add the attribute to the contract if it's a ContractClause
            if inspect.isclass(attr) and issubclass(attr, ContractClause):
                clause_list.append(attr)

        return clause_list

    @staticmethod
    def _normalize_clause_dict(clause_dict):
        """Resolve dependencies and set up chronology of clauses.

        Args:
            clause_dict: ({basestring: class}) A dictionary mapping clause
                names to their respective classes.

        Resolving dependencies:
        At the time this function is called, clauses may have lists of
        _unresolved_dependencies, _unresolved_dependents, etc. These are just
        lists of strings that are supposed to correspond to other clauses. This
        method resolves the clause names to *actual* clauses. The reason that
        this resolution is necessary is that hook clauses might depend on other
        clauses. These dependencies cannot be resolved when each hook clause is
        added, since a hook clause might depend on another hook clause that has
        not yet been discovered. Therefore, initially, dependencies get
        recorded as string names and are later resolved to classes (via this
        method).

        Arranging chronology:
        This method arranges dependents to set up a depth first traversal
        of the dependency graph. That is, each clause may have a list of
        dependents - other clauses that must depend on the first clause.
        For instance, suppose clause X has clauses A, B and C as dependents.
        The easiest way to deal with this is to add clause X to A, B and C's
        dependencies before beginning the traversal.
        """
        for unused_name, clause in clause_dict.iteritems():
            def _resolve_name(name):
                try:
                    # clause_dict maps names to clauses.
                    return clause_dict[name]
                except KeyError:
                    #  pylint: disable=cell-var-from-loop
                    raise utils.AppstartAbort(
                        'In {0}: could not resolve clause '
                        '{1}'.format(clause._conf_file, name))
                    #  pylint: enable=cell-var-from-loop

            # pylint: disable=unused-argument
            def resolve(resolved, unresolved):
                # For each item in unresolved, resolve it. Then union the
                # set of resolved items with the results.
                resolved |= set(map(_resolve_name, unresolved))

            # pylint: enable=unused-argument

            # Perform the actual resolution.  The reason we have to specify
            # "afters" is because users can add custom clauses to the
            # runtime contract. The developer should really have a way to
            # specify that a default clause in the runtime contract should
            # depend on their custom clause without having to change this code.
            resolve(clause.after, clause._unresolved_after)
            resolve(clause.before, clause._unresolved_before)
            resolve(clause.dependents, clause._unresolved_dependents)
            resolve(clause.dependencies, clause._unresolved_dependencies)

            # If X has dependent A, add X to A's dependencies.
            for dependent_clause in clause.dependents:
                if clause not in dependent_clause.dependencies:
                    dependent_clause.dependencies.add(clause)

            for after_clause in clause.after:
                if clause not in after_clause.before:
                    after_clause.before.add(clause)

    def _construct_contract(self):
        """Recursively add clauses to the contract."""
        for unused_name, clause in self._clause_dict.iteritems():
            self._add_clause(clause, set(), [])

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

    def _add_clause(self, clause_class, visited_classes, recursion_stack):
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
            errors.CircularDepencencyError: If a circular dependency is
                detected.
            ValueError: If a clause has an earlier lifecycle_point than
                another clause that it depends on OR if more than one
                clause with a lifecycle_point in _SINGULAR_POINTS is
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
            raise errors.CircularDependencyError(
                'Circular dependency was detected: {0}'.format(message))

        # Mark that we've visited the clause already. If we come back to
        # the same clause later, we'll know that a cycle has occured.
        visited_classes.add(clause_class)
        recursion_stack.append(clause_class)

        for dep in clause_class.dependencies | clause_class.before:
            # A clause must have either the same lifecycle point or a later one
            # than all of the clauses it depends on.
            if dep.lifecycle_point > clause_class.lifecycle_point:
                raise errors.CircularDependencyError(
                    '{0}->{1}: Clause cannot have earlier lifecycle_point '
                    'than a clause that must run before '
                    'it.'.format(clause_class.__name__, dep.__name__))

            # Recurse on all clauses that this clause depends on. We want to add
            # these clauses to the contract before we add the current one.
            # That's because the clauses upon which the current clause depends
            # should be evaluated first.
            self._add_clause(dep, visited_classes, recursion_stack)

        # At this point, we've finished recursion and need to prepare to return
        # and take a step backward in our DFS traversal. Therefore, remove the
        # current clause from the set of visited clauses and pop the stack.
        visited_classes.remove(clause_class)
        recursion_stack.pop()

        # Construct an actual instance of this clause with the sandbox.
        clause = clause_class(self.sandbox)

        # Add the clause to the appropriate list. Note that the list may not yet
        # exist.
        self.contract.setdefault(clause.lifecycle_point, [])
        clause_list = self.contract.get(clause.lifecycle_point)

        # Singular points are those for which only ONE clause can be present.
        if clause.lifecycle_point in _SINGULAR_POINTS and len(clause_list):
            raise ValueError(
                'Cannot add more than one "{0}" '
                'clause'.format(
                    _TIMELINE_NUMBERS_TO_NAMES[clause.lifecycle_point]))

        clause.evaluate_clause = self._dependency_and_tag_wrapper(
            clause, clause.evaluate_clause)
        clause_list.append(clause)
        self.__added_clauses.add(clause_class)

    def _make_hook_clauses(self):
        """Construct the hook clauses to add to the contract.

        Hook clauses are clauses created on the fly to incorporated custom
        tests defined by the user in the form of scripts. See README.md for
        more info on hook clauses.

        Returns:
            ([class, ...]) A list of ContractClause classes corresponding to
                each hook clause.
        """
        # Get the directory where the hook tests should be.
        hook_test_dir = os.path.join(self.sandbox.app_dir, HOOK_DIRECTORY)

        # If the path doesn't exist or it's not a directory, return early.
        if not os.path.isdir(hook_test_dir):
            return []

        hook_clauses = []

        # Walk the directory and for each configuration file, make a hook
        # clause.
        for root, _, files in os.walk(hook_test_dir):
            for yaml_file in [os.path.join(root, f) for f in files
                              if f.endswith(_HOOK_CONF_EXTENSION)]:
                hook_clauses.append(self._make_hook_clause_for_yaml(yaml_file))

        return hook_clauses

    def _make_hook_clause_for_yaml(self, yaml_file):
        """Make hook clauses for all the scripts inside a directory.

        Args:
            yaml_file: (basestring) Path to the config file from which to make
                a hook clause.

        Returns:
            ([class, ...]) A list of ContractClause classes corresponding to
                each hook clause. Note that one hook clause is made per
                executable script.
        """
        hook_config = yaml.load(open(yaml_file))

        def verify_has_key_and_set_defaults(key):
            """Verify that the key exists or set a default if possible."""
            if key in _DEFAULT_YAML_ATTRS:

                # Only set the default value if the key is not not in the
                # configuration
                hook_config.setdefault(key, copy.copy(_DEFAULT_YAML_ATTRS[key]))

            # If the key wasn't optional, complain.
            elif key not in hook_config:
                raise utils.AppstartAbort('{0} has no attribute '
                                          '{1}'.format(yaml_file, key))

        # Get the keys whose existence we need to verify
        keys = _DEFAULT_YAML_ATTRS.keys() + _REQUIRED_YAML_ATTRS

        if 'command' not in hook_config:
            # The default executable is presumed to be a file of the same
            # name, less the hook configuration extension.
            executable = yaml_file[:-len(_HOOK_CONF_EXTENSION)]

            # Bail out if we can't find the file.
            if not os.path.exists(executable):
                raise utils.AppstartAbort('Default executable for {0} not '
                                          'found'.format(yaml_file))

            if not os.path.isfile(executable):
                raise utils.AppstartAbort('Default executable for {0} must be '
                                          'a file: {0}'.format(yaml_file))

            # If we can find the file but it's not executable, bail out.
            if not os.access(executable, os.X_OK):
                raise utils.AppstartAbort('Default executable for {0} is not '
                                          'executable'.format(yaml_file))
            hook_config['command'] = executable

        # Verify the existence of keys and set defaults if possible.
        map(verify_has_key_and_set_defaults, keys)
        sandbox = self.sandbox

        # The new hook clause
        class NewClause(ContractClause):
            title = hook_config['title']
            description = hook_config['description']
            error_level = LEVEL_NAMES_TO_NUMBERS.get(
                hook_config['error_level'])
            tags = set(hook_config['tags'])
            lifecycle_point = _TIMELINE_NAMES_TO_NUMBERS.get(
                hook_config['lifecycle_point'])

            # Currently, dependencies, dependents, before, and after are
            # unresolved. That is, they refer to clause names, not classes.
            # We cannot resolve them yet, because we need to finish creating
            # all of the clauses. (Imagine the scenario where custom hook x
            # wants to run before custom hook y, but y has not yet been
            # created.
            _unresolved_dependencies = set(hook_config['dependencies'])
            _unresolved_dependents = set(hook_config['dependents'])
            _unresolved_before = set(hook_config['before'])
            _unresolved_after = set(hook_config['after'])
            _conf_file = yaml_file

            def evaluate_clause(self, app_container):
                env = dict(os.environ)

                # These environment variables will give the hook access
                # to the necessary parameters.
                env['APP_CONTAINER_ID'] = app_container.get_id()
                env['APP_CONTAINER_HOST'] = app_container.host
                env['APP_CONTAINER_PORT'] = str(sandbox.port)

                stdout = tempfile.TemporaryFile()

                # Run the command and assert a 0 exit code.
                return_code = subprocess.Popen(
                    args=hook_config['command'],
                    env=env,
                    stdout=stdout,
                    stderr=subprocess.STDOUT,
                    shell=True).wait()

                stdout.seek(0)

                self.assertEqual(return_code,
                                 0,
                                 'Return code was {0}. Printing '
                                 'stdout:\n{1}'.format(return_code,
                                                       stdout.read()))

        NewClause.__name__ = hook_config['name']

        return NewClause

    def _dependency_and_tag_wrapper(self, clause, func):
        """Wrap func to achieve contingency on tags and dependencies.

        This will cause func to run only if dependency conditions and
        tag conditions have been met. In cases where the clause's dependencies
        have failed, or the clause does not have the necessary tags to be run,
        the wrapper will raise a SkipTest.

        Args:
            clause: (ContractClause) The clause whose function to wrap.
            func: (callable) The actual function to patch.

        Returns:
            (callable) The wrapper around func.
        """
        def _wrapper(*args, **kwargs):

            # Check the dependencies at runtime. If any haven't passed, skip.
            for dependency_class in clause.dependencies:
                if dependency_class not in self.__success_set:
                    raise unittest.SkipTest(
                        '"{0}" did not pass'.format(dependency_class.title))

            # Only check against tags if self._tags is not an empty set.
            if self._tags:
                for tag in clause.tags:
                    # If a single tags matches, apply func.
                    if tag in self._tags:
                        return func(*args, **kwargs)

                raise unittest.SkipTest('Clause is tagged with: {0}. '
                                        'Currently running: '
                                        '{1}'.format(clause.tags, self._tags))
            else:
                return func(*args, **kwargs)

        return _wrapper

    def list_clauses(self):
        keys = self._clause_dict.keys()
        keys.sort()

        def make_name_list(class_list):
            names = [c.__name__ for c in class_list]
            return ', '.join(names)

        for clause in [self._clause_dict[name] for name in keys]:
            print clause.__name__ 
            print '\tTitle: {0}'.format(clause.title)
            print '\tDescription: {0}'.format(clause.description)
            print '\tTags: {0}'.format(', '.join([t for t in clause.tags]))
            
            error_level = LEVEL_NUMBERS_TO_NAMES[clause.error_level]
            print '\tError Level: {0}'.format(error_level)

            if clause.dependencies:
                print '\tDependencies: {0}'.format(make_name_list(
                                                       clause.dependencies))
            if clause.dependents:
                print '\tDependants: {0}'.format(make_name_list(
                                                     clause.dependents))
            if clause.before:
                print '\tBefore: {0}'.format(make_name_list(clause.before))

            if clause.after:
                print '\tAfter: {0}'.format(make_name_list(clause.after))

    def validate(self,
                 tags=None,
                 threshold='WARNING',
                 logfile=None,
                 verbose=False):
        """Evaluate all clauses.

        Args:
            tags: ([basestring, ...]) A list of tags to identify the
                desired tests to run. A clause will only be evaluated if
                it contains a tag that appears in this list.
            threshold: (int) One of the error levels as specified above
                in the LEVEL_NUMBERS_TO_NAMES global var. Validation will
                result in failure if and only if a test with an error_level
                greater than threshold fails.
            logfile: (basestring or None) The name of the log file to append
                to.
            verbose: (bool) Whether or not to run tests verbosely. If False,
                some non-essential information is ommitted from the output
                printed to stdout. Note that ALL information is logged to
                the logfile, if one is specified.

        Returns:
            (bool) True if validation was successful. False otherwise.
        """
        self._tags.update(tags or set())

        # The threshold comes in as a string. Convert it to a numerical value.
        threshold = LEVEL_NAMES_TO_NUMBERS[threshold]

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
                res = test_runner.run(suite, _TIMELINE_NUMBERS_TO_NAMES[point])
                validation_passed = validation_passed and res.success
        finally:
            self.sandbox.stop()

        return validation_passed
