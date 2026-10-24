"""LLM tools for controlling Music Assistant."""

from abc import abstractmethod
from typing import Any

import probatio

from homeassistant.components.media_player import ATTR_MEDIA_VOLUME_LEVEL
from homeassistant.const import (
    SERVICE_MEDIA_NEXT_TRACK,
    SERVICE_MEDIA_PAUSE,
    SERVICE_MEDIA_PLAY,
    SERVICE_MEDIA_PREVIOUS_TRACK,
    SERVICE_MEDIA_STOP,
    SERVICE_VOLUME_SET,
)
from homeassistant.core import HomeAssistant
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
    TOOL_SET_VOLUME,
    VOLUME_STEP,
)
from .player_resolver import player_name, resolve_control_player, resolve_player
from .settings import MaAssistSettings

type ToolArgs = dict[str, Any]

MEDIA_CONTROL_SERVICES = {
    "pause": SERVICE_MEDIA_PAUSE,
    "resume": SERVICE_MEDIA_PLAY,
    "stop": SERVICE_MEDIA_STOP,
    "next": SERVICE_MEDIA_NEXT_TRACK,
    "previous": SERVICE_MEDIA_PREVIOUS_TRACK,
}


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
            data = await self.async_run(hass, tool_input.tool_args, llm_context)
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
        "`query` is what to play, e.g. 'Hot Potato by The Wiggles'."
    )
    parameters = probatio.Schema(
        {
            probatio.Required("query"): str,
            probatio.Optional("area"): str,
            probatio.Optional("media_type"): probatio.In(MEDIA_TYPES),
            probatio.Optional("enqueue"): probatio.In(ENQUEUE_OPTIONS),
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
        "Pause, resume, stop (turn off) or skip the music. "
        "Use this, not a turn-off tool, for music."
    )
    parameters = probatio.Schema(
        {
            probatio.Required("action"): probatio.In(list(MEDIA_CONTROL_SERVICES)),
            probatio.Optional("area"): str,
        }
    )

    async def async_run(
        self, hass: HomeAssistant, args: ToolArgs, llm_context: llm.LLMContext
    ) -> JsonObjectType:
        player = resolve_control_player(
            hass, self.settings, args.get("area"), llm_context.device_id
        )
        await hass.services.async_call(
            MEDIA_PLAYER_DOMAIN,
            MEDIA_CONTROL_SERVICES[args["action"]],
            target={"entity_id": player},
            blocking=True,
            context=llm_context.context,
        )
        return {"done": args["action"], "player": player_name(hass, player)}


class SetVolumeTool(MusicAssistantTool):
    name = TOOL_SET_VOLUME
    description = (
        "Change the music volume. Give `level` (0-100) to set it, "
        "or `direction` to nudge it up or down a bit."
    )
    parameters = probatio.Schema(
        {
            probatio.Optional("level"): probatio.All(
                probatio.Coerce(int), probatio.Range(min=0, max=100)
            ),
            probatio.Optional("direction"): probatio.In(["up", "down"]),
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


def play_media_data(args: ToolArgs) -> dict[str, str]:
    data = {"media_id": args["query"]}
    for key in ("media_type", "enqueue"):
        if key in args:
            data[key] = args[key]
    return data


def target_volume(hass: HomeAssistant, player: str, args: ToolArgs) -> float:
    if "level" in args:
        return args["level"] / 100
    direction = args.get("direction")
    if direction is None:
        raise HomeAssistantError("Give a volume level or a direction.")
    step = VOLUME_STEP if direction == "up" else -VOLUME_STEP
    return min(1.0, max(0.0, current_volume(hass, player) + step))


def current_volume(hass: HomeAssistant, player: str) -> float:
    state = hass.states.get(player)
    level = state.attributes.get(ATTR_MEDIA_VOLUME_LEVEL) if state else None
    if level is None:
        raise HomeAssistantError("Current volume is unknown. Give a level instead.")
    return float(level)


def build_tools(settings: MaAssistSettings) -> list[llm.Tool]:
    tools: list[llm.Tool] = [
        PlayMusicTool(settings),
        MediaControlTool(settings),
        SetVolumeTool(settings),
    ]
    return [tool for tool in tools if tool.name not in settings.disabled_tools]
