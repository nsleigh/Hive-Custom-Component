"""Support for the Hive devices and services."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Coroutine
from functools import wraps
import logging
from typing import Any, Concatenate

from aiohttp.web_exceptions import HTTPException
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryNotReady,
    HomeAssistantError,
)
from homeassistant.helpers import aiohttp_client, config_validation as cv, device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .apyhiveapi import Auth, Hive
from .apyhiveapi.helper.hive_exceptions import (
    HiveApiError,
    HiveReauthRequired,
    HiveUnknownConfiguration,
)
from .const import (
    DOMAIN,
    PLATFORM_LOOKUP,
    PLATFORMS,
    SERVICE_CANCEL_HOLIDAY_MODE,
    SERVICE_SET_HOLIDAY_MODE,
)
from .entity import HiveEntity

_LOGGER = logging.getLogger(__name__)

type HiveConfigEntry = ConfigEntry[Hive]

SET_HOLIDAY_MODE_SCHEMA = vol.Schema(
    {
        vol.Required("start"): cv.datetime,
        vol.Required("end"): cv.datetime,
        vol.Required("temperature"): vol.All(
            vol.Coerce(float), vol.Range(min=7, max=35)
        ),
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: HiveConfigEntry) -> bool:
    """Set up Hive from a config entry."""
    web_session = aiohttp_client.async_get_clientsession(hass)
    hive_config = dict(entry.data)
    hive = Hive(web_session)

    hive_config["options"] = {}
    hive_config["options"].update(
        {CONF_SCAN_INTERVAL: dict(entry.options).get(CONF_SCAN_INTERVAL, 120)}
    )
    entry.runtime_data = hive

    try:
        devices = await hive.session.startSession(hive_config)
    except HTTPException as error:
        _LOGGER.error("Could not connect to the internet: %s", error)
        raise ConfigEntryNotReady from error
    except HiveUnknownConfiguration as error:
        # Raised when the Hive API returns no devices/products, which also
        # happens on a transient timeout during a cold boot (no cached data
        # yet to fall back on). Treat as retryable rather than a hard error
        # so HA's automatic setup-retry backoff picks it up.
        _LOGGER.error("Hive API returned no devices: %s", error)
        raise ConfigEntryNotReady from error
    except HiveReauthRequired as err:
        raise ConfigEntryAuthFailed from err

    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, devices["parent"][0]["device_id"])},
        name=devices["parent"][0]["hiveName"],
        model=devices["parent"][0]["deviceData"]["model"],
        sw_version=devices["parent"][0]["deviceData"]["version"],
        manufacturer=devices["parent"][0]["deviceData"]["manufacturer"],
    )

    await hass.config_entries.async_forward_entry_setups(
        entry,
        [
            ha_type
            for ha_type, hive_type in PLATFORM_LOOKUP.items()
            if devices.get(hive_type)
        ],
    )

    async def _async_set_holiday_mode(call: ServiceCall) -> None:
        """Handle the set_holiday_mode service call."""
        try:
            success = await hive.hub.set_holiday_mode(
                call.data["start"], call.data["end"], call.data["temperature"]
            )
        except (HTTPException, HiveApiError, HiveReauthRequired) as err:
            raise HomeAssistantError(f"Failed to set Hive holiday mode: {err}") from err
        if not success:
            raise HomeAssistantError("Hive rejected the set holiday mode request.")
        async_dispatcher_send(hass, DOMAIN)

    async def _async_cancel_holiday_mode(call: ServiceCall) -> None:
        """Handle the cancel_holiday_mode service call."""
        try:
            success = await hive.hub.cancel_holiday_mode()
        except (HTTPException, HiveApiError, HiveReauthRequired) as err:
            raise HomeAssistantError(
                f"Failed to cancel Hive holiday mode: {err}"
            ) from err
        if not success:
            raise HomeAssistantError("Hive rejected the cancel holiday mode request.")
        async_dispatcher_send(hass, DOMAIN)

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_HOLIDAY_MODE,
        _async_set_holiday_mode,
        schema=SET_HOLIDAY_MODE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_CANCEL_HOLIDAY_MODE, _async_cancel_holiday_mode
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: HiveConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: HiveConfigEntry) -> None:
    """Remove a config entry."""
    hive = Auth(entry.data["username"], entry.data["password"])
    await hive.forget_device(
        entry.data["tokens"]["AuthenticationResult"]["AccessToken"],
        entry.data["device_data"][1],
    )


async def async_remove_config_entry_device(
    hass: HomeAssistant, config_entry: HiveConfigEntry, device_entry: dr.DeviceEntry
) -> bool:
    """Remove a config entry from a device."""
    return True


def refresh_system[_HiveEntityT: HiveEntity, **_P](
    func: Callable[Concatenate[_HiveEntityT, _P], Awaitable[Any]],
) -> Callable[Concatenate[_HiveEntityT, _P], Coroutine[Any, Any, None]]:
    """Force update all entities after state change."""

    @wraps(func)
    async def wrapper(self: _HiveEntityT, *args: _P.args, **kwargs: _P.kwargs) -> None:
        await func(self, *args, **kwargs)
        async_dispatcher_send(self.hass, DOMAIN)

    return wrapper
