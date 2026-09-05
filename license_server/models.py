from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Literal


Payway = Literal["wechat", "alipay"]


@dataclass(frozen=True)
class Checkout:
    kind: Literal["url", "html"]
    value: str


@dataclass(frozen=True)
class ProviderOrder:
    order_id: str
    state: int
    amount: int
    description: str
    charge_id: str
    payway: int
    raw: Dict[str, Any]
