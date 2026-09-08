from pathlib import Path
import shutil

from setuptools import setup
from setuptools.command.build_py import build_py as setuptools_build_py


class CleanBuildPy(setuptools_build_py):
    """Prevent deleted source modules from surviving in incremental builds."""

    def run(self):
        repo_root = Path(__file__).resolve().parent
        build_root = repo_root / "build"
        build_lib = Path(self.get_finalized_command("build").build_lib)
        if not build_lib.is_absolute():
            build_lib = repo_root / build_lib

        resolved_build_root = build_root.resolve()
        resolved_build_lib = build_lib.resolve()
        if (
            build_root.is_symlink()
            or build_lib.is_symlink()
            or resolved_build_lib.parent != resolved_build_root
            or not resolved_build_lib.name.startswith("lib")
        ):
            raise RuntimeError(f"refusing to clear unexpected build directory: {build_lib}")

        if resolved_build_lib.is_dir():
            shutil.rmtree(resolved_build_lib)
        super().run()


setup(cmdclass={"build_py": CleanBuildPy})
