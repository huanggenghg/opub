from __future__ import annotations

import pytest

from publish.licensing.codes import ActivationCodeFormatError, normalize_activation_code


def test_normalize_activation_code_accepts_lowercase_display_form() -> None:
    displayed = "  opub0-01234-56789-abcde-fghjk-mnpqr-stvwx  "

    assert normalize_activation_code(displayed) == "OPUB00123456789ABCDEFGHJKMNPQRSTVWX"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "OPUB1-01234-56789-ABCDE-FGHJK-MNPQR-STVWX",
        "OPUB0-01234-56789-ABODE-FGHJK-MNPQR-STVWX",
        "OPUB0-01234-56789-ABCDE-FGHJK-MNPQR-\u017fTVWX",
        "../../OPUB0-01234-56789-ABCDE-FGHJK-MNPQR-STVWX",
        "OPUB0-01234-56789-ABCDE-FGHJK-MNPQR-STVWXYZZ",
        "OPUB0-012345-6789A-BCDEF-GHJKM-NPQRS-TVWXYZ",
        None,
        123,
    ],
)
def test_normalize_activation_code_rejects_invalid_values(value: object) -> None:
    with pytest.raises(ActivationCodeFormatError, match="^invalid activation code$"):
        normalize_activation_code(value)
