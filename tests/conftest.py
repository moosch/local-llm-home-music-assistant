"""Shared fixtures for ma_assist tests."""

from dataclasses import dataclass

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    MockModule,
    mock_integration,
)

from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    return


@pytest.fixture(autouse=True)
def mock_music_assistant(hass: HomeAssistant) -> None:
    # The real integration drags in tts, mutagen and a live MA client.
    mock_integration(hass, MockModule("music_assistant"))


@dataclass
class PlayerFactory:
    hass: HomeAssistant
    device_registry: dr.DeviceRegistry
    entity_registry: er.EntityRegistry

    def add(
        self,
        config_entry: MockConfigEntry,
        name: str,
        area_id: str | None = None,
        platform: str = "music_assistant",
        state: str = "idle",
        volume_level: float | None = None,
    ) -> str:
        device = self.device_registry.async_get_or_create(
            config_entry_id=config_entry.entry_id,
            identifiers={(platform, name)},
            name=name,
        )
        if area_id is not None:
            self.device_registry.async_update_device(device.id, area_id=area_id)
        entity = self.entity_registry.async_get_or_create(
            "media_player",
            platform,
            name,
            config_entry=config_entry,
            device_id=device.id,
        )
        attributes: dict[str, object] = {"friendly_name": name}
        if volume_level is not None:
            attributes["volume_level"] = volume_level
        self.hass.states.async_set(entity.entity_id, state, attributes)
        return entity.entity_id


@pytest.fixture
def music_assistant_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain="music_assistant")
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def players(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> PlayerFactory:
    return PlayerFactory(hass, device_registry, entity_registry)


@pytest.fixture
def office(area_registry: ar.AreaRegistry) -> ar.AreaEntry:
    return area_registry.async_create("Office", aliases={"study"})


@pytest.fixture
def kitchen(area_registry: ar.AreaRegistry) -> ar.AreaEntry:
    return area_registry.async_create("Kitchen")


def add_satellite(
    hass: HomeAssistant, device_registry: dr.DeviceRegistry, area_id: str
) -> str:
    satellite_entry = MockConfigEntry(domain="esphome")
    satellite_entry.add_to_hass(hass)
    satellite = device_registry.async_get_or_create(
        config_entry_id=satellite_entry.entry_id,
        identifiers={("esphome", f"satellite-{area_id}")},
    )
    device_registry.async_update_device(satellite.id, area_id=area_id)
    return satellite.id
