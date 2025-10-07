"""
Pricing configuration for Paris transport options
"""

# Metro pricing
METRO_COST = 2.50  # € per trip

# E-bike providers pricing
# Format: {"provider": {"unlock": €, "per_minute": €, "pass_30min": €}}
BIKE_PROVIDERS = {
    "Voi": {
        "unlock": 0.00,
        "per_minute": 0.25,
        "pass_30min": 0.10
    },
    "Dott": {
        "unlock": 1.00,
        "per_minute": 0.35,
        "pass_30min": 0.13
    },
    "Lime": {
        "unlock": 1.00,
        "per_minute": 0.28,
        "pass_30min": 0.13
    },
    "Velib'": {
        "unlock": 0.00,  # With 30min pass
        "per_minute": None,  # Not applicable
        "pass_30min": 0.10
    }
}

# Geovelo API settings
GEOVELO_BIKE_PROFILE = "MEDIAN"
GEOVELO_EBIKE = True  # All providers use electric bikes
GEOVELO_BIKE_TYPE = "BSS"  # Bike sharing system

# API endpoints
NAVITIA_ENDPOINT = "https://prim.iledefrance-mobilites.fr/marketplace/v2/navitia"
GEOVELO_ENDPOINT = "https://prim.iledefrance-mobilites.fr/marketplace/computedroutes"
