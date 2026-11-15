import csv
import io
import zipfile
from datetime import date

import pytest

from app.gtfs.importer import import_feed
from app.gtfs.schedule import gtfs_seconds


def csv_text(header, rows):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(header.split(","))
    writer.writerows(rows)
    return output.getvalue()


def clock(seconds):
    return f"{seconds // 3600:02}:{seconds // 60 % 60:02}:{seconds % 60:02}"


def files(operator, arrival="17:42:00", departures_at=("17:51:00", "18:03:00", "18:15:00")):
    stops = [("H", "Station", 54, 18, 1, ""), ("1", "Earlier stop", 54, 18, 0, ""),
             ("7500", "GDAŃSK GŁÓWNY", 54, 18, 0, "H"),
             ("2001", "Dworzec Główny 01", 54, 18, 0, "H"),
             ("2002", "Dworzec Główny 01", 54, 18, 0, "H"),
             ("9", "Destination", 54, 18, 0, ""), ("10", "Other destination", 54, 18, 0, "")]
    trips, times = [], []
    if operator == "skm":
        trips = [("rail", "S", "a", "Gdańsk Śródmieście", "")]
        seconds = gtfs_seconds(arrival)
        times = [("a", clock(seconds - 600), clock(seconds - 600), "1", 1, 0, 0),
                 ("a", arrival, clock(seconds + 60), "7500", 2, 0, 0)]
    else:
        for index, departure in enumerate(departures_at):
            trip_id = chr(97 + index)
            trips.append(("8", "S", trip_id, "Oliwa", 0))
            times.extend([(trip_id, departure, departure, "2001", 1, 0, 0),
                          (trip_id, clock(gtfs_seconds(departure) + 300), clock(gtfs_seconds(departure) + 300), "9", 2, 0, 0)])
    return {
        "agency.txt": "agency_id,agency_name,agency_url,agency_timezone\nA,Fixture,https://example.invalid,Europe/Warsaw\n",
        "stops.txt": csv_text("stop_id,stop_name,stop_lat,stop_lon,location_type,parent_station", stops),
        "routes.txt": "route_id,agency_id,route_short_name,route_type\nrail,A,SKM,2\n8,A,8,3\nother,A,8,3\n",
        "trips.txt": csv_text("route_id,service_id,trip_id,trip_headsign,direction_id", trips),
        "stop_times.txt": csv_text("trip_id,arrival_time,departure_time,stop_id,stop_sequence,pickup_type,drop_off_type", times),
        "calendar.txt": "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\nS,1,1,1,1,1,0,0,20260101,20261231\n",
        "calendar_dates.txt": "service_id,date,exception_type\nS,20261114,1\nS,20261116,2\n",
    }


@pytest.fixture
def setup_feed(tmp_path):
    def setup(skm=None, ztm=None):
        database = tmp_path / "transit.db"
        for operator, content in (("skm", skm or files("skm")), ("ztm", ztm or files("ztm"))):
            archive = tmp_path / f"{operator}.zip"
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
                for name, text in content.items():
                    output.writestr(name, text)
            import_feed(operator, archive, database)
        return database
    return setup


