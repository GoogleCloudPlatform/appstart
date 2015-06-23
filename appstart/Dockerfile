# Copyright 2015 Google Inc. All Rights Reserved.
# This is the Dockerfile for building a devappserver base image.
FROM debian
RUN apt-get update
RUN apt-get install -y python

# Put all devappserver files/dependencies under devappserver
RUN mkdir /devappserver
ADD ./platform/google_appengine/lib/ /devappserver/lib
ADD ./platform/google_appengine/dev_appserver.py /devappserver/
ADD ./platform/google_appengine/_python_runtime.py /devappserver/
ADD ./platform/google_appengine/wrapper_util.py /devappserver/
ADD ./platform/google_appengine/google /devappserver/google
ADD ./lib/docker/ /devappserver/docker

# Invoke devappserver with the proper arguments, some of which come from
# environment variables.
ENTRYPOINT /usr/bin/python -S /devappserver/dev_appserver.py --allow_skipped_files=False --api_host=0.0.0.0 --api_port=$API_PORT --admin_host=0.0.0.0 --application=$APP_ID --auth_domain=gmail.com --clear_datastore=False --datastore_consistency_policy=time --dev_appserver_log_level=info --enable_cloud_datastore=False --enable_mvm_logs=False --enable_sendmail=False --log_level=info --require_indexes=False --show_mail_body=False --skip_sdk_update_check=True --port=$PROXY_PORT --smtp_allow_tls=False --use_mtime_file_watcher=False --external_port=8080 --host=0.0.0.0 --storage_path=/storage --logs_path=./log.txt /app/$CONFIG_FILE
