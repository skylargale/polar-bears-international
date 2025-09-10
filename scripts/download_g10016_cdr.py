import os
import datetime
import requests

# Output directory (on Cheyenne WORK space)
BASE_DIR = "/glade/work/skygale/data/G10016_V3_CDR_25km_2025"
BASE_URL = "https://noaadata.apps.nsidc.org/NOAA/G10016_V3/CDR/north/daily"

# List of possible platform identifiers
PLATFORMS = ["n07", "F08", "F11", "F13", "F17", "F18"]

# Define start and end dates
start_date = datetime.date(2025, 1, 1)
end_date = datetime.date(2025, 9, 8)

# Loop through dates
current_date = start_date
while current_date <= end_date:
    ymd = current_date.strftime("%Y%m%d")
    year = current_date.year
    year_dir = os.path.join(BASE_DIR, str(year))
    os.makedirs(year_dir, exist_ok=True)

    downloaded = False

    for platform in PLATFORMS:
        filename = f"sic_psn25_{ymd}_{platform}_icdr_v03r00.nc"
        url = f"{BASE_URL}/{year}/{filename}"
        local_path = os.path.join(year_dir, filename)

        if os.path.exists(local_path):
            print(f"✅ Already exists: {filename}")
            downloaded = True
            break

        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                with open(local_path, "wb") as f:
                    f.write(response.content)
                print(f"📥 Downloaded: {filename}")
                downloaded = True
                break  # Stop trying platforms if one worked
        except Exception as e:
            print(f"⚠️ Error fetching {filename}: {e}")

    if not downloaded:
        print(f"❌ No file found for {ymd} on any platform.")

    current_date += datetime.timedelta(days=1)

print("✅ Finished downloading G10016 daily data.")
