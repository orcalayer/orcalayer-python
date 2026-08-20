"""orcalayer — Python client for the OrcaLayer API (https://orcalayer.com)."""

from ._version import __version__
from .client import OrcaLayer
from .errors import (
    APIError,
    AuthenticationError,
    OrcaLayerError,
    PremiumRequiredError,
    RateLimitError,
    ServerError,
    WalletComputingError,
)

__all__ = [
    "APIError",
    "AuthenticationError",
    "OrcaLayer",
    "OrcaLayerError",
    "PremiumRequiredError",
    "RateLimitError",
    "ServerError",
    "WalletComputingError",
    "__version__",
]
