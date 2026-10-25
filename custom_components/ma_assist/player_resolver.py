"""Resolve a spoken room name to a single Music Assistant media_player entity."""

from homeassistant.components.media_player import MediaPlayerState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
)

from .const import MEDIA_PLAYER_DOMAIN
from .settings import MaAssistSettings, normalize_room_name

PLAYING_STATES = {MediaPlayerState.PLAYING, MediaPlayerState.BUFFERING}
PAUSED_STATES = {MediaPlayerState.PAUSED}


class PlayerNotFoundError(HomeAssistantError):
    """No single Music Assistant player matches the request."""


def resolve_player(
    hass: HomeAssistant,
    settings: MaAssistSettings,
    room: str | None,
    device_id: str | None,
) -> str:
    if room is not None:
        return resolve_named_room(hass, settings, room)

    satellite_area_id = device_area_id(hass, device_id)
    if satellite_area_id is not None:
        candidates = players_in_area(hass, settings, satellite_area_id)
        if candidates:
            return choose_player(hass, settings, candidates, "this room")

    if settings.default_player is not None:
        return settings.default_player

    rooms = ", ".join(available_rooms(hass, settings))
    raise PlayerNotFoundError(f"No room given. Ask which room: {rooms}.")


def resolve_control_player(
    hass: HomeAssistant,
    settings: MaAssistSettings,
    room: str | None,
    device_id: str | None,
    resuming: bool = False,
) -> str:
    """Like resolve_player, but prefers players that are actually in use.

    "Pause the music" should reach the one speaker that's playing, even when
    the user is talking to a satellite in a quiet room.
    """
    if room is not None:
        candidates = named_room_players(hass, settings, room)
        in_use = in_use_players(hass, candidates, resuming)
        return choose_player(hass, settings, in_use or candidates, room)

    nearby = in_use_nearby(hass, settings, device_id, resuming)
    if len(nearby) == 1:
        return nearby[0]
    if settings.default_player in nearby:
        return settings.default_player
    if nearby:
        names = ", ".join(player_name(hass, entity_id) for entity_id in nearby)
        raise PlayerNotFoundError(
            f"Music is playing on several players: {names}. Ask which one."
        )

    return resolve_player(hass, settings, None, device_id)


def in_use_nearby(
    hass: HomeAssistant,
    settings: MaAssistSettings,
    device_id: str | None,
    resuming: bool = False,
) -> list[str]:
    """In-use players in the satellite's room if there are any, else anywhere."""
    all_players = [
        player.entity_id for player in music_assistant_players(hass, settings)
    ]
    in_use = in_use_players(hass, all_players, resuming)

    satellite_area_id = device_area_id(hass, device_id)
    if satellite_area_id is None:
        return in_use
    in_use_here = [
        entity_id
        for entity_id in players_in_area(hass, settings, satellite_area_id)
        if entity_id in in_use
    ]
    return in_use_here or in_use


def resolve_named_room(
    hass: HomeAssistant, settings: MaAssistSettings, room: str
) -> str:
    candidates = named_room_players(hass, settings, room)
    return choose_player(hass, settings, candidates, room)


def named_room_players(
    hass: HomeAssistant, settings: MaAssistSettings, room: str
) -> list[str]:
    alias_target = settings.room_aliases.get(normalize_room_name(room))
    if alias_target is not None:
        if not is_music_assistant_player(hass, settings, alias_target):
            raise PlayerNotFoundError(
                f"The alias for '{room}' points to {alias_target}, "
                "which is not a Music Assistant player."
            )
        return [alias_target]

    area_id = find_area_id(hass, room)
    if area_id is not None:
        candidates = players_in_area(hass, settings, area_id)
        if candidates:
            return candidates

    candidates = players_named(hass, settings, room)
    if candidates:
        return candidates

    rooms = ", ".join(available_rooms(hass, settings))
    raise PlayerNotFoundError(
        f"No player found for '{room}'. Available rooms: {rooms}."
    )


def in_use_players(
    hass: HomeAssistant, entity_ids: list[str], resuming: bool
) -> list[str]:
    """Playing players, or paused ones first when the user wants to resume."""
    preferred, fallback = PLAYING_STATES, PAUSED_STATES
    if resuming:
        preferred, fallback = PAUSED_STATES, PLAYING_STATES
    matches = players_in_states(hass, entity_ids, preferred)
    if matches:
        return matches
    return players_in_states(hass, entity_ids, fallback)


def players_in_states(
    hass: HomeAssistant, entity_ids: list[str], states: set[MediaPlayerState]
) -> list[str]:
    matches: list[str] = []
    for entity_id in entity_ids:
        state = hass.states.get(entity_id)
        if state is not None and state.state in states:
            matches.append(entity_id)
    return matches


def choose_player(
    hass: HomeAssistant,
    settings: MaAssistSettings,
    candidates: list[str],
    room: str,
) -> str:
    if len(candidates) == 1:
        return candidates[0]
    if settings.default_player in candidates:
        return settings.default_player
    names = ", ".join(player_name(hass, entity_id) for entity_id in candidates)
    raise PlayerNotFoundError(f"Several players in {room}: {names}. Ask which one.")


def music_assistant_players(
    hass: HomeAssistant, settings: MaAssistSettings
) -> list[er.RegistryEntry]:
    # Filtering by the MA config entry skips the native duplicates (e.g. the
    # WiiM entity), which music_assistant.* actions reject.
    entity_registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(
        entity_registry, settings.music_assistant_entry_id
    )
    players: list[er.RegistryEntry] = []
    for entry in entries:
        if entry.domain == MEDIA_PLAYER_DOMAIN and not entry.disabled:
            players.append(entry)
    return players


def players_in_area(
    hass: HomeAssistant, settings: MaAssistSettings, area_id: str
) -> list[str]:
    matches: list[str] = []
    for player in music_assistant_players(hass, settings):
        if player_area_id(hass, player) == area_id:
            matches.append(player.entity_id)
    return matches


def is_music_assistant_player(
    hass: HomeAssistant, settings: MaAssistSettings, entity_id: str
) -> bool:
    # music_assistant.* actions silently skip other entities, so a wrong
    # target would look like success.
    for player in music_assistant_players(hass, settings):
        if player.entity_id == entity_id:
            return True
    return False


def players_named(
    hass: HomeAssistant, settings: MaAssistSettings, name: str
) -> list[str]:
    wanted = normalize_room_name(name)
    matches: list[str] = []
    for player in music_assistant_players(hass, settings):
        if normalize_room_name(player_name(hass, player.entity_id)) == wanted:
            matches.append(player.entity_id)
    return matches


def player_area_id(hass: HomeAssistant, player: er.RegistryEntry) -> str | None:
    if player.area_id is not None:
        return player.area_id
    return device_area_id(hass, player.device_id)


def device_area_id(hass: HomeAssistant, device_id: str | None) -> str | None:
    if device_id is None:
        return None
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        return None
    return device.area_id


def find_area_id(hass: HomeAssistant, room: str) -> str | None:
    wanted = normalize_room_name(room)
    for area in ar.async_get(hass).async_list_areas():
        names = [area.name, *area.aliases]
        for name in names:
            if normalize_room_name(name) == wanted:
                return area.id
    return None


def player_name(hass: HomeAssistant, entity_id: str) -> str:
    state = hass.states.get(entity_id)
    if state is None:
        return entity_id
    return state.name


def available_rooms(hass: HomeAssistant, settings: MaAssistSettings) -> list[str]:
    """Room names the model may pass as `area`, for prompts and error messages."""
    area_registry = ar.async_get(hass)
    rooms: set[str] = set(settings.room_aliases)
    for player in music_assistant_players(hass, settings):
        area_id = player_area_id(hass, player)
        area = area_registry.async_get_area(area_id) if area_id else None
        if area is None:
            rooms.add(player_name(hass, player.entity_id))
        else:
            rooms.add(area.name)
    return sorted(rooms)
