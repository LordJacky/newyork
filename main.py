import streamlit as st
import folium
from streamlit_folium import st_folium
from data_loader.loader import DataLoader
from scorer.scorer import Scorer


# crs flow
# Input: lat/lon coordinates
# crs="EPSG:4326"  # WGS84 (latitude/longitude) -> Convert to projected CRS for accurate distance calculations to_crs("EPSG:2263") # NewYork -> EPSG:4325 for Folium

st.set_page_config(page_title="NYC Event Location Finder", layout="wide")

st.title("🗽 NYC Event Location Finder")


# Load data
@st.cache_data
def load_data():
    parks_df = DataLoader.download_parks()
    restaurants_df = DataLoader.download_restaurants()
    subway_df = DataLoader.download_subway_stations()
    return parks_df, restaurants_df, subway_df


parks_df, restaurants_df, subway_df = load_data()

# Sidebar configuration
st.sidebar.header("⚙️ Configuration")

st.sidebar.subheader("Park Filters")
min_park_area = st.sidebar.slider(
    "Minimum park area (acres)",
    min_value=1.0,
    max_value=20.0,
    value=5.0,
    step=0.5,
    help="Parameter: min_park_area - Filters out parks smaller than this size",
)

st.sidebar.subheader("Accessibility")
max_park_distance = st.sidebar.slider(
    "Max distance to subway (meters)",
    min_value=200,
    max_value=1000,
    value=500,
    step=50,
    help="Parameter: max_park_distance - Maximum walking distance to nearest subway station",
)

st.sidebar.subheader("Social Activity")
restaurant_radius = st.sidebar.slider(
    "Restaurant search radius (meters)",
    min_value=200,
    max_value=1000,
    value=500,
    step=50,
    help="Parameter: restaurant_radius - Radius to count nearby quality restaurants",
)

st.sidebar.subheader("Results")
top_n_per_borough = st.sidebar.slider(
    "Parks per borough",
    min_value=1,
    max_value=5,
    value=3,
    step=1,
    help="Parameter: top_n_per_borough - Number of top parks to select from each borough",
)

st.sidebar.divider()

st.sidebar.subheader("Map Display")
show_restaurants = st.sidebar.checkbox(
    "Show restaurants",
    value=False,
    help="Display quality restaurants (score ≤ 20) near selected parks on the map",
)

# Check if parameters changed
current_params = {
    "min_park_area": min_park_area,
    "max_park_distance": max_park_distance,
    "restaurant_radius": restaurant_radius,
    "top_n_per_borough": top_n_per_borough,
}

# Clear results if parameters changed
if "params" in st.session_state and st.session_state["params"] != current_params:
    st.session_state.clear()

# Run analysis
if st.sidebar.button("🔍 Find Best Locations", type="primary"):
    with st.spinner("Analyzing locations..."):
        scorer = Scorer(
            parks_df,
            restaurants_df,
            subway_df,
            min_park_area=min_park_area,
            max_park_distance=max_park_distance,
            restaurant_radius=restaurant_radius,
        )

        best_parks = scorer.summary(top_n_per_borough=top_n_per_borough)

        # Convert to WGS84 for folium
        best_parks_wgs84 = best_parks.to_crs("EPSG:4326")

        st.session_state["best_parks"] = best_parks_wgs84
        st.session_state["scorer"] = scorer
        st.session_state["params"] = current_params

# Display results
if "best_parks" in st.session_state:
    best_parks = st.session_state["best_parks"]
    scorer = st.session_state["scorer"]

    st.header(f"📍 Top {len(best_parks)} Event Locations")

    # Create map
    st.subheader("Interactive Map")

    # Center map on NYC
    nyc_center = [40.7128, -74.0060]
    m = folium.Map(location=nyc_center, zoom_start=11)

    # Collect unique nearby stations
    nearby_station_ids = set()
    for idx, park in best_parks.iterrows():
        nearby_station_ids.update(park["nearby_station_ids"])

    # Add nearby subway stations to map
    subway_wgs84 = scorer.subway_gdf.to_crs("EPSG:4326")
    for station_id in nearby_station_ids:
        station = subway_wgs84.loc[station_id]
        folium.Marker(
            location=[station.geometry.y, station.geometry.x],
            popup=f"<b>🚇 {station['station_name']}</b><br>Routes: {station['routes']}",
            icon=folium.Icon(color="blue", icon="train", prefix="fa"),
            tooltip=station["station_name"],
        ).add_to(m)

    # Add nearby restaurants if enabled
    if show_restaurants:
        nearby_restaurant_ids = set()
        for idx, park in best_parks.iterrows():
            nearby_restaurant_ids.update(park["nearby_restaurant_ids"])

        # Get quality restaurants and convert to WGS84
        quality_restaurants = scorer.restaurants_gdf[
            scorer.restaurants_gdf["score"] <= 20
        ]
        restaurants_wgs84 = quality_restaurants.to_crs("EPSG:4326")

        for restaurant_id in nearby_restaurant_ids:
            if restaurant_id in restaurants_wgs84.index:
                restaurant = restaurants_wgs84.loc[restaurant_id]
                folium.Marker(
                    location=[restaurant.geometry.y, restaurant.geometry.x],
                    popup=folium.Popup(
                        f"<b>🍴 {restaurant['restaurant_name']}</b><br>"
                        f"Cuisine: {restaurant['cuisine']}<br>"
                        f"Inspection Score: {restaurant['score']:.0f}",
                        max_width=250,
                    ),
                    icon=folium.Icon(color="orange", icon="utensils", prefix="fa"),
                    tooltip=restaurant["restaurant_name"],
                ).add_to(m)

    # Add park markers
    for idx, park in best_parks.iterrows():
        folium.Marker(
            location=[park.geometry.y, park.geometry.x],
            popup=folium.Popup(
                f"<b>🌳 {park['park_name']}</b><br>"
                f"Borough: {park['borough_left']}<br>"
                f"Area: {park['acres']:.1f} acres<br>"
                f"Score: {park['combined_score']:.1f}/100<br><br>"
                f"{park['justification']}",
                max_width=300,
            ),
            tooltip=park["park_name"],
            icon=folium.Icon(color="red", icon="tree", prefix="fa"),
        ).add_to(m)

        # Add circle showing restaurant search radius
        folium.Circle(
            location=[park.geometry.y, park.geometry.x],
            radius=restaurant_radius,
            color="orange",
            fill=True,
            fillOpacity=0.1,
            popup=f"{restaurant_radius}m radius",
        ).add_to(m)

    # Display map
    st_folium(m, width=1400, height=600)

    # Display park details
    st.subheader("Park Details")

    for idx, park in best_parks.iterrows():
        with st.expander(
            f"🌳 {park['park_name']} - {park['borough_left']} (Score: {park['combined_score']:.1f}/100)"
        ):
            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("Area", f"{park['acres']:.1f} acres")
                st.metric(
                    "Accessibility Score", f"{park['accessibility_score']:.1f}/100"
                )

            with col2:
                st.metric("Distance to Subway", f"{park['distance_to_subway_m']:.0f}m")
                st.metric(
                    "Nearby Stations", f"{park[f'subway_count_{max_park_distance}m']}"
                )

            with col3:
                st.metric(
                    "Social Activity Score", f"{park['social_activity_score']:.1f}/100"
                )
                st.metric(
                    "Quality Restaurants",
                    f"{park[f'restaurant_count_{restaurant_radius}m']}",
                )

            st.info(f"**Why this location?** {park['justification']}")

    # Summary statistics
    st.subheader("📊 Summary Statistics")
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Total Locations", len(best_parks))
        st.metric("Boroughs Covered", best_parks["borough_left"].nunique())

    with col2:
        st.metric(
            "Avg Accessibility Score",
            f"{best_parks['accessibility_score'].mean():.1f}/100",
        )
        st.metric(
            "Avg Social Activity Score",
            f"{best_parks['social_activity_score'].mean():.1f}/100",
        )

    with col3:
        st.metric(
            "Avg Distance to Subway",
            f"{best_parks['distance_to_subway_m'].mean():.0f}m",
        )
        st.metric(
            "Avg Restaurants Nearby",
            f"{best_parks[f'restaurant_count_{restaurant_radius}m'].mean():.1f}",
        )

else:
    pass
