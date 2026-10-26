"""LLM tools for controlling Music Assistant."""

from abc import abstractmethod
from dataclasses import dataclass, field
from typing import Any

import probatio

from homeassistant.components.media_player import (
    ATTR_MEDIA_ALBUM_NAME,
    ATTR_MEDIA_ARTIST,
    ATTR_MEDIA_REPEAT,
    ATTR_MEDIA_SHUFFLE,
    ATTR_MEDIA_TITLE,
    ATTR_MEDIA_VOLUME_LEVEL,
    RepeatMode,
)
from homeassistant.const import (
    SERVICE_MEDIA_NEXT_TRACK,
    SERVICE_MEDIA_PAUSE,
    SERVICE_MEDIA_PLAY,
    SERVICE_MEDIA_PREVIOUS_TRACK,
    SERVICE_MEDIA_STOP,
    SERVICE_REPEAT_SET,
    SERVICE_SHUFFLE_SET,
    SERVICE_VOLUME_SET,
)
from homeassistant.core import HomeAssistant, ServiceResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import llm
from homeassistant.util.json import JsonObjectType

from .const import (
    DOMAIN,
    ENQUEUE_OPTIONS,
    MEDIA_PLAYER_DOMAIN,
    MEDIA_TYPES,
    MUSIC_ASSISTANT_DOMAIN,
    TOOL_MEDIA_CONTROL,
    TOOL_PLAY_MUSIC,
    TOOL_SEARCH_MUSIC,
    TOOL_SET_VOLUME,
    TOOL_TRANSFER_PLAYBACK,
    TOOL_WHATS_PLAYING,
)
from .player_resolver import (
    in_use_nearby,
    player_name,
    resolve_control_player,
    resolve_named_room,
    resolve_player,
    resolve_transfer_source,
)
from .settings import MaAssistSettings

type ToolArgs = dict[str, Any]


@dataclass(frozen=True, slots=True)
class MediaCommand:
    service: str
    data: dict[str, object] = field(default_factory=dict)


MEDIA_COMMANDS = {
    "pause": MediaCommand(SERVICE_MEDIA_PAUSE),
    "resume": MediaCommand(SERVICE_MEDIA_PLAY),
    "stop": MediaCommand(SERVICE_MEDIA_STOP),
    "next": MediaCommand(SERVICE_MEDIA_NEXT_TRACK),
    "previous": MediaCommand(SERVICE_MEDIA_PREVIOUS_TRACK),
    "shuffle_on": MediaCommand(SERVICE_SHUFFLE_SET, {ATTR_MEDIA_SHUFFLE: True}),
    "shuffle_off": MediaCommand(SERVICE_SHUFFLE_SET, {ATTR_MEDIA_SHUFFLE: False}),
    "repeat_one": MediaCommand(SERVICE_REPEAT_SET, {ATTR_MEDIA_REPEAT: RepeatMode.ONE}),
    "repeat_all": MediaCommand(SERVICE_REPEAT_SET, {ATTR_MEDIA_REPEAT: RepeatMode.ALL}),
    "repeat_off": MediaCommand(SERVICE_REPEAT_SET, {ATTR_MEDIA_REPEAT: RepeatMode.OFF}),
}

NOW_PLAYING_ATTRIBUTES = {
    "title": ATTR_MEDIA_TITLE,
    "artist": ATTR_MEDIA_ARTIST,
    "album": ATTR_MEDIA_ALBUM_NAME,
}

# Searching every type at once returns a result list per type; keep the total
# small enough for a local model's context.
SEARCH_LIMIT_ONE_TYPE = 5
SEARCH_LIMIT_PER_TYPE = 3

READ_ONLY = llm.ToolAnnotations(read_only=True, destructive=False, idempotent=True)


class MusicAssistantTool(llm.Tool):
    """Base for tools that report Home Assistant errors back to the model."""

    annotations = llm.ToolAnnotations(destructive=False)
    integration = DOMAIN

    def __init__(self, settings: MaAssistSettings) -> None:
        self.settings = settings

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> llm.ToolResult:
        try:
            # Home Assistant hands tools the model's raw arguments unvalidated.
            args = self.parameters(tool_input.tool_args)
            data = await self.async_run(hass, args, llm_context)
        except probatio.Invalid as err:
            return llm.ToolResult(
                data={"error": f"Invalid arguments: {err}"}, error=True
            )
        except HomeAssistantError as err:
            return llm.ToolResult(data={"error": str(err)}, error=True)
        return llm.ToolResult(data=data)

    @abstractmethod
    async def async_run(
        self, hass: HomeAssistant, args: ToolArgs, llm_context: llm.LLMContext
    ) -> JsonObjectType:
        raise NotImplementedError


class PlayMusicTool(MusicAssistantTool):
    name = TOOL_PLAY_MUSIC
    description = (
        "Play a song, album, artist, playlist or radio station. "
        "`query` is what to play, e.g. 'Hot Potato by The Wiggles', "
        "or a `uri` from search_music. Set `radio_mode` for 'songs like ...' "
        "to keep playing similar music."
    )
    parameters = probatio.Schema(
        {
            probatio.Required("query"): str,
            probatio.Optional("area"): str,
            probatio.Optional("media_type"): probatio.In(MEDIA_TYPES),
            probatio.Optional("enqueue"): probatio.In(ENQUEUE_OPTIONS),
            probatio.Optional("radio_mode"): bool,
        }
    )

    async def async_run(
        self, hass: HomeAssistant, args: ToolArgs, llm_context: llm.LLMContext
    ) -> JsonObjectType:
        player = resolve_player(
            hass, self.settings, args.get("area"), llm_context.device_id
        )
        await hass.services.async_call(
            MUSIC_ASSISTANT_DOMAIN,
            "play_media",
            play_media_data(args),
            target={"entity_id": player},
            blocking=True,
            context=llm_context.context,
        )
        return {"playing": args["query"], "player": player_name(hass, player)}


class MediaControlTool(MusicAssistantTool):
    name = TOOL_MEDIA_CONTROL
    description = (
        "Pause, resume, stop (turn off), skip, shuffle or repeat the music. "
        "Use this, not a turn-off tool, for music."
    )
    parameters = probatio.Schema(
        {
            probatio.Required("action"): probatio.In(list(MEDIA_COMMANDS)),
            probatio.Optional("area"): str,
        }
    )

    async def async_run(
        self, hass: HomeAssistant, args: ToolArgs, llm_context: llm.LLMContext
    ) -> JsonObjectType:
        player = resolve_control_player(
            hass,
            self.settings,
            args.get("area"),
            llm_context.device_id,
            resuming=args["action"] == "resume",
        )
        command = MEDIA_COMMANDS[args["action"]]
        await hass.services.async_call(
            MEDIA_PLAYER_DOMAIN,
            command.service,
            command.data,
            target={"entity_id": player},
            blocking=True,
            context=llm_context.context,
        )
        return {"done": args["action"], "player": player_name(hass, player)}


class SetVolumeTool(MusicAssistantTool):
    name = TOOL_SET_VOLUME
    description = (
        "Change the music volume. Use this, not other volume tools, for music. "
        "Give `level` (0-100) to set it, or `change` in percent to adjust it, "
        "e.g. -10 for 'down by 10 percent'. 'A bit' is 10."
    )
    parameters = probatio.Schema(
        {
            probatio.Optional("level"): probatio.All(
                probatio.Coerce(int), probatio.Range(min=0, max=100)
            ),
            probatio.Optional("change"): probatio.All(
                probatio.Coerce(int), probatio.Range(min=-100, max=100)
            ),
            probatio.Optional("area"): str,
        }
    )

    async def async_run(
        self, hass: HomeAssistant, args: ToolArgs, llm_context: llm.LLMContext
    ) -> JsonObjectType:
        player = resolve_control_player(
            hass, self.settings, args.get("area"), llm_context.device_id
        )
        volume = target_volume(hass, player, args)
        await hass.services.async_call(
            MEDIA_PLAYER_DOMAIN,
            SERVICE_VOLUME_SET,
            {ATTR_MEDIA_VOLUME_LEVEL: volume},
            target={"entity_id": player},
            blocking=True,
            context=llm_context.context,
        )
        return {"volume": round(volume * 100), "player": player_name(hass, player)}


class TransferPlaybackTool(MusicAssistantTool):
    name = TOOL_TRANSFER_PLAYBACK
    description = "Move the music from one room to another, keeping its place."
    parameters = probatio.Schema(
        {
            probatio.Required("to_area"): str,
            probatio.Optional("from_area"): str,
        }
    )

    async def async_run(
        self, hass: HomeAssistant, args: ToolArgs, llm_context: llm.LLMContext
    ) -> JsonObjectType:
        destination = resolve_named_room(hass, self.settings, args["to_area"])
        source = resolve_transfer_source(
            hass,
            self.settings,
            args.get("from_area"),
            llm_context.device_id,
            destination,
        )
        await hass.services.async_call(
            MUSIC_ASSISTANT_DOMAIN,
            "transfer_queue",
            {"source_player": source, "auto_play": True},
            target={"entity_id": destination},
            blocking=True,
            context=llm_context.context,
        )
        return {
            "moved_from": player_name(hass, source),
            "moved_to": player_name(hass, destination),
        }


class WhatsPlayingTool(MusicAssistantTool):
    name = TOOL_WHATS_PLAYING
    description = "Tell what music is playing, and on which player."
    parameters = probatio.Schema({probatio.Optional("area"): str})
    annotations = READ_ONLY

    async def async_run(
        self, hass: HomeAssistant, args: ToolArgs, llm_context: llm.LLMContext
    ) -> JsonObjectType:
        area = args.get("area")
        if area is None:
            players = in_use_nearby(hass, self.settings, llm_context.device_id)
        else:
            players = [
                resolve_control_player(hass, self.settings, area, llm_context.device_id)
            ]
        if not players:
            return {"nothing_playing": True}
        return {"players": [now_playing(hass, player) for player in players]}


class SearchMusicTool(MusicAssistantTool):
    name = TOOL_SEARCH_MUSIC
    description = (
        "Search for songs, albums, artists, playlists or radio stations. "
        "To play a result, pass its `uri` to play_music as `query`."
    )
    parameters = probatio.Schema(
        {
            probatio.Required("query"): str,
            probatio.Optional("media_type"): probatio.In(MEDIA_TYPES),
        }
    )
    annotations = READ_ONLY

    async def async_run(
        self, hass: HomeAssistant, args: ToolArgs, llm_context: llm.LLMContext
    ) -> JsonObjectType:
        response = await hass.services.async_call(
            MUSIC_ASSISTANT_DOMAIN,
            "search",
            search_data(self.settings, args),
            blocking=True,
            context=llm_context.context,
            return_response=True,
        )
        return {"results": search_results(response)}


def play_media_data(args: ToolArgs) -> dict[str, object]:
    data: dict[str, object] = {"media_id": args["query"]}
    for key in ("media_type", "enqueue", "radio_mode"):
        if key in args:
            data[key] = args[key]
    return data


def target_volume(hass: HomeAssistant, player: str, args: ToolArgs) -> float:
    if "level" in args:
        return args["level"] / 100
    if "change" not in args:
        raise HomeAssistantError("Give a volume level or a change.")
    change = args["change"] / 100
    return min(1.0, max(0.0, current_volume(hass, player) + change))


def current_volume(hass: HomeAssistant, player: str) -> float:
    state = hass.states.get(player)
    level = state.attributes.get(ATTR_MEDIA_VOLUME_LEVEL) if state else None
    if level is None:
        raise HomeAssistantError(
            "Current volume is unknown. Ask the user for a level from 0 to 100."
        )
    return float(level)


def now_playing(hass: HomeAssistant, player: str) -> JsonObjectType:
    summary: JsonObjectType = {"player": player_name(hass, player)}
    state = hass.states.get(player)
    if state is None:
        return summary
    summary["state"] = state.state
    for key, attribute in NOW_PLAYING_ATTRIBUTES.items():
        value = state.attributes.get(attribute)
        if value is not None:
            summary[key] = value
    return summary


def search_data(settings: MaAssistSettings, args: ToolArgs) -> dict[str, object]:
    media_type = args.get("media_type")
    if media_type is None:
        media_types, limit = MEDIA_TYPES, SEARCH_LIMIT_PER_TYPE
    else:
        media_types, limit = [media_type], SEARCH_LIMIT_ONE_TYPE
    return {
        "config_entry_id": settings.music_assistant_entry_id,
        "name": args["query"],
        "media_type": media_types,
        "limit": limit,
    }


def search_results(response: ServiceResponse) -> list[JsonObjectType]:
    """Flatten MA's per-type result lists into short name/type/uri entries."""
    results: list[JsonObjectType] = []
    if response is None:
        return results
    for items in response.values():
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict):
                results.append(search_result(item))
    return results


def search_result(item: JsonObjectType) -> JsonObjectType:
    result: JsonObjectType = {
        "name": item.get("name"),
        "type": str(item.get("media_type")),
        "uri": item.get("uri"),
    }
    artists = item.get("artists")
    if isinstance(artists, list):
        names = [artist["name"] for artist in artists if isinstance(artist, dict)]
        if names:
            result["artist"] = ", ".join(str(name) for name in names)
    return result


def build_tools(settings: MaAssistSettings) -> list[llm.Tool]:
    tools: list[llm.Tool] = [
        PlayMusicTool(settings),
        MediaControlTool(settings),
        SetVolumeTool(settings),
        TransferPlaybackTool(settings),
        WhatsPlayingTool(settings),
        SearchMusicTool(settings),
    ]
    return [tool for tool in tools if tool.name not in settings.disabled_tools]
