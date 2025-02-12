import threading


import requests
from io import BytesIO, TextIOWrapper
from zipfile import ZipFile
from csv import DictReader

from datetime import date, datetime, timedelta
from bs4 import BeautifulSoup

from pyproj import Geod

from models import DWDStation, PrecipitationMeasurement


__dataset_urls: dict[str, str] | None = None
__dataset_urls_lock = threading.Lock()


def get_precipitation_dataset_urls() -> dict[str, str]:
    """Returns a dict mapping station IDs to urls"""
    global __dataset_urls
    with __dataset_urls_lock:
        if __dataset_urls:
            return __dataset_urls
        url = (
            "https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/daily/more_precip/historical/"
        )
        with requests.get(url) as page:
            soup = BeautifulSoup(page.text, "html.parser")
            __dataset_urls = dict(
                [
                    [link[14:19], url + link]
                    for link in (a.get("href") for a in soup.find_all("a"))
                    if link.startswith("tageswerte_RR_")
                ]
            )
        return __dataset_urls


__stations: list[DWDStation] | None = None
__stations_lock = threading.Lock()


def get_stations() -> list[DWDStation]:
    global __stations
    with __stations_lock:
        if __stations:
            return __stations
        # Stations_id von_datum bis_datum Stationshoehe geoBreite geoLaenge Stationsname Bundesland
        #                 00001 19120101 19860630            478     47.8413    8.8493 Aach                                     Baden-Württemberg
        line_reference = "00001 19120101 19860630            478     47.8413    8.8493 Aach                                     Baden-Württemberg                                                                                 "

        def lfield(field_ref: str, next_field: str | None):
            start = line_reference.find(field_ref)
            end = line_reference.find(next_field) - 1 if next_field else -1
            return lambda line: line[start:end].strip()

        def rfield(field_ref: str, prev_field: str | None):
            start = line_reference.find(prev_field) + len(prev_field) + 1 if prev_field else 0
            end = line_reference.find(field_ref) + len(field_ref)
            return lambda line: line[start:end].strip()

        parse_station_id = rfield("00001", None)
        parse_data_since = rfield("19120101", "00001")
        parse_data_until = rfield("19860630", "19120101")
        parse_height = rfield("478", "19860630")
        parse_lon = rfield("47.8413", "478")
        parse_lat = rfield("8.8493", "47.8413")
        parse_name = lfield("Aach", "Baden-Württemberg")
        parse_state = lfield("Baden-Württemberg", None)

        datasets = get_precipitation_dataset_urls()

        def parse_station(line) -> DWDStation:
            station_id = parse_station_id(line)
            return DWDStation(
                station_id=station_id,
                data_since=datetime.strptime(parse_data_since(line), "%Y%m%d").date(),
                data_until=datetime.strptime(parse_data_until(line), "%Y%m%d").date(),
                height=int(parse_height(line)),
                lon=float(parse_lon(line)),
                lat=float(parse_lat(line)),
                name=parse_name(line),
                state=parse_state(line),
                historic_precipitation_dataset_url=datasets[station_id],
            )

        url = "https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/daily/more_precip/historical/RR_Tageswerte_Beschreibung_Stationen.txt"
        result = []
        with requests.get(url, stream=True) as resp:
            for line in resp.text.splitlines()[2:]:
                if parse_station_id(line) in datasets:
                    result.append(parse_station(line))
        __stations = result
        return __stations


geod = Geod(ellps="WGS84")


def distance(lon1: float, lat1: float, lon2: float, lat2: float):
    return geod.inv(lons1=[lon1], lats1=[lat1], lons2=[lon2], lats2=[lat2])[2][0]


def nearest_station(lon: float, lat: float) -> DWDStation:
    return min(get_stations(), key=lambda station: distance(lon, lat, station.lon, station.lat))


def nearest_active_station(lon: float, lat: float) -> DWDStation:
    at_least_active_until = date.today() - timedelta(days=32)
    active_stations = filter(
        lambda station: station.historic_precipitation_dataset_url is not None
        and station.data_until > at_least_active_until,
        get_stations(),
    )
    return min(
        active_stations,
        key=lambda station: distance(lon, lat, station.lon, station.lat),
    )


def get_precipitation(station: DWDStation) -> list[PrecipitationMeasurement]:
    with requests.get(station.historic_precipitation_dataset_url) as resp:
        zipfile = ZipFile(BytesIO(resp.content))
        product_file_name = next((file for file in zipfile.namelist() if file.startswith("produkt")), None)
        assert product_file_name, "No product file found in downloaded zip"
        product_file = zipfile.open(product_file_name, "r")
        result = []
        for row in DictReader(TextIOWrapper(product_file), delimiter=";", skipinitialspace=True):
            try:
                rs = float(row.get("RS"))  # type: ignore
                rsf = int(row.get("RSF"))  # type: ignore
                qn = int(row.get("QN_6"))  # type: ignore
                measurement_date = datetime.strptime(row.get("MESS_DATUM"), "%Y%m%d").date()  # type: ignore
                if rs != -999:
                    result.append(
                        PrecipitationMeasurement(
                            station=station,
                            date=measurement_date,
                            precipitation=rs,
                            form=rsf,
                            quality=qn,
                        )
                    )
                else:
                    print(f"Row without precipitation value! station: {station.station_id}, row: {row}")
            except Exception as e:
                print(f"Could not parse row: {row}, eror: {e}")
        return result


def run():
    station = nearest_active_station(52, 8.53)
    print(f"Station: {station.name}, id: {station.station_id}")
    data = get_precipitation(station)
    print(f"Received {len(data)} measurements for station. Latest 30:")
    for x in data[-30:]:
        print(f"{x.date}: {x.precipitation}")


if __name__ == "__main__":
    run()
