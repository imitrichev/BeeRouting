#install requirements in .venv and .venv timefold
#  python3 -m venv .venv
#  .venv/bin/python -m pip install -r requirements-dev.txt
#  .venv/bin/python backend/web_mvp/manage.py migrate
#

# download maps/schedules

PUBLIC_URL="https://disk.yandex.ru/d/KoUJyULv4J3Orw"

mkdir -p routing/osm
mkdir -p routing/otp

PBF="routing/osm/moscow-region.osm.pbf"
GTFS="routing/otp/latest_raw.zip"
GRAPH="routing/otp/graph.obj"
METRO_GTFS="routing/otp/moscow_metro_final.zip"

# Скачиваем архив, если отсутствует хотя бы один файл
if [ ! -f "$PBF" ] || \
   [ ! -f "$GTFS" ] || \
   [ ! -f "$GRAPH" ] || \
   [ ! -f "$METRO_GTFS" ]; then

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

    # Ищем файлы независимо от структуры каталогов внутри архива
    FOUND_PBF=$(find .routing-download -type f \
        -name "moscow-region.osm.pbf" -print -quit)

    FOUND_GTFS=$(find .routing-download -type f \
        -name "latest_raw.zip" -print -quit)

    FOUND_GRAPH=$(find .routing-download -type f \
        -name "graph.obj" -print -quit)

    FOUND_METRO_GTFS=$(find .routing-download -type f \
        -name "moscow_metro_final.zip" -print -quit)

    # Проверяем наличие необходимых файлов в архиве
    if [ -z "$FOUND_PBF" ]; then
        echo "ERROR: moscow-region.osm.pbf not found in archive"
        exit 1
    fi

    if [ -z "$FOUND_GTFS" ]; then
        echo "ERROR: latest_raw.zip not found in archive"
        exit 1
    fi

    if [ -z "$FOUND_GRAPH" ]; then
        echo "ERROR: graph.obj not found in archive"
        exit 1
    fi

    if [ -z "$FOUND_METRO_GTFS" ]; then
        echo "ERROR: moscow_metro_final.zip not found in archive"
        exit 1
    fi

    # Копируем только отсутствующие файлы
    if [ ! -f "$PBF" ]; then
        mv "$FOUND_PBF" "$PBF"
        echo "Installed: $PBF"
    fi

    if [ ! -f "$GTFS" ]; then
        mv "$FOUND_GTFS" "$GTFS"
        echo "Installed: $GTFS"
    fi

    if [ ! -f "$GRAPH" ]; then
        mv "$FOUND_GRAPH" "$GRAPH"
        echo "Installed: $GRAPH"
    fi

    if [ ! -f "$METRO_GTFS" ]; then
        mv "$FOUND_METRO_GTFS" "$METRO_GTFS"
        echo "Installed: $METRO_GTFS"
    fi

    rm -rf .routing-download
    rm -f yandex-routing.zip

else
    echo "OSM, GTFS, OTP graph and Metro GTFS already downloaded."
fi

# create OSM/OTP and docker compose
cd routing

PBF="./osm/moscow-region.osm.pbf"

# clean data: latest_raw to latest
../.venv/bin/python patch2.py

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

# Строим OTP-граф только если его ещё нет
if [ ! -f "$OTP_GRAPH" ]; then
    echo "Building OpenTripPlanner graph..."

    docker run --rm \
        -e JAVA_TOOL_OPTIONS="-Xmx6g" \
        -v "${PWD}/otp:/var/opentripplanner" \
        -v "${PWD}/osm/moscow-region.osm.pbf:/var/opentripplanner/moscow-region.osm.pbf" \
        opentripplanner/opentripplanner:2.10.0 \
        --build --save

    if [ $? -eq 0 ]; then
      echo "OTP graph building finished."
    else
      echo "OTP graph building failed."
    fi
else
    echo "OTP graph already exists. Skipping build."
fi

# Запускаем сервисы
docker compose up -d

echo "Done."
docker compose ps
