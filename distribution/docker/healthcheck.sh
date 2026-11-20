#!/bin/sh
# Optional port is for isolated fixture tests; production defaults to 9696.
status=$(curl --disable --noproxy '*' --proto '=http' --max-time 3 --silent \
    --output /dev/null --write-out '%{http_code}' "http://127.0.0.1:${1:-9696}/ping") || exit 1
test "$status" = 200
