"""
I define exceptions used in the model implementation.
"""

class ModelError(Exception):
    """
    Integrity constraints of the Advene model have been violated.
    """
    pass

class NoClaimingError(Exception):
    """Raised whenever no backend nor parser claims a package URL."""
    pass

class NoSuchElementError(KeyError):
    """Raised whenever an element cannot be found in a package."""
    pass

class UnreachableImportError(KeyError):
    """Raised whenever an element from an unreachable import is sought."""
    pass

