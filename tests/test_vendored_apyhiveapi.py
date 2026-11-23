"""Tests for the fixes carried in the bundled 1.0.x apyhiveapi.

The other tests mock the library out entirely, so these exercise it directly.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.hive.apyhiveapi import Hive
from custom_components.hive.apyhiveapi.api.hive_async_api import HiveApiAsync
from custom_components.hive.apyhiveapi.api.hive_auth import HiveAuth
from custom_components.hive.apyhiveapi.api.hive_auth_async import HiveAuthAsync
from custom_components.hive.apyhiveapi.helper.hive_exceptions import (
    HiveApiError,
    HiveConnectionError,
    HiveInvalidPassword,
    HiveReauthRequired,
)
import pytest

TOKENS = {"token": "id", "refreshToken": "refresh", "accessToken": "access"}
CONFIG = {"tokens": TOKENS, "username": "user@example.com", "password": "pw"}
LOGIN_INFO = {"UPID": "eu-west-1_pool", "CLIID": "client", "REGION": "eu-west-1_pool"}


@pytest.fixture(autouse=True)
def no_sso_page():
    """The sync HiveAuth fetches the SSO page when created; skip that."""
    with patch("custom_components.hive.apyhiveapi.api.hive_auth.HiveApi") as hive_api:
        hive_api.return_value.getLoginInfo.return_value = LOGIN_INFO
        yield


def test_connection_error_is_an_api_error() -> None:
    """Existing `except HiveApiError` handlers still catch it."""
    assert issubclass(HiveConnectionError, HiveApiError)


@pytest.mark.parametrize("auth_class", [HiveAuthAsync, HiveAuth])
async def test_username_is_normalised(auth_class: type) -> None:
    """A capitalised or padded email still logs in (Pyhive #179)."""
    auth = auth_class(" User@Example.COM ", "pw")
    assert auth.username == "user@example.com"

    auth.username = "Other@Example.com"
    assert auth.username == "other@example.com"


@pytest.mark.parametrize("auth_class", [HiveAuthAsync, HiveAuth])
async def test_file_mode_username_is_normalised(auth_class: type) -> None:
    """File mode is detected however the address is typed (Pyhive #187)."""
    assert auth_class("Use@File.com", "pw").use_file is True

    hive = Hive(websession=MagicMock())
    await hive.session.useFile(" USE@file.com ")
    assert hive.session.config.file is True


async def test_start_session_failed_fetch_retries() -> None:
    """A failed first fetch is a connection problem, not a reauth."""
    hive = Hive(websession=MagicMock())
    with (
        patch.object(hive.session, "getDevices", AsyncMock(return_value=False)),
        pytest.raises(HiveConnectionError),
    ):
        await hive.session.startSession(dict(CONFIG))


async def test_start_session_empty_account_needs_reauth() -> None:
    """A successful fetch with no devices still asks for reauth."""
    hive = Hive(websession=MagicMock())
    with (
        patch.object(hive.session, "getDevices", AsyncMock(return_value=True)),
        pytest.raises(HiveReauthRequired),
    ):
        await hive.session.startSession(dict(CONFIG))


async def test_retry_login_unreachable_raises_connection_error() -> None:
    """Login retries that can't reach Hive don't turn into a reauth."""
    hive = Hive(websession=MagicMock())
    with (
        patch.object(
            hive.session, "login", AsyncMock(side_effect=HiveConnectionError)
        ) as login,
        patch("asyncio.sleep", AsyncMock()),
        pytest.raises(HiveConnectionError),
    ):
        await hive.session._retryLogin()
    assert login.await_count == 3


async def test_retry_login_bad_password_needs_reauth() -> None:
    """Rejected credentials still start a reauth."""
    hive = Hive(websession=MagicMock())
    with (
        patch.object(hive.session, "login", AsyncMock(side_effect=HiveInvalidPassword)),
        pytest.raises(HiveReauthRequired),
    ):
        await hive.session._retryLogin()


async def test_set_state_timeout_returns_failure() -> None:
    """A timed-out setState reports failure instead of raising HTTPError."""
    session = MagicMock()
    session.config.file = False
    api = HiveApiAsync(hiveSession=session, websession=MagicMock())
    with patch.object(api, "request", AsyncMock(side_effect=TimeoutError)):
        resp = await api.setState("heating", "node", target=20)
    assert resp == {"original": "timeout", "parsed": None}


async def test_set_target_temperature_timeout_returns_false() -> None:
    """The device call returns False, so a multi-entity service carries on."""
    hive = Hive(websession=MagicMock())
    hive.session.data.products = {"node": {"type": "heating"}}
    device = {
        "hiveID": "node",
        "haName": "Heating",
        "deviceData": {"online": True},
    }
    with (
        patch.object(hive.session, "hiveRefreshTokens", AsyncMock()),
        patch.object(hive.session.api, "request", AsyncMock(side_effect=TimeoutError)),
    ):
        assert await hive.heating.setTargetTemperature(device, 20) is False
