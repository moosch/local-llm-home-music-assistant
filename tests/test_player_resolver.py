"""Tests for resolving spoken rooms to Music Assistant players."""

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ma_assist.player_resolver import (
    PlayerNotFoundError,
    available_rooms,
    resolve_control_player,
    resolve_player,
)
from custom_components.ma_assist.settings import (
    InvalidAliasesError,
    MaAssistSettings,
    parse_room_aliases,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar, device_registry as dr

from .conftest import PlayerFactory, add_satellite


def make_settings(
    entry: MockConfigEntry,
    default_player: str | None = None,
    room_aliases: dict[str, str] | None = None,
) -> MaAssistSettings:
    return MaAssistSettings(
        music_assistant_entry_id=entry.entry_id,
        default_player=default_player,
        room_aliases=room_aliases or {},
    )


async def test_resolves_area_name_case_insensitively(
    hass: HomeAssistant,
    music_assistant_entry: MockConfigEntry,
    players: PlayerFactory,
    office: ar.AreaEntry,
) -> None:
    player = players.add(music_assistant_entry, "Office WiiM", office.id)
    settings = make_settings(music_assistant_entry)

    assert resolve_player(hass, settings, "office", None) == player
    assert resolve_player(hass, settings, "  OFFICE ", None) == player


async def test_resolves_home_assistant_area_alias(
    hass: HomeAssistant,
    music_assistant_entry: MockConfigEntry,
    players: PlayerFactory,
    office: ar.AreaEntry,
) -> None:
    player = players.add(music_assistant_entry, "Office WiiM", office.id)

    assert (
        resolve_player(hass, make_settings(music_assistant_entry), "Study", None)
        == player
    )


async def test_configured_room_alias_wins(
    hass: HomeAssistant,
    music_assistant_entry: MockConfigEntry,
    players: PlayerFactory,
    office: ar.AreaEntry,
) -> None:
    players.add(music_assistant_entry, "Office WiiM", office.id)
    den_speaker = players.add(music_assistant_entry, "Den Speaker")
    settings = make_settings(music_assistant_entry, room_aliases={"den": den_speaker})

    assert resolve_player(hass, settings, "Den", None) == den_speaker


async def test_alias_to_native_entity_is_an_error(
    hass: HomeAssistant,
    music_assistant_entry: MockConfigEntry,
    players: PlayerFactory,
    office: ar.AreaEntry,
) -> None:
    native_entry = MockConfigEntry(domain="sonos")
    native_entry.add_to_hass(hass)
    native = players.add(native_entry, "Lounge Sonos", platform="sonos")
    settings = make_settings(music_assistant_entry, room_aliases={"lounge": native})

    with pytest.raises(PlayerNotFoundError, match="not a Music Assistant player"):
        resolve_player(hass, settings, "lounge", None)


async def test_ignores_native_duplicate_players(
    hass: HomeAssistant,
    music_assistant_entry: MockConfigEntry,
    players: PlayerFactory,
    office: ar.AreaEntry,
) -> None:
    native_entry = MockConfigEntry(domain="linkplay")
    native_entry.add_to_hass(hass)
    players.add(native_entry, "WiiM Native", office.id, platform="linkplay")
    player = players.add(music_assistant_entry, "Office WiiM", office.id)

    assert (
        resolve_player(hass, make_settings(music_assistant_entry), "office", None)
        == player
    )


async def test_matches_player_name_without_area(
    hass: HomeAssistant,
    music_assistant_entry: MockConfigEntry,
    players: PlayerFactory,
) -> None:
    player = players.add(music_assistant_entry, "Garage")

    assert (
        resolve_player(hass, make_settings(music_assistant_entry), "garage", None)
        == player
    )


async def test_falls_back_to_satellite_area(
    hass: HomeAssistant,
    music_assistant_entry: MockConfigEntry,
    players: PlayerFactory,
    device_registry: dr.DeviceRegistry,
    office: ar.AreaEntry,
    kitchen: ar.AreaEntry,
) -> None:
    players.add(music_assistant_entry, "Office WiiM", office.id)
    kitchen_player = players.add(music_assistant_entry, "Kitchen Speaker", kitchen.id)
    satellite_id = add_satellite(hass, device_registry, kitchen.id)

    settings = make_settings(music_assistant_entry)

    assert resolve_player(hass, settings, None, satellite_id) == kitchen_player


async def test_falls_back_to_default_player(
    hass: HomeAssistant,
    music_assistant_entry: MockConfigEntry,
    players: PlayerFactory,
    office: ar.AreaEntry,
) -> None:
    player = players.add(music_assistant_entry, "Office WiiM", office.id)
    settings = make_settings(music_assistant_entry, default_player=player)

    assert resolve_player(hass, settings, None, None) == player


async def test_no_room_and_no_default_lists_rooms(
    hass: HomeAssistant,
    music_assistant_entry: MockConfigEntry,
    players: PlayerFactory,
    office: ar.AreaEntry,
    kitchen: ar.AreaEntry,
) -> None:
    players.add(music_assistant_entry, "Office WiiM", office.id)
    players.add(music_assistant_entry, "Kitchen Speaker", kitchen.id)

    with pytest.raises(PlayerNotFoundError, match="Kitchen, Office"):
        resolve_player(hass, make_settings(music_assistant_entry), None, None)


async def test_unknown_room_lists_rooms(
    hass: HomeAssistant,
    music_assistant_entry: MockConfigEntry,
    players: PlayerFactory,
    office: ar.AreaEntry,
) -> None:
    players.add(music_assistant_entry, "Office WiiM", office.id)

    with pytest.raises(PlayerNotFoundError, match="'attic'.*Office"):
        resolve_player(hass, make_settings(music_assistant_entry), "attic", None)


async def test_several_players_in_room_is_ambiguous(
    hass: HomeAssistant,
    music_assistant_entry: MockConfigEntry,
    players: PlayerFactory,
    office: ar.AreaEntry,
) -> None:
    players.add(music_assistant_entry, "Office WiiM", office.id)
    players.add(music_assistant_entry, "Office Sonos", office.id)

    with pytest.raises(PlayerNotFoundError, match="Several players"):
        resolve_player(hass, make_settings(music_assistant_entry), "office", None)


async def test_default_player_breaks_ties(
    hass: HomeAssistant,
    music_assistant_entry: MockConfigEntry,
    players: PlayerFactory,
    office: ar.AreaEntry,
) -> None:
    players.add(music_assistant_entry, "Office WiiM", office.id)
    sonos = players.add(music_assistant_entry, "Office Sonos", office.id)
    settings = make_settings(music_assistant_entry, default_player=sonos)

    assert resolve_player(hass, settings, "office", None) == sonos


async def test_available_rooms(
    hass: HomeAssistant,
    music_assistant_entry: MockConfigEntry,
    players: PlayerFactory,
    office: ar.AreaEntry,
) -> None:
    players.add(music_assistant_entry, "Office WiiM", office.id)
    players.add(music_assistant_entry, "Garage")
    settings = make_settings(
        music_assistant_entry, room_aliases={"den": "media_player.den_speaker"}
    )

    assert available_rooms(hass, settings) == ["Garage", "Office", "den"]


async def test_control_pauses_playing_and_resumes_paused_players(
    hass: HomeAssistant,
    music_assistant_entry: MockConfigEntry,
    players: PlayerFactory,
    device_registry: dr.DeviceRegistry,
    office: ar.AreaEntry,
    kitchen: ar.AreaEntry,
) -> None:
    office_player = players.add(
        music_assistant_entry, "Office WiiM", office.id, state="playing"
    )
    kitchen_player = players.add(
        music_assistant_entry, "Kitchen Speaker", kitchen.id, state="paused"
    )
    satellite_id = add_satellite(hass, device_registry, kitchen.id)
    settings = make_settings(music_assistant_entry)

    assert resolve_control_player(hass, settings, None, satellite_id) == office_player
    assert (
        resolve_control_player(hass, settings, None, satellite_id, resuming=True)
        == kitchen_player
    )


async def test_control_reaches_the_only_active_player(
    hass: HomeAssistant,
    music_assistant_entry: MockConfigEntry,
    players: PlayerFactory,
    device_registry: dr.DeviceRegistry,
    office: ar.AreaEntry,
    kitchen: ar.AreaEntry,
) -> None:
    office_player = players.add(
        music_assistant_entry, "Office WiiM", office.id, state="playing"
    )
    players.add(music_assistant_entry, "Kitchen Speaker", kitchen.id)
    satellite_id = add_satellite(hass, device_registry, kitchen.id)
    settings = make_settings(music_assistant_entry)

    assert resolve_control_player(hass, settings, None, satellite_id) == office_player


async def test_control_asks_when_several_are_playing(
    hass: HomeAssistant,
    music_assistant_entry: MockConfigEntry,
    players: PlayerFactory,
    device_registry: dr.DeviceRegistry,
    office: ar.AreaEntry,
    kitchen: ar.AreaEntry,
    area_registry: ar.AreaRegistry,
) -> None:
    lounge = area_registry.async_create("Lounge")
    players.add(music_assistant_entry, "Office WiiM", office.id, state="playing")
    players.add(music_assistant_entry, "Lounge Sonos", lounge.id, state="playing")
    players.add(music_assistant_entry, "Kitchen Speaker", kitchen.id)
    satellite_id = add_satellite(hass, device_registry, kitchen.id)
    settings = make_settings(music_assistant_entry)

    with pytest.raises(
        PlayerNotFoundError, match="several players: Office WiiM, Lounge Sonos"
    ):
        resolve_control_player(hass, settings, None, satellite_id)


async def test_control_prefers_playing_over_paused(
    hass: HomeAssistant,
    music_assistant_entry: MockConfigEntry,
    players: PlayerFactory,
    office: ar.AreaEntry,
    kitchen: ar.AreaEntry,
) -> None:
    office_player = players.add(
        music_assistant_entry, "Office WiiM", office.id, state="playing"
    )
    players.add(music_assistant_entry, "Kitchen Speaker", kitchen.id, state="paused")
    settings = make_settings(music_assistant_entry)

    assert resolve_control_player(hass, settings, None, None) == office_player


async def test_control_prefers_playing_player_in_satellite_room(
    hass: HomeAssistant,
    music_assistant_entry: MockConfigEntry,
    players: PlayerFactory,
    device_registry: dr.DeviceRegistry,
    office: ar.AreaEntry,
    kitchen: ar.AreaEntry,
) -> None:
    players.add(music_assistant_entry, "Office WiiM", office.id, state="playing")
    kitchen_player = players.add(
        music_assistant_entry, "Kitchen Speaker", kitchen.id, state="playing"
    )
    satellite_id = add_satellite(hass, device_registry, kitchen.id)
    settings = make_settings(music_assistant_entry)

    assert resolve_control_player(hass, settings, None, satellite_id) == kitchen_player


async def test_control_in_named_room_picks_the_playing_player(
    hass: HomeAssistant,
    music_assistant_entry: MockConfigEntry,
    players: PlayerFactory,
    office: ar.AreaEntry,
) -> None:
    players.add(music_assistant_entry, "Office WiiM", office.id)
    sonos = players.add(
        music_assistant_entry, "Office Sonos", office.id, state="playing"
    )
    settings = make_settings(music_assistant_entry)

    assert resolve_control_player(hass, settings, "office", None) == sonos


async def test_control_with_named_room_ignores_activity(
    hass: HomeAssistant,
    music_assistant_entry: MockConfigEntry,
    players: PlayerFactory,
    office: ar.AreaEntry,
    kitchen: ar.AreaEntry,
) -> None:
    players.add(music_assistant_entry, "Office WiiM", office.id, state="playing")
    kitchen_player = players.add(music_assistant_entry, "Kitchen Speaker", kitchen.id)
    settings = make_settings(music_assistant_entry)

    assert resolve_control_player(hass, settings, "kitchen", None) == kitchen_player


def test_parse_room_aliases() -> None:
    text = "Office: media_player.wiim_office\n\n  Living  Room : media_player.lounge\n"

    assert parse_room_aliases(text) == {
        "office": "media_player.wiim_office",
        "living room": "media_player.lounge",
    }


@pytest.mark.parametrize(
    "text", ["office media_player.wiim", ": media_player.wiim", "office: light.desk"]
)
def test_parse_room_aliases_rejects_bad_lines(text: str) -> None:
    with pytest.raises(InvalidAliasesError):
        parse_room_aliases(text)
