"""Tests for the play_music tool and the API prompt."""

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.ma_assist.api import MusicAssistantLLMAPI
from custom_components.ma_assist.settings import MaAssistSettings
from custom_components.ma_assist.tools import PlayMusicTool
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import area_registry as ar, llm

from .conftest import PlayerFactory


def make_llm_context(device_id: str | None = None) -> llm.LLMContext:
    return llm.LLMContext(
        platform="test",
        context=Context(),
        language="en",
        assistant="conversation",
        device_id=device_id,
    )


async def test_play_music_calls_music_assistant(
    hass: HomeAssistant,
    music_assistant_entry: MockConfigEntry,
    players: PlayerFactory,
    office: ar.AreaEntry,
) -> None:
    player = players.add(music_assistant_entry, "Office WiiM", office.id)
    calls = async_mock_service(hass, "music_assistant", "play_media")
    tool = PlayMusicTool(MaAssistSettings(music_assistant_entry.entry_id))
    tool_input = llm.ToolInput(
        tool_name="play_music",
        tool_args={
            "query": "Dinner Playlist",
            "area": "office",
            "media_type": "playlist",
        },
    )

    result = await tool.async_call(hass, tool_input, make_llm_context())

    assert result == llm.ToolResult(
        data={"playing": "Dinner Playlist", "player": "Office WiiM"}
    )
    assert len(calls) == 1
    assert calls[0].data == {
        "entity_id": player,
        "media_id": "Dinner Playlist",
        "media_type": "playlist",
    }


async def test_play_music_reports_unknown_room(
    hass: HomeAssistant,
    music_assistant_entry: MockConfigEntry,
    players: PlayerFactory,
    office: ar.AreaEntry,
) -> None:
    players.add(music_assistant_entry, "Office WiiM", office.id)
    calls = async_mock_service(hass, "music_assistant", "play_media")
    tool = PlayMusicTool(MaAssistSettings(music_assistant_entry.entry_id))
    tool_input = llm.ToolInput(
        tool_name="play_music", tool_args={"query": "Hot Potato", "area": "attic"}
    )

    result = await tool.async_call(hass, tool_input, make_llm_context())

    assert result.error is True
    assert "attic" in str(result.data["error"])
    assert calls == []


async def test_api_instance_lists_rooms_and_tools(
    hass: HomeAssistant,
    music_assistant_entry: MockConfigEntry,
    players: PlayerFactory,
    office: ar.AreaEntry,
) -> None:
    players.add(music_assistant_entry, "Office WiiM", office.id)
    api = MusicAssistantLLMAPI(hass, MaAssistSettings(music_assistant_entry.entry_id))

    instance = await api.async_get_api_instance(make_llm_context())

    assert "Available rooms: Office." in instance.api_prompt
    assert [tool.name for tool in instance.tools] == ["play_music"]
