# Appstart Manual

## by: gouzenko


## Introduction

Appstart is a tool that allows Managed VM applications to be deployed locally
for testing purposes. It provides access to Google Cloud Platform stubs
via an API server that runs in its own container. Appstart relies on docker-py
to manage the API server container and the user's application container.

This is not an official Google product (experimental or otherwise), it is just
code that happens to be owned by Google.


## Installation

From its root directory, appstart can be installed like so:

    $ python setup.py sdist
    $ sudo pip install dist/appstart-0.8.tar.gz


## Requirements

Appstart requires a running Docker server. The server can be running in a
Boot2Docker VM, as long as the docker environment variable are set correctly.
See the link below for boot2docker to find out more about docker environment
variables. Appstart is known to work for Docker server version 1.5.0.  For
information about installing docker and/or Boot2Docker see:

  * docker: https://docs.docker.com/installation/
  * boot2docker: http://boot2docker.io/


## Usage

Before using appstart for the first time, run:

    $ appstart init

This generates a 'devappserver base image', which Appstart will later use to
run the API server.

For a list of permissible command line options, you can run:

    $ appstart --help


### Default invocation

Appstart can be used to start the application from the command line.
It is invoked as follows:

    $ appstart run PATH_TO_CONFIG_FILE

`PATH_TO_CONFIG_FILE` must be a path to the application's configuration file,
which is either `appengine-web.xml` or a `.yaml` file. For Java standard runtime
applications, the `appengine-web.xml` file must be inside WEB-INF, along with a
web.xml file. For all other applications, the `.yaml` file must be in the root
directory of the application. By default, Appstart will attempt to locate the
Dockerfile in the application's root directory and use it to build the
application's image.

As stated earlier, Appstart will also run an api server to provide stubs for
Google Cloud Platform.

### Specifying an image

The `--image_name` flag can be used to specify an existing image rather than
having Appstart build one from the Dockerfile. When `--image_name` is specified,
a Dockerfile is not needed:

    $ appstart PATH_TO_CONFIG_FILE --image_name=IMAGE_NAME

Appstart can also start an image without a configuration file like so:

    $ appstart --image_name=IMAGE_NAME

In this case, appstart uses a "phony" app.yaml file as the application's
configuration file.


### Turning off the api server

By default, Appstart runs an api server so that the application can make calls
to Google Cloud Platform services (datastore, taskqueue, logging, etc). If you
don't consume these services, you can run appstart like this:

    $ appstart PATH_TO_CONFIG_FILE --no_api_server


## Options

To see all command line options, run:

    $ appstart run --help

## Under the hood

Appstart runs the aforementioned api server in the devappserver container.  The
`appstart init` command builds the 'devappserver base image', which contains all
the source files necessary for the api server to run.


Appstart will also build a layer on top of the devappserver image, populating
the devappserver image with the application's configuration files. As was
mentioned earlier, if Appstart is not provided with a configuration file, it
adds a "phony" app.yaml file to the devappserver base image.


After building images for devappserver and the application, appstart will start
containers based on these images, using the correct environment variables. The
environment variables allow the application container to locate the devappserver
container, and allow the devappserver container to locate the application
container. The containers currently run on the same network stack for
simplicity, but that's subject to change in the future.


All of the functionality described above is implemented by the ContainerSandbox
class. This class constructs a sandbox consisting of an application container
and a devappserver container, and it connects the two together. Upon exiting, it
will stop these containers and remove them. It's quite resilient, so it won't
litter the docker environment with old containers.


# The Validator

The validator is a framework built to validate whether or not a container
conforms to the runtime contract. The runtime contract consists of a set of
requirements imposed on it by the Google Cloud Platform. For instance, a
container must respond to health checks on the `_ah/health` endpoint.

The validator can test an application container to see if it meets the
requirements of the runtime contract.

## Default Invocation

The validator can be invoked like this:

    $ appstart validate <PATH_TO_CONFIG>

The validator gets the container running in the same way as `appstart run`
does. It then runs through a series of 'clauses', each of which test if
the container is meeting a specific expectation. For example, a particular
clause might send an HTTP request to the `_ah/health` endpoint to see if the
application container properly responds to health checks. Another clause
might check if the application is writing logs correctly.

## Lifecycle points

The validator evaluates clauses at very specific points of the container's
lifecycle. The time period in which a clause is evaluated is called its
'lifecycle point'. Lifecycle points include the following:

  * `PRE_START`: the time before a start request is sent to the container
  * `START`: the time during which a start request is sent to the container.
    Note that only one clause can be defined for this lifecycle point.
  * `POST_START`: the time after the container has received the start request.
  * `STOP`: the time during which a stop request is sent to the container.
    Note that only one clause can be defined for this lifecycle point.
  * `POST_STOP`: the time after the container has received the stop request.

## Error levels

Each clause is marked with a specific error level. The error level denotes the
severity of the error that would occur, should the clause fail to pass. Error
levels include the following:

  * FATAL: If the container fails a clause marked as FATAL, the container will
    absolutely not work. FATAL errors include not listening on port 8080, not
    responding properly to health checks, etc.

  * WARNING: If the container fails a clause marked as WARNING,
    it will possibly exhibit unexpected behavior. WARNING errors include
    not writing logs in the correct format.

  * UNUSED: If the container does not pass a clause marked as UNUSED, no real
    error has occurred. It just means that the container isn't taking full
    advantage of the runtime contract. UNUSED level errors include not writing
    access or diagnostic logs. Other errors (namely WARNING errors) might be
    dependent on UNUSED-level clauses. For instance, logging format is
    contingent on the existence of logs in the proper location.

By default, validation will fail if any clauses with error level WARNING or
higher fail. This behavior can be changed by specifying a threshold. See
`appstart validate --help` for more info.

## Options

The validator accepts all of the same options as `appstart run` does. In
addition, the validator provides several options specific to its own
functionality. To see all available options, run:

    $ appstart validate --help

## Custom Hook Clauses

The validator provides functionality to write "hook clauses". These are
user-supplied clauses generated at runtime.

### Adding a hook clause

To find hook clauses, the validator looks in the application's root for a
directory by the name of `validator_hooks`. If such a directory is present,
the validator recursively walks it, looking for any configuration files that
end with `.conf.yaml`. For every such file found, the validator generates a
hook clause, which will be evaluated along with all of the validator's default
clauses. Note that for the validator to discover hook clauses, it must be run
on the application's configuration file. In other words, hook clause will
not fire if the following command is run:

    $ appstart validate --image_name=<IMAGE_TO_RUN>

### Writing a hook clause

Specifying the behavior of a hook clause is very simple. As an example, let's
walk through how this is done. Suppose we have an application with a very
sophisticated `/foo` url endpoint. When we hit the `/foo` endpoint, we expect
it to return a response whose body consists of the word, 'bar'.

To write a hook clause to test this behavior, create the file
`validator_hooks/test.py.conf.yaml` with the following content:

    name: TestClause
    title: Foo endpoint test
    description: Test that /foo endpoint of the application returns 'bar'
    lifecycle_point: POST_START

Upon encountering our test.py.conf.yaml file, the validator will search for
a script called `test.py` in the same directory. If it finds one, the validator
will execute it at runtime, providing it with the following environment
variables:

  * `APP_CONTAINER_ID`: The application's Docker container ID. This can be used
    to perform docker commands on the application.
  * `APP_CONTAINER_HOST`: The host where the application container is running.
  * `APP_CONTAINER_PORT`: The port where the application container is running.

These environment variables can be used to test the container by sending it
requests or even examining its internal state with docker. Since we're testing
the `/foo` endpoint, our `validator_hooks/test.py` might look like this:

    #!/usr/bin/python
    import os
    import requests

    host = os.environ.get('APP_CONTAINER_HOST')
    port = os.environ.get('APP_CONTAINER_PORT')

    response = requests.get('http://{0}:{1}/foo'.format(host, port))
    assert response.text == 'bar'

Make sure that test.py is an executable. To do this, you can run:

    $ chmod u+x test.py

The hook clause will only be considered a failure if the executable returns a
nonzero exit code. In the case of failure, the stdout and stderr of the
executable will be reported in the test results. 

### Configuring Hook Clauses

In our `.conf.yaml` file, we specified only a few key-value pairs. Those were
the minimum parameters a hook clause needs. Of course, we can make our hook
clause more configurable than that. Here's a list of configurable keys that can
be put into a hook clause's `.conf.yaml` file:

  * name: The name of the clause, used to identify the clause by other clauses.
  * title: The title of the clause, displayed in test results
  * description: A brief description of the thing the clause is validating. This
    description is also displayed in test results.
  * lifecycle\_point: The point of the container's lifecycle in which the hook
    clause should be executed.
  * error\_level: The severity of the error that would occur, should the clause
    fail. Defaults to `UNUSED`.
  * tags: A list of string tags to mark the hook clause with. The validator can
    be invoked with the `--tags' option, which specifies a subset of clauses to
    be evaluated.
  * command: A string representing the command used to "evaluate" the hook clause.
    By default, the validator will search for an executable of the same name,
    less the `.conf.yaml` suffix. The hook clause is considered a success if it
    returns with an exit code of 0.
  * dependencies: A list of clauses that must have passed before the hook clause
    is evaluated. If any of the hook clauses dependencies have failed, the hook
    clause will be skipped.
  * dependants: A list of clauses whose evaluation should be contingent on the
    success of the hook clause. If the hook clause fails, none of its dependants
    will run.
  * before: A list of clauses that should be evaluated BEFORE the hook clause.
    Similar to dependencies, but the hook clause will run even if any of its
    "before" clauses have failed.
  * after: A list of clauses that should be evaluated AFTER the hook clause.

To specify a list of clauses for the last four keys, simply supply their names
as they appear in the "name" key. For example, here's our old `.conf.yaml` file
with a little more configuration:

    name: TestClause
    title: Foo endpoint test
    description: Test that /foo endpoint of the application returns 'bar'
    lifecycle_point: POST_START
    error_level: WARNING
    tags:
        - test
        - foo
        - baz
    dependencies:
        - StartClause
        - HealthChecksEnabledClause
    after:
        - HealthCheckClause
    command: /path/to/some/executable
