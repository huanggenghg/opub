from pathlib import Path

import pytest

from license_server.config import Settings


VALID_PRIVATE_KEY_B64 = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
INVALID_PRIVATE_KEY_B64 = "not-base64"
SHORT_PRIVATE_KEY_B64 = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=="
LONG_PRIVATE_KEY_B64 = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"


def _valid_env() -> dict[str, str]:
    return {
        "OPUB_PUBLIC_BASE_URL": "https://example.com/license",
        "OPUB_LICENSE_PRIVATE_KEY": VALID_PRIVATE_KEY_B64,
        "OPUB_LICENSE_KEY_ID": "key-id",
        "OPUB_LICENSE_DB_PATH": "/tmp/licenses.db",
    }


def test_settings_defaults_are_fixed() -> None:
    settings = Settings(
        public_base_url="https://example.com",
        license_private_key=VALID_PRIVATE_KEY_B64,
        license_key_id="key-id",
        database_path=Path("/tmp/licenses.db"),
    )

    assert settings.product_id == "opub-major-0"
    assert settings.product_name == "opub 0.x 创始版"
    assert settings.price_fen == 990
    assert not hasattr(settings, "mbd_app_id")
    assert not hasattr(settings, "mbd_app_key")
    assert not hasattr(settings, "payment_return_url")


def test_public_base_url_requires_https() -> None:
    with pytest.raises(ValueError, match="OPUB_PUBLIC_BASE_URL"):
        Settings.from_env(
            {
                "OPUB_PUBLIC_BASE_URL": "http://example.com",
                "OPUB_LICENSE_PRIVATE_KEY": VALID_PRIVATE_KEY_B64,
                "OPUB_LICENSE_KEY_ID": "key-id",
                "OPUB_LICENSE_DB_PATH": "/tmp/licenses.db",
            }
        )


@pytest.mark.parametrize(
    "missing_name",
    [
        "OPUB_PUBLIC_BASE_URL",
        "OPUB_LICENSE_PRIVATE_KEY",
        "OPUB_LICENSE_KEY_ID",
        "OPUB_LICENSE_DB_PATH",
    ],
)
def test_missing_required_config_is_reported(missing_name: str) -> None:
    env = _valid_env()
    env.pop(missing_name)

    with pytest.raises(ValueError, match=missing_name):
        Settings.from_env(env)


@pytest.mark.parametrize("field_name", [
    "OPUB_PUBLIC_BASE_URL",
    "OPUB_LICENSE_PRIVATE_KEY",
    "OPUB_LICENSE_KEY_ID",
    "OPUB_LICENSE_DB_PATH",
])
@pytest.mark.parametrize("field_value", ["", "   "])
def test_empty_and_whitespace_values_are_missing(field_name: str, field_value: str) -> None:
    env = _valid_env()
    env[field_name] = field_value

    with pytest.raises(ValueError, match=field_name):
        Settings.from_env(env)


def test_absent_and_empty_values_are_reported_together() -> None:
    env = _valid_env()
    env.pop("OPUB_PUBLIC_BASE_URL")
    env.pop("OPUB_LICENSE_PRIVATE_KEY")
    env["OPUB_LICENSE_KEY_ID"] = "   "

    with pytest.raises(ValueError) as exc_info:
        Settings.from_env(env)

    message = str(exc_info.value)
    assert "OPUB_PUBLIC_BASE_URL" in message
    assert "OPUB_LICENSE_PRIVATE_KEY" in message
    assert "OPUB_LICENSE_KEY_ID" in message


@pytest.mark.parametrize("bad_url", ["https://?x", "https://#x"])
def test_public_base_url_rejects_empty_host(bad_url: str) -> None:
    env = _valid_env()
    env["OPUB_PUBLIC_BASE_URL"] = bad_url

    with pytest.raises(ValueError, match="OPUB_PUBLIC_BASE_URL"):
        Settings.from_env(env)


def test_public_base_url_rejects_credentials_and_query() -> None:
    for bad_url in [
        "https://user:pass@example.com/license",
        "https://example.com/license?x=1",
        "https://example.com/license#x",
    ]:
        env = _valid_env()
        env["OPUB_PUBLIC_BASE_URL"] = bad_url

        with pytest.raises(ValueError, match="OPUB_PUBLIC_BASE_URL"):
            Settings.from_env(env)


def test_public_base_url_accepts_valid_https_host_and_path() -> None:
    env = _valid_env()
    env["OPUB_PUBLIC_BASE_URL"] = "https://example.com/license/v1/"
    settings = Settings.from_env(env)

    assert settings.public_base_url == "https://example.com/license/v1"


def test_private_key_must_be_valid_base64_32_byte_ed25519_seed() -> None:
    for bad_key in [INVALID_PRIVATE_KEY_B64, SHORT_PRIVATE_KEY_B64, LONG_PRIVATE_KEY_B64]:
        env = _valid_env()
        env["OPUB_LICENSE_PRIVATE_KEY"] = bad_key

        with pytest.raises(ValueError, match="OPUB_LICENSE_PRIVATE_KEY"):
            Settings.from_env(env)
