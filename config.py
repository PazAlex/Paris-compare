"""
Pricing configuration for Paris transport options
"""

# Metro pricing
METRO_COST = 2.50  # € per trip

# E-bike providers pricing
BIKE_PROVIDERS = {
    "Voi": {
        "unlock": 1.00,
        "per_minute": 0.19,
        "passes": [
            {"minutes": 30, "cost": 2.99},
            {"minutes": 60, "cost": 5.49},
            {"minutes": 120, "cost": 10.99},
            {"minutes": 200, "cost": 16.99},
            {"minutes": 400, "cost": 31.99}
        ]
    },
    "Dott": {
        "unlock": 1.00,
        "per_minute": 0.28,
        "passes": [
            {"minutes": 30, "cost": 3.99},
            {"minutes": 100, "cost": 11.99}
        ]
    },
    "Lime": {
        "unlock": 1.00,
        "per_minute": 0.23,
        "passes": [
            {"minutes": 30, "cost": 3.99},
            {"minutes": 60, "cost": 6.99},
            {"minutes": 200, "cost": 21.99},
            {"minutes": 400, "cost": 39.99}
        ]
    },
    "Velib'": {
        "unlock": 0.00,
        "per_minute": None,
        "passes": [
            {"name": "Ticket V", "minutes": 45, "cost": 3.00, "overage_per_30min": 2.00, "type": "single"},
            {"name": "24h Pass", "minutes": 45, "cost": 10.00, "trips": 5, "overage_per_30min": 2.00, "type": "multi"}
        ]
    }
}

# Geovelo API settings
GEOVELO_BIKE_PROFILE = "MEDIAN"
GEOVELO_EBIKE = True  # All providers use electric bikes
GEOVELO_BIKE_TYPE = "BSS"  # Bike sharing system

# API endpoints
NAVITIA_ENDPOINT = "https://prim.iledefrance-mobilites.fr/marketplace/v2/navitia"
GEOVELO_ENDPOINT = "https://prim.iledefrance-mobilites.fr/marketplace/computedroutes"
