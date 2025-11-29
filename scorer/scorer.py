class Scorer:
    """Score park locations based on multiple criteria"""

    def __init__(self, parks_gdf, restaurants_gdf, subway_gdf,
             min_park_area=5.0, max_subway_distance=500):
        pass


    # filtering metro stations
    def calculate_park_accessibility(self) -> None: # top parks
        """Calculate distance to parth from nearest station"""
        return df

    # filtering parks based on area, ignore small ones

    def calculate_social_activity(self, radius=500) -> None:
        """Calculate restaurant density around each park"""
        # judge restaurants based on inspection ratings -> density
        pass

    def calculate_borough_balance(self) -> None:
        # filter top parks based on borough
        pass

    def find_best_locations(self, n=5) -> pd.DataFrame:
        # filter park based on distance to the our metro station and other metric if needed
        # can use crime dataset
        pass

    def get_location_justification(self, location) -> list[str]:
        # out of scope
        justifications = []

        return justifications