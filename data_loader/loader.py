import pandas as pd
from sodapy import Socrata


class DataLoader:
    @staticmethod
    def download_parks() -> pd.DataFrame:
        """Download parks data"""
        client = Socrata("data.cityofnewyork.us", None)
        results = client.get("enfh-gkve", limit=5000)
        df = pd.DataFrame.from_records(results)

        print(df.head())

        if 'multipolygon' in df.columns:
            df['longitude'] = df['multipolygon'].apply(
            lambda x: float(x['coordinates'][0][0][0][0]) if pd.notna(x) and 'coordinates' in x else None
        )
            df['latitude'] = df['multipolygon'].apply(
            lambda x: float(x['coordinates'][0][0][0][1]) if pd.notna(x) and 'coordinates' in x else None
        )

        df = df.dropna(subset=['longitude', 'latitude'])

        df['acres'] = pd.to_numeric(df.get('acres', 0), errors='coerce').fillna(0)
        df['park_name'] = df.get('signname', df.get('name', 'Unknown Park'))
        df['borough'] = df.get('borough', 'Unknown')

        cols_to_keep = ['park_name', 'borough', 'acres', 'latitude', 'longitude']
        df = df[[col for col in cols_to_keep if col in df.columns]]

        return df








