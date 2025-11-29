import pandas as pd
import geopandas as gpd


class Scorer:
    """Score park locations based on multiple criteria"""

    def __init__(
        self,
        parks_df,
        restaurants_df,
        subway_df,
        min_park_area=5.0,
        max_park_distance=500,
        restaurant_radius=500,
    ):
        """
        Initialize scorer with data

        Args:
            parks_df: DataFrame with parks data
            restaurants_df: DataFrame with restaurants data
            subway_df: DataFrame with subway stations data
            min_park_area: Minimum park area in acres
            max_park_distance: Maximum distance to subway in meters
            restaurant_radius: Radius in meters to count restaurants for social activity
        """
        # Convert to GeoDataFrames with proper CRS (WGS84) https://en.wikipedia.org/wiki/Spatial_reference_system
        self.parks_gdf = gpd.GeoDataFrame(
            parks_df,
            geometry=gpd.points_from_xy(parks_df.longitude, parks_df.latitude),
            crs="EPSG:4326",
        )

        self.restaurants_gdf = gpd.GeoDataFrame(
            restaurants_df,
            geometry=gpd.points_from_xy(
                restaurants_df.longitude, restaurants_df.latitude
            ),
            crs="EPSG:4326",
        )

        self.subway_gdf = gpd.GeoDataFrame(
            subway_df,
            geometry=gpd.points_from_xy(subway_df.longitude, subway_df.latitude),
            crs="EPSG:4326",
        )

        # Convert to projected CRS for accurate distance calculations (meters)
        # EPSG:2263 - NAD83 / New York Long Island (ftUS) converted to meters
        self.parks_gdf = self.parks_gdf.to_crs("EPSG:2263")
        self.subway_gdf = self.subway_gdf.to_crs("EPSG:2263")
        self.restaurants_gdf = self.restaurants_gdf.to_crs("EPSG:2263")

        self.min_park_area = min_park_area
        self.max_park_distance = max_park_distance
        self.restaurant_radius = restaurant_radius
        self.parks_with_scores = None

    def calculate_park_accessibility(self) -> gpd.GeoDataFrame:
        """
        Calculate accessibility score for parks based on subway proximity

        Filters:
        - Parks with area < min_park_area (acres)
        - Parks with distance > max_park_distance (meters) to nearest subway
        - Excludes playgrounds and undeveloped parks

        Returns:
            GeoDataFrame with parks and accessibility metrics
        """
        # Filter by minimum park area
        parks = self.parks_gdf[self.parks_gdf["acres"] >= self.min_park_area].copy()

        # Filter out playgrounds and undeveloped parks
        exclude_types = ["Playground", "Undeveloped", "Triangle/Plaza"]
        if "park_type" in parks.columns:
            parks = parks[~parks["park_type"].isin(exclude_types)].copy()

        # Find one nearest subway station for each park
        nearest = parks.sjoin_nearest(
            self.subway_gdf,
            how="left",
            distance_col="distance_to_subway_m",
            max_distance=self.max_park_distance,
        )

        # sjoin creates duplicates and adds suffixes for conflicting columns
        # Drop duplicates based on park geometry (unique identifier)
        nearest = nearest.drop_duplicates(subset=["park_name", "geometry"])

        # Rename station_name from right side (may have suffix)
        if "station_name" in nearest.columns:
            nearest = nearest.rename(columns={"station_name": "nearest_station"})
        elif "station_name_right" in nearest.columns:
            nearest = nearest.rename(columns={"station_name_right": "nearest_station"})

        # Filter out parks with no nearby subway (NaN from sjoin)
        nearest = nearest.dropna(subset=["nearest_station"])

        # Count subway stations within max_park_distance radius for each park
        # Also store station IDs for map display (to avoid recalculating)
        subway_counts = []
        nearby_station_ids = []

        for idx, park in nearest.iterrows():
            buffer = park.geometry.buffer(self.max_park_distance)
            nearby_stations = self.subway_gdf[self.subway_gdf.intersects(buffer)]
            subway_counts.append(len(nearby_stations))
            nearby_station_ids.append(list(nearby_stations.index))

        nearest[f"subway_count_{self.max_park_distance}m"] = subway_counts
        nearest["nearby_station_ids"] = nearby_station_ids

        # Calculate accessibility score (inverse of distance, normalized)
        # Closer = better score
        # Base Accessibility Score (0-100)

        # How it works:
        # - Normalization: Converts distance to a 0-100 scale
        # - Inverse relationship: Closer parks = higher score

        # Example (if max_dist = 500m):
        # Park 50m from subway:  100 * (1 - 50/500)  = 90 points
        # Park 250m from subway: 100 * (1 - 250/500) = 50 points
        # Park 500m from subway: 100 * (1 - 500/500) = 0 points

        max_dist = nearest["distance_to_subway_m"].max()
        if max_dist > 0:
            nearest["accessibility_score"] = 100 * (
                1 - nearest["distance_to_subway_m"] / max_dist
            )
        else:
            nearest["accessibility_score"] = 100

        # Bonus for multiple nearby stations
        # Logic:
        # - More nearby stations = better transit options
        # - Each additional station within 500m adds +5 points
        # Example:
        # Park A: 100m from 1 station  → 80 base + 5  = 85 total
        # Park B: 150m from 3 stations → 70 base + 15 = 85 total (comparable!)

        # nearest['accessibility_score'] += nearest['subway_count_500m'] * 5

        self.parks_with_scores = nearest
        return nearest

    def calculate_social_activity(self) -> gpd.GeoDataFrame:
        """
        Calculate social activity score based on restaurant density around parks

        Filters:
        - Only includes restaurants with inspection score

        Returns:
            GeoDataFrame with parks and social activity metrics
        """

        # restaurant score based on inspection ratings
        # - 0-13 = A grade (best)
        # - 14-27 = B grade
        # - 28+ = C grade

        GRADE_TRESHOLDS = 20  # Score <= 20 includes A and most of B grades
        if self.parks_with_scores is None:
            raise ValueError("Run calculate_park_accessibility() first")

        parks = self.parks_with_scores.copy()

        good_restaurants = self.restaurants_gdf[
            self.restaurants_gdf["score"] <= GRADE_TRESHOLDS
        ].copy()

        # Count quality restaurants within radius for each park
        # Also store restaurant IDs for map display (to avoid recalculating)
        restaurant_counts = []
        nearby_restaurant_ids = []

        for idx, park in parks.iterrows():
            buffer = park.geometry.buffer(self.restaurant_radius)
            nearby_restaurants = good_restaurants[good_restaurants.intersects(buffer)]
            restaurant_counts.append(len(nearby_restaurants))
            nearby_restaurant_ids.append(list(nearby_restaurants.index))

        parks[f"restaurant_count_{self.restaurant_radius}m"] = restaurant_counts
        parks["nearby_restaurant_ids"] = nearby_restaurant_ids

        # Calculate social activity score (0-100)
        # Normalizes restaurant counts: park with most restaurants = 100, others scaled proportionally
        # Example: If max is 40 restaurants, park with 20 gets score of 50
        max_count = parks[f"restaurant_count_{self.restaurant_radius}m"].max()
        if max_count > 0:
            parks["social_activity_score"] = (
                100 * parks[f"restaurant_count_{self.restaurant_radius}m"] / max_count
            )
        else:
            parks["social_activity_score"] = 0

        self.parks_with_scores = parks
        return parks

    def calculate_borough_balance(self, top_n=3) -> gpd.GeoDataFrame:
        """
        Select top N parks from each borough to ensure geographic balance

        Args:
            top_n: Number of parks to select from each borough (default: 3)

        Returns:
            GeoDataFrame with top parks from each borough
        """
        if self.parks_with_scores is None:
            raise ValueError(
                "Run calculate_park_accessibility() and calculate_social_activity() first"
            )

        parks = self.parks_with_scores.copy()

        # Calculate combined score (average of accessibility and social activity)
        parks["combined_score"] = (
            parks["accessibility_score"] + parks["social_activity_score"]
        ) / 2

        # Get top N parks from each borough
        balanced_parks = (
            parks.groupby("borough_left", group_keys=False)
            .apply(lambda x: x.nlargest(top_n, "combined_score"))
            .reset_index(drop=True)
        )

        self.parks_with_scores = balanced_parks
        return parks

    def find_best_locations(self) -> pd.DataFrame:
        """
        Placeholder for future filtering logic
        :param n:
        :return:
        """
        pass

    def summary(self, top_n_per_borough=3) -> gpd.GeoDataFrame:
        """
        Run complete analysis pipeline and return top parks with justifications

        Args:
            top_n_per_borough: Number of parks to select from each borough

        Returns:
            GeoDataFrame with top parks and justification text
        """
        self.calculate_park_accessibility()
        self.calculate_social_activity()
        balanced_parks = self.calculate_borough_balance(top_n=top_n_per_borough)

        # Generate justification text for each park
        justifications = []
        for idx, park in balanced_parks.iterrows():
            subway_count = park[f"subway_count_{self.max_park_distance}m"]
            restaurant_count = park[f"restaurant_count_{self.restaurant_radius}m"]
            nearest_station = park["nearest_station"]
            distance = int(park["distance_to_subway_m"])

            # Calculate average restaurant score around this park
            buffer = park.geometry.buffer(self.restaurant_radius)
            nearby_restaurants = self.restaurants_gdf[
                self.restaurants_gdf.intersects(buffer)
            ]
            avg_score = (
                nearby_restaurants["score"].mean() if len(nearby_restaurants) > 0 else 0
            )

            justification = (
                f"Located {distance}m from {nearest_station} station. "
                f"Has {subway_count} metro stations and {restaurant_count} quality restaurants "
                f"within {self.restaurant_radius}m (avg inspection score: {avg_score:.1f}). "
                f"Combined score: {park['combined_score']:.1f}/100"
            )
            justifications.append(justification)

        balanced_parks["justification"] = justifications

        self.parks_with_scores = balanced_parks
        return balanced_parks
