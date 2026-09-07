import base64
import contextlib
import io
import json
import sys
from importlib.metadata import PackageNotFoundError
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import publish_all
from publish.errors import EXIT_LICENSE_ERROR, EXIT_OK
from publish.licensing import (
    print_license_error,
    require_valid_license,
    run_activation,
    show_license_status,
)
from publish.licensing.activation import ActivationError
from publish.licensing.api import ActivationServiceError
from publish.licensing.fingerprint import DeviceFingerprintError
from publish.licensing.verifier import LicenseValidationError, canonical_json


def _signed_document(device_hash="a" * 64):
    private = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    payload = {
        "schema_version": 1,
        "key_id": "test",
        "license_id": "lic-1",
        "product": "opub-major-0",
        "device_hash": device_hash,
        "issued_at": "2026-09-05T00:00:00Z",
    }
    signature = base64.b64encode(private.sign(canonical_json(payload))).decode("ascii")
    public = base64.b64encode(private.public_key().public_bytes_raw()).decode("ascii")
    return {"payload": payload, "signature": signature}, {"test": public}


def test_parser_exposes_license_commands():
    help_text = publish_all.build_parser().format_help()
    assert "--license-status" in help_text
    assert "--activate" in help_text
    assert "--pay-with {wechat,alipay}" in help_text


def test_parser_makes_status_and_activate_mutually_exclusive():
    with pytest.raises(SystemExit) as exc:
        publish_all.build_parser().parse_args(["--license-status", "--activate"])
    assert exc.value.code == 2


def test_parser_rejects_unknown_payment_method():
    with pytest.raises(SystemExit) as exc:
        publish_all.build_parser().parse_args(["--activate", "--pay-with", "card"])
    assert exc.value.code == 2


def test_pay_with_is_only_valid_for_activation():
    with pytest.raises(SystemExit) as exc:
        publish_all.main(["--pay-with", "wechat"])
    assert exc.value.code == 2


def test_license_status_does_not_build_publish_arguments_or_run_publish():
    with patch("publish.orchestrator.show_license_status", return_value=0), \
         patch("publish.orchestrator._build_overrides") as build_overrides, \
         patch("publish.orchestrator.run_publish", new=AsyncMock()) as publish:
        assert publish_all.main(["--license-status"]) == 0
    build_overrides.assert_not_called()
    publish.assert_not_awaited()


@pytest.mark.parametrize("args", [["--help"], ["--version"]])
def test_help_and_version_do_not_check_license(args):
    with patch("publish.orchestrator.require_valid_license") as require:
        with pytest.raises(SystemExit) as exc:
            publish_all.main(args)
    assert exc.value.code == 0
    require.assert_not_called()


@pytest.mark.parametrize("payway", ["wechat", "alipay"])
def test_activation_with_explicit_payment_does_not_check_license_or_publish(payway):
    with patch("publish.orchestrator.run_activation", return_value=0) as activate, \
         patch("publish.orchestrator.require_valid_license") as require, \
         patch("publish.orchestrator.run_publish", new=AsyncMock()) as publish:
        assert publish_all.main(["--activate", "--pay-with", payway]) == 0
    activate.assert_called_once_with(payway)
    require.assert_not_called()
    publish.assert_not_awaited()


def test_noninteractive_activation_without_payment_has_stable_error():
    stderr = io.StringIO()
    with patch("publish.orchestrator.sys.stdin.isatty", return_value=False), \
         patch("publish.orchestrator.run_activation") as activate, \
         contextlib.redirect_stderr(stderr):
        code = publish_all.main(["--activate"])
    assert code == EXIT_LICENSE_ERROR
    assert stderr.getvalue() == (
        "[opub] LIC-001: 非交互激活必须指定支付方式。建议: "
        "使用 --activate --pay-with wechat 或 alipay\n"
    )
    activate.assert_not_called()


@pytest.mark.parametrize("selection,payway", [("1", "wechat"), ("2", "alipay")])
def test_interactive_activation_prompts_for_payment(selection, payway):
    with patch("publish.orchestrator.sys.stdin.isatty", return_value=True), \
         patch("builtins.input", return_value=selection) as prompt, \
         patch("publish.orchestrator.run_activation", return_value=0) as activate:
        assert publish_all.main(["--activate"]) == 0
    prompt.assert_called_once_with("选择支付方式 [1=微信, 2=支付宝]: ")
    activate.assert_called_once_with(payway)


def test_interactive_activation_rejects_invalid_selection():
    stderr = io.StringIO()
    with patch("publish.orchestrator.sys.stdin.isatty", return_value=True), \
         patch("builtins.input", return_value="3"), \
         patch("publish.orchestrator.run_activation") as activate, \
         contextlib.redirect_stderr(stderr):
        code = publish_all.main(["--activate"])
    assert code == EXIT_LICENSE_ERROR
    assert "LIC-001" in stderr.getvalue()
    activate.assert_not_called()


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["--platforms", "weibo"],
        ["--platforms", "weibo", "--video", "/secret/video.mp4", "--title", "t"],
        ["--platforms", "xiaohongshu", "--note", "--images", "/secret/a.png", "--title", "t"],
    ],
)
def test_unlicensed_publish_always_has_stable_license_error(argv):
    stderr = io.StringIO()
    with patch("publish.orchestrator.require_valid_license", return_value=(False, "LIC-001")), \
         contextlib.redirect_stderr(stderr):
        code = publish_all.main(argv)
    assert code == EXIT_LICENSE_ERROR
    assert "[opub] LIC-001:" in stderr.getvalue()


def test_unlicensed_publish_stops_before_overrides_cookies_runtime_or_asset_access():
    with patch("publish.orchestrator.require_valid_license", return_value=(False, "LIC-001")), \
         patch("publish.orchestrator._build_overrides") as overrides, \
         patch("publish.orchestrator.default_params_from_overrides") as defaults, \
         patch("publish.config._discover_account_files") as cookies, \
         patch("publish.orchestrator.runtime_preflight", new=AsyncMock()) as preflight, \
         patch("publish.orchestrator.get_video_files") as assets, \
         patch("publish.orchestrator.ensure_account_login", new=AsyncMock()) as browser, \
         patch("publish.orchestrator.publish_to_platform", new=AsyncMock()) as upload, \
         patch("publish.orchestrator.run_publish", new=AsyncMock()) as publish:
        code = publish_all.main(
            ["--platforms", "weibo", "--video", "/secret/video.mp4", "--title", "t"]
        )
    assert code == EXIT_LICENSE_ERROR
    overrides.assert_not_called()
    defaults.assert_not_called()
    cookies.assert_not_called()
    preflight.assert_not_awaited()
    assets.assert_not_called()
    browser.assert_not_awaited()
    upload.assert_not_awaited()
    publish.assert_not_awaited()


def test_valid_license_enters_existing_publish_flow_without_license_network():
    with patch("publish.orchestrator.require_valid_license", return_value=(True, None)), \
         patch("publish.orchestrator.run_publish", new=AsyncMock(return_value=0)) as publish, \
         patch("requests.Session.request", side_effect=AssertionError("network called")):
        code = publish_all.main(
            ["--platforms", "weibo", "--video", "v.mp4", "--title", "t"]
        )
    assert code == 0
    assert publish.await_args.args[0].video == "v.mp4"


def test_print_license_error_uses_stable_public_text_without_internal_details():
    stderr = io.StringIO()
    with contextlib.redirect_stderr(stderr):
        print_license_error("LIC-011")
    assert stderr.getvalue() == (
        "[opub] LIC-011: 激活服务不可用。建议: 检查网络后稍后重试\n"
    )
    assert "token" not in stderr.getvalue().lower()


def test_require_valid_license_builds_fingerprint_before_checking_file(tmp_path):
    order = []
    with patch("publish.licensing.build_device_hash", side_effect=lambda: order.append("fingerprint") or "a" * 64), \
         patch("publish.licensing.license_path", side_effect=lambda base: order.append("path") or tmp_path / "missing.json"):
        assert require_valid_license(tmp_path) == (False, "LIC-001")
    assert order == ["fingerprint", "path"]


def test_require_valid_license_maps_fingerprint_failure_to_lic004(tmp_path):
    with patch("publish.licensing.build_device_hash", side_effect=DeviceFingerprintError("secret uuid")):
        assert require_valid_license(tmp_path) == (False, "LIC-004")


def test_require_valid_license_accepts_signed_license_fully_offline(tmp_path):
    document, keys = _signed_document()
    deployment = SimpleNamespace(TRUSTED_PUBLIC_KEYS=keys)
    (tmp_path / "license.json").write_text(json.dumps(document), encoding="utf-8")
    with patch.dict(sys.modules, {"publish.licensing.deployment": deployment}), \
         patch("publish.licensing.build_device_hash", return_value="a" * 64), \
         patch("requests.Session.request", side_effect=AssertionError("network called")):
        assert require_valid_license(tmp_path) == (True, None)


@pytest.mark.parametrize(
    "device_hash,document_device,expected",
    [("a" * 64, "b" * 64, "LIC-003"), ("a" * 64, "a" * 64, "LIC-002")],
)
def test_require_valid_license_preserves_stable_validation_codes(
    tmp_path, device_hash, document_device, expected
):
    document, keys = _signed_document(document_device)
    if expected == "LIC-002":
        document["signature"] = "damaged"
    (tmp_path / "license.json").write_text(json.dumps(document), encoding="utf-8")
    with patch("publish.licensing.build_device_hash", return_value=device_hash):
        assert require_valid_license(tmp_path, keys) == (False, expected)


def test_require_valid_license_maps_unreadable_or_malformed_file_to_lic002(tmp_path):
    (tmp_path / "license.json").write_text("not-json", encoding="utf-8")
    with patch("publish.licensing.build_device_hash", return_value="a" * 64):
        assert require_valid_license(tmp_path, {"test": "unused"}) == (False, "LIC-002")


def test_require_valid_license_maps_path_io_failure_to_lic002(tmp_path):
    with patch("publish.licensing.build_device_hash", return_value="a" * 64), \
         patch("publish.licensing.license_path", side_effect=PermissionError("/private/license")):
        assert require_valid_license(tmp_path) == (False, "LIC-002")


@pytest.mark.parametrize("valid,code,expected", [(True, None, EXIT_OK), (False, "LIC-001", EXIT_LICENSE_ERROR), (False, "LIC-002", EXIT_LICENSE_ERROR), (False, "LIC-003", EXIT_LICENSE_ERROR), (False, "LIC-004", EXIT_LICENSE_ERROR)])
def test_show_license_status_reports_all_validation_states(valid, code, expected):
    stdout, stderr = io.StringIO(), io.StringIO()
    with patch("publish.licensing.require_valid_license", return_value=(valid, code)), \
         contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        result = show_license_status()
    assert result == expected
    if valid:
        assert "许可证有效" in stdout.getvalue()
        assert stderr.getvalue() == ""
    else:
        assert code in stderr.getvalue()
        assert stdout.getvalue() == ""


def test_run_activation_lazily_loads_deployment_and_passes_client_version():
    document, keys = _signed_document("d" * 64)
    deployment = SimpleNamespace(
        LICENSE_API_BASE_URL="https://license.example.test",
        TRUSTED_PUBLIC_KEYS=keys,
    )
    api = object()
    with patch.dict(sys.modules, {"publish.licensing.deployment": deployment}), \
         patch("publish.licensing.build_device_hash", return_value="d" * 64), \
         patch("publish.licensing.version", return_value="1.2.3"), \
         patch("publish.licensing.LicenseApi", return_value=api) as api_cls, \
         patch("publish.licensing.data_dir", return_value="/safe/data"), \
         patch("publish.licensing.activate", return_value=0) as activate:
        assert run_activation("OPUB0-01234-56789-ABCDE-FGHJK-MNPQR-STVWX") == 0
    api_cls.assert_called_once_with("https://license.example.test")
    args, kwargs = activate.call_args
    assert args[:4] == (
        "OPUB0-01234-56789-ABCDE-FGHJK-MNPQR-STVWX",
        "d" * 64,
        api,
        "/safe/data",
    )
    assert kwargs == {"client_version": "1.2.3"}
    args[4](document, "d" * 64)


def test_run_activation_uses_major_zero_fallback_version_when_uninstalled():
    deployment = SimpleNamespace(
        LICENSE_API_BASE_URL="https://license.example.test",
        TRUSTED_PUBLIC_KEYS={"prod": "public"},
    )
    with patch.dict(sys.modules, {"publish.licensing.deployment": deployment}), \
         patch("publish.licensing.build_device_hash", return_value="d" * 64), \
         patch("publish.licensing.version", side_effect=PackageNotFoundError), \
         patch("publish.licensing.LicenseApi", return_value=object()), \
         patch("publish.licensing.data_dir", return_value="/safe/data"), \
         patch("publish.licensing.activate", return_value=0) as activate:
        assert run_activation("OPUB0-01234-56789-ABCDE-FGHJK-MNPQR-STVWX") == 0

    assert activate.call_args.kwargs == {"client_version": "0.8.0.dev0"}


@pytest.mark.parametrize("service_code", ["LIC-013", "LIC-014", "LIC-015"])
def test_run_activation_preserves_public_activation_service_codes(service_code):
    deployment = SimpleNamespace(
        LICENSE_API_BASE_URL="https://license.example.test",
        TRUSTED_PUBLIC_KEYS={"prod": "public"},
    )
    stderr = io.StringIO()
    with patch.dict(sys.modules, {"publish.licensing.deployment": deployment}), \
         patch("publish.licensing.build_device_hash", return_value="d" * 64), \
         patch("publish.licensing.LicenseApi", return_value=object()), \
         patch("publish.licensing.activate", side_effect=ActivationServiceError(service_code)), \
         contextlib.redirect_stderr(stderr):
        result = run_activation("OPUB0-01234-56789-ABCDE-FGHJK-MNPQR-STVWX")

    assert result == EXIT_LICENSE_ERROR
    assert service_code in stderr.getvalue()


@pytest.mark.parametrize(
    "failure,code",
    [
        (DeviceFingerprintError("private uuid"), "LIC-004"),
        (ActivationServiceError("bearer secret"), "LIC-011"),
        (ActivationError("LIC-010", "private order"), "LIC-010"),
        (LicenseValidationError("LIC-003", "private device"), "LIC-003"),
        (OSError("/private/path/license.json"), "LIC-011"),
    ],
)
def test_run_activation_maps_failures_without_leaking_internal_values(failure, code):
    deployment = SimpleNamespace(
        LICENSE_API_BASE_URL="https://license.example.test",
        TRUSTED_PUBLIC_KEYS={"prod": "public"},
    )
    stderr = io.StringIO()
    with patch.dict(sys.modules, {"publish.licensing.deployment": deployment}), \
         patch("publish.licensing.build_device_hash", side_effect=failure), \
         contextlib.redirect_stderr(stderr):
        result = run_activation("OPUB0-01234-56789-ABCDE-FGHJK-MNPQR-STVWX")
    assert result == EXIT_LICENSE_ERROR
    assert code in stderr.getvalue()
    assert str(failure) not in stderr.getvalue()


def test_run_activation_maps_unexpected_checkout_failure_without_leaking_details(tmp_path):
    deployment = SimpleNamespace(
        LICENSE_API_BASE_URL="https://license.example.test",
        TRUSTED_PUBLIC_KEYS={"prod": "public"},
    )
    failure = RuntimeError("secret checkout URL")
    stderr = io.StringIO()
    with patch.dict(sys.modules, {"publish.licensing.deployment": deployment}), \
         patch("publish.licensing.build_device_hash", return_value="d" * 64), \
         patch("publish.licensing.LicenseApi", return_value=object()), \
         patch("publish.licensing.data_dir", return_value=tmp_path), \
         patch("publish.licensing.activate", side_effect=failure), \
         contextlib.redirect_stderr(stderr):
        result = run_activation("OPUB0-01234-56789-ABCDE-FGHJK-MNPQR-STVWX")
    assert result == EXIT_LICENSE_ERROR
    assert "LIC-011" in stderr.getvalue()
    assert str(failure) not in stderr.getvalue()
