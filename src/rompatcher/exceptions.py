class RomPatcherError(Exception):
    """Base class for project-specific errors."""


class PatchFormatError(RomPatcherError):
    """Raised when a patch cannot be parsed."""


class UnsupportedPatchFormatError(RomPatcherError):
    """Raised when a patch format is not supported."""


class ChecksumMismatchError(RomPatcherError):
    """Raised when a source or target checksum does not match the patch."""


class DependencyMissingError(RomPatcherError):
    """Raised when an optional dependency is required but missing."""
