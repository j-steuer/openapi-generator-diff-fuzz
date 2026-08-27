#!/usr/bin/env bash

# shell for resetting docker containers and networks
docker ps -aq | xargs -r docker rm -f
docker network prune -f
