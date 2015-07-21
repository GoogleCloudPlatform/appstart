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
It is required that the user have a working copy of gcloud with the app
module.  To get the app module, run ``gcloud components update preview``.
Gcloud will complain that there's no app module, and it will provide a
prompt to install it. It is also required that the user have a docker
client running, interfacing with the boot2docker vm. For instructions on
installing these things see: ::

    - gcloud: https://cloud.google.com/sdk/
    - docker: https://docs.docker.com/installation/ubuntulinux/
    - boot2docker: http://boot2docker.io/

Usage
===========================================================================
Before using appstart for the first time, generate a devappserver base
image like this: ::

    $ appstart init

This command will take a while to complete (1-2 min).

Default invocation
---------------------------------------------------------------------------
The appstart script can be use to start the application from the command
line. It is invoked as follows: ::

    $ appstart <PATH_TO_CONFIG_FILE>

<PATH_TO_CONFIG_FILE> must be a path to the application’s configuration
file, which is either 'appengine-web.xml' or a .yaml file. For Java
standard runtime applications, the 'appengine-web.xml' file must be inside
WEB-INF, along with a web.xml file. For all other applications, the .yaml
file must be in the root directory. By default, Appstart will attempt
to locate the Dockerfile in the application's root directory and use it to
build the application's image.

Specifying an image
---------------------------------------------------------------------------
The --image_name flag can be used to specify an existing image rather than
having Appstart build one from the Dockerfile. When --image_name is
specified, a Dockerfile is not needed: ::

    $ appstart <PATH_TO_CONFIG_FILE> --image_name=<IMAGE_NAME>

Turning off the api server
---------------------------------------------------------------------------
By default, Appstart runs an api server so that the application can make
calls to Google's services (datastore, taskqueue, logging, etc). If you
don't consume these services, you can run appstart like this: ::

    $ appstart <PATH_TO_CONFIG_FILE> --run_api_server=false

Under the hood
===========================================================================
Appstart will look in the target directory for the application’s
Dockerfile. Upon finding one, it will build the application’s image with
that Dockerfile. It will also build a layer on top of the devappserver
image, populating the devappserver image with the contents of the
application’s root directory. When devappserver starts, it will use the
application’s configuration file to do so.  After building images for
devappserver and the application, appstart will start containers based on
these images, using the correct environment variables. The environment
variables allow the application container to locate the devappserver
container, and allow the devappserver container to locate the application
container. The containers currently run on the same network stack for
simplicity, but that’s subject to change in the future.

All of the functionality described above is implemented by the
ContainerSandbox class. This class constructs a sandbox consisting of an
application container and a devappserver container, and it connects the two
together. Upon exiting, it will stop these containers and remove them. It’s
quite resilient, so it won’t litter the docker environment with old
containers.
