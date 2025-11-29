from data_loader import DataLoader


data_loader = DataLoader()

parks_df = data_loader.download_parks()

print(parks_df.head())