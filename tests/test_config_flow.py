"""Tests for the config and options flows, and entry setup."""

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ma_assist.const import (
    CONF_DEFAULT_PLAYER,
    CONF_DISABLED_TOOLS,
    CONF_MUSIC_ASSISTANT_ENTRY_ID,
    CONF_ROOM_ALIASES,
    DOMAIN,
)
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import llm

from .conftest import PlayerFactory


def add_music_assistant_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain="music_assistant", state=ConfigEntryState.LOADED)
    entry.add_to_hass(hass)
    return entry


async def test_aborts_without_music_assistant(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "music_assistant_not_found"


async def test_picks_only_music_assistant_entry(hass: HomeAssistant) -> None:
    music_assistant_entry = add_music_assistant_entry(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_MUSIC_ASSISTANT_ENTRY_ID: music_assistant_entry.entry_id
    }


async def test_asks_when_several_music_assistant_entries(hass: HomeAssistant) -> None:
    add_music_assistant_entry(hass)
    second_entry = add_music_assistant_entry(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MUSIC_ASSISTANT_ENTRY_ID: second_entry.entry_id}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_MUSIC_ASSISTANT_ENTRY_ID: second_entry.entry_id}


async def test_setup_registers_and_unload_removes_api(hass: HomeAssistant) -> None:
    music_assistant_entry = add_music_assistant_entry(hass)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_MUSIC_ASSISTANT_ENTRY_ID: music_assistant_entry.entry_id},
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    assert DOMAIN in [api.id for api in llm.async_get_apis(hass)]

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert DOMAIN not in [api.id for api in llm.async_get_apis(hass)]


async def test_options_flow_validates_aliases(
    hass: HomeAssistant, players: PlayerFactory
) -> None:
    music_assistant_entry = add_music_assistant_entry(hass)
    office_player = players.add(music_assistant_entry, "Office WiiM")
    native_entry = MockConfigEntry(domain="sonos")
    native_entry.add_to_hass(hass)
    native_player = players.add(native_entry, "Lounge Sonos", platform="sonos")
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_MUSIC_ASSISTANT_ENTRY_ID: music_assistant_entry.entry_id},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_ROOM_ALIASES: "office"}
    )
    assert result["errors"] == {CONF_ROOM_ALIASES: "invalid_aliases"}

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_ROOM_ALIASES: f"lounge: {native_player}"}
    )
    assert result["errors"] == {CONF_ROOM_ALIASES: "alias_not_music_assistant"}

    options = {
        CONF_DEFAULT_PLAYER: office_player,
        CONF_ROOM_ALIASES: f"study: {office_player}",
        CONF_DISABLED_TOOLS: ["set_volume"],
    }
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], options
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == options
    assert entry.state is ConfigEntryState.LOADED
