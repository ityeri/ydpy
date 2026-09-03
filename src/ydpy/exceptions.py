"""Exception hierarchy for ydpy."""

__all__ = [
    'YdpyException',
    'InvalidVideoIdentifierException',
    'RequestException',
    'ExtractionException',
]


class YdpyException(Exception):
    """Base error for all ydpy failures."""


class InvalidVideoIdentifierException(ValueError):
    """Raised when a value cannot be interpreted as a YouTube video identifier."""


class RequestException(YdpyException):
    """Raised when an HTTP request fails or returns an unexpected status."""


class ExtractionException(YdpyException):
    """Raised when a YouTube response cannot be parsed or targets another video."""
