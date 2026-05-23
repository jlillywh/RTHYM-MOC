"""
setup.py – builds the _rthym_moc C++ extension via pybind11.

Usage:
    pip install pybind11 numpy
    pip install -e .          # editable install (development)
    pip install .             # standard install
    python setup.py build_ext --inplace   # build in-place for quick testing
"""
import os
import sys

from setuptools import setup
from pybind11.setup_helpers import Pybind11Extension, build_ext


def read_version():
    namespace = {}
    with open("rthym_moc/_version.py", encoding="utf-8") as version_file:
        exec(version_file.read(), namespace)
    return namespace["__version__"]


def get_extra_compile_args():
    if sys.platform == "win32":
        return ["/O2", "/EHsc"]

    extra_compile_args = ["-O3", "-ffast-math", "-funroll-loops"]
    if os.environ.get("RTHYM_MOC_NATIVE_OPT") == "1":
        extra_compile_args.append("-march=native")
    return extra_compile_args

ext_modules = [
    Pybind11Extension(
        name="rthym_moc._rthym_moc",
        sources=[
            "src/moc_solver.cpp",
            "src/bindings.cpp",
        ],
        include_dirs=["src"],
        extra_compile_args=get_extra_compile_args(),
        cxx_std=17,
    ),
]

setup(
    name="rthym-moc",
    version=read_version(),
    ext_modules=ext_modules,
    cmdclass={"build_ext": build_ext},
    packages=["rthym_moc"],
    package_data={"rthym_moc": ["*.pyi", "py.typed"]},
    zip_safe=False,
)
