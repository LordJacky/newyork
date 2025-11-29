import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from data_loader.loader import DataLoader
from scorer.scorer import Scorer


# TODO: split this file into multiple modules according to tabs

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
    ridership_df = DataLoader.download_subway_ridership()
    return parks_df, restaurants_df, subway_df, ridership_df


parks_df, restaurants_df, subway_df, ridership_df = load_data()

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

max_restaurant_score = st.sidebar.slider(
    "Max restaurant inspection score",
    min_value=0,
    max_value=50,
    value=27,
    step=1,
    help="Parameter: max_restaurant_score - Only count restaurants with inspection score below this (0-13=A, 14-27=B, 28+=C)",
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

min_score_threshold = st.sidebar.slider(
    "Minimum combined score",
    min_value=0,
    max_value=100,
    value=0,
    step=5,
    help="Parameter: min_score_threshold - Hide parks with combined score below this threshold",
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
    "max_restaurant_score": max_restaurant_score,
    "top_n_per_borough": top_n_per_borough,
    "min_score_threshold": min_score_threshold,
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
            ridership_df,
            min_park_area=min_park_area,
            max_park_distance=max_park_distance,
            restaurant_radius=restaurant_radius,
            max_restaurant_score=max_restaurant_score,
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

    # Create tabs
    tab1, tab2 = st.tabs(["📍 Results", "🔍 Analysis Steps"])

    with tab1:
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

            # popup with ridership info
            popup_text = (
                f"<b>🚇 {station['station_name']}</b><br>Routes: {station['routes']}"
            )
            if "avg_daily_ridership" in station and pd.notna(
                station["avg_daily_ridership"]
            ):
                popup_text += (
                    f"<br>Daily Ridership: {int(station['avg_daily_ridership']):,}"
                )

            folium.Marker(
                location=[station.geometry.y, station.geometry.x],
                popup=popup_text,
                icon=folium.Icon(color="blue", icon="train", prefix="fa"),
                tooltip=station["station_name"],
            ).add_to(m)

        # Add nearby restaurants if enabled
        if show_restaurants:
            nearby_restaurant_ids = set()
            for idx, park in best_parks.iterrows():
                nearby_restaurant_ids.update(park["nearby_restaurant_ids"])

            # Get quality restaurants and convert to WGS84
            restaurants_wgs84 = scorer.quality_restaurants_gdf.to_crs("EPSG:4326")

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

        # Filter by minimum score threshold
        filtered_parks = best_parks[
            best_parks["combined_score"] >= min_score_threshold
        ].copy()

        # Sort by combined score (descending)
        filtered_parks = filtered_parks.sort_values("combined_score", ascending=False)

        if len(filtered_parks) == 0:
            st.warning(f"No parks found with combined score >= {min_score_threshold}")
        else:
            # Group by borough
            for borough in filtered_parks["borough_left"].unique():
                borough_parks = filtered_parks[
                    filtered_parks["borough_left"] == borough
                ]

                st.markdown(f"### {borough} ({len(borough_parks)} parks)")

                for idx, park in borough_parks.iterrows():
                    with st.expander(
                        f"🌳 {park['park_name']} (Score: {park['combined_score']:.1f}/100)"
                    ):
                        col1, col2, col3 = st.columns(3)

                        with col1:
                            st.metric("Area", f"{park['acres']:.1f} acres")
                            st.metric(
                                "Accessibility Score",
                                f"{park['accessibility_score']:.1f}/100",
                            )

                        with col2:
                            st.metric(
                                "Distance to Subway",
                                f"{park['distance_to_subway_m']:.0f}m",
                            )
                            st.metric(
                                "Nearby Stations",
                                f"{park[f'subway_count_{max_park_distance}m']}",
                            )

                        with col3:
                            st.metric(
                                "Social Activity Score",
                                f"{park['social_activity_score']:.1f}/100",
                            )
                            st.metric(
                                "Quality Restaurants",
                                f"{park[f'restaurant_count_{restaurant_radius}m']}",
                            )

                        st.info(f"**Why this location?** {park['justification']}")

                        # Show nearby stations with ridership
                        if len(park["nearby_station_ids"]) > 0:
                            st.markdown("**Nearby Subway Stations:**")
                            subway_wgs84 = scorer.subway_gdf.to_crs("EPSG:4326")
                            for station_id in park["nearby_station_ids"]:
                                if station_id in subway_wgs84.index:
                                    station = subway_wgs84.loc[station_id]
                                    station_info = f"• {station['station_name']} ({station['routes']})"
                                    if "avg_daily_ridership" in station and pd.notna(
                                        station["avg_daily_ridership"]
                                    ):
                                        station_info += f" - {int(station['avg_daily_ridership']):,} daily riders"
                                    st.text(station_info)

        # Summary statistics
        st.subheader("📊 Summary Statistics")

        if len(filtered_parks) > 0:
            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("Total Locations", len(filtered_parks))
                st.metric("Boroughs Covered", filtered_parks["borough_left"].nunique())

            with col2:
                st.metric(
                    "Avg Accessibility Score",
                    f"{filtered_parks['accessibility_score'].mean():.1f}/100",
                )
                st.metric(
                    "Avg Social Activity Score",
                    f"{filtered_parks['social_activity_score'].mean():.1f}/100",
                )

            with col3:
                st.metric(
                    "Avg Distance to Subway",
                    f"{filtered_parks['distance_to_subway_m'].mean():.0f}m",
                )
                st.metric(
                    "Avg Restaurants Nearby",
                    f"{filtered_parks[f'restaurant_count_{restaurant_radius}m'].mean():.1f}",
                )

    with tab2:
        st.header("🔍 Analysis Process - Step by Step")
        st.write("Click each step to see the analysis progression on the map")

        # Initialize session state for analysis step
        if "analysis_step" not in st.session_state:
            st.session_state.analysis_step = None

        # Step buttons
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("Step 1: Show All Parks", use_container_width=True):
                st.session_state.analysis_step = 1
            if st.button("Step 2: Filter Parks by Size", use_container_width=True):
                st.session_state.analysis_step = 2

        with col2:
            if st.button(
                "Step 3: Find Nearest Subway Stations", use_container_width=True
            ):
                st.session_state.analysis_step = 3
            if st.button("Step 4: Count Nearby Restaurants", use_container_width=True):
                st.session_state.analysis_step = 4

        with col3:
            if st.button("Step 5: Calculate & Rank Parks", use_container_width=True):
                st.session_state.analysis_step = 5
            if st.button(
                "Step 6: Select Top Parks per Borough", use_container_width=True
            ):
                st.session_state.analysis_step = 6

        st.divider()

        # Display selected step
        if st.session_state.analysis_step == 1:
            st.write(f"📊 Loaded **{len(parks_df)}** parks from NYC Open Data")

            m1 = folium.Map(location=[40.7128, -74.0060], zoom_start=11)
            parks_wgs84 = scorer.parks_gdf.to_crs("EPSG:4326")

            for idx, park in parks_wgs84.iterrows():
                folium.CircleMarker(
                    location=[park.geometry.y, park.geometry.x],
                    radius=5,
                    color="green",
                    fill=True,
                    fillOpacity=0.3,
                ).add_to(m1)

            st_folium(m1, width=1000, height=500)

        elif st.session_state.analysis_step == 2:
            filtered = scorer.parks_gdf[scorer.parks_gdf["acres"] >= min_park_area]
            st.write(f"🔍 Filtered: **{len(filtered)}** parks (≥{min_park_area} acres)")

            m2 = folium.Map(location=[40.7128, -74.0060], zoom_start=11)
            filtered_wgs84 = filtered.to_crs("EPSG:4326")

            for idx, park in filtered_wgs84.iterrows():
                folium.CircleMarker(
                    location=[park.geometry.y, park.geometry.x],
                    radius=5,
                    color="green",
                    fill=True,
                    fillOpacity=0.5,
                    tooltip=park["park_name"],
                ).add_to(m2)

            st_folium(m2, width=1000, height=500)

        elif st.session_state.analysis_step == 3:
            parks_with_subway = scorer.parks_with_scores
            st.write(
                f"🚇 Found **{len(parks_with_subway)}** parks within {max_park_distance}m of subway"
            )

            m3 = folium.Map(location=[40.7128, -74.0060], zoom_start=11)

            # Add subway stations
            subway_wgs84 = scorer.subway_gdf.to_crs("EPSG:4326")
            for idx, station in subway_wgs84.iterrows():
                folium.CircleMarker(
                    location=[station.geometry.y, station.geometry.x],
                    radius=2,
                    color="blue",
                    fill=True,
                ).add_to(m3)

            # Add accessible parks
            parks_wgs84 = parks_with_subway.to_crs("EPSG:4326")
            for idx, park in parks_wgs84.iterrows():
                folium.Marker(
                    location=[park.geometry.y, park.geometry.x],
                    icon=folium.Icon(color="green", icon="tree", prefix="fa"),
                    tooltip=f"{park['park_name']} - {park['distance_to_subway_m']:.0f}m to subway",
                ).add_to(m3)

            st_folium(m3, width=1000, height=500)

        elif st.session_state.analysis_step == 4:
            parks_with_restaurants = scorer.parks_with_scores
            st.write(
                f"🍴 Counted quality restaurants within {restaurant_radius}m for each park"
            )

            m4 = folium.Map(location=[40.7128, -74.0060], zoom_start=11)

            # Collect all nearby restaurants
            all_restaurant_ids = set()
            for idx, park in parks_with_restaurants.iterrows():
                all_restaurant_ids.update(park["nearby_restaurant_ids"])

            # Show restaurants
            restaurants_wgs84 = scorer.quality_restaurants_gdf.to_crs("EPSG:4326")

            for rest_id in all_restaurant_ids:
                if rest_id in restaurants_wgs84.index:
                    rest = restaurants_wgs84.loc[rest_id]
                    folium.CircleMarker(
                        location=[rest.geometry.y, rest.geometry.x],
                        radius=5,
                        color="orange",
                        fill=True,
                        fillOpacity=0.6,
                        tooltip=f"{rest['restaurant_name']} - {rest['cuisine']}",
                    ).add_to(m4)

            # Show all parks with restaurant counts
            parks_wgs84 = parks_with_restaurants.to_crs("EPSG:4326")
            for idx, park in parks_wgs84.iterrows():
                restaurant_count = park[f"restaurant_count_{restaurant_radius}m"]
                folium.Marker(
                    location=[park.geometry.y, park.geometry.x],
                    icon=folium.Icon(color="green", icon="tree", prefix="fa"),
                    tooltip=f"{park['park_name']}: {restaurant_count} restaurants",
                ).add_to(m4)

            st_folium(m4, width=1000, height=500)

        elif st.session_state.analysis_step == 5:
            st.write("📊 Scored all parks by accessibility + social activity")

            # Show score distribution
            col1, col2 = st.columns(2)
            with col1:
                st.metric(
                    "Avg Accessibility",
                    f"{scorer.parks_with_scores['accessibility_score'].mean():.1f}/100",
                )
            with col2:
                st.metric(
                    "Avg Social Activity",
                    f"{scorer.parks_with_scores['social_activity_score'].mean():.1f}/100",
                )

            # Map with color-coded scores
            m5 = folium.Map(location=[40.7128, -74.0060], zoom_start=11)

            for idx, park in scorer.parks_with_scores.to_crs("EPSG:4326").iterrows():
                score = park["combined_score"]
                color = "red" if score > 70 else "orange" if score > 50 else "green"

                folium.Marker(
                    location=[park.geometry.y, park.geometry.x],
                    icon=folium.Icon(color="green", icon="tree", prefix="fa"),
                    tooltip=f"{park['park_name']}: {score:.1f}/100",
                ).add_to(m5)

            st_folium(m5, width=1000, height=500)

        elif st.session_state.analysis_step == 6:
            st.write(
                f"🎯 Selected top {top_n_per_borough} parks from each borough = **{len(best_parks)}** total"
            )

            borough_counts = best_parks["borough_left"].value_counts()
            for borough, count in borough_counts.items():
                st.write(f"- {borough}: {count} parks")

            m6 = folium.Map(location=[40.7128, -74.0060], zoom_start=11)

            for idx, park in best_parks.iterrows():
                folium.Marker(
                    location=[park.geometry.y, park.geometry.x],
                    icon=folium.Icon(color="red", icon="star", prefix="fa"),
                    tooltip=f"{park['park_name']} - Score: {park['combined_score']:.1f}",
                ).add_to(m6)

            st_folium(m6, width=1000, height=500)

else:
    pass
