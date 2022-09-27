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
    patches = ["preprocessor.patch"]

    call_hostpython_via_targetpython = False  # For setuptools


recipe = ZStandardRecipe()
