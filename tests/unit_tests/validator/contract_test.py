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

"""Unit tests for validator.container."""

# This file conforms to the external style guide.
# pylint: disable=bad-indentation, g-bad-import-order

import logging
import os
import stat
import tempfile
import textwrap

from appstart import utils
from appstart.sandbox import container_sandbox
from appstart.validator import contract
from appstart.validator import errors

from fakes import fake_docker


class ClauseTestBase(fake_docker.FakeDockerTestBase):

    def setUp(self):
        """Prepare a temporary application directory."""
        super(ClauseTestBase, self).setUp()
        self.app_dir = tempfile.mkdtemp()
        self._add_file('app.yaml', 'vm: true')
        self.conf_file = os.path.join(self.app_dir, 'app.yaml')
        os.mkdir(os.path.join(self.app_dir, 'validator_tests'))

    def _add_file(self, name, string):
        f = open(os.path.join(self.app_dir, name), 'w')
        f.write(string)
        f.close()


class ClauseTest(ClauseTestBase):

    def test_bad_clause_definitions(self):
        """Ensure that it's impossible to define bad clause classes."""

        # pylint: disable=unused-variable, function-redefined

        # Clause doesn't have any required attributes.
        with self.assertRaises(errors.ContractAttributeError):

            class TestClause(contract.ContractClause):
                pass

        # Clause doesn't have description or lifecycle_point
        with self.assertRaises(errors.ContractAttributeError):

            class TestClause(contract.ContractClause):
                title = 'Test'

        # Clause doesn't have lifecycle_point
        with self.assertRaises(errors.ContractAttributeError):

            class TestClause(contract.ContractClause):
                title = 'Test'
                description = 'foobar'

        # Clause has invalid lifecycle_point
        with self.assertRaises(errors.ContractAttributeError):

            class TestClause(contract.ContractClause):
                title = 'Test'
                description = 'foobar'
                lifecycle_point = -10

        # Clause has invalid error_level
        with self.assertRaises(errors.ContractAttributeError):

            class TestClause(contract.ContractClause):
                title = 'Test'
                description = 'foobar'
                lifecycle_point = contract.POST_START
                error_level = -10

        # Clause has improper type for unresolved_dependencies
        with self.assertRaises(errors.ContractAttributeError):

            class Test4(contract.ContractClause):
              title = 'Test'
              description = 'foobar'
              lifecycle_point = contract.POST_START
              _unresolved_dependencies = 'blah'

        # Clause is ok.
        class TestClause(contract.ContractClause):
            title = 'Test'
            description = 'foobar'
            lifecycle_point = contract.POST_START
            _unresolved_dependencies = {'blah'}

    def test_extract_clauses(self):
        """Test that validator extracts only clauses from module."""

        class TestClause(contract.ContractClause):
            title = 'Test'
            description = 'foobar'
            lifecycle_point = contract.POST_START

        class TestClause2(contract.ContractClause):
            title = 'Test2'
            description = 'baz'
            lifecycle_point = contract.POST_START

        class NotAClause(object):
            pass

        class Module(object):

            # Should be extracted
            testclause = TestClause
            testclause2 = TestClause2
            notaclause = NotAClause

            # Should not be extracted
            foo = 'foo'
            bar = 1

        clauses = contract.ContractValidator._extract_clauses(Module)
        clauses.sort()

        expected = [TestClause, TestClause2]
        expected.sort()

        self.assertEqual(clauses, expected)

    def test_normalize_clauses(self):
        """Test that clauses are properly normalized."""

        class TestClause(contract.ContractClause):
            title = 'Test'
            description = 'foo'
            lifecycle_point = contract.POST_START
            _unresolved_dependants = {'TestClause2'}
            _unresolved_after = {'TestClause3'}

        class TestClause2(contract.ContractClause):
            title = 'Test2'
            description = 'bar'
            lifecycle_point = contract.POST_START
            _unresolved_before = {'TestClause'}
            _unresolved_dependencies = {'TestClause'}

        class TestClause3(contract.ContractClause):
            title = 'Test3'
            description = 'baz'
            lifecycle_point = contract.POST_START
            _unresolved_dependencies = {'TestClause', 'TestClause2'}

        clause_dict = {'TestClause': TestClause,
                       'TestClause2': TestClause2,
                       'TestClause3': TestClause3}

        contract.ContractValidator._normalize_clause_dict(clause_dict)
        self.assertEqual(TestClause.dependants, {TestClause2})
        self.assertEqual(TestClause.after, {TestClause3})
        self.assertEqual(TestClause2.before, {TestClause})
        self.assertEqual(TestClause2.dependencies, {TestClause})


class HookClauseTest(ClauseTestBase):

    def setUp(self):
        super(HookClauseTest, self).setUp()

        # Disable excessively verbose output from the validator (for now)
        logging.getLogger('appstart.validator').disabled = True

        class FakeAppContainer(object):
            host = 'localhost'

            def get_id(self):
                return '123'

        class FakeSandbox(object):
            app_dir = self.app_dir
            app_container = FakeAppContainer()
            port = 8080

            def __init__(self, *args, **kwargs):
                pass

            def start(self):
                pass

            def stop(self):
                pass

        class Module(object):
            pass

        self.module = Module
        self.old_sandbox = container_sandbox.ContainerSandbox
        container_sandbox.ContainerSandbox = FakeSandbox

        # Should result in a successful hook clause
        self.successful_hook = textwrap.dedent('''\
            #!/usr/bin/python
            import sys
            sys.exit(0)''')

        # Should result in a failed hook clause.
        self.unsuccessful_hook = textwrap.dedent('''\
            #!/usr/bin/python
            import sys
            sys.exit(1)''')

        self.default_test_file = 'validator_tests/test1.py'

    def test_make_hook_clauses(self):
        """Test the construction of hook clauses from a .conf.yaml file."""

        test_config = textwrap.dedent('''\
            name: Test1
            title: Test number 1
            lifecycle_point: POST_START''')
        self._add_file('validator_tests/test1.py.conf.yaml', test_config)

        # The default test file does not exist.
        with self.assertRaises(utils.AppstartAbort):
            contract.ContractValidator(self.module, config_file=self.conf_file)

        self._add_file(self.default_test_file, self.successful_hook)

        # The default test file is not executable
        with self.assertRaises(utils.AppstartAbort):
            contract.ContractValidator(self.module, config_file=self.conf_file)

        os.chmod(os.path.join(self.app_dir, self.default_test_file),
                 stat.S_IEXEC | stat.S_IREAD)

        # The 'description' attribute is missing from the configuration file.
        with self.assertRaises(utils.AppstartAbort):
            contract.ContractValidator(self.module, config_file=self.conf_file)

        test_config = textwrap.dedent('''\
            name: Test1
            title: Test number 1
            lifecycle_point: POST_START
            description: This is a test.''')
        self._add_file('validator_tests/test1.py.conf.yaml', test_config)

        # The initialization should be okay now.
        contract.ContractValidator(
            self.module,
            config_file=os.path.join(self.app_dir, 'app.yaml'))

    def test_evaluate_hook_clauses(self):
        """Test that hook clauses are actually being evaluated."""

        test_config = textwrap.dedent('''\
            name: Test1
            title: Test number 1
            lifecycle_point: POST_START
            description: This is a test.''')
        self._add_file('validator_tests/test1.py.conf.yaml', test_config)
        self._add_file(self.default_test_file, self.successful_hook)
        os.chmod(os.path.join(self.app_dir, self.default_test_file),
                 stat.S_IEXEC | stat.S_IREAD | stat.S_IWRITE)

        validator = contract.ContractValidator(self.module,
                                               config_file=self.conf_file)
        self.assertTrue(validator.validate())

        self._add_file(self.default_test_file, self.unsuccessful_hook)
        os.chmod(os.path.join(self.app_dir, self.default_test_file),
                 stat.S_IEXEC | stat.S_IREAD | stat.S_IWRITE)

        # Validator should still pass because the default threshold is higher
        # than UNUSED.
        self.assertTrue(validator.validate())

        self.assertFalse(validator.validate(threshold='UNUSED'))

        test_config = textwrap.dedent('''\
            name: Test1
            title: Test number 1
            lifecycle_point: POST_START
            description: This is a test.
            error_level: FATAL''')
        self._add_file('validator_tests/test1.py.conf.yaml', test_config)
        validator = contract.ContractValidator(self.module,
                                               config_file=self.conf_file)

        # Validator should fail because the defaul threshold should be less
        # than FATAL.
        self.assertFalse(validator.validate())

    def test_loop_detection(self):
        """Test that the validator detects dependency loops."""

        class Test1(contract.ContractClause):
            title = 'test'
            description = 'test'
            lifecycle_point = contract.POST_START
            _unresolved_dependencies = {'Test2'}

        class Test2(contract.ContractClause):
            title = 'test'
            description = 'test'
            lifecycle_point = contract.POST_START
            dependencies = {Test1}

        class LoopyModule(object):
            test1 = Test1
            test2 = Test2

        class Test3(contract.ContractClause):
            title = 'test'
            description = 'test'
            lifecycle_point = contract.POST_START
            _unresolved_dependencies = {'Test3'}

        class LoopyModule2(object):
            test3 = Test3

        class Test4(contract.ContractClause):
            title = 'test'
            description = 'test'
            lifecycle_point = contract.POST_START
            dependencies = {Test1}

        class LoopyModule3(object):
            test4 = Test4

        class Test5(contract.ContractClause):
            title = 'test'
            description = 'test'
            lifecycle_point = contract.POST_START

        class Test6(contract.ContractClause):
            title = 'test'
            description = 'test'
            lifecycle_point = contract.PRE_START
            dependencies = {Test5}

        class LoopyModule4(object):
            test5 = Test5
            test6 = Test6

        for mod in [LoopyModule, LoopyModule2, LoopyModule3, LoopyModule4]:
            with self.assertRaises(errors.CircularDependencyError):
                contract.ContractValidator(mod, config_file=self.conf_file)

    def test_dependency_order(self):
        """Test that dependencies get executed in correct order."""
        ordering = []

        class Test1(contract.ContractClause):
            title = 'test'
            description = 'test'
            lifecycle_point = contract.POST_START

            def evaluate_clause(self, app_container):
                ordering.append(self)

        class Test3(contract.ContractClause):
            title = 'test'
            description = 'test'
            lifecycle_point = contract.POST_START
            dependencies = {Test1}

            def evaluate_clause(self, app_container):
                ordering.append(self)

        class Test2(contract.ContractClause):
            title = 'test'
            description = 'test'
            lifecycle_point = contract.POST_START
            dependants = {Test3}

            def evaluate_clause(self, app_container):
                ordering.append(self)

        class Test0(contract.ContractClause):
            title = 'test'
            description = 'test'
            lifecycle_point = contract.POST_START
            after = {Test1}

            def evaluate_clause(self, app_container):
                ordering.append(self)

        class GoodModule(object):
            test1 = Test1
            test3 = Test3
            test2 = Test2
            test0 = Test0

        validator = contract.ContractValidator(GoodModule,
                                               config_file=self.conf_file)
        validator.validate()
        types = [type(obj) for obj in ordering]
        self.assertEqual(types, [Test0, Test1, Test2, Test3])

    def tearDown(self):
        super(HookClauseTest, self).tearDown()
        logging.getLogger('appstart.validator').disabled = False
        container_sandbox.ContainerSandbox = self.old_sandbox
