"""Exception hierarchy for ydpy."""

__all__ = [
    'YdpyException',
    'InvalidVideoIdentifierException',
    'RequestException',
    'DataParsingException',
    'ExtractionException',
    'DownloadException',
    'ThrottledDownload',
]


class YdpyException(Exception):
    """Base error for all ydpy failures."""


class InvalidVideoIdentifierException(ValueError):
    """Raised when a value cannot be interpreted as a YouTube video identifier."""


class RequestException(YdpyException):
    """Raised when an HTTP request fails or returns an unexpected status."""


class DataParsingException(YdpyException):
    """Raised when a YouTube response field cannot be parsed."""


class ExtractionException(YdpyException):
    """Raised when a player response cannot be parsed or targets another video."""


class DownloadException(YdpyException):
    """Raised when a stream download fails."""


class ThrottledDownload(DownloadException):
    """Raised when the download speed stays under the throttle limit for too long."""
