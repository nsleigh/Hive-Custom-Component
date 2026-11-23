"""Hive exception class."""

# pylint: skip-file


class FileInUse(Exception):
    """File in use exception.

    Args:
        Exception (object): Exception object to invoke
    """


class NoApiToken(Exception):
    """No API token exception.

    Args:
        Exception (object): Exception object to invoke
    """


class HiveApiError(Exception):
    """Api error.

    Args:
        Exception (object): Exception object to invoke
    """


class HiveConnectionError(HiveApiError):
    """Hive could not be reached (timeout or network error).

    The failure is expected to be transient, so callers can retry.

    Args:
        HiveApiError (object): Parent API error class
    """


class HiveAuthError(HiveApiError):
    """Auth error (401/403) — token may be expired or invalid.

    Args:
        HiveApiError (object): Parent API error class
    """


class HiveRefreshTokenExpired(Exception):
    """Refresh token expired.

    Args:
        Exception (object): Exception object to invoke
    """


class HiveReauthRequired(Exception):
    """Re-Authentication is required.

    Args:
        Exception (object): Exception object to invoke
    """


class HiveUnknownConfiguration(Exception):
    """Unknown Hive Configuration.

    Args:
        Exception (object): Exception object to invoke
    """


class HiveInvalidUsername(Exception):
    """Raise invalid Username.

    Args:
        Exception (object): Exception object to invoke
    """


class HiveInvalidPassword(Exception):
    """Raise invalid password.

    Args:
        Exception (object): Exception object to invoke
    """


class HiveInvalid2FACode(Exception):
    """Raise invalid 2FA code.

    Args:
        Exception (object): Exception object to invoke
    """


class HiveInvalidDeviceAuthentication(Exception):
    """Raise invalid device authentication.

    Args:
        Exception (object): Exception object to invoke
    """


class HiveFailedToRefreshTokens(Exception):
    """Raise invalid refresh tokens.

    Args:
        Exception (object): Exception object to invoke
    """
