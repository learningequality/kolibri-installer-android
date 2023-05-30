#!/usr/bin/env python3
import os
import subprocess
import sys
import time


if "EXPLOREPLUGIN_WHEEL_PATH" in os.environ:
    EXPLOREPLUGIN_TARGET = "src"
else:
    EXPLOREPLUGIN_TARGET = "_explore"


def kolibri_version():
    """
    Returns the major.minor version of Kolibri if it exists
    """
    with open("./src/kolibri/VERSION", "r") as version_file:
        # p4a only likes digits and decimals
        version = version_file.read().strip()
        # For git dev builds, shorten the version by removing date details:
        if "+git" not in version:
            return version
        return version.split("+git")[0]


def explore_plugin_version_name():
    with open(
        f"./{EXPLOREPLUGIN_TARGET}/kolibri_explore_plugin/VERSION", "r"
    ) as version_name_file:
        return version_name_file.read().strip()


def explore_plugin_version():
    with open(
        f"./{EXPLOREPLUGIN_TARGET}/kolibri_explore_plugin/__init__.py", "r"
    ) as version_file:
        # The __init__.py file always has the plugin version between quotes:
        return version_file.read().split('"')[1]


def explore_plugin_simple_version():
    full_version = explore_plugin_version()
    major, minor, patch = full_version.split(".")
    if patch == "0":
        return ".".join([major, minor])
    return full_version


def commit_hash():
    """
    Returns the number of commits of the Kolibri Android repo. Returns 0 if something fails.
    TODO hash, unless there's a tag. Use alias to annotate
    """
    repo_dir = os.path.dirname(os.path.abspath(__file__))
    p = subprocess.Popen(
        "git rev-parse --short HEAD",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=True,
        cwd=repo_dir,
        universal_newlines=True,
    )
    return p.communicate()[0].rstrip()


def git_tag():
    repo_dir = os.path.dirname(os.path.abspath(__file__))
    p = subprocess.Popen(
        "git tag --points-at {}".format(commit_hash()),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=True,
        cwd=repo_dir,
        universal_newlines=True,
    )
    return p.communicate()[0].rstrip()


def get_version_name():
    """
    Returns the user-visible version to be used for the Android app.
    """
    return "{} {}-{}".format(
        explore_plugin_version_name(),
        explore_plugin_simple_version(),
        get_version_code(),
    )


def get_ek_version():
    """
    Returns detailed version of major modules for debugging.
    """
    android_version_indicator = git_tag() or commit_hash()
    return "{}-{}-{}".format(
        explore_plugin_version(), kolibri_version(), android_version_indicator
    )


def get_version_code():
    """
    Returns the version code for the build. This is the mechanism
    used by Android to understand whether one build is newer than
    another. Uses jenkins build number with time as fallback for local
    builds.
    """

    # At one point a release was made from the PR job, which had a build
    # number far ahead of the standard job.
    build_base_number = 169

    jenkins_build_number = os.getenv("BUILD_NUMBER")
    if jenkins_build_number:
        build_number = build_base_number + int(jenkins_build_number)
    else:
        build_number = int(time.time())
    return build_number


if __name__ == "__main__":
    if sys.argv[1] == "version_name":
        print(get_version_name())
    elif sys.argv[1] == "ek_version":
        print(get_ek_version())
    elif sys.argv[1] == "version_code":
        print(get_version_code())
