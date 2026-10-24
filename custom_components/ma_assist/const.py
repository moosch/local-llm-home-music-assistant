"""Constants for the Music Assistant Voice Tools integration."""

DOMAIN = "ma_assist"
MUSIC_ASSISTANT_DOMAIN = "music_assistant"
MEDIA_PLAYER_DOMAIN = "media_player"

CONF_MUSIC_ASSISTANT_ENTRY_ID = "music_assistant_entry_id"
CONF_DEFAULT_PLAYER = "default_player"
CONF_ROOM_ALIASES = "room_aliases"
CONF_DISABLED_TOOLS = "disabled_tools"

TOOL_PLAY_MUSIC = "play_music"
TOOL_MEDIA_CONTROL = "media_control"
TOOL_SET_VOLUME = "set_volume"
ALL_TOOLS = [TOOL_PLAY_MUSIC, TOOL_MEDIA_CONTROL, TOOL_SET_VOLUME]

MEDIA_TYPES = ["track", "album", "artist", "playlist", "radio"]
ENQUEUE_OPTIONS = ["play", "next", "add"]

# "Turn it up a bit": a tenth of the player's volume range.
VOLUME_STEP = 0.1
