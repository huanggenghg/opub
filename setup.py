import os
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py as setuptools_build_py


_OBSOLETE_MODULE = Path("utils/excel_writer.py")


def _absolute_path(path):
    return Path(os.path.abspath(os.fspath(path)))


def _require_unredirected_directory(path, label):
    absolute_path = _absolute_path(path)
    if absolute_path != absolute_path.resolve():
        raise RuntimeError(f"refusing redirected {label}: {absolute_path}")
    return absolute_path


def _remove_obsolete_module(staging_root):
    staging_root = _require_unredirected_directory(staging_root, "staging directory")
    utils_directory = _require_unredirected_directory(
        staging_root / _OBSOLETE_MODULE.parent,
        "staging utils directory",
    )
    obsolete_module = utils_directory / _OBSOLETE_MODULE.name
    if os.path.lexists(obsolete_module):
        try:
            obsolete_module.unlink()
        except FileNotFoundError:
            pass


class CleanBuildPy(setuptools_build_py):
    """Prevent deleted source modules from surviving in incremental builds."""

    def run(self):
        _remove_obsolete_module(self.build_lib)

        bdist_wheel = self.distribution.get_command_obj("bdist_wheel", create=False)
        if bdist_wheel is not None:
            bdist_wheel.ensure_finalized()
            _remove_obsolete_module(bdist_wheel.bdist_dir)

        super().run()


setup(cmdclass={"build_py": CleanBuildPy})
