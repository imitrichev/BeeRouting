import json
from datetime import datetime
from zoneinfo import ZoneInfo

import requests


OTP_URL = "http://localhost:8081/otp/transmodel/v3"


def test_public_transport():
    # Кремль / Красная площадь
    from_lat = 55.7539
    from_lon = 37.6208

    # ВДНХ
    to_lat = 55.8298
    to_lon = 37.6330

    departure_time = datetime(
        year=2026,
        month=9,
        day=26,
        hour=15,
        minute=0,
        tzinfo=ZoneInfo("Europe/Moscow"),
    )

    query = """
    query Trip(
        $fromLat: Float!,
        $fromLon: Float!,
        $toLat: Float!,
        $toLon: Float!,
        $dateTime: DateTime!
    ) {
      trip(
        from: {
          coordinates: {
            latitude: $fromLat
            longitude: $fromLon
          }
        }

        to: {
          coordinates: {
            latitude: $toLat
            longitude: $toLon
          }
        }

        dateTime: $dateTime
        arriveBy: false
        numTripPatterns: 3

        modes: {
          accessMode: foot
          egressMode: foot

          transportModes: [
            { transportMode: bus }
            { transportMode: metro }
            { transportMode: tram }
            { transportMode: rail }
          ]
        }
      ) {
        tripPatterns {
          duration

          legs {
            mode
            distance
            expectedStartTime
            expectedEndTime

            fromPlace {
              name
            }

            toPlace {
              name
            }

            line {
              publicCode
              name
            }
          }
        }
      }
    }
    """

    variables = {
        "fromLat": from_lat,
        "fromLon": from_lon,
        "toLat": to_lat,
        "toLon": to_lon,
        "dateTime": departure_time.isoformat(),
    }

    print("Requesting public transport route from OTP...")
    print("Departure:", departure_time.isoformat())

    response = requests.post(
        OTP_URL,
        json={
            "query": query,
            "variables": variables,
        },
        timeout=60,
    )

    print("HTTP:", response.status_code)

    data = response.json()

    if "errors" in data:
        print("\nGraphQL errors:")
        print(json.dumps(data["errors"], indent=2, ensure_ascii=False))
        return

    trip_patterns = data["data"]["trip"]["tripPatterns"]

    if not trip_patterns:
        print("\nNo public transport route found.")
        return

    print(f"\nFound {len(trip_patterns)} route(s).")

    for route_index, pattern in enumerate(trip_patterns, start=1):
        duration_minutes = pattern["duration"] / 60.0

        print()
        print("=" * 60)
        print(f"Route {route_index}")
        print(f"Total time: {duration_minutes:.1f} min")

        for leg_index, leg in enumerate(pattern["legs"], start=1):
            distance_km = leg["distance"] / 1000.0

            line = leg.get("line")
            line_name = ""

            if line:
                line_name = line.get("publicCode") or line.get("name") or ""

            print()
            print(f"  Leg {leg_index}: {leg['mode']}")

            if line_name:
                print(f"    Line: {line_name}")

            print(
                f"    {leg['fromPlace']['name']}"
                f" -> {leg['toPlace']['name']}"
            )

            print(f"    Distance: {distance_km:.2f} km")
            print(f"    Start: {leg['expectedStartTime']}")
            print(f"    End:   {leg['expectedEndTime']}")

    print()
    print("=" * 60)


if __name__ == "__main__":
    test_public_transport()
