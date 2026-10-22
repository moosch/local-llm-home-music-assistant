"""LLM tools for controlling Music Assistant."""

import probatio

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import llm

from .const import DOMAIN, ENQUEUE_OPTIONS, MEDIA_TYPES, MUSIC_ASSISTANT_DOMAIN
from .player_resolver import player_name, resolve_player
from .settings import MaAssistSettings


class PlayMusicTool(llm.Tool):
    name = "play_music"
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
        args = tool_input.tool_args
        try:
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
        except HomeAssistantError as err:
            return llm.ToolResult(data={"error": str(err)}, error=True)
        return llm.ToolResult(
            data={"playing": args["query"], "player": player_name(hass, player)}
        )


def play_media_data(args: dict[str, str]) -> dict[str, str]:
    data = {"media_id": args["query"]}
    for key in ("media_type", "enqueue"):
        if key in args:
            data[key] = args[key]
    return data


def build_tools(settings: MaAssistSettings) -> list[llm.Tool]:
    return [PlayMusicTool(settings)]
