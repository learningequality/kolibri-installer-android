import os

from pythonforandroid.recipe import CompiledComponentsPythonRecipe


class ZStandardRecipe(CompiledComponentsPythonRecipe):
    """
    Recipe for zstandard
    """

    name = "zstandard"
    version = "0.18.0"
    url = (
        "https://pypi.python.org/packages/source/z/zstandard/zstandard-{version}.tar.gz"
    )
    depends = ["cffi", "setuptools"]

    # Local patches need to be an absolute paths or they won't be found
    # by patch.
    #
    # https://github.com/kivy/python-for-android/issues/2623
    patches = [
        os.path.realpath(os.path.join(os.path.dirname(__file__), "preprocessor.patch")),
    ]

    call_hostpython_via_targetpython = False  # For setuptools


recipe = ZStandardRecipe()
