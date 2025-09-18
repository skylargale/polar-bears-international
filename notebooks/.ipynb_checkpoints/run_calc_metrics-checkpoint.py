import glob
import numpy as np
import pandas as pd
import xarray as xr
from pyproj import Transformer
from shapely.geometry import Polygon, Point
import warnings
warnings.simplefilter(action='ignore', category=FutureWarning)


def get_hudson_masks(ds):
    """
    Create masks for West and South Hudson Bay based on x/y or lat/lon bounds.

    Returns:
        mask_west, mask_south : xarray.DataArray (boolean)
    """

    # Define bounds (lon/lat)
    west_bounds = {'lon_min': -95, 'lon_max': -88, 'lat_min': 56, 'lat_max': 63}
    south_bounds = {'lon_min': -88, 'lon_max': -75, 'lat_min': 51, 'lat_max': 59}

    if 'lat' in ds.coords and 'lon' in ds.coords:
        print("Using lat/lon coordinates for masking")

        mask_west = ((ds.lon >= west_bounds['lon_min']) & (ds.lon <= west_bounds['lon_max']) &
                     (ds.lat >= west_bounds['lat_min']) & (ds.lat <= west_bounds['lat_max']))

        mask_south = ((ds.lon >= south_bounds['lon_min']) & (ds.lon <= south_bounds['lon_max']) &
                      (ds.lat >= south_bounds['lat_min']) & (ds.lat <= south_bounds['lat_max']))

    elif 'x' in ds.coords and 'y' in ds.coords:
        print("Using x/y coordinates for masking")

        # Set up transformer
        transformer = Transformer.from_crs("EPSG:4326", "EPSG:3413", always_xy=True)

        # Define West polygon in lon/lat
        west_poly_lonlat = [
            (west_bounds['lon_min'], west_bounds['lat_min']),
            (west_bounds['lon_max'], west_bounds['lat_min']),
            (west_bounds['lon_max'], west_bounds['lat_max']),
            (west_bounds['lon_min'], west_bounds['lat_max']),
            (west_bounds['lon_min'], west_bounds['lat_min'])
        ]

        # Define South polygon in lon/lat
        south_poly_lonlat = [
            (south_bounds['lon_min'], south_bounds['lat_min']),
            (south_bounds['lon_max'], south_bounds['lat_min']),
            (south_bounds['lon_max'], south_bounds['lat_max']),
            (south_bounds['lon_min'], south_bounds['lat_max']),
            (south_bounds['lon_min'], south_bounds['lat_min'])
        ]

        # Transform both polygons to projected x/y
        west_poly_proj = [transformer.transform(lon, lat) for lon, lat in west_poly_lonlat]
        south_poly_proj = [transformer.transform(lon, lat) for lon, lat in south_poly_lonlat]

        # Create shapely polygons
        west_polygon = Polygon(west_poly_proj)
        south_polygon = Polygon(south_poly_proj)

        # Create 2D meshgrid of x and y coordinates from dataset
        xx, yy = np.meshgrid(ds.x.values, ds.y.values)

        # Flatten meshgrid for efficient point-in-polygon testing
        points = np.vstack((xx.ravel(), yy.ravel())).T

        # Create masks by checking if points fall inside polygons
        mask_west_flat = np.array([west_polygon.contains(Point(x, y)) for x, y in points])
        mask_south_flat = np.array([south_polygon.contains(Point(x, y)) for x, y in points])

        # Reshape masks back to 2D (y, x)
        mask_west = xr.DataArray(mask_west_flat.reshape(xx.shape), dims=('y', 'x'), coords={'y': ds.y, 'x': ds.x})
        mask_south = xr.DataArray(mask_south_flat.reshape(xx.shape), dims=('y', 'x'), coords={'y': ds.y, 'x': ds.x})

    else:
        raise ValueError("Dataset does not have expected coordinate system (lat/lon or x/y)")

    return mask_west, mask_south


def calc_event_day(da, threshold, min_days, event_type, default_day=None, doy_start=1, perennial_day=None):
    """
    Calculate day-of-year (DOY) when SIC condition is met for a minimum number of days.

    Parameters:
        da : xarray.DataArray
            SIC values [0 to 100], with 'time' dim
        threshold : float
            SIC threshold (in %)
        min_days : int
            Rolling window size (1 = first day condition is met)
        event_type : str
            'ice_free' or 'freeze_up'
        default_day : int or None
            Value if event never occurs
        doy_start : int
            DOY of first time index (used to convert to calendar DOY)
        perennial_day : int or None
            Day to assign if region never changes state (e.g. always frozen)

    Returns:
        event_doy : xarray.DataArray with DOY of event
    """
    da = da.set_index(time='time')

    # Rolling window of booleans
    rolling = da.rolling(time=min_days, center=False).construct("window_dim")

    if event_type == 'ice_free':
        cond = (rolling < threshold).all('window_dim')
        perenial_mask = (da.min(dim='time') >= threshold)
    elif event_type == 'freeze_up':
        cond = (rolling > threshold).all('window_dim')
        perenial_mask = (da.max(dim='time') <= threshold)
    else:
        raise ValueError("event_type must be 'ice_free' or 'freeze_up'")

    # First occurrence of window meeting condition
    event_idx = cond.argmax(dim='time')
    event_idx = event_idx.where(cond.any(dim='time'), np.nan)

    # Convert to DOY
    event_doy = event_idx + doy_start - 1

    # Set perennially ice-covered/open regions
    if perennial_day is not None:
        event_doy = event_doy.where(~perenial_mask, other=perennial_day)

    # Set default if event never occurred (but not perennially)
    if default_day is not None:
        event_doy = event_doy.fillna(default_day)

    event_doy = event_doy.where(da.isel(time=0).notnull())  # Apply mask
    event_doy.name = f"{event_type}_day"

    return event_doy


def calc_ice_free_days(da, threshold):
    """
    Count number of days with SIC < threshold.

    Parameters:
        da : xarray.DataArray
        threshold : float

    Returns:
        xarray.DataArray with ice-free days
    """
    result = (da < threshold).sum(dim='time')
    result.name = 'ice_free_days'
    return result


def compute_all_metrics(
    ds,
    name,
    years,
    freeze_threshold=30,
    icefree_threshold=15,
    breakup_threshold=15,
    freeze_min_days=5,
    icefree_min_days=10,
    breakup_min_days=10,
    default_breakup_day=150,
    default_freeze_day=275,
    perennial_freeze_day=275,
    perennial_icefree_day=150,
):
    """
    Compute per-year sea ice metrics (freeze-up, breakup, and ice-free days) for West/South Hudson Bay.
    Includes diagnostics printing to help debug event detection.

    Parameters:
        ds : xarray.DataArray (SIC)
        name : str (dataset label)
        years : list of int
        freeze_threshold, icefree_threshold, breakup_threshold : float
        *_min_days : int
            Rolling window for detecting events (1 = single-day)
        default_*_day : int
            DOY to assign if condition never met
        perennial_*_day : int
            DOY to assign if region is perennially frozen or ice-free

    Returns:
        dict with structure:
            { region: { metric_name: xarray.DataArray (year, y, x), ... }, ... }
    """

    mask_west, mask_south = get_hudson_masks(ds)
    results = {"west": {}, "south": {}}

    for region, mask in zip(["west", "south"], [mask_west, mask_south]):
        print(f"\nProcessing {name} for {region} Hudson Bay")

        ds_masked = ds.where(mask)
        freeze_list, icefree_list, breakup_list = [], [], []

        for year in years:
            print(f"  Year: {year}")
            ds_y = ds_masked.sel(time=str(year))

            if ds_y.time.size == 0:
                print(f"    No data for year {year}, skipping")
                continue

            doy_start = pd.to_datetime(ds_y.time.values[0]).dayofyear

            freeze = calc_event_day(
                ds_y,
                threshold=freeze_threshold,
                min_days=freeze_min_days,
                event_type='freeze_up',
                doy_start=doy_start,
                default_day=default_freeze_day,
                perennial_day=perennial_freeze_day,
            ).assign_coords(year=year)

            icefree_days = calc_ice_free_days(
                ds_y, threshold=icefree_threshold
            ).assign_coords(year=year)

            breakup = calc_event_day(
                ds_y,
                threshold=breakup_threshold,
                min_days=breakup_min_days,
                event_type='ice_free',
                doy_start=doy_start,
                default_day=default_breakup_day,
                perennial_day=perennial_icefree_day,
            ).assign_coords(year=year)

            freeze_list.append(freeze)
            icefree_list.append(icefree_days)
            breakup_list.append(breakup)

        # Concatenate along 'year' dimension
        results[region]["freeze_up_day"] = xr.concat(freeze_list, dim="year")
        results[region]["ice_free_days"] = xr.concat(icefree_list, dim="year")
        results[region]["breakup_day"] = xr.concat(breakup_list, dim="year")

    return results


def save_dict_to_netcdf(data_dict, filename):
    dataset = xr.Dataset()

    for region, variables in data_dict.items():
        for var_name, da in variables.items():
            new_var_name = f"{region}_{var_name}"
            dataset[new_var_name] = da

    encoding = {
        var: {"zlib": True, "complevel": 1}
        for var in dataset.data_vars
    }

    dataset.to_netcdf(filename, engine="netcdf4", encoding=encoding)


# List potential sea ice variable names
vars = ['am2_seaice_conc', 'cdr_seaice_conc', 'ICECON', 'sic']

# Allocate for dataset information
names, ds_all = [], []

for file_path in glob.glob('/glade/work/skygale/pbi-data/combined/*.nc'):
    name = file_path[38:-3]
    names.append(name)
    print(f'Processing {name}...')

    # Open dataset
    ds = xr.open_dataset(file_path, chunks={})

    # Get sea ice
    for varname in vars:
        if varname in ds.data_vars:
            ds = ds[varname]
            break

    # Standardize DataArrays names
    rename_dict = {}
    if 'ni' in ds.dims:
        rename_dict['ni'] = 'x'
    if 'nj' in ds.dims:
        rename_dict['nj'] = 'y'
    ds = ds.rename(rename_dict)

    # Reorder dimensions
    existing_dims = [dim for dim in ['time', 'y', 'x'] if dim in ds.dims]
    ds = ds.transpose(*existing_dims)

    min_val, max_val = np.nanmin(ds), np.nanmax(ds)
    if max_val <= 1.05:
        ds = ds * 100

    ds_all.append(ds)

# Sensor Comparison: AMSR2_25km_2012_2025 and G02202_25km_1978_2025
# Resolution Comparison: AMSR2_12.5km_2012_2025 and AMSR2_25km_2012_2025

years = list(range(2012, 2025))

ds_chunked = ds_all[1].chunk({'time': 31})
results_lazy = compute_all_metrics(ds_chunked, name="AMSR2_12.5km", years=years)
save_dict_to_netcdf(
    results_lazy,
    "/glade/derecho/scratch/skygale/metrics/AMSR2_12.5km_metrics.nc"
)

ds_chunked = ds_all[2].chunk({'time': 31})
results_lazy = compute_all_metrics(ds_chunked, name="AMSR2_25km", years=years)

save_dict_to_netcdf(
    results_lazy,
    "/glade/derecho/scratch/skygale/metrics/AMSR2_25km_metrics.nc"
)

ds_chunked = ds_all[4].chunk({'time': 31})
results_lazy = compute_all_metrics(ds_chunked, name="G02202", years=years)
save_dict_to_netcdf(
    results_lazy,
    "/glade/derecho/scratch/skygale/metrics/G02202_25km_metrics.nc"
)

print("Done!")
