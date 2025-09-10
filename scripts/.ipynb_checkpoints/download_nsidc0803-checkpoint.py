import os
import datetime
import requests

# Output directory (on Cheyenne WORK space)
BASE_DIR = "/glade/work/skygale/data/NSIDC_0803_25km_2023_Present"
BASE_URL = "https://daacdata.apps.nsidc.org/pub/DATASETS/nsidc0803_daily_a2_seaice_conc_v2"

# List of possible platform identifiers
PLATFORMS = ["am2", "n07", "F08", "F11", "F13", "F17", "F18"]

# Define start and end dates
start_date = datetime.date(2023, 1, 1)
end_date = datetime.date(2025, 9, 8)

# Loop through dates
current_date = start_date
while current_date <= end_date:
    ymd = current_date.strftime("%Y%m%d")
    year = current_date.strftime("%Y")
    month = current_date.strftime("%m")

    filename = f"NSIDC-0803_SEAICE_AMSR2_N_{ymd}_v2.0.nc"
    file_url = f"{BASE_URL}/{filename}"

    local_dir = os.path.join(BASE_DIR, year, month)
    os.makedirs(local_dir, exist_ok=True)
    local_path = os.path.join(local_dir, filename)

    if not os.path.exists(local_path):
        try:
            response = requests.get(file_url, timeout=10)
            if response.status_code == 200:
                with open(local_path, 'wb') as f:
                    f.write(response.content)
                print(f"📥 Downloaded: {filename}")
            else:
                print(f"❌ File not found: {filename} (HTTP {response.status_code})")
        except Exception as e:
            print(f"⚠️ Error fetching {filename}: {e}")
    else:
        print(f"✅ File already exists: {filename}")

    current_date += datetime.timedelta(days=1)

print("✅ Finished downloading NSIDC-0803 daily data.")