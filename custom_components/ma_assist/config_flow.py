"""Config and options flows for Music Assistant Voice Tools."""

from typing import Any, override

import probatio

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    ConfigEntrySelector,
    ConfigEntrySelectorConfig,
    EntitySelector,
    EntitySelectorConfig,
    TextSelector,
    TextSelectorConfig,
)

from .const import (
    CONF_DEFAULT_PLAYER,
    CONF_MUSIC_ASSISTANT_ENTRY_ID,
    CONF_ROOM_ALIASES,
    DOMAIN,
    MEDIA_PLAYER_DOMAIN,
    MUSIC_ASSISTANT_DOMAIN,
)
from .settings import InvalidAliasesError, parse_room_aliases

TITLE = "Music Assistant Voice Tools"

USER_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_MUSIC_ASSISTANT_ENTRY_ID): ConfigEntrySelector(
            ConfigEntrySelectorConfig(integration=MUSIC_ASSISTANT_DOMAIN)
        ),
    }
)

OPTIONS_SCHEMA = probatio.Schema(
    {
        probatio.Optional(CONF_DEFAULT_PLAYER): EntitySelector(
            EntitySelectorConfig(
                domain=MEDIA_PLAYER_DOMAIN, integration=MUSIC_ASSISTANT_DOMAIN
            )
        ),
        probatio.Optional(CONF_ROOM_ALIASES): TextSelector(
            TextSelectorConfig(multiline=True)
        ),
    }
)


class MaAssistConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return MaAssistOptionsFlow()

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        music_assistant_entries = self.hass.config_entries.async_loaded_entries(
            MUSIC_ASSISTANT_DOMAIN
        )
        if not music_assistant_entries:
            return self.async_abort(reason="music_assistant_not_found")

        if user_input is not None:
            return self.create_entry(user_input[CONF_MUSIC_ASSISTANT_ENTRY_ID])

        if len(music_assistant_entries) == 1:
            return self.create_entry(music_assistant_entries[0].entry_id)

        return self.async_show_form(step_id="user", data_schema=USER_SCHEMA)

    def create_entry(self, music_assistant_entry_id: str) -> ConfigFlowResult:
        return self.async_create_entry(
            title=TITLE,
            data={CONF_MUSIC_ASSISTANT_ENTRY_ID: music_assistant_entry_id},
        )


class MaAssistOptionsFlow(OptionsFlow):
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                parse_room_aliases(user_input.get(CONF_ROOM_ALIASES, ""))
            except InvalidAliasesError:
                errors[CONF_ROOM_ALIASES] = "invalid_aliases"
            else:
                return self.async_create_entry(data=user_input)

        schema = self.add_suggested_values_to_schema(
            OPTIONS_SCHEMA, user_input or self.config_entry.options
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
