"""orcalayer — Python client for the OrcaLayer API (https://orcalayer.com)."""

from .client import OrcaLayer
from .errors import (
    AuthenticationError,
    OrcaLayerError,
    PremiumRequiredError,
    RateLimitError,
    ServerError,
    WalletComputingError,
)

__version__ = "0.1.0"

__all__ = [
    "OrcaLayer",
    "OrcaLayerError",
    "PremiumRequiredError",
    "AuthenticationError",
    "RateLimitError",
    "ServerError",
    "WalletComputingError",
    "__version__",
]
