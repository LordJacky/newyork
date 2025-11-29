import pandas as pd
from sodapy import Socrata
from pathlib import Path
from datetime import datetime, timedelta
from functools import wraps

# TODO: unhardcode dataset IDs
# TODO: add error handling for network issues
# TODO: validate data schema


def cache_result(cache_file: str):
    """Decorator to cache function results to parquet file"""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache_path = DataLoader.CACHE_DIR / cache_file

            # Try to load from cache
            if cache_path.exists():
                file_time = datetime.fromtimestamp(cache_path.stat().st_mtime)
                age = datetime.now() - file_time

                if age <= timedelta(hours=DataLoader.CACHE_EXPIRY_HOURS):
                    print(f"Loading from cache: {cache_file}")
                    return pd.read_parquet(cache_path)
                else:
                    print(f"Cache expired for {cache_file}")

            df = func(*args, **kwargs)

            # Save to cache
            DataLoader.CACHE_DIR.mkdir(exist_ok=True)
            df.to_parquet(cache_path, index=False)
            print(f"Saved to cache: {cache_file}")

            return df

        return wrapper

    return decorator


class DataLoader:
    CACHE_DIR = Path("cache")
    CACHE_EXPIRY_HOURS = 5

    @staticmethod
    @cache_result("parks.parquet")
    def download_parks() -> pd.DataFrame:
        """Download parks data"""
        client = Socrata("data.cityofnewyork.us", None)
        results = client.get("enfh-gkve", limit=5000)
        df = pd.DataFrame.from_records(results)

        if "multipolygon" in df.columns:
            df["longitude"] = df["multipolygon"].apply(
                lambda x: float(x["coordinates"][0][0][0][0])
                if pd.notna(x) and "coordinates" in x
                else None
            )
            df["latitude"] = df["multipolygon"].apply(
                lambda x: float(x["coordinates"][0][0][0][1])
                if pd.notna(x) and "coordinates" in x
                else None
            )

        df = df.dropna(subset=["longitude", "latitude"])

        df["acres"] = pd.to_numeric(df.get("acres", 0), errors="coerce").fillna(0)
        df["park_name"] = df.get("signname", df.get("name", "Unknown Park"))
        df["borough"] = df.get("borough", "Unknown")
        df["park_type"] = df.get("typecategory", "Unknown")

        cols_to_keep = [
            "park_name",
            "borough",
            "acres",
            "park_type",
            "latitude",
            "longitude",
        ]
        df = df[[col for col in cols_to_keep if col in df.columns]]

        return df

    @staticmethod
    @cache_result("restaurants.parquet")
    def download_restaurants() -> pd.DataFrame:
        """Download restaurant inspection data with pagination"""
        client = Socrata("data.cityofnewyork.us", None)

        # Pagination to not exceed row limits
        all_results = []
        offset = 0
        limit = 50000

        while True:
            results = client.get("43nn-pn8j", limit=limit, offset=offset)
            if not results:
                break
            all_results.extend(results)
            offset += limit

        df = pd.DataFrame.from_records(all_results)

        if "latitude" in df.columns and "longitude" in df.columns:
            df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
            df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")

        df = df.dropna(subset=["longitude", "latitude"])

        df["restaurant_name"] = df.get("dba", "Unknown Restaurant")
        df["cuisine"] = df.get("cuisine_description", "Unknown")
        df["borough"] = df.get("boro", "Unknown")
        df["zipcode"] = df.get("zipcode", "")
        df["score"] = pd.to_numeric(df.get("score", None), errors="coerce")

        cols_to_keep = [
            "restaurant_name",
            "cuisine",
            "borough",
            "zipcode",
            "score",
            "latitude",
            "longitude",
        ]
        df = df[[col for col in cols_to_keep if col in df.columns]]

        df = df.drop_duplicates(subset=["restaurant_name", "latitude", "longitude"])

        return df

    @staticmethod
    @cache_result("subway_ridership.parquet")
    def download_subway_ridership() -> pd.DataFrame:
        """Download MTA subway hourly ridership data with pagination"""
        client = Socrata("data.ny.gov", None)

        # Pagination to not exceed row limits
        all_results = []
        offset = 0
        limit = 50000

        while True:
            results = client.get("wujg-7c2s", limit=limit, offset=offset)
            if not results:
                break
            all_results.extend(results)
            offset += limit
            # Limit total records to avoid excessive loading
            if offset >= 500000:
                break

        df = pd.DataFrame.from_records(all_results)

        if df.empty:
            return df

        if "ridership" in df.columns:
            df["ridership"] = pd.to_numeric(df["ridership"], errors="coerce")
        if "latitude" in df.columns:
            df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
        if "longitude" in df.columns:
            df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")

        df = df.dropna(subset=["longitude", "latitude"])

        return df

    @staticmethod
    @cache_result("subway_stations.parquet")
    def download_subway_stations() -> pd.DataFrame:
        """Download MTA subway station data from NY State Open Data"""
        client = Socrata("data.ny.gov", None)
        results = client.get("39hk-dx4f", limit=5000)
        df = pd.DataFrame.from_records(results)

        if "gtfs_latitude" in df.columns and "gtfs_longitude" in df.columns:
            df["latitude"] = pd.to_numeric(df["gtfs_latitude"], errors="coerce")
            df["longitude"] = pd.to_numeric(df["gtfs_longitude"], errors="coerce")

        df = df.dropna(subset=["longitude", "latitude"])

        df["station_name"] = df.get("stop_name", "Unknown Station")
        df["routes"] = df.get("daytime_routes", "")
        df["borough"] = df.get("borough", "Unknown")
        df["ada_accessible"] = pd.to_numeric(df.get("ada", 0), errors="coerce")

        cols_to_keep = [
            "station_name",
            "routes",
            "borough",
            "ada_accessible",
            "latitude",
            "longitude",
        ]
        df = df[[col for col in cols_to_keep if col in df.columns]]

        return df
