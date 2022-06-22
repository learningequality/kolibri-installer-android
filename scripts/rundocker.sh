#!/bin/bash

set -e

SCRIPTDIR=$(realpath "$(dirname "$0")")
SRCDIR=$(dirname "$SCRIPTDIR")
DOCKER=${DOCKER:-"docker"}

BUILD_CACHE_VOLUME=kolibri-android-cache
BUILD_CACHE_PATH=/cache

docker_is_podman() {
    "${DOCKER}" --version 2>/dev/null | grep -q "^podman"
}

# Build array of options to pass to docker run.
RUN_OPTS=(
  -it --rm

  # Bind mount the source directory into the container and make it the
  # working dirctory.
  --mount "type=bind,src=${SRCDIR},dst=${SRCDIR}"
  --workdir "${SRCDIR}"

  # Pass through other environment variables.
  --env BUILDKITE_BUILD_NUMBER
  --env P4A_RELEASE_KEYALIAS
  --env P4A_RELEASE_KEYSTORE_PASSWD
  --env P4A_RELEASE_KEYALIAS_PASSWD
  --env ARCHES
)

# If we're running in podman, assume the user namespace is setup so that
# root inside the container is the same as the outside user. Otherwise,
# get the UID and GID to run as.
if docker_is_podman; then
  BUILD_UID=0
  BUILD_GID=0
else
  BUILD_UID=$(id -u)
  BUILD_GID=$(id -g)
fi

# If the container user is root, mount the cache at /root. Otherwise,
# set HOME since there's likely no account with that UID in the image.
# The user's home directory is where all the intermediate build outputs
# (e.g., ~/.local/share/python-for-android and ~/.gradle) are stored.
if [ "$BUILD_UID" -eq 0 ]; then
  BUILD_CACHE_PATH=/root
else
  BUILD_CACHE_PATH=/cache
  RUN_OPTS+=(
    --user "${BUILD_UID}:${BUILD_GID}"
    --env HOME="${BUILD_CACHE_PATH}"
  )
fi

# Mount the cache volume.
RUN_OPTS+=(
  --mount "type=volume,src=${BUILD_CACHE_VOLUME},dst=${BUILD_CACHE_PATH}"
)

# If the release signing key has been specified and exists, ensure the
# path is absolute and bind mount it readonly into the container.
if [ -e "${P4A_RELEASE_KEYSTORE}" ]; then
  P4A_RELEASE_KEYSTORE=$(realpath "${P4A_RELEASE_KEYSTORE}")
  RUN_OPTS+=(
    --env P4A_RELEASE_KEYSTORE
    --volume "${P4A_RELEASE_KEYSTORE}:${P4A_RELEASE_KEYSTORE}:ro"
  )
fi

exec "${DOCKER}" run "${RUN_OPTS[@]}" android_kolibri "$@"
