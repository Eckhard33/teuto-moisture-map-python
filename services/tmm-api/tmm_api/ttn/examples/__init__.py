from datetime import datetime, timedelta
from random import random


def construct_data(device_id, lon, lat, received_at, moisture, temperature, conductivity):
    return {
        "latitude": lat,
        "longitude": lon,
        "altitude": 17.42,
        "device_id": str(device_id),
        "device_brand": "test_brand",
        "device_model": "test_model",
        "received_at": received_at,
        "battery": 0.8,
        "conductivity": conductivity,
        "temperature": temperature,
        "moisture": moisture,
        "battery_unit": "V",
        "conductivity_unit": "uS/cm",
        "temperature_unit": "°C",
        "moisture_unit": "%",
    }


def generate_test_data(num_devices: int, days: int, num_measurements: int = 24):
    last = datetime.now()
    for device in range(num_devices):
        lat = 52.01 + (random() - 0.5) / 2
        lon = 8.542732 + (random() - 0.5)
        for day in range(days):
            for measurement in range(num_measurements):
                received_at = last - timedelta(days=day + measurement / num_measurements)
                yield construct_data(
                    device,
                    lon,
                    lat,
                    received_at,
                    random() * 10 + random() * random() * 90,
                    random() * 30,
                    random(),
                )
