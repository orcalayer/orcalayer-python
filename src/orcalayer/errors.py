"""Exception types raised by the OrcaLayer client."""

PRICING_URL = "https://orcalayer.com/pricing"


class OrcaLayerError(Exception):
    """Base class for all OrcaLayer client errors."""


class PremiumRequiredError(OrcaLayerError):
    """A Premium endpoint was called without an API key."""

    def __init__(self, endpoint: str):
        super().__init__(
            f"'{endpoint}' is a Premium endpoint and requires an API key. "
            f"Create one at {PRICING_URL} and pass it as "
            f"OrcaLayer(api_key=\"...\")."
        )
        self.endpoint = endpoint


class AuthenticationError(OrcaLayerError):
    """The API key was rejected (HTTP 401/403)."""

    def __init__(self, status_code: int, detail: str = ""):
        msg = f"API key rejected (HTTP {status_code})."
        if detail:
            msg += f" Server said: {detail}"
        msg += f" Check your key at https://orcalayer.com/settings or get one at {PRICING_URL}."
        super().__init__(msg)
        self.status_code = status_code


class RateLimitError(OrcaLayerError):
    """Rate limit still exceeded after all retries (HTTP 429)."""

    def __init__(self, retry_after: float, detail: str = ""):
        msg = f"Rate limit exceeded; retry after {retry_after:.0f}s."
        if detail:
            msg += f" Server said: {detail}"
        super().__init__(msg)
        self.retry_after = retry_after


class ServerError(OrcaLayerError):
    """The API returned an unexpected 5xx response."""

    def __init__(self, status_code: int, detail: str = ""):
        msg = f"OrcaLayer API server error (HTTP {status_code})."
        if detail:
            msg += f" Body: {detail[:200]}"
        super().__init__(msg)
        self.status_code = status_code
