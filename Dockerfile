# Dockerfile for build

FROM registry.endlessm-sf.com/eos:master

# Install the dependencies for the build system
RUN export DEBIAN_FRONTEND=noninteractive && \
    apt-get update && \
    apt-get install -y \
        autoconf \
        automake \
        autopoint \
        build-essential \
        ccache \
        git \
        libffi-dev \
        libssl-dev \
        libtool \
        openjdk-11-jdk-headless \
        python-is-python3 \
        python3-dev \
        python3-pip \
        python3-venv \
        unzip \
        wget \
        zip \
        && \
    apt-get clean

# Install Android SDK
ENV ANDROID_HOME=/opt/android
ENV ANDROIDSDK=$ANDROID_HOME/sdk
ENV ANDROIDNDK=$ANDROIDSDK/ndk-bundle
COPY Makefile /tmp/
RUN make -C /tmp setup SDK=$ANDROIDSDK && \
  rm -f /tmp/Makefile

# install python dependencies
COPY requirements.txt /tmp/
RUN pip install -r /tmp/requirements.txt && \
  rm -f /tmp/requirements.txt

# Configure gradle for use in docker. Disable gradle's automatically
# detected rich console doesn't work in docker. Disable the gradle
# daemon since it will be stopped as soon as the container exits.
ENV GRADLE_OPTS="-Dorg.gradle.console=plain -Dorg.gradle.daemon=false"

# Create a mount point for the build cache and make it world writable so
# that the volume can be used by an unprivileged user without additional
# setup.
RUN mkdir /cache && chmod 777 /cache

CMD [ "make", "kolibri.apk" ]
