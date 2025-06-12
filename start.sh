#!/bin/bash

# Simple script to start the Duescord bot using docker-compose.
# Requires the DISCORD_TOKEN environment variable to be set.

set -e

if [ -z "$DISCORD_TOKEN" ]; then
  echo "DISCORD_TOKEN environment variable not set" >&2
  exit 1
fi

# Build the image if necessary and start the container
exec docker compose up --build
