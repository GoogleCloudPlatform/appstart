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
