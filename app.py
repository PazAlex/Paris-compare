"""
Paris Metro vs E-Bike Comparison Tool
Streamlit web interface
"""

import streamlit as st
import requests
import os
import folium
from streamlit_folium import st_folium
from dotenv import load_dotenv
from config import METRO_COST, BIKE_PROVIDERS, GEOVELO_ENDPOINT, NAVITIA_ENDPOINT
import json

# Paris boundary polygon
PARIS_BOUNDARY = {
    "type": "Feature",
    "geometry": {
        "type": "Polygon",
        "coordinates": [[[2.3198871747441,48.90045978209],[2.3851496429397,48.902007785215],[2.394906293421,48.898444039523],[2.3988455271816,48.887109095072],[2.4132702557262,48.872892145992],[2.4163411302989,48.849233783552],[2.4122456125626,48.834538914673],[2.4221386362435,48.835797660955],[2.4281301699852,48.841528392473],[2.447699326814,48.844818443355],[2.4634383121686,48.842089485269],[2.4675819883673,48.833133318793],[2.4626960627524,48.819059770564],[2.4384475102742,48.818232447877],[2.406031823401,48.827615470779],[2.3909392530738,48.826078980076],[2.363946550191,48.816314210034],[2.3318980606376,48.817010929642],[2.2921959226619,48.82714160912],[2.2790519306533,48.832489952145],[2.2727931901868,48.827920084226],[2.2551442384175,48.834809549369],[2.2506124417162,48.845554851211],[2.2242191058804,48.853516917557],[2.2317363597469,48.86906858161],[2.2584671711142,48.880387263086],[2.2774870298138,48.877968320853],[2.2915068524977,48.8894718708],[2.3198871747441,48.90045978209]]]
    },
    "properties": {"code": "75", "nom": "Paris"}
}

# Load API key - try Streamlit secrets first, then fall back to .env
try:
    API_KEY = st.secrets["PRIM_API_KEY"]
except:
    load_dotenv()
    API_KEY = os.getenv('PRIM_API_KEY')

# Initialize session state for map selections
if 'origin' not in st.session_state:
    st.session_state.origin = None
if 'destination' not in st.session_state:
    st.session_state.destination = None
if 'last_clicked' not in st.session_state:
    st.session_state.last_clicked = None
if 'results' not in st.session_state:
    st.session_state.results = None

# Page config
st.set_page_config(
    page_title="Paris: Metro vs E-Bike",
    page_icon="🚇",
    layout="wide"
)

# Title and description
st.title("🚇 🚴 Paris: Metro vs Bikeshare Comparisonerizer 9001")
st.markdown("""
Compare travel time and cost between taking the metro or riding a shared e-bike in Paris.
**Click on the map to select your origin and destination.**
""")

# Author credit
st.info("""
👋 This app was built in a few hours by **Alex Pazuchanics** from **Jump Seat Strategies**.  
Interested in collaborating on something similar? [Reach out on LinkedIn!](https://www.linkedin.com/in/pazuchanics/)
""")

# Helper functions
def calculate_all_bike_costs(duration_minutes, provider):
    """Calculate all pricing options for a provider
    
    Returns: list of dicts with pricing info
    """
    import math
    
    pricing = BIKE_PROVIDERS[provider]
    options = []
    
    # Per-minute pricing
    if pricing["per_minute"] is not None:
        cost = pricing["unlock"] + (duration_minutes * pricing["per_minute"])
        options.append({
            "name": "Per-minute",
            "cost": cost,
            "remaining": None,
            "remaining_type": None
        })
    
    # Pass options
    if provider == "Velib'":
        # Velib' special handling
        for pass_option in pricing["passes"]:
            overage_blocks = 0
            if duration_minutes > pass_option["minutes"]:
                overage_minutes = duration_minutes - pass_option["minutes"]
                overage_blocks = math.ceil(overage_minutes / 30)
            
            if pass_option["type"] == "single":
                # Ticket V - single trip
                cost = pass_option["cost"] + (overage_blocks * pass_option["overage_per_30min"])
                options.append({
                    "name": pass_option["name"],
                    "cost": cost,
                    "remaining": 0,
                    "remaining_type": "trips"
                })
            else:
                # 24h Pass - effective cost per trip
                cost_per_trip = pass_option["cost"] / pass_option["trips"]
                cost = cost_per_trip + (overage_blocks * pass_option["overage_per_30min"])
                options.append({
                    "name": pass_option["name"],
                    "cost": cost,
                    "remaining": pass_option["trips"] - 1,  # 4 trips left
                    "remaining_type": "trips"
                })
    else:
        # Voi, Dott, Lime - pass bundles with carryover
        for pass_option in pricing["passes"]:
            if duration_minutes <= pass_option["minutes"]:
                # Trip fits in pass - prorate cost
                cost_per_minute = pass_option["cost"] / pass_option["minutes"]
                cost = duration_minutes * cost_per_minute
                remaining = pass_option["minutes"] - duration_minutes
            else:
                # Trip exceeds pass - charge marginal minutes at per-minute rate
                cost = pass_option["cost"] + ((duration_minutes - pass_option["minutes"]) * pricing["per_minute"])
                remaining = 0
            
            options.append({
                "name": f"{pass_option['minutes']} min pass",
                "cost": cost,
                "remaining": remaining,
                "remaining_type": "minutes"
            })
    
    return options

def get_metro_journey(from_coords, to_coords):
    """Get metro journey from Navitia API"""
    url = f"{NAVITIA_ENDPOINT}/journeys"
    params = {
        "from": f"{from_coords[1]};{from_coords[0]}",  # lon;lat
        "to": f"{to_coords[1]};{to_coords[0]}"
    }
    headers = {"apikey": API_KEY}
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if data.get('journeys'):
            journey = data['journeys'][0]
            duration_sec = journey.get('duration', 0)
            transfers = journey.get('nb_transfers', 0)
            
            # Extract route sections for visualization
            sections = journey.get('sections', [])
            
            # Calculate time breakdown
            walking_time = 0
            transfer_time = 0
            public_transport_time = 0
            waiting_time = 0
            
            origin_station = None
            destination_station = None
            
            for section in sections:
                section_duration = section.get('duration', 0)
                section_type = section.get('type')
                
                if section_type == 'street_network':
                    walking_time += section_duration
                elif section_type == 'transfer':
                    transfer_time += section_duration
                elif section_type == 'public_transport':
                    public_transport_time += section_duration
                    # Get origin station if first public transport section
                    if not origin_station and section.get('from'):
                        origin_station = section['from'].get('name', 'Unknown')
                    # Get destination station (last public transport section)
                    if section.get('to'):
                        destination_station = section['to'].get('name', 'Unknown')
                elif section_type == 'waiting':
                    waiting_time += section_duration
            
            return {
                "duration_min": duration_sec / 60,
                "duration_sec": duration_sec,
                "transfers": transfers,
                "cost": METRO_COST,
                "sections": sections,
                "raw_journey": journey,
                "walking_time": walking_time,
                "transfer_time": transfer_time,
                "public_transport_time": public_transport_time,
                "waiting_time": waiting_time,
                "origin_station": origin_station,
                "destination_station": destination_station
            }
    except Exception as e:
        st.error(f"Metro API error: {e}")
    
    return None

def get_bike_journey(from_coords, to_coords):
    """Get e-bike journey from Geovelo API"""
    url = GEOVELO_ENDPOINT
    params = {
        "instructions": "false",
        "elevations": "false",
        "geometry": "true",
        "single_result": "true"
    }
    headers = {
        "Content-Type": "application/json",
        "apikey": API_KEY
    }
    payload = {
        "waypoints": [
            {"latitude": from_coords[0], "longitude": from_coords[1], "title": "Start"},
            {"latitude": to_coords[0], "longitude": to_coords[1], "title": "End"}
        ],
        "bikeDetails": {
            "profile": "MEDIAN",
            "bikeType": "BSS",
            "eBike": True
        },
        "transportModes": ["BIKE"]
    }
    
    try:
        response = requests.post(url, json=payload, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if isinstance(data, list) and len(data) > 0:
            route = data[0]
            duration_sec = route.get('duration', 0)
            distance_m = route.get('distances', {}).get('total', 0)
            
            # Extract geometry from sections (not top level!)
            geometry = ''
            sections = route.get('sections', [])
            if sections:
                # Get geometry from the first BIKE section
                for section in sections:
                    if section.get('transportMode') == 'BIKE':
                        geometry = section.get('geometry', '')
                        break
            
            return {
                "duration_min": duration_sec / 60,
                "duration_sec": duration_sec,
                "distance_km": distance_m / 1000,
                "geometry": geometry
            }
    except Exception as e:
        st.error(f"E-Bike API error: {e}")
    
    return None

def geocode_address(address):
    """Geocode an address to coordinates using Nominatim"""
    try:
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": address + ", Paris, France",
            "format": "json",
            "limit": 1
        }
        headers = {
            "User-Agent": "ParisMetroBikeComparison/1.0"
        }
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data and len(data) > 0:
            result = data[0]
            return [float(result['lat']), float(result['lon'])], result.get('display_name', address)
        else:
            return None, None
    except Exception as e:
        st.error(f"Geocoding error: {e}")
        return None, None

def get_walking_journey(from_coords, to_coords):
    """Get walking journey from Geovelo API"""
    url = GEOVELO_ENDPOINT
    params = {
        "instructions": "false",
        "elevations": "false",
        "geometry": "true",
        "single_result": "true"
    }
    headers = {
        "Content-Type": "application/json",
        "apikey": API_KEY
    }
    payload = {
        "waypoints": [
            {"latitude": from_coords[0], "longitude": from_coords[1], "title": "Start"},
            {"latitude": to_coords[0], "longitude": to_coords[1], "title": "End"}
        ],
        "transportModes": ["PEDESTRIAN"]
    }
    
    try:
        response = requests.post(url, json=payload, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if isinstance(data, list) and len(data) > 0:
            route = data[0]
            duration_sec = route.get('duration', 0)
            distance_m = route.get('distances', {}).get('total', 0)
            
            # Extract geometry from sections (not top level!)
            geometry = ''
            sections = route.get('sections', [])
            if sections:
                # Get geometry from the first PEDESTRIAN section
                for section in sections:
                    if section.get('transportMode') == 'PEDESTRIAN':
                        geometry = section.get('geometry', '')
                        break
            
            return {
                "duration_min": duration_sec / 60,
                "duration_sec": duration_sec,
                "distance_km": distance_m / 1000,
                "geometry": geometry,
                "cost": 0  # Walking is free!
            }
    except Exception as e:
        st.error(f"Walking API error: {e}")
    
    return None

# Main app interface - Map Selection
st.subheader("📍 Select Origin and Destination")
st.markdown("**Option 1:** Search by address | **Option 2:** Click on the map")

# Address search
with st.expander("🔍 Search by Address", expanded=False):
    col1, col2 = st.columns(2)
    
    with col1:
        origin_address = st.text_input("Origin Address", placeholder="e.g., Eiffel Tower, Louvre Museum, etc.")
        if st.button("Set Origin", disabled=not origin_address):
            with st.spinner("Searching for address..."):
                coords, display_name = geocode_address(origin_address)
                if coords:
                    st.session_state.origin = coords
                    st.success(f"✅ Origin set to: {display_name}")
                    st.rerun()
                else:
                    st.error("❌ Address not found. Try a different search term.")
    
    with col2:
        dest_address = st.text_input("Destination Address", placeholder="e.g., Arc de Triomphe, Notre-Dame, etc.")
        if st.button("Set Destination", disabled=not dest_address):
            with st.spinner("Searching for address..."):
                coords, display_name = geocode_address(dest_address)
                if coords:
                    st.session_state.destination = coords
                    st.success(f"✅ Destination set to: {display_name}")
                    st.rerun()
                else:
                    st.error("❌ Address not found. Try a different search term.")

st.markdown("**Or click on the map:** First click = origin, second click = destination")

# Create the selection map
m = folium.Map(
    location=[48.8566, 2.3522],  # Center of Paris
    zoom_start=12,
    tiles="OpenStreetMap"
)

# Add Paris boundary
folium.GeoJson(
    PARIS_BOUNDARY,
    name="Paris Boundary",
    style_function=lambda x: {
        'fillColor': 'transparent',
        'color': 'red',
        'weight': 2,
        'dashArray': '5, 5'
    }
).add_to(m)

# Add origin marker if set
if st.session_state.origin:
    folium.Marker(
        st.session_state.origin,
        popup="Origin",
        icon=folium.Icon(color='green', icon='play'),
        tooltip="Origin"
    ).add_to(m)

# Add destination marker if set
if st.session_state.destination:
    folium.Marker(
        st.session_state.destination,
        popup="Destination",
        icon=folium.Icon(color='red', icon='stop'),
        tooltip="Destination"
    ).add_to(m)

# Display map and capture clicks
map_data = st_folium(m, width=700, height=500, key="selection_map")

# Handle map clicks
if map_data and map_data.get('last_clicked'):
    clicked = map_data['last_clicked']
    if clicked != st.session_state.last_clicked:
        st.session_state.last_clicked = clicked
        lat, lon = clicked['lat'], clicked['lng']
        
        if not st.session_state.origin:
            st.session_state.origin = [lat, lon]
            st.success(f"✅ Origin set: ({lat:.6f}, {lon:.6f})")
            st.rerun()
        elif not st.session_state.destination:
            st.session_state.destination = [lat, lon]
            st.success(f"✅ Destination set: ({lat:.6f}, {lon:.6f})")
            st.rerun()

# Reset button
if st.button("🔄 Reset Selection"):
    st.session_state.origin = None
    st.session_state.destination = None
    st.session_state.last_clicked = None
    st.session_state.results = None
    st.rerun()

# Display selected coordinates
col1, col2 = st.columns(2)
with col1:
    if st.session_state.origin:
        st.info(f"**Origin:** {st.session_state.origin[0]:.6f}, {st.session_state.origin[1]:.6f}")
    else:
        st.warning("Click map to set origin")

with col2:
    if st.session_state.destination:
        st.info(f"**Destination:** {st.session_state.destination[0]:.6f}, {st.session_state.destination[1]:.6f}")
    else:
        st.warning("Click map to set destination")

# E-Bike settings
st.subheader("🚴 E-Bike Settings")
walk_to_bike_distance = st.slider(
    "Walking distance to nearest e-bike (meters):",
    min_value=0,
    max_value=500,
    value=50,
    step=10,
    help="Estimated distance you need to walk to find an available e-bike"
)
# Calculate walking time (assume 1.4 m/s = 5 km/h walking speed)
walk_to_bike_time = walk_to_bike_distance / 1.4 / 60  # in minutes

# Calculate button
if st.button("🔍 Compare Routes", type="primary", disabled=not (st.session_state.origin and st.session_state.destination)):
    with st.spinner("Calculating routes..."):
        from_coords = tuple(st.session_state.origin)
        to_coords = tuple(st.session_state.destination)
        
        # Get journeys
        metro = get_metro_journey(from_coords, to_coords)
        bike = get_bike_journey(from_coords, to_coords)
        walking = get_walking_journey(from_coords, to_coords)
        
        # Store results in session state
        st.session_state.results = {
            'metro': metro,
            'bike': bike,
            'walking': walking,
            'from_coords': from_coords,
            'to_coords': to_coords,
            'walk_to_bike_time': walk_to_bike_time
        }

# Display results if available
if st.session_state.results:
    results = st.session_state.results
    metro = results['metro']
    bike = results['bike']
    walking = results.get('walking')
    from_coords = results['from_coords']
    to_coords = results['to_coords']
    walk_to_bike_time = results.get('walk_to_bike_time', 0)
    
    if metro and bike:
        st.success("✅ Routes calculated successfully!")
        
        # Display results
        st.markdown("---")
        st.header("📊 Results")
        
        # Metro results
        st.subheader("🚇 Metro Journey")
        
        # Show stations
        if metro.get('origin_station') and metro.get('destination_station'):
            st.markdown(f"**From Station:** {metro['origin_station']}  \n**To Station:** {metro['destination_station']}")
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("⏱️ Total Time", f"{metro['duration_min']:.1f} min")
        with col2:
            st.metric("🚇 Transit Time", f"{metro['public_transport_time']/60:.1f} min")
        with col3:
            st.metric("🚶 Walking", f"{metro['walking_time']/60:.1f} min")
        with col4:
            st.metric("🔄 Transfers", metro['transfers'])
        
        # Add metro cost
        st.metric("💰 Cost", f"€{metro['cost']:.2f}")
        
        # Add time breakdown in expander
        with st.expander("📊 Metro Time Breakdown"):
            st.write(f"- Public Transport: {metro['public_transport_time']/60:.1f} min")
            st.write(f"- Walking: {metro['walking_time']/60:.1f} min")
            st.write(f"- Transfer Time: {metro['transfer_time']/60:.1f} min")
            st.write(f"- Waiting Time: {metro['waiting_time']/60:.1f} min")
            st.write(f"- **Total: {metro['duration_min']:.1f} min**")
        
        st.markdown("---")
        
        # E-bike results - show ALL pricing options
        st.subheader("🚴 E-Bike Options")
        st.caption(f"Cycling time: {bike['duration_min']:.1f} min | Total journey: {bike['duration_min'] + walk_to_bike_time:.1f} min (includes {walk_to_bike_time:.1f} min walk to bike)")
        
        # Calculate total bike time including walking (for comparison only)
        total_bike_time = bike['duration_min'] + walk_to_bike_time
        
        # Calculate all pricing options for each provider
        all_options = []
        for provider in BIKE_PROVIDERS.keys():
            options = calculate_all_bike_costs(bike['duration_min'], provider)  # Cost based on cycling time only
            for option in options:
                all_options.append({
                    **option,
                    "provider": provider
                })
        
        # Count how many options are cheaper than metro (excluding Velib')
        cheaper_count = sum(1 for opt in all_options 
                           if opt['provider'] != "Velib'" and opt['cost'] < METRO_COST)
        total_count = sum(1 for opt in all_options if opt['provider'] != "Velib'")
        
        # Display options by provider in columns
        provider_list = list(BIKE_PROVIDERS.keys())
        cols = st.columns(len(provider_list))
        
        for idx, provider in enumerate(provider_list):
            with cols[idx]:
                st.markdown(f"### 🚴 {provider}")
                provider_options = [opt for opt in all_options if opt['provider'] == provider]
                
                for option in provider_options:
                    # Determine icon
                    icon = "✅" if option['cost'] < METRO_COST else "❌"
                    
                    # Format remaining info with clarity
                    if option['remaining_type'] == "minutes":
                        remaining_text = f"{int(round(option['remaining']))} min remaining"
                    elif option['remaining_type'] == "trips":
                        remaining_text = f"{option['remaining']} trips remaining"
                    else:
                        remaining_text = ""
                    
                    # Display option compactly
                    if remaining_text:
                        st.markdown(f"{icon} **{option['name']}** - €{option['cost']:.2f} *({remaining_text})*")
                    else:
                        st.markdown(f"{icon} **{option['name']}** - €{option['cost']:.2f}")
        
        # Walking results
        if walking:
            st.subheader("🚶 Walking Journey")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("⏱️ Duration", f"{walking['duration_min']:.1f} min")
            with col2:
                st.metric("📏 Distance", f"{walking['distance_km']:.2f} km")
            with col3:
                st.metric("💰 Cost", "FREE")
        
        st.markdown("---")
        
        # Comparison and recommendation
        st.header("🎯 Recommendation")
        
        # Find cheapest option overall
        cheapest_option = min(all_options, key=lambda x: x['cost'])
        min_cost = cheapest_option['cost']
        
        # Find all providers/options that match the minimum cost (within €0.01)
        cheapest_providers = list(set([opt['provider'] for opt in all_options if abs(opt['cost'] - min_cost) < 0.01]))
        
        # Format provider list
        if len(cheapest_providers) == 1:
            provider_text = cheapest_providers[0]
        elif len(cheapest_providers) == 2:
            provider_text = f"{cheapest_providers[0]} and {cheapest_providers[1]}"
        else:
            provider_text = ", ".join(cheapest_providers[:-1]) + f", and {cheapest_providers[-1]}"
        
        time_diff = total_bike_time - metro['duration_min']
        cost_diff = min_cost - metro['cost']
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("⏱️ Time Comparison")
            if time_diff < 0:
                st.success(f"E-Bike is **{abs(time_diff):.1f} minutes faster**")
            elif time_diff > 0:
                st.info(f"Metro is **{time_diff:.1f} minutes faster**")
            else:
                st.info("Same duration")
        
        with col2:
            st.subheader("💰 Cost Comparison")
            st.info(f"💡 **{cheaper_count} out of {total_count}** e-bike options are cheaper than metro (€{METRO_COST:.2f}) for this trip")
        
        # Final recommendation
        st.markdown("---")
        
        # Check if per-minute or any pass under 60 minutes is cheaper than metro
        short_term_cheaper = any(
            opt['cost'] < METRO_COST 
            for opt in all_options 
            if opt['provider'] != "Velib'" and (
                opt['name'] == "Per-minute" or 
                ('min pass' in opt['name'] and int(opt['name'].split()[0]) < 60)
            )
        )
        
        recommended_mode = None
        if short_term_cheaper:
            st.success(f"### ✅ Recommended: **E-Bike**")
            st.markdown(f"**{cheaper_count}** practical e-bike options beat metro pricing!")
            recommended_mode = "bike"
        else:
            st.info("### 🚇 Recommended: **Metro**")
            st.markdown(f"While **{cheaper_count}** e-bike options are cheaper, they require longer-term passes. Metro offers better value for single trips.")
            recommended_mode = "metro"
        
        # Route visualization - side by side maps
        st.markdown("---")
        st.header("🗺️ Route Visualization")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.subheader("🚇 Metro Route")
            metro_map = folium.Map(
                location=[from_coords[0], from_coords[1]],
                zoom_start=13,
                tiles="OpenStreetMap"
            )
            
            folium.Marker(
                from_coords,
                popup="Origin",
                icon=folium.Icon(color='green', icon='play')
            ).add_to(metro_map)
            
            folium.Marker(
                to_coords,
                popup="Destination",
                icon=folium.Icon(color='red', icon='stop')
            ).add_to(metro_map)
            
            # Add metro route with walking sections
            metro_displayed = False
            walking_displayed = False
            if metro.get('sections'):
                for section in metro['sections']:
                    section_type = section.get('type')
                    
                    # Display public transport sections (purple)
                    if section_type == 'public_transport':
                        geojson = section.get('geojson')
                        if geojson and geojson.get('coordinates'):
                            try:
                                coords = geojson['coordinates']
                                coords = [[c[1], c[0]] for c in coords]
                                
                                display_info = section.get('display_informations', {})
                                line_name = display_info.get('code', 'Metro')
                                
                                folium.PolyLine(
                                    coords,
                                    color='purple',
                                    weight=6,
                                    opacity=0.9,
                                    popup=f"Line {line_name}"
                                ).add_to(metro_map)
                                
                                metro_displayed = True
                            except:
                                pass
                    
                    # Display walking sections (green)
                    elif section_type == 'street_network' or section_type == 'transfer':
                        geojson = section.get('geojson')
                        if geojson and geojson.get('coordinates'):
                            try:
                                coords = geojson['coordinates']
                                coords = [[c[1], c[0]] for c in coords]
                                
                                folium.PolyLine(
                                    coords,
                                    color='green',
                                    weight=4,
                                    opacity=0.7,
                                    dash_array='5, 5',
                                    popup="Walking"
                                ).add_to(metro_map)
                                
                                walking_displayed = True
                            except:
                                pass
            
            try:
                metro_map.fit_bounds([[from_coords[0], from_coords[1]], [to_coords[0], to_coords[1]]])
            except:
                pass
            
            st_folium(metro_map, width=250, height=400, key="metro_map")
            if metro_displayed:
                if walking_displayed:
                    st.caption("Purple: Metro lines | Green dashed: Walking")
                else:
                    st.caption("Purple: Metro lines")
            else:
                st.caption("⚠️ Route geometry not available")
        
        with col2:
            st.subheader("🚴 E-Bike Route")
            bike_map = folium.Map(
                location=[from_coords[0], from_coords[1]],
                zoom_start=13,
                tiles="OpenStreetMap"
            )
            
            folium.Marker(
                from_coords,
                popup="Origin",
                icon=folium.Icon(color='green', icon='play')
            ).add_to(bike_map)
            
            folium.Marker(
                to_coords,
                popup="Destination",
                icon=folium.Icon(color='red', icon='stop')
            ).add_to(bike_map)
            
            # Add bike route
            bike_displayed = False
            if bike.get('geometry'):
                try:
                    import polyline
                    geometry_str = bike['geometry']
                    
                    if geometry_str:
                        coordinates = polyline.decode(geometry_str, 6)
                        
                        if coordinates and len(coordinates) > 0:
                            folium.PolyLine(
                                coordinates,
                                color='blue',
                                weight=6,
                                opacity=0.9,
                                popup=f"E-Bike: {bike['distance_km']:.2f} km"
                            ).add_to(bike_map)
                            
                            bike_displayed = True
                except Exception as e:
                    pass
            
            try:
                bike_map.fit_bounds([[from_coords[0], from_coords[1]], [to_coords[0], to_coords[1]]])
            except:
                pass
            
            st_folium(bike_map, width=250, height=400, key="bike_map")
        
        with col3:
            st.subheader("🚶 Walking Route")
            walk_map = folium.Map(
                location=[from_coords[0], from_coords[1]],
                zoom_start=13,
                tiles="OpenStreetMap"
            )
            
            folium.Marker(
                from_coords,
                popup="Origin",
                icon=folium.Icon(color='green', icon='play')
            ).add_to(walk_map)
            
            folium.Marker(
                to_coords,
                popup="Destination",
                icon=folium.Icon(color='red', icon='stop')
            ).add_to(walk_map)
            
            # Add walking route
            walk_displayed = False
            if walking and walking.get('geometry'):
                try:
                    import polyline
                    geometry_str = walking['geometry']
                    
                    if geometry_str:
                        coordinates = polyline.decode(geometry_str, 6)
                        
                        if coordinates and len(coordinates) > 0:
                            folium.PolyLine(
                                coordinates,
                                color='orange',
                                weight=6,
                                opacity=0.9,
                                popup=f"Walking: {walking['distance_km']:.2f} km"
                            ).add_to(walk_map)
                            
                            walk_displayed = True
                except Exception as e:
                    pass
            
            try:
                walk_map.fit_bounds([[from_coords[0], from_coords[1]], [to_coords[0], to_coords[1]]])
            except:
                pass
            
            st_folium(walk_map, width=250, height=400, key="walk_map")
        
        # Detailed breakdown
        with st.expander("📋 Detailed Breakdown"):
            st.markdown("**Metro Journey:**")
            st.write(f"- Duration: {metro['duration_min']:.1f} minutes")
            st.write(f"- Transfers: {metro['transfers']}")
            st.write(f"- Cost: €{metro['cost']:.2f}")
            if metro.get('origin_station'):
                st.write(f"- From: {metro['origin_station']}")
            if metro.get('destination_station'):
                st.write(f"- To: {metro['destination_station']}")
            
            st.markdown("**E-Bike Journey:**")
            st.write(f"- Cycling Duration: {bike['duration_min']:.1f} minutes")
            st.write(f"- Walking to Bike: {walk_to_bike_time:.1f} minutes")
            st.write(f"- Total Duration: {total_bike_time:.1f} minutes")
            st.write(f"- Distance: {bike['distance_km']:.2f} km")
            
            st.markdown("**E-Bike Pricing Options:**")
            for provider in BIKE_PROVIDERS.keys():
                st.write(f"\n**{provider}:**")
                provider_options = [opt for opt in all_options if opt['provider'] == provider]
                for option in provider_options:
                    icon = "✅" if option['cost'] < METRO_COST else "❌"
                    st.write(f"  {icon} {option['name']}: €{option['cost']:.2f}")
    
    elif not metro:
        st.error("❌ Could not calculate metro route")
    elif not bike:
        st.error("❌ Could not calculate e-bike route")

# Footer with info
st.markdown("---")
st.markdown("""
**ℹ️ About**
- Metro cost: Fixed €2.50 per trip
- E-Bike providers: Voi, Dott, Lime, Velib'
- All e-bikes are electric
- Data from PRIM Île-de-France Mobilités APIs
""")
