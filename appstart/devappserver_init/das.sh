SDK_ROOT=/sdk/$(ls /sdk/)
export PYTHONPATH=$SDK_ROOT/lib/
python $(find $SDK_ROOT -name dev_appserver.py | head -1) \
    --allow_skipped_files=False \
    --api_host=0.0.0.0 \
    --api_port=$API_PORT \
    --admin_host=0.0.0.0 \
    --admin_port=$ADMIN_PORT \
    --application=$APP_ID \
    --auth_domain=gmail.com \
    --clear_datastore=$CLEAR_DATASTORE \
    --datastore_consistency_policy=time \
    --dev_appserver_log_level=info \
    --enable_cloud_datastore=False \
    --enable_mvm_logs=False \
    --enable_sendmail=False \
    --log_level=info \
    --require_indexes=False \
    --show_mail_body=False \
    --skip_sdk_update_check=True \
    --port=$PROXY_PORT \
    --smtp_allow_tls=False \
    --use_mtime_file_watcher=False \
    --external_port=8088 \
    --host=0.0.0.0 \
    --storage_path=/storage \
    --logs_path=./log.txt \
    /app/$CONFIG_FILE