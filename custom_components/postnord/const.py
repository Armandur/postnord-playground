"""Constants for the PostNord integration."""

DOMAIN = "postnord"

# Config entry data keys
CONF_API_KEY = "api_key"
CONF_POSTAL_CODE = "postal_code"

# Package config keys (stored in options)
CONF_PACKAGES = "packages"
CONF_TRACKING_ID = "tracking_id"
CONF_DISPLAY_NAME = "display_name"
CONF_OWNER = "owner"
CONF_COUNTRY = "country"

# Options
CONF_UPDATE_INTERVAL = "update_interval_minutes"
DEFAULT_UPDATE_INTERVAL = 30
MIN_UPDATE_INTERVAL_MINUTES = 5

# Countries
DEFAULT_COUNTRY = "SE"
SUPPORTED_COUNTRIES = ["SE", "NO", "FI", "DK"]

# Delivery types
DELIVERY_TYPE_SERVICE_POINT = "SERVICE_POINT"
DELIVERY_TYPE_PARCEL_BOX = "PARCEL_BOX"
DELIVERY_TYPE_HOME = "HOME"
DELIVERY_TYPE_MAILBOX = "MAILBOX"
DELIVERY_TYPE_UNKNOWN = "UNKNOWN"

# Sensor attribute keys
ATTR_TRACKING_ID = "tracking_id"
ATTR_OWNER = "owner"
ATTR_TRACKING_URL = "tracking_url"
ATTR_STATUS_HEADER = "status_header"
ATTR_STATUS_BODY = "status_body"
ATTR_ETA = "eta"
ATTR_PUBLIC_ETA = "public_eta"
ATTR_ETA_TIMESTAMP = "eta_timestamp"
ATTR_DELIVERY_DATE = "delivery_date"
ATTR_RISK_FOR_DELAY = "risk_for_delay"
ATTR_IS_DELAYED = "is_delayed"
ATTR_SENDER = "sender"
ATTR_SERVICE = "service"
ATTR_DELIVERY_TYPE = "delivery_type"
ATTR_PICKUP_LOCATION = "pickup_location"
ATTR_LAST_EVENT = "last_event"
ATTR_COUNTRY = "country"
ATTR_ARCHIVED = "archived"
