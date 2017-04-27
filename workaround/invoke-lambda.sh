#!/usr/bin/env bash

aws lambda invoke --function-name $1 \
    --invocation-type Event \
    --payload "{\"build_id\": \"$2\"}" \
    /dev/stdout
