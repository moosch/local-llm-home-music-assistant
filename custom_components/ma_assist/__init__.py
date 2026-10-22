"""Music Assistant Voice Tools: room-aware Music Assistant tools for LLM agents."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm

from .api import MusicAssistantLLMAPI
from .settings import settings_from_entry


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    api = MusicAssistantLLMAPI(hass, settings_from_entry(entry))
    entry.async_on_unload(llm.async_register_api(hass, api))
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
