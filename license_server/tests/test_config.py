from pathlib import Path

import pytest

from license_server.config import Settings


def test_settings_defaults_are_fixed() -> None:
    settings = Settings(
        public_base_url="https://example.com",
        payment_return_url="https://example.com/return",
        mbd_app_id="app-id",
        mbd_app_key="app-key",
        license_private_key="private-key",
        license_key_id="key-id",
        database_path=Path("/tmp/licenses.db"),
    )

    assert settings.product_id == "opub-lifetime-v1"
    assert settings.product_name == "opub 永久设备许可证"
    assert settings.price_fen == 990


def test_public_base_url_requires_https() -> None:
    with pytest.raises(ValueError, match="OPUB_PUBLIC_BASE_URL"):
        Settings.from_env(
            {
                "OPUB_PUBLIC_BASE_URL": "http://example.com",
                "OPUB_PAYMENT_RETURN_URL": "https://example.com/return",
                "OPUB_MBD_APP_ID": "app-id",
                "OPUB_MBD_APP_KEY": "app-key",
                "OPUB_LICENSE_PRIVATE_KEY": "private-key",
                "OPUB_LICENSE_KEY_ID": "key-id",
                "OPUB_LICENSE_DB_PATH": "/tmp/licenses.db",
            }
        )


def test_payment_return_url_requires_https() -> None:
    with pytest.raises(ValueError, match="OPUB_PAYMENT_RETURN_URL"):
        Settings.from_env(
            {
                "OPUB_PUBLIC_BASE_URL": "https://example.com",
                "OPUB_PAYMENT_RETURN_URL": "http://example.com/return",
                "OPUB_MBD_APP_ID": "app-id",
                "OPUB_MBD_APP_KEY": "app-key",
                "OPUB_LICENSE_PRIVATE_KEY": "private-key",
                "OPUB_LICENSE_KEY_ID": "key-id",
                "OPUB_LICENSE_DB_PATH": "/tmp/licenses.db",
            }
        )


@pytest.mark.parametrize(
    "missing_name",
    [
        "OPUB_PUBLIC_BASE_URL",
        "OPUB_PAYMENT_RETURN_URL",
        "OPUB_MBD_APP_ID",
        "OPUB_MBD_APP_KEY",
        "OPUB_LICENSE_PRIVATE_KEY",
        "OPUB_LICENSE_KEY_ID",
        "OPUB_LICENSE_DB_PATH",
    ],
)
def test_missing_required_config_is_reported(missing_name: str) -> None:
    env = {
        "OPUB_PUBLIC_BASE_URL": "https://example.com",
        "OPUB_PAYMENT_RETURN_URL": "https://example.com/return",
        "OPUB_MBD_APP_ID": "app-id",
        "OPUB_MBD_APP_KEY": "app-key",
        "OPUB_LICENSE_PRIVATE_KEY": "private-key",
        "OPUB_LICENSE_KEY_ID": "key-id",
        "OPUB_LICENSE_DB_PATH": "/tmp/licenses.db",
    }
    env.pop(missing_name)

    with pytest.raises(ValueError, match=missing_name):
        Settings.from_env(env)


def test_trailing_slash_is_normalized_from_public_url() -> None:
    settings = Settings.from_env(
        {
            "OPUB_PUBLIC_BASE_URL": "https://example.com/",
            "OPUB_PAYMENT_RETURN_URL": "https://example.com/return",
            "OPUB_MBD_APP_ID": "app-id",
            "OPUB_MBD_APP_KEY": "app-key",
            "OPUB_LICENSE_PRIVATE_KEY": "private-key",
            "OPUB_LICENSE_KEY_ID": "key-id",
            "OPUB_LICENSE_DB_PATH": "/tmp/licenses.db",
        }
    )

    assert settings.public_base_url == "https://example.com"
