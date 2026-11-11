"""Constants for E.ON Smart Charging integration."""

DOMAIN = "eon_smart_charging"

# OAuth 2.0 Credentials & Endpoints
OAUTH_AUTHORIZE_URL = "https://crm.eon.de/services/oauth2/authorize"
OAUTH_TOKEN_URL = "https://crm.eon.de/services/oauth2/token"
OAUTH_CLIENT_ID = "3MVG9HxRZv05HarQJF.yfFT6ufYGybYqUcQ.rU_F0ghcQ7OqHwChUXNXJYRoc7W2KMucU3kOkdD8HBd.ohais"
OAUTH_REDIRECT_URI = "meineonandroid://auth/success/auth0"
OAUTH_SCOPES = "refresh_token openid profile api email offline_access"

# API Endpoints
DEFAULT_FEH_BASE_URL = "https://one.api.feh.eon.de/dashboard"
DEFAULT_FEH_TOKEN_URL = "https://one.api.feh.eon.de/oauth2/token"

# Config entries
CONF_CALLBACK_URL = "callback_url"
CONF_HEMS_TOKEN = "hems_token"
CONF_B2C_TOKEN = "b2c_token"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_CONFIG_ID = "config_id"
CONF_DEVICE_TYPE = "device_type"
CONF_DEVICE_NAME = "device_name"

DEVICE_TYPE_CAR = "electric_car"
DEVICE_TYPE_WALLBOX = "wallbox"

# Modes
MODE_OFF = "Aus"
MODE_SMART = "Smart Laden (Autopilot)"
MODE_NORMAL = "Normal Laden (Sofort)"
MODE_SOLAR = "Solar Laden"

MODES_CAR = [MODE_OFF, MODE_SMART, MODE_NORMAL]
MODES_WALLBOX = [MODE_OFF, MODE_SMART, MODE_NORMAL]

# Update Interval
DEFAULT_SCAN_INTERVAL_SECONDS = 60
