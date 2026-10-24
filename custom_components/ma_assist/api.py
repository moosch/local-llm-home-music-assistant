"""The LLM API that exposes Music Assistant tools to conversation agents."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm

from .const import DOMAIN
from .player_resolver import available_rooms
from .settings import MaAssistSettings
from .tools import build_tools


class MusicAssistantLLMAPI(llm.API):
    def __init__(self, hass: HomeAssistant, settings: MaAssistSettings) -> None:
        super().__init__(hass=hass, id=DOMAIN, name="Music Assistant")
        self.settings = settings

    async def async_get_api_instance(
        self, llm_context: llm.LLMContext
    ) -> llm.APIInstance:
        return llm.APIInstance(
            api=self,
            api_prompt=build_prompt(self.hass, self.settings),
            llm_context=llm_context,
            tools=build_tools(self.settings),
        )


def build_prompt(hass: HomeAssistant, settings: MaAssistSettings) -> str:
    rooms = ", ".join(available_rooms(hass, settings))
    return (
        "You can play and control music via Music Assistant.\n"
        f"Available rooms: {rooms}.\n"
        "When the user names a room, pass it as `area` using one of these names.\n"
        "If no room is given, leave `area` out; music plays where the user is.\n"
        "Only say music was played, paused or changed after a tool call "
        "succeeds. If it returns an error, say so.\n"
    )
