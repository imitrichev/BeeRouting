#install requirements in .venv and .venv timefold
#
#

# download maps/schedules

PUBLIC_URL="https://disk.yandex.ru/d/KoUJyULv4J3Orw"

mkdir -p routing/osm
mkdir -p routing/otp

PBF="routing/osm/moscow-region.osm.pbf"
GTFS="routing/otp/latest.zip"

# Скачиваем только если каких-то данных ещё нет
if [ ! -f "$PBF" ] || [ ! -f "$GTFS" ]; then

    echo "Getting Yandex Disk download URL..."

    RESPONSE=$(
        curl -fsSLG \
            "https://cloud-api.yandex.net/v1/disk/public/resources/download" \
            --data-urlencode "public_key=$PUBLIC_URL"
    )

    DOWNLOAD_URL=$(
        printf '%s' "$RESPONSE" |
        python3 -c '
import json
import sys

data = json.load(sys.stdin)

if "href" not in data:
    print("Yandex API error:", data, file=sys.stderr)
    sys.exit(1)

print(data["href"])
'
    )

    echo "Downloading archive..."

    curl -fL \
        --retry 3 \
        --retry-delay 5 \
        --progress-bar \
        "$DOWNLOAD_URL" \
        -o yandex-routing.zip

    echo "Archive contents:"
    unzip -l yandex-routing.zip

    echo "Extracting..."

    rm -rf .routing-download
    mkdir .routing-download

    unzip -q yandex-routing.zip -d .routing-download

    # Ищем файлы независимо от того, лежат они в Files/
    # или Яндекс изменил структуру архива.

    FOUND_PBF=$(find .routing-download -type f \
        -name "moscow-region.osm.pbf" -print -quit)

    FOUND_GTFS=$(find .routing-download -type f \
        -name "latest.zip" -print -quit)

    if [ -z "$FOUND_PBF" ]; then
        echo "ERROR: moscow-region.osm.pbf not found in archive"
        exit 1
    fi

    if [ -z "$FOUND_GTFS" ]; then
        echo "ERROR: latest.zip not found in archive"
        exit 1
    fi

    # Копируем только то, чего ещё нет

    if [ ! -f "$PBF" ]; then
        mv "$FOUND_PBF" "$PBF"
        echo "Installed: $PBF"
    fi

    if [ ! -f "$GTFS" ]; then
        mv "$FOUND_GTFS" "$GTFS"
        echo "Installed: $GTFS"
    fi

    rm -rf .routing-download
    rm -f yandex-routing.zip

else
    echo "OSM and GTFS already downloaded."
fi

# create OSM/OTP and docker compose
cd routing

PBF="./osm/moscow-region.osm.pbf"
GTFS="./otp/latest.zip"
OTP_GRAPH="./otp/graph.obj"

# Проверяем входные данные
if [ ! -f "$PBF" ]; then
    echo "ERROR: OSM file not found: $PBF"
    exit 1
fi

if [ ! -f "$GTFS" ]; then
    echo "ERROR: GTFS file not found: $GTFS"
    exit 1
fi

#ptach URLs for companies
../.venv/bin/python patch.py

# Строим OTP-граф только если его ещё нет
if [ ! -f "$OTP_GRAPH" ]; then
    echo "Building OpenTripPlanner graph..."

    docker run --rm \
        -e JAVA_TOOL_OPTIONS="-Xmx6g" \
        -v "${PWD}/otp:/var/opentripplanner" \
        -v "${PWD}/osm/moscow-region.osm.pbf:/var/opentripplanner/moscow-region.osm.pbf" \
        opentripplanner/opentripplanner:2.10.0 \
        --build --save

    echo "OTP graph built."
else
    echo "OTP graph already exists. Skipping build."
fi

# Запускаем сервисы
docker compose up -d

echo "Done."
docker compose ps
