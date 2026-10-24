"""Typed view of the integration's config entry data and options."""

from dataclasses import dataclass, field

from homeassistant.config_entries import ConfigEntry

from .const import (
    CONF_DEFAULT_PLAYER,
    CONF_DISABLED_TOOLS,
    CONF_MUSIC_ASSISTANT_ENTRY_ID,
    CONF_ROOM_ALIASES,
)

type RoomAliases = dict[str, str]


class InvalidAliasesError(ValueError):
    """Raised when the room alias text cannot be parsed."""


@dataclass(frozen=True, slots=True)
class MaAssistSettings:
    music_assistant_entry_id: str
    default_player: str | None = None
    room_aliases: RoomAliases = field(default_factory=dict)
    disabled_tools: frozenset[str] = frozenset()


def normalize_room_name(name: str) -> str:
    return " ".join(name.casefold().split())


def parse_room_aliases(text: str) -> RoomAliases:
    """Parse lines of `spoken name: media_player.entity_id`."""
    aliases: RoomAliases = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        spoken_name, separator, entity_id = line.partition(":")
        entity_id = entity_id.strip()
        if not separator or not spoken_name.strip():
            raise InvalidAliasesError(line)
        if not entity_id.startswith("media_player."):
            raise InvalidAliasesError(line)
        aliases[normalize_room_name(spoken_name)] = entity_id
    return aliases


def settings_from_entry(entry: ConfigEntry) -> MaAssistSettings:
    return MaAssistSettings(
        music_assistant_entry_id=entry.data[CONF_MUSIC_ASSISTANT_ENTRY_ID],
        default_player=entry.options.get(CONF_DEFAULT_PLAYER) or None,
        room_aliases=parse_room_aliases(entry.options.get(CONF_ROOM_ALIASES, "")),
        disabled_tools=frozenset(entry.options.get(CONF_DISABLED_TOOLS, [])),
    )
