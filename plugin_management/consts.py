# This module's package.
PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")

# Installed plugin packages advertise this entry-point group and ship this
# TOML manifest (see PLUGIN_DEVELOPMENT.md).
ENTRY_POINT_GROUP = "microdrop.plugins"
MANIFEST_RESOURCE = "microdrop_plugin.toml"

# The hosted conda channel Browse Plugins installs from.
PLUGIN_CHANNEL_URL = "https://prefix.dev/microdrop-plugins"

# Built-in toggleable plugin groups. EMPTY since the device stacks (heater,
# magnet/Z-Stage) were extracted into standalone installable packages
# (heater-microdrop-plugin, magnet-microdrop-plugin) — every group now comes
# from an installed package's microdrop_plugin.toml manifest, discovered via
# the microdrop.plugins entry point. The tuple stays as the seam for any
# future group that genuinely ships inside the app itself.
BUILTIN_PLUGIN_GROUPS = ()

# Application-preferences node holding each group's persisted enabled flag
# (full path: f"{GROUP_ENABLED_PREFERENCES_PATH}.{enabled_key}"). The flags
# must live in the preferences FILE — the Redis-backed app_globals runs with
# persistence disabled (redis.conf: save "") and dies with the app.
GROUP_ENABLED_PREFERENCES_PATH = "microdrop.plugin_groups"
