from __future__ import annotations

import os
import re
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import Optional


CLIENT_LICENSE_FILES = {
    "publish/licensing/__init__.py",
    "publish/licensing/activation.py",
    "publish/licensing/api.py",
    "publish/licensing/codes.py",
    "publish/licensing/deployment.py",
    "publish/licensing/fingerprint.py",
    "publish/licensing/storage.py",
    "publish/licensing/verifier.py",
}
PRIVATE_KEY_ENV_NAMES = ("OPUB_LICENSE_PRIVATE_KEY",)


def _normalized_name(name: str) -> str:
    """Strip an sdist's generated opub-version root from a member name."""
    parts = Path(name).parts
    if len(parts) > 1 and parts[0].startswith("opub-"):
        return Path(*parts[1:]).as_posix()
    return Path(name).as_posix()


def _assert_client_license_files(
    test_case: unittest.TestCase,
    names: set[str],
    *,
    deployment_file: Optional[str] = None,
) -> None:
    """Assert client modules, optionally including generated deployment config."""
    required = set(CLIENT_LICENSE_FILES)
    if deployment_file is not None:
        required.add(deployment_file)
    missing = sorted(required - {_normalized_name(name) for name in names})
    test_case.assertFalse(
        missing,
        "distribution is missing required license client files: " + ", ".join(missing),
    )


def _archive_payloads(path: Path) -> dict[str, bytes]:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            return {
                member: archive.read(member)
                for member in archive.namelist()
                if not member.endswith("/")
            }
    with tarfile.open(path) as archive:
        return {
            member.name: extracted.read()
            for member in archive.getmembers()
            if member.isfile() and (extracted := archive.extractfile(member)) is not None
        }


def _assert_no_private_bytes(
    test_case: unittest.TestCase,
    repo_root: Path,
    artifact_name: str,
    payloads: dict[str, bytes],
) -> None:
    private_sources = {
        path.name: path.read_bytes()
        for path in (repo_root / "license_server").glob("*.py")
        if path.stat().st_size >= 64
    }
    for source_name, private_bytes in private_sources.items():
        if any(private_bytes in payload for payload in payloads.values()):
            test_case.fail(
                f"{artifact_name} contains private service module bytes from {source_name}"
            )

    for env_name in PRIVATE_KEY_ENV_NAMES:
        secret = os.environ.get(env_name)
        if secret and any(secret.encode("utf-8") in payload for payload in payloads.values()):
            test_case.fail(f"{artifact_name} contains the value of {env_name}")


def _assert_no_activation_inventories(
    test_case: unittest.TestCase,
    artifact_name: str,
    payloads: dict[str, bytes],
) -> None:
    inventory_names = [
        _normalized_name(name)
        for name in payloads
        if Path(_normalized_name(name)).name.lower().endswith(".txt")
        and "code" in Path(_normalized_name(name)).name.lower()
    ]
    test_case.assertEqual(
        [],
        inventory_names,
        f"{artifact_name} contains activation-code inventory files",
    )

    code_pattern = re.compile(
        r"(?:OPUB0(?:-[0-9A-HJKMNPQRSTVWXYZ]{5}){6}"
        r"|OPUB0[0-9A-HJKMNPQRSTVWXYZ]{30})"
    )
    for name, payload in payloads.items():
        if not Path(_normalized_name(name)).name.lower().endswith(".txt"):
            continue
        lines = [
            line.strip()
            for line in payload.decode("utf-8", errors="ignore").splitlines()
            if line.strip()
        ]
        if any(code_pattern.fullmatch(line) for line in lines):
            test_case.fail(
                f"{artifact_name} contains plaintext activation-code inventory payload in {name}"
            )


def _build_wheel(repo_root: Path, outdir: Path) -> set[str]:
    """Build the public wheel exactly the way a real pip install would."""
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--wheel-dir",
            str(outdir),
            str(repo_root),
        ],
        cwd=repo_root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    wheel = next(outdir.glob("opub-*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        return set(archive.namelist())


def _build_sdist(repo_root: Path, outdir: Path) -> set[str]:
    """Build the public sdist exactly the way a release upload would."""
    outdir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--sdist",
            "--outdir",
            str(outdir),
            str(repo_root),
        ],
        cwd=repo_root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    sdist = next(outdir.glob("opub-*.tar.gz"))
    with tarfile.open(sdist) as archive:
        return set(archive.getnames())


class PackageBuildTest(unittest.TestCase):
    def test_distributions_exclude_stale_deleted_modules(self):
        repo_root = Path(__file__).resolve().parents[1]
        stale_module = repo_root / "build/lib/utils/excel_writer.py"
        stale_module.parent.mkdir(parents=True, exist_ok=True)
        stale_module.write_text("# stale generated build artifact\n", encoding="utf-8")

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                outdir = Path(tmpdir)
                distributions = {
                    "sdist": _build_sdist(repo_root, outdir / "sdist"),
                    "wheel": _build_wheel(repo_root, outdir / "wheel"),
                }
        finally:
            stale_module.unlink(missing_ok=True)

        for artifact_name, names in distributions.items():
            normalized_names = {_normalized_name(name) for name in names}
            with self.subTest(artifact=artifact_name):
                self.assertNotIn(
                    "utils/excel_writer.py",
                    normalized_names,
                    f"{artifact_name} contains a stale deleted module",
                )

    def test_inventory_detector_rejects_headered_and_normalized_code_files(self):
        samples = (
            (
                "private/inventory.txt",
                b"generated inventory\nOPUB0-01234-56789-ABCDE-FGHJK-MNPQR-STVWX\n",
            ),
            (
                "private/inventory.txt",
                b"generated inventory\nOPUB00123456789ABCDEFGHJKMNPQRSTVWX\n",
            ),
            ("private/activation-code.txt", b"generated elsewhere\n"),
        )
        for name, payload in samples:
            with self.subTest(name=name, payload=payload), self.assertRaises(AssertionError):
                _assert_no_activation_inventories(
                    self,
                    "synthetic distribution",
                    {name: payload},
                )

    def test_wheel_contains_opub_entry_modules(self):
        repo_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmpdir:
            names = _build_wheel(repo_root, Path(tmpdir))

        self.assertIn("conf.py", names)
        self.assertNotIn("opub_cli.py", names)
        self.assertIn("publish_all.py", names)
        self.assertNotIn("sau_cli.py", names)
        # The client-facing publish packages must keep shipping in the wheel.
        self.assertIn("publish/orchestrator.py", names)
        self.assertIn("uploader/weibo_uploader/main.py", names)
        self.assertIn("utils/stealth.min.js", names)
        _assert_client_license_files(self, names)

    def test_distributions_contain_only_public_license_client(self):
        repo_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmpdir:
            outdir = Path(tmpdir)
            wheel_names = _build_wheel(repo_root, outdir / "wheel")
            sdist_names = _build_sdist(repo_root, outdir / "sdist")

            distributions = (
                ("wheel", wheel_names, next((outdir / "wheel").glob("opub-*.whl"))),
                ("sdist", sdist_names, next((outdir / "sdist").glob("opub-*.tar.gz"))),
            )

            for artifact_name, names, artifact_path in distributions:
                normalized_names = {_normalized_name(name) for name in names}
                payloads = _archive_payloads(artifact_path)
                _assert_client_license_files(self, names)
                self.assertFalse(
                    any("license_server" in Path(name).parts for name in normalized_names)
                )
                self.assertFalse(
                    any(".secrets" in Path(name).parts for name in normalized_names)
                )
                self.assertFalse(any(".sqlite3" in name for name in normalized_names))
                self.assertFalse(
                    any(
                        part == ".env" or part.startswith(".env.")
                        for name in normalized_names
                        for part in Path(name).parts
                    )
                )
                _assert_no_private_bytes(
                    self,
                    repo_root,
                    artifact_name,
                    payloads,
                )
                _assert_no_activation_inventories(
                    self,
                    artifact_name,
                    payloads,
                )

    def test_release_version_is_consistent(self):
        repo_root = Path(__file__).resolve().parents[1]
        pyproject_text = (repo_root / "pyproject.toml").read_text(encoding="utf-8")
        skill_text = (repo_root / "skills/opub-cli/SKILL.md").read_text(encoding="utf-8")
        lock_text = (repo_root / "uv.lock").read_text(encoding="utf-8")

        self.assertIn('version = "0.8.1"', pyproject_text)
        self.assertIn('version: "0.8.1"', skill_text)
        self.assertIn('name = "opub"\nversion = "0.8.1"', lock_text)
        self.assertNotIn('{ name = "qrcode"', lock_text)

    def test_manifest_explicitly_excludes_activation_code_inventories(self):
        repo_root = Path(__file__).resolve().parents[1]
        manifest_text = (repo_root / "MANIFEST.in").read_text(encoding="utf-8")
        self.assertIn("global-exclude *codes*.txt", manifest_text.splitlines())
