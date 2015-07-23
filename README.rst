===========================================================================
Appstart Manual
===========================================================================

---------------------------------------------------------------------------
by: gouzenko
---------------------------------------------------------------------------


Introduction
===========================================================================
Appstart is a tool that allows Managed VM applications to be deployed
locally for testing purposes. It mimics the current "gcloud preview app
run" command for managed vms, with a few notable exceptions. Firstly,
devappserver does not run the application. Instead, dev_appserver runs
standalone, only starting the API server. It hooks up to the application
via the --external_port flag. Secondly, devappserver runs inside a
container. No health checking (as of now) is being performed on the
application container. The purpose of appstart is to provide a way for
custom runtime VMs to be started locally after the docker library is
removed from devappserver.

This is not an official Google product (experimental or otherwise), it is
just code that happens to be owned by Google.

Installation
===========================================================================
From its root directory, appstart can be installed like so: ::

    $ python setup.py sdist
    $ sudo pip install dist/appstart-0.8.tar.gz

Requirements
===========================================================================
It is required that the user have a Docker client running, interfacing
with the boot2docker vm. Appstart is known to work for Docker api version
1.19 (the latest version). For instructions on installing these things see: ::

    - docker: https://docs.docker.com/installation/
    - boot2docker: http://boot2docker.io/

Usage
===========================================================================
Before using appstart for the first time, generate a devappserver base
image like this: ::

    $ appstart init

You can run `appstart --help` for a list of permissible command line
options.

Default invocation
---------------------------------------------------------------------------
The appstart script can be use to start the application from the command
line. It is invoked as follows: ::

    $ appstart PATH_TO_CONFIG_FILE

PATH_TO_CONFIG_FILE must be a path to the application’s configuration
file, which is either 'appengine-web.xml' or a .yaml file. For Java
standard runtime applications, the 'appengine-web.xml' file must be inside
WEB-INF, along with a web.xml file. For all other applications, the .yaml
file must be in the root directory. By default, Appstart will attempt
to locate the Dockerfile in the application's root directory and use it to
build the application's image.

Furthermore, Appstart will run an api server, simulating the Google Cloud
Platform's services. It will invoke this api server using the
application's configuration file.

Specifying an image
---------------------------------------------------------------------------
The --image_name flag can be used to specify an existing image rather than
having Appstart build one from the Dockerfile. When --image_name is
specified, a Dockerfile is not needed: ::

    $ appstart PATH_TO_CONFIG_FILE --image_name=IMAGE_NAME

Appstart can also start an image without a configuration file like so: ::

    $ appstart --image_name=IMAGE_NAME

In this case, appstart uses a "phony" app.yaml file as the application's
configuration file.

Turning off the api server
---------------------------------------------------------------------------
By default, Appstart runs an api server so that the application can make
calls to Google Cloud Platform services (datastore, taskqueue, logging,
etc). If you don't consume these services, you can run appstart like
this: ::

    $ appstart PATH_TO_CONFIG_FILE --run_api_server=false

Under the hood
===========================================================================
Appstart runs the aforementioned api server in the devappserver container.
The `appstart init` command builds the 'devappserver base image', which
contains all the source files necessary for the api server to run.

Appstart will also build a layer on top of the devappserver image,
populating the devappserver image with the application’s configuration
files. As was mentioned earlier, if Appstart is not provided with a
configuration file, it adds a "phony" app.yaml file to the devappserver
base image.

After building images for devappserver and the application, appstart will
start containers based on these images, using the correct environment
variables. The environment variables allow the application container to
locate the devappserver container, and allow the devappserver container to
locate the application container. The containers currently run on the same
network stack for simplicity, but that’s subject to change in the future.

All of the functionality described above is implemented by the
ContainerSandbox class. This class constructs a sandbox consisting of an
application container and a devappserver container, and it connects the two
together. Upon exiting, it will stop these containers and remove them. It’s
quite resilient, so it won’t litter the docker environment with old
containers.
