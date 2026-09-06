import contextlib
import hashlib
import io
import unittest
from types import SimpleNamespace

from publish.licensing.fingerprint import DeviceFingerprintError, build_device_hash


def _digest(system, *values):
    material = "\n".join(("opub-device-v1", system, *values))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class DeviceFingerprintTests(unittest.TestCase):
    def test_darwin_hashes_normalized_ioreg_platform_uuid(self):
        calls = []

        def run(command, **kwargs):
            calls.append((command, kwargs))
            return SimpleNamespace(
                stdout='    "IOPlatformUUID" = "  AABBCCDD-0011-2233-4455-66778899AABB  "\n',
                stderr="must-not-be-read",
                returncode=17,
            )

        result = build_device_hash(system="Darwin", run=run, read=lambda path: "")

        self.assertEqual(
            result,
            _digest("macos", "aabbccdd-0011-2233-4455-66778899aabb"),
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0][0], "ioreg")
        self.assertEqual(
            calls[0][1],
            {"capture_output": True, "text": True, "timeout": 8, "check": False},
        )

    def test_windows_combines_smbios_uuid_then_machine_guid(self):
        commands = []

        def run(command, **kwargs):
            commands.append(command)
            joined = " ".join(command).lower()
            if "win32_computersystemproduct" in joined:
                return SimpleNamespace(stdout=' "SMBIOS-ID" \n')
            if "machineguid" in joined:
                return SimpleNamespace(stdout=" 'MACHINE-GUID' \n")
            raise AssertionError("unexpected command")

        result = build_device_hash(system="Windows", run=run, read=lambda path: "")

        self.assertEqual(
            result,
            _digest("windows", "smbios-id", "machine-guid"),
        )
        self.assertEqual(len(commands), 2)

    def test_linux_prefers_product_uuid_without_reading_machine_id(self):
        paths = []

        def read(path):
            paths.append(path)
            if path == "/sys/class/dmi/id/product_uuid":
                return ' "PRODUCT-UUID" \n'
            raise AssertionError("machine-id fallback must not be read")

        result = build_device_hash(system="Linux", run=lambda *args, **kwargs: None, read=read)

        self.assertEqual(result, _digest("linux", "product-uuid"))
        self.assertEqual(paths, ["/sys/class/dmi/id/product_uuid"])

    def test_linux_falls_back_to_machine_id_when_product_uuid_is_empty(self):
        values = {
            "/sys/class/dmi/id/product_uuid": "  \n",
            "/etc/machine-id": " 'MACHINE-ID' \n",
        }

        result = build_device_hash(
            system="Linux",
            run=lambda *args, **kwargs: None,
            read=lambda path: values[path],
        )

        self.assertEqual(result, _digest("linux", "machine-id"))

    def test_unknown_system_raises_stable_error_without_touching_io(self):
        def unexpected(*args, **kwargs):
            raise AssertionError("I/O must not run for an unsupported system")

        with self.assertRaises(DeviceFingerprintError) as raised:
            build_device_hash(system="FreeBSD", run=unexpected, read=unexpected)

        self.assertEqual(raised.exception.code, "LIC-004")
        self.assertNotIn("FreeBSD", str(raised.exception))

    def test_missing_identifiers_raise_stable_error(self):
        with self.assertRaises(DeviceFingerprintError) as raised:
            build_device_hash(
                system="Linux",
                run=lambda *args, **kwargs: SimpleNamespace(stdout=""),
                read=lambda path: "\n",
            )

        self.assertEqual(raised.exception.code, "LIC-004")

    def test_raw_identifiers_are_never_printed_or_returned(self):
        raw_identifier = "TOP-SECRET-DEVICE-ID"
        stdout = io.StringIO()
        stderr = io.StringIO()

        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = build_device_hash(
                system="Linux",
                run=lambda *args, **kwargs: None,
                read=lambda path: raw_identifier,
            )

        self.assertNotIn(raw_identifier, result)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "")

    def test_command_exception_maps_to_safe_device_error(self):
        raw_identifier = "SECRET-FROM-COMMAND"

        def failing_run(*args, **kwargs):
            raise RuntimeError(raw_identifier)

        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            with self.assertRaises(DeviceFingerprintError) as raised:
                build_device_hash(system="Darwin", run=failing_run, read=lambda path: "")

        self.assertEqual(raised.exception.code, "LIC-004")
        self.assertNotIn(raw_identifier, str(raised.exception))
        self.assertIsNone(raised.exception.__cause__)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "")

    def test_file_exception_maps_to_safe_device_error(self):
        def failing_read(path):
            raise UnicodeError("SECRET-FROM-FILE")

        with self.assertRaises(DeviceFingerprintError) as raised:
            build_device_hash(system="Linux", run=lambda *args, **kwargs: None, read=failing_read)

        self.assertEqual(raised.exception.code, "LIC-004")
        self.assertNotIn("SECRET-FROM-FILE", str(raised.exception))
        self.assertIsNone(raised.exception.__cause__)


if __name__ == "__main__":
    unittest.main()
