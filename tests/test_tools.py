"""Tests for the LLM tools and the API prompt."""

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.ma_assist.api import MusicAssistantLLMAPI
from custom_components.ma_assist.settings import MaAssistSettings
from custom_components.ma_assist.tools import (
    MediaControlTool,
    PlayMusicTool,
    SearchMusicTool,
    SetVolumeTool,
    TransferPlaybackTool,
    WhatsPlayingTool,
    build_tools,
)
from homeassistant.core import Context, HomeAssistant, SupportsResponse
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
    assert [tool.name for tool in instance.tools] == [
        "play_music",
        "media_control",
        "set_volume",
        "transfer_playback",
        "whats_playing",
        "search_music",
    ]


def test_disabled_tools_are_left_out() -> None:
    settings = MaAssistSettings(
        "entry", disabled_tools=frozenset({"set_volume", "search_music"})
    )

    assert [tool.name for tool in build_tools(settings)] == [
        "play_music",
        "media_control",
        "transfer_playback",
        "whats_playing",
    ]


async def test_media_control_pauses_the_playing_player(
    hass: HomeAssistant,
    music_assistant_entry: MockConfigEntry,
    players: PlayerFactory,
    office: ar.AreaEntry,
    kitchen: ar.AreaEntry,
) -> None:
    office_player = players.add(
        music_assistant_entry, "Office WiiM", office.id, state="playing"
    )
    players.add(music_assistant_entry, "Kitchen Speaker", kitchen.id)
    calls = async_mock_service(hass, "media_player", "media_pause")
    tool = MediaControlTool(MaAssistSettings(music_assistant_entry.entry_id))
    tool_input = llm.ToolInput(tool_name="media_control", tool_args={"action": "pause"})

    result = await tool.async_call(hass, tool_input, make_llm_context())

    assert result == llm.ToolResult(data={"done": "pause", "player": "Office WiiM"})
    assert [call.data for call in calls] == [{"entity_id": office_player}]


async def test_set_volume_to_level(
    hass: HomeAssistant,
    music_assistant_entry: MockConfigEntry,
    players: PlayerFactory,
    office: ar.AreaEntry,
) -> None:
    player = players.add(music_assistant_entry, "Office WiiM", office.id)
    calls = async_mock_service(hass, "media_player", "volume_set")
    tool = SetVolumeTool(MaAssistSettings(music_assistant_entry.entry_id))
    tool_input = llm.ToolInput(
        tool_name="set_volume", tool_args={"level": 30, "area": "office"}
    )

    result = await tool.async_call(hass, tool_input, make_llm_context())

    assert result == llm.ToolResult(data={"volume": 30, "player": "Office WiiM"})
    assert [call.data for call in calls] == [{"entity_id": player, "volume_level": 0.3}]


async def test_set_volume_change_clamps(
    hass: HomeAssistant,
    music_assistant_entry: MockConfigEntry,
    players: PlayerFactory,
    office: ar.AreaEntry,
) -> None:
    players.add(music_assistant_entry, "Office WiiM", office.id, volume_level=0.95)
    calls = async_mock_service(hass, "media_player", "volume_set")
    tool = SetVolumeTool(MaAssistSettings(music_assistant_entry.entry_id))
    tool_input = llm.ToolInput(
        tool_name="set_volume", tool_args={"change": 10, "area": "office"}
    )

    result = await tool.async_call(hass, tool_input, make_llm_context())

    assert result.data["volume"] == 100
    assert calls[0].data["volume_level"] == 1.0


async def test_set_volume_change_needs_known_volume(
    hass: HomeAssistant,
    music_assistant_entry: MockConfigEntry,
    players: PlayerFactory,
    office: ar.AreaEntry,
) -> None:
    players.add(music_assistant_entry, "Office WiiM", office.id)
    calls = async_mock_service(hass, "media_player", "volume_set")
    tool = SetVolumeTool(MaAssistSettings(music_assistant_entry.entry_id))
    tool_input = llm.ToolInput(
        tool_name="set_volume", tool_args={"change": -10, "area": "office"}
    )

    result = await tool.async_call(hass, tool_input, make_llm_context())

    assert result.error is True
    assert "Current volume is unknown" in str(result.data["error"])
    assert calls == []


async def test_set_volume_lowers_by_percent(
    hass: HomeAssistant,
    music_assistant_entry: MockConfigEntry,
    players: PlayerFactory,
    office: ar.AreaEntry,
) -> None:
    players.add(
        music_assistant_entry,
        "Office WiiM",
        office.id,
        state="playing",
        volume_level=0.5,
    )
    calls = async_mock_service(hass, "media_player", "volume_set")
    tool = SetVolumeTool(MaAssistSettings(music_assistant_entry.entry_id))
    tool_input = llm.ToolInput(tool_name="set_volume", tool_args={"change": -10})

    result = await tool.async_call(hass, tool_input, make_llm_context())

    assert result == llm.ToolResult(data={"volume": 40, "player": "Office WiiM"})
    assert calls[0].data["volume_level"] == 0.4


async def test_media_control_resumes_the_paused_player(
    hass: HomeAssistant,
    music_assistant_entry: MockConfigEntry,
    players: PlayerFactory,
    office: ar.AreaEntry,
    kitchen: ar.AreaEntry,
) -> None:
    players.add(music_assistant_entry, "Office WiiM", office.id, state="playing")
    kitchen_player = players.add(
        music_assistant_entry, "Kitchen Speaker", kitchen.id, state="paused"
    )
    calls = async_mock_service(hass, "media_player", "media_play")
    tool = MediaControlTool(MaAssistSettings(music_assistant_entry.entry_id))
    tool_input = llm.ToolInput(
        tool_name="media_control", tool_args={"action": "resume"}
    )

    await tool.async_call(hass, tool_input, make_llm_context())

    assert [call.data for call in calls] == [{"entity_id": kitchen_player}]


async def test_whats_playing_reports_the_playing_player(
    hass: HomeAssistant,
    music_assistant_entry: MockConfigEntry,
    players: PlayerFactory,
    office: ar.AreaEntry,
    kitchen: ar.AreaEntry,
) -> None:
    office_player = players.add(music_assistant_entry, "Office WiiM", office.id)
    players.add(music_assistant_entry, "Kitchen Speaker", kitchen.id)
    hass.states.async_set(
        office_player,
        "playing",
        {
            "friendly_name": "Office WiiM",
            "media_title": "Hot Potato",
            "media_artist": "The Wiggles",
        },
    )
    tool = WhatsPlayingTool(MaAssistSettings(music_assistant_entry.entry_id))
    tool_input = llm.ToolInput(tool_name="whats_playing", tool_args={})

    result = await tool.async_call(hass, tool_input, make_llm_context())

    assert result == llm.ToolResult(
        data={
            "players": [
                {
                    "player": "Office WiiM",
                    "state": "playing",
                    "title": "Hot Potato",
                    "artist": "The Wiggles",
                }
            ]
        }
    )


async def test_whats_playing_when_nothing_is(
    hass: HomeAssistant,
    music_assistant_entry: MockConfigEntry,
    players: PlayerFactory,
    office: ar.AreaEntry,
) -> None:
    players.add(music_assistant_entry, "Office WiiM", office.id)
    tool = WhatsPlayingTool(MaAssistSettings(music_assistant_entry.entry_id))
    tool_input = llm.ToolInput(tool_name="whats_playing", tool_args={})

    result = await tool.async_call(hass, tool_input, make_llm_context())

    assert result == llm.ToolResult(data={"nothing_playing": True})


async def test_whats_playing_in_named_room(
    hass: HomeAssistant,
    music_assistant_entry: MockConfigEntry,
    players: PlayerFactory,
    office: ar.AreaEntry,
) -> None:
    players.add(music_assistant_entry, "Office WiiM", office.id)
    tool = WhatsPlayingTool(MaAssistSettings(music_assistant_entry.entry_id))
    tool_input = llm.ToolInput(tool_name="whats_playing", tool_args={"area": "office"})

    result = await tool.async_call(hass, tool_input, make_llm_context())

    assert result == llm.ToolResult(
        data={"players": [{"player": "Office WiiM", "state": "idle"}]}
    )


async def test_search_music_returns_short_results(
    hass: HomeAssistant, music_assistant_entry: MockConfigEntry
) -> None:
    response = {
        "artists": [],
        "albums": [],
        "tracks": [
            {
                "media_type": "track",
                "uri": "spotify://track/1",
                "name": "Hot Potato",
                "image": "http://example/image.png",
                "artists": [{"media_type": "artist", "name": "The Wiggles"}],
            }
        ],
        "playlists": [
            {
                "media_type": "playlist",
                "uri": "library://playlist/7",
                "name": "Feel Good Dinner",
            }
        ],
    }
    calls = async_mock_service(
        hass,
        "music_assistant",
        "search",
        response=response,
        supports_response=SupportsResponse.ONLY,
    )
    tool = SearchMusicTool(MaAssistSettings(music_assistant_entry.entry_id))
    tool_input = llm.ToolInput(tool_name="search_music", tool_args={"query": "wiggles"})

    result = await tool.async_call(hass, tool_input, make_llm_context())

    assert result == llm.ToolResult(
        data={
            "results": [
                {
                    "name": "Hot Potato",
                    "type": "track",
                    "uri": "spotify://track/1",
                    "artist": "The Wiggles",
                },
                {
                    "name": "Feel Good Dinner",
                    "type": "playlist",
                    "uri": "library://playlist/7",
                },
            ]
        }
    )
    assert calls[0].data == {
        "config_entry_id": music_assistant_entry.entry_id,
        "name": "wiggles",
        "media_type": ["track", "album", "artist", "playlist", "radio"],
        "limit": 3,
    }


async def test_search_music_by_type_asks_for_more_results(
    hass: HomeAssistant, music_assistant_entry: MockConfigEntry
) -> None:
    calls = async_mock_service(
        hass,
        "music_assistant",
        "search",
        response={"playlists": []},
        supports_response=SupportsResponse.ONLY,
    )
    tool = SearchMusicTool(MaAssistSettings(music_assistant_entry.entry_id))
    tool_input = llm.ToolInput(
        tool_name="search_music",
        tool_args={"query": "dinner", "media_type": "playlist"},
    )

    result = await tool.async_call(hass, tool_input, make_llm_context())

    assert result == llm.ToolResult(data={"results": []})
    assert calls[0].data["media_type"] == ["playlist"]
    assert calls[0].data["limit"] == 5


async def test_play_music_passes_radio_mode(
    hass: HomeAssistant,
    music_assistant_entry: MockConfigEntry,
    players: PlayerFactory,
    office: ar.AreaEntry,
) -> None:
    players.add(music_assistant_entry, "Office WiiM", office.id)
    calls = async_mock_service(hass, "music_assistant", "play_media")
    tool = PlayMusicTool(MaAssistSettings(music_assistant_entry.entry_id))
    tool_input = llm.ToolInput(
        tool_name="play_music",
        tool_args={"query": "Hot Potato", "area": "office", "radio_mode": True},
    )

    await tool.async_call(hass, tool_input, make_llm_context())

    assert calls[0].data["radio_mode"] is True


async def test_media_control_turns_shuffle_on(
    hass: HomeAssistant,
    music_assistant_entry: MockConfigEntry,
    players: PlayerFactory,
    office: ar.AreaEntry,
) -> None:
    player = players.add(
        music_assistant_entry, "Office WiiM", office.id, state="playing"
    )
    calls = async_mock_service(hass, "media_player", "shuffle_set")
    tool = MediaControlTool(MaAssistSettings(music_assistant_entry.entry_id))
    tool_input = llm.ToolInput(
        tool_name="media_control", tool_args={"action": "shuffle_on"}
    )

    result = await tool.async_call(hass, tool_input, make_llm_context())

    assert result == llm.ToolResult(
        data={"done": "shuffle_on", "player": "Office WiiM"}
    )
    assert [call.data for call in calls] == [{"entity_id": player, "shuffle": True}]


async def test_media_control_sets_repeat(
    hass: HomeAssistant,
    music_assistant_entry: MockConfigEntry,
    players: PlayerFactory,
    office: ar.AreaEntry,
) -> None:
    player = players.add(
        music_assistant_entry, "Office WiiM", office.id, state="playing"
    )
    calls = async_mock_service(hass, "media_player", "repeat_set")
    tool = MediaControlTool(MaAssistSettings(music_assistant_entry.entry_id))
    tool_input = llm.ToolInput(
        tool_name="media_control", tool_args={"action": "repeat_one"}
    )

    await tool.async_call(hass, tool_input, make_llm_context())

    assert [call.data for call in calls] == [{"entity_id": player, "repeat": "one"}]


async def test_transfer_moves_the_playing_queue(
    hass: HomeAssistant,
    music_assistant_entry: MockConfigEntry,
    players: PlayerFactory,
    office: ar.AreaEntry,
    kitchen: ar.AreaEntry,
) -> None:
    office_player = players.add(
        music_assistant_entry, "Office WiiM", office.id, state="playing"
    )
    kitchen_player = players.add(music_assistant_entry, "Kitchen Speaker", kitchen.id)
    calls = async_mock_service(hass, "music_assistant", "transfer_queue")
    tool = TransferPlaybackTool(MaAssistSettings(music_assistant_entry.entry_id))
    tool_input = llm.ToolInput(
        tool_name="transfer_playback", tool_args={"to_area": "kitchen"}
    )

    result = await tool.async_call(hass, tool_input, make_llm_context())

    assert result == llm.ToolResult(
        data={"moved_from": "Office WiiM", "moved_to": "Kitchen Speaker"}
    )
    assert calls[0].data == {
        "entity_id": kitchen_player,
        "source_player": office_player,
        "auto_play": True,
    }


async def test_transfer_from_named_room(
    hass: HomeAssistant,
    music_assistant_entry: MockConfigEntry,
    players: PlayerFactory,
    office: ar.AreaEntry,
    kitchen: ar.AreaEntry,
    area_registry: ar.AreaRegistry,
) -> None:
    lounge = area_registry.async_create("Lounge")
    players.add(music_assistant_entry, "Office WiiM", office.id, state="playing")
    lounge_player = players.add(
        music_assistant_entry, "Lounge Sonos", lounge.id, state="playing"
    )
    players.add(music_assistant_entry, "Kitchen Speaker", kitchen.id)
    calls = async_mock_service(hass, "music_assistant", "transfer_queue")
    tool = TransferPlaybackTool(MaAssistSettings(music_assistant_entry.entry_id))
    tool_input = llm.ToolInput(
        tool_name="transfer_playback",
        tool_args={"to_area": "kitchen", "from_area": "lounge"},
    )

    await tool.async_call(hass, tool_input, make_llm_context())

    assert calls[0].data["source_player"] == lounge_player


async def test_transfer_with_nothing_playing(
    hass: HomeAssistant,
    music_assistant_entry: MockConfigEntry,
    players: PlayerFactory,
    office: ar.AreaEntry,
    kitchen: ar.AreaEntry,
) -> None:
    players.add(music_assistant_entry, "Office WiiM", office.id)
    players.add(music_assistant_entry, "Kitchen Speaker", kitchen.id)
    calls = async_mock_service(hass, "music_assistant", "transfer_queue")
    tool = TransferPlaybackTool(MaAssistSettings(music_assistant_entry.entry_id))
    tool_input = llm.ToolInput(
        tool_name="transfer_playback", tool_args={"to_area": "kitchen"}
    )

    result = await tool.async_call(hass, tool_input, make_llm_context())

    assert result.error is True
    assert "Nothing is playing" in str(result.data["error"])
    assert calls == []


async def test_transfer_to_the_room_already_playing(
    hass: HomeAssistant,
    music_assistant_entry: MockConfigEntry,
    players: PlayerFactory,
    office: ar.AreaEntry,
) -> None:
    players.add(music_assistant_entry, "Office WiiM", office.id, state="playing")
    calls = async_mock_service(hass, "music_assistant", "transfer_queue")
    tool = TransferPlaybackTool(MaAssistSettings(music_assistant_entry.entry_id))
    tool_input = llm.ToolInput(
        tool_name="transfer_playback", tool_args={"to_area": "office"}
    )

    result = await tool.async_call(hass, tool_input, make_llm_context())

    assert result.error is True
    assert "already on Office WiiM" in str(result.data["error"])
    assert calls == []


async def test_invalid_arguments_are_reported_to_the_model(
    hass: HomeAssistant,
    music_assistant_entry: MockConfigEntry,
    players: PlayerFactory,
    office: ar.AreaEntry,
) -> None:
    players.add(music_assistant_entry, "Office WiiM", office.id)
    calls = async_mock_service(hass, "music_assistant", "play_media")
    tool = PlayMusicTool(MaAssistSettings(music_assistant_entry.entry_id))
    tool_input = llm.ToolInput(
        tool_name="play_music",
        tool_args={"query": "Hot Potato", "media_type": "song"},
    )

    result = await tool.async_call(hass, tool_input, make_llm_context())

    assert result.error is True
    assert "Invalid arguments" in str(result.data["error"])
    assert calls == []


async def test_arguments_are_coerced(
    hass: HomeAssistant,
    music_assistant_entry: MockConfigEntry,
    players: PlayerFactory,
    office: ar.AreaEntry,
) -> None:
    players.add(music_assistant_entry, "Office WiiM", office.id)
    calls = async_mock_service(hass, "media_player", "volume_set")
    tool = SetVolumeTool(MaAssistSettings(music_assistant_entry.entry_id))
    tool_input = llm.ToolInput(
        tool_name="set_volume", tool_args={"level": "40", "area": "office"}
    )

    result = await tool.async_call(hass, tool_input, make_llm_context())

    assert result.data["volume"] == 40
    assert calls[0].data["volume_level"] == 0.4
