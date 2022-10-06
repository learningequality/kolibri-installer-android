import os
import subprocess
import sys
import time


def kolibri_version():
    """
    Returns the major.minor version of Kolibri if it exists
    """
    with open("./src/kolibri/VERSION", "r") as version_file:
        # p4a only likes digits and decimals
        return version_file.read().strip()


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


def build_type():
    key_alias = os.getenv("P4A_RELEASE_KEYALIAS", "unknown")
    if key_alias == "LE_DEV_KEY":
        return "dev"
    if key_alias == "LE_RELEASE_KEY":
        return "official"
    return key_alias


def apk_version():
    """
    Returns the version to be used for the Kolibri Android app.
    Schema: [kolibri version]-[android installer version or githash]-[build signature type]
    """
    android_version_indicator = git_tag() or commit_hash()
    return "{}-{}-{}".format(kolibri_version(), android_version_indicator, build_type())


def build_number():
    """
    Returns the build number for the apk. This is the mechanism used to understand whether one
    build is newer than another. Uses jenkins build number with time as local dev backup
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
    if sys.argv[1] == "apk_version":
        print(apk_version())
    elif sys.argv[1] == "build_number":
        print(build_number())
