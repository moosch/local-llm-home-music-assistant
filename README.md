# Music Assistant Voice Tools

A Home Assistant custom integration (`ma_assist`) that gives LLM conversation agents
room-aware control of [Music Assistant](https://www.music-assistant.io/), using Home
Assistant's native LLM Tools API.

> "Play my Dinner Playlist in the office" · "Play Hot Potato by The Wiggles"

## Requirements

- Home Assistant **2026.10** or newer
- The Music Assistant integration, set up and connected to an MA 2.4+ server
- A conversation agent that supports LLM APIs (e.g. Local OpenAI LLM, Ollama, OpenAI)
  and a model that emits real tool calls

## Install

Install through [HACS](https://hacs.xyz/) as a custom repository:

1. In Home Assistant, open **HACS → ⋮ (top right) → Custom repositories**.
2. Paste `https://github.com/moosch/local-llm-home-music-assistant`, set the type to
   **Integration**, and click **Add**.
3. Find **Music Assistant Voice Tools** in HACS and click **Download**.
4. Restart Home Assistant.
5. Go to **Settings → Devices & services → Add integration** and search for
   **Music Assistant Voice Tools**.
6. In your conversation agent's options, enable **Music Assistant** under the
   "Control Home Assistant" LLM APIs.

HACS will flag new versions as updates. After downloading one, restart Home Assistant
to load it.

## How rooms are resolved

When the model passes an `area`, it's matched, in order, against:

1. Room aliases configured in this integration's options
2. Home Assistant area names and area aliases
3. Music Assistant player names

If no `area` is given, the player in the voice satellite's area is used, then the
configured default player. Only Music Assistant's own `media_player` entities are
considered, not the native duplicates (e.g. the WiiM entity).

## Options

- **Default player**: used when there's no room to go on, or a room has several players.
- **Room aliases**: one per line, `spoken name: media_player.entity_id`.

## Tools

| Tool | Status |
|------|--------|
| `play_music` | ✅ |
| `media_control`, `set_volume` | planned (M2) |
| `search_music`, `whats_playing` | planned (M3) |

## Development

```sh
python3.14 -m venv .venv
.venv/bin/pip install pytest-homeassistant-custom-component
.venv/bin/pytest
```
