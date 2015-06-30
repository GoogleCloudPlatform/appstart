# Copyright 2015 Google Inc. All Rights Reserved.

"""The runtime contract is a set of requirements on GAE app containers."""

# This file conforms to the external style guide.
# see: https://www.python.org/dev/peps/pep-0008/.
# pylint: disable=bad-indentation, g-bad-import-order

import inspect
import sys
import requests

import docker

import contract


class HealthClause(contract.ContractClause):
    """Validate health checking."""

    def __init__(self, lifecyle_point=contract.POST_START):
        """Initializer for HealthClause.

        Args:
            lifecyle_point: (int) a point in contract._TIMELINE.keys().
                This determines when in the container's lifecycle the
                clause will be evaluated.
        """
        title = 'Health checking'
        description = 'container must respond to /_ah/health endpoint'
        super(HealthClause, self).__init__(title,
                                           description,
                                           lifecyle_point)

    def evaluate_clause(self, sandbox):
        """Ensure that the application responds to '_ah/health' endpoint.

        Args:
            sandbox: (appstart.ContainerSandbox) A sandbox that manages
                the container that is to be tested.
        """
        url = ('http://%s:%s/_ah/health' %
               (sandbox.get_docker_host(), sandbox.port))
        rep = requests.get(url)
        if rep.status_code != 200:
            raise contract.ContractFailureError('the container did not '
                                                'properly respond to '
                                                'health checks.')


class LoggingLocationClause(contract.ContractClause):
    """Validate logging location."""

    def __init__(self, lifecyle_point=contract.POST_START):
        """Initializer for LoggingLocationClause.

        Args:
            lifecyle_point: (int) a point in contract._TIMELINE.keys().
                This determines when in the container's lifecycle the
                clause will be evaluated.
        """
        title = 'Logging location'
        description = 'logs must be written to /var/log/app_engine'
        super(LoggingLocationClause, self).__init__(
            title,
            description,
            lifecyle_point,
            error_level=contract.WARNING)

    def evaluate_clause(self, sandbox):
        """Ensure that the application writes logs to /var/log/app_engine.

        Args:
            sandbox: (appstart.ContainerSandbox) A sandbox that manages
                the container that is to be tested.
        """
        try:
            sandbox.dclient.copy(container=sandbox.app_container.get('Id'),
                                 resource='/var/log/app_engine/request.log')
        except docker.errors.APIError:
            self.fail('could not find /var/log/app_engine/request.log')


_CONTRACT = None


def get_contract():
    """Get the runtime contract.

    Returns:
        ([contract.ContractClause, ...]) A list of clauses collectively
        representing the runtime contract.
    """
    global _CONTRACT
    if not _CONTRACT:
        _CONTRACT = build_contract_from_module()
    return _CONTRACT


def build_contract_from_module(omit=None):
    """Build a runtime contract from the clauses in this module.

    Args:
        omit: ([class, ...]) A list of class objects to be omitted from
            the runtime contract.

    Returns:
        ([contract.ContractClause, ...]) A list of clauses collectively
        representing the runtime contract.
    """
    clause_list = []
    omit = omit or []

    # Get all classes in this module.
    classes = inspect.getmembers(sys.modules[__name__], inspect.isclass)

    # Add all contract.ContractClauses to the clause list.
    for _, cls in classes:
        if issubclass(cls, contract.ContractClause) and cls not in omit:
            clause_list.append(cls())
    return clause_list
