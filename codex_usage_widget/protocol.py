"""Build the ordered Codex app-server handshake messages."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codex_usage_widget.parser import JsonValue


class RpcStage(StrEnum):
    """Handshake stage associated with an RPC outcome."""

    INITIALIZE = "initialize"
    ACCOUNT = "account"
    RATE_LIMITS = "rate_limits"


@dataclass(frozen=True, slots=True)
class RpcRequest:
    """One response-bearing request and messages sent before waiting for it."""

    request_id: int
    messages: tuple[JsonValue, ...]


def request_for(stage: RpcStage) -> RpcRequest:
    """Build the schema-valid messages for one handshake stage."""
    match stage:
        case RpcStage.INITIALIZE:
            return RpcRequest(
                request_id=1,
                messages=(
                    {
                        "method": "initialize",
                        "id": 1,
                        "params": {
                            "clientInfo": {
                                "name": "codex-usage-widget",
                                "title": "Codex Usage Widget",
                                "version": "0.1.0",
                            },
                            "capabilities": {"experimentalApi": True},
                        },
                    },
                ),
            )
        case RpcStage.ACCOUNT:
            return RpcRequest(
                request_id=2,
                messages=(
                    {"method": "initialized"},
                    {
                        "method": "account/read",
                        "id": 2,
                        "params": {"refreshToken": False},
                    },
                ),
            )
        case RpcStage.RATE_LIMITS:
            return RpcRequest(
                request_id=3,
                messages=(
                    {
                        "method": "account/rateLimits/read",
                        "id": 3,
                        "params": None,
                    },
                ),
            )
