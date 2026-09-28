import csv
import io
import zipfile


INPUT_ZIP = "otp/latest_raw.zip"
OUTPUT_ZIP = "otp/latest.zip"

DEFAULT_AGENCY_URL = "https://transport.mos.ru"


def read_csv(archive: zipfile.ZipFile, filename: str):
    """Читает CSV-файл из GTFS ZIP."""
    text = archive.read(filename).decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


def write_csv(rows: list[dict], fieldnames: list[str]) -> bytes:
    """Преобразует строки обратно в CSV."""
    output = io.StringIO()

    writer = csv.DictWriter(
        output,
        fieldnames=fieldnames,
        lineterminator="\n",
    )

    writer.writeheader()
    writer.writerows(rows)

    return output.getvalue().encode("utf-8")


def main():
    # Шаг 1. Читаем исходный ZIP целиком.
    with zipfile.ZipFile(INPUT_ZIP, "r") as source:
        files = {
            name: source.read(name)
            for name in source.namelist()
        }

    # ---------------------------------------------------------
    # Шаг 2. Исправляем пустые agency_url
    # ---------------------------------------------------------

    agency_text = files["agency.txt"].decode("utf-8-sig")
    agency_reader = csv.DictReader(io.StringIO(agency_text))

    agency_fieldnames = agency_reader.fieldnames
    agency_rows = list(agency_reader)

    fixed_agency_urls = 0

    for row in agency_rows:
        if not row["agency_url"].strip():
            row["agency_url"] = DEFAULT_AGENCY_URL
            fixed_agency_urls += 1

    files["agency.txt"] = write_csv(
        agency_rows,
        agency_fieldnames,
    )

    # ---------------------------------------------------------
    # Шаг 3. Получаем существующие trip_id
    # ---------------------------------------------------------

    trips_text = files["trips.txt"].decode("utf-8-sig")
    trips_reader = csv.DictReader(io.StringIO(trips_text))

    trip_ids = {
        row["trip_id"]
        for row in trips_reader
    }

    # ---------------------------------------------------------
    # Шаг 4. Получаем существующие stop_id
    # ---------------------------------------------------------

    stops_text = files["stops.txt"].decode("utf-8-sig")
    stops_reader = csv.DictReader(io.StringIO(stops_text))

    stop_ids = {
        row["stop_id"]
        for row in stops_reader
    }

    # ---------------------------------------------------------
    # Шаг 5. Фильтруем stop_times
    # ---------------------------------------------------------

    stop_times_text = files["stop_times.txt"].decode("utf-8-sig")
    stop_times_reader = csv.DictReader(io.StringIO(stop_times_text))

    stop_times_fieldnames = stop_times_reader.fieldnames

    valid_stop_times = []

    total = 0
    removed = 0

    missing_trip = 0
    missing_stop = 0
    missing_both = 0

    for row in stop_times_reader:
        total += 1

        trip_missing = row["trip_id"] not in trip_ids
        stop_missing = row["stop_id"] not in stop_ids

        if trip_missing:
            missing_trip += 1

        if stop_missing:
            missing_stop += 1

        if trip_missing and stop_missing:
            missing_both += 1

        # Такая запись всё равно не может быть использована OTP.
        if trip_missing or stop_missing:
            removed += 1
            continue

        valid_stop_times.append(row)

    files["stop_times.txt"] = write_csv(
        valid_stop_times,
        stop_times_fieldnames,
    )

    # ---------------------------------------------------------
    # Шаг 6. Создаём новый GTFS ZIP
    # ---------------------------------------------------------

    with zipfile.ZipFile(
        OUTPUT_ZIP,
        "w",
        zipfile.ZIP_DEFLATED,
    ) as destination:

        for filename, data in files.items():
            destination.writestr(filename, data)

    # ---------------------------------------------------------
    # Статистика
    # ---------------------------------------------------------

    print()
    print("GTFS preparation finished")
    print("-------------------------")
    print(f"Fixed agency_url:          {fixed_agency_urls}")
    print()
    print(f"Stop times total:          {total}")
    print(f"Missing trip:              {missing_trip}")
    print(f"Missing stop:              {missing_stop}")
    print(f"Missing both:              {missing_both}")
    print(f"Removed stop times:        {removed}")
    print(f"Remaining stop times:      {len(valid_stop_times)}")
    print(f"Removed:                   {removed / total * 100:.2f}%")
    print()
    print(f"Output: {OUTPUT_ZIP}")


if __name__ == "__main__":
    main()
