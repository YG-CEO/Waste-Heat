from pathlib import Path

from openpyxl import load_workbook
import yaml
from flask import Flask, abort, render_template, request


ROOT = Path(__file__).resolve().parent
CONFIG_DIR = ROOT / "source-configs"
DEFAULT_SOURCE = "dataCenters"

METRO_SYSTEMS = [
    {"name": "Edmonton", "mwh": 1156.751553},
    {"name": "Montreal", "mwh": 1308.322701},
    {"name": "Toronto", "mwh": 1487.278993},
    {"name": "Calgary", "mwh": 961.927747},
    {"name": "Ottawa", "mwh": 1311.406449},
    {"name": "Vancouver", "mwh": 1706.967994},
]

MAP_WORKBOOKS = [
    {
        "id": "dataCenters",
        "file": "Data centers calculations.xlsx",
        "sheet": "GIS",
        "name": "Name/ Nom",
        "city": "City/ Ville",
        "province": "Province",
        "annualLower": "Annual GJ (Lower)",
        "annualUpper": "Annual GJ (Upper)",
        "quarters": (
            ("Q1 GJ (Lower)", "Q1 GJ (Upper)"),
            ("Q2 GJ (Lower)", "Q2 GJ (Upper)"),
            ("Q3 GJ (Lower)", "Q3 GJ (Upper)"),
            ("Q4 GJ (Lower)", "Q4 GJ (Upper)"),
        ),
    },
    {
        "id": "supermarkets",
        "file": "supermarket calculations.xlsx",
        "sheet": "GIS",
        "name": "Name/ Nom",
        "city": "City/ Ville",
        "province": "Province",
        "annualLower": "Annual GJ (Lower)",
        "annualUpper": "Annual GJ (Upper)",
        "quarters": (
            ("Q1 GJ (Lower)", "Q1 GJ (Upper)"),
            ("Q2 GJ (Lower)", "Q2 GJ (Upper)"),
            ("Q3 GJ (Lower)", "Q3 GJ (Upper)"),
            ("Q4 GJ (Lower)", "Q4 GJ (Upper)"),
        ),
    },
    {
        "id": "wastewater",
        "file": "Wastewaster calculations.xlsx",
        "sheet": "GIS",
        "name": "Name/ Nom",
        "city": "City/ Ville",
        "province": "Province",
        "annualLower": "Annual GJ/",
        "annualUpper": "Annual GJ/",
        "quarters": (
            ("Q1 GJ", "Q1 GJ"),
            ("Q2 GJ", "Q2 GJ"),
            ("Q3 GJ", "Q3 GJ"),
            ("Q4 GJ", "Q4 GJ"),
        ),
    },
    {
        "id": "arenas",
        "file": "Arenas_Calculations_2026-08.xlsx",
        "sheet": "Total for GIS",
        "name": "Facility Name",
        "city": "City/Ville",
        "province": "Province",
        "annualLower": "Annual Excess Waste Heat (GJ) - Lower Bound",
        "annualUpper": "Annual Excess Waste Heat (GJ) - Upper Bound",
        "quarters": (
            ("Q1 Excess Waste Heat (GJ) - Lower Bound", "Q1 Excess Waste Heat (GJ) - Upper Bound"),
            ("Q2 Excess Waste Heat (GJ) - Lower Bound", "Q2 Excess Waste Heat (GJ) - Upper Bound"),
            ("Q3 Excess Waste Heat (GJ) - Lower Bound", "Q3 Excess Waste Heat (GJ) - Upper Bound"),
            ("Q4 Excess Waste Heat (GJ) - Lower Bound", "Q4 Excess Waste Heat (GJ) - Upper Bound"),
        ),
    },
]


def _read_config(filename):
    with (CONFIG_DIR / filename).open(encoding="utf-8") as config_file:
        return yaml.safe_load(config_file)


def _heat_range(source):
    heat_range = source.get("annualHeatRange") or source.get("assumptions", {}).get(
        "annualHeatRangeMWh"
    )
    lower = (heat_range or {}).get("lower", source["annualHeatAvailable"])
    upper = (heat_range or {}).get("upper", lower)
    return lower, upper


def _equivalent_homes(source, lower, upper):
    homes_range = source.get("equivalentHomesRange") or source.get(
        "annualEquivalentHomesRange"
    )
    if homes_range:
        return homes_range["lower"], homes_range["upper"]
    household_heat = source.get("assumptions", {}).get("annualHeatPerHouseholdMWh")
    if household_heat:
        return round(lower / household_heat), round(upper / household_heat)
    if "annualEquivalentHomes" in source:
        homes = source["annualEquivalentHomes"]
        return homes, homes
    if "equivalentHomes" in source:
        homes = source["equivalentHomes"]
        return homes, homes
    return None, None


def _column_index(headers, prefix, workbook, sheet):
    for index, header in enumerate(headers):
        if isinstance(header, str) and header.startswith(prefix):
            return index
    raise ValueError(f"Column {prefix!r} not found in {workbook}, sheet {sheet}")


def _canada_coordinates(first, second):
    if not isinstance(first, (int, float)) or not isinstance(second, (int, float)):
        return None
    if 41 <= first <= 84 and -142 <= second <= -52:
        return float(first), float(second)
    if 41 <= second <= 84 and -142 <= first <= -52:
        return float(second), float(first)
    return None


def _load_map_sites():
    sites_by_source = {spec["id"]: [] for spec in MAP_WORKBOOKS}
    sites_by_source["metroStations"] = []
    map_stats = {
        spec["id"]: {"mapped": 0, "excluded": 0}
        for spec in MAP_WORKBOOKS
    }
    map_stats["metroStations"] = {"mapped": 0, "excluded": 0}

    for spec in MAP_WORKBOOKS:
        workbook_path = ROOT / spec["file"]
        workbook = load_workbook(workbook_path, read_only=True, data_only=True)
        try:
            worksheet = workbook[spec["sheet"]]
            rows = worksheet.iter_rows(values_only=True)
            headers = next(rows)
            columns = {
                key: _column_index(headers, prefix, spec["file"], spec["sheet"])
                for key, prefix in (
                    ("name", spec["name"]),
                    ("city", spec["city"]),
                    ("province", spec["province"]),
                    ("annualLower", spec["annualLower"]),
                    ("annualUpper", spec["annualUpper"]),
                )
            }
            columns["quarters"] = [
                (
                    _column_index(headers, lower, spec["file"], spec["sheet"]),
                    _column_index(headers, upper, spec["file"], spec["sheet"]),
                )
                for lower, upper in spec["quarters"]
            ]
            latitude_column = _column_index(headers, "Latitude", spec["file"], spec["sheet"])
            longitude_column = _column_index(headers, "Longitude", spec["file"], spec["sheet"])
            for row in rows:
                name = row[columns["name"]] if columns["name"] < len(row) else None
                if not name:
                    continue
                coordinates = _canada_coordinates(
                    row[latitude_column] if latitude_column < len(row) else None,
                    row[longitude_column] if longitude_column < len(row) else None,
                )
                if coordinates is None:
                    map_stats[spec["id"]]["excluded"] += 1
                    continue

                def value_at(column):
                    if column >= len(row) or not isinstance(row[column], (int, float)):
                        return 0
                    return row[column]

                lower = value_at(columns["annualLower"]) / 3.6
                upper = value_at(columns["annualUpper"]) / 3.6
                if upper <= 0:
                    map_stats[spec["id"]]["excluded"] += 1
                    continue
                latitude, longitude = coordinates
                sites_by_source[spec["id"]].append(
                    {
                        "name": str(name),
                        "city": str(row[columns["city"]] or ""),
                        "province": str(row[columns["province"]] or ""),
                        "lat": latitude,
                        "lon": longitude,
                        "lower": lower,
                        "upper": upper,
                        "quarters": [
                            {
                                "lower": value_at(lower_column) / 3.6,
                                "upper": value_at(upper_column) / 3.6,
                            }
                            for lower_column, upper_column in columns["quarters"]
                        ],
                    }
                )
                map_stats[spec["id"]]["mapped"] += 1
        finally:
            workbook.close()

    metro_workbook = load_workbook(
        ROOT / "MetroStationCalcs.xlsx", read_only=True, data_only=True
    )
    try:
        worksheet = metro_workbook["GIS"]
        rows = worksheet.iter_rows(values_only=True)
        headers = next(rows)
        name_column = _column_index(headers, "Name/ Nom", "MetroStationCalcs.xlsx", "GIS")
        city_column = _column_index(headers, "City/ Ville", "MetroStationCalcs.xlsx", "GIS")
        province_column = _column_index(headers, "Province", "MetroStationCalcs.xlsx", "GIS")
        latitude_column = _column_index(headers, "Latitude", "MetroStationCalcs.xlsx", "GIS")
        longitude_column = _column_index(headers, "Longitude", "MetroStationCalcs.xlsx", "GIS")
        station_groups = {}
        for row in rows:
            city = row[city_column] if city_column < len(row) else None
            coordinates = _canada_coordinates(
                row[latitude_column] if latitude_column < len(row) else None,
                row[longitude_column] if longitude_column < len(row) else None,
            )
            if not city or coordinates is None:
                continue
            group = station_groups.setdefault(
                str(city).casefold(),
                {"city": str(city), "province": str(row[province_column] or ""), "points": []},
            )
            group["points"].append(coordinates)

        for system in METRO_SYSTEMS:
            group = station_groups.get(system["name"].casefold())
            if not group:
                map_stats["metroStations"]["excluded"] += 1
                continue
            points = group["points"]
            sites_by_source["metroStations"].append(
                {
                    "name": f"{system['name']} transit system",
                    "city": group["city"],
                    "province": group["province"],
                    "lat": sum(point[0] for point in points) / len(points),
                    "lon": sum(point[1] for point in points) / len(points),
                    "lower": system["mwh"],
                    "upper": system["mwh"],
                    "quarters": [],
                    "locationNote": "Approximate center of workbook station locations; heat is a system total.",
                }
            )
            map_stats["metroStations"]["mapped"] += 1
    finally:
        metro_workbook.close()

    return sites_by_source, map_stats


def load_heat_sources():
    source_files = [
        "data-centers.yaml",
        "supermarkets.yaml",
        "wastewater.yaml",
        "arenas.yaml",
        "metro-stations.yaml",
    ]
    descriptions = {
        "dataCenters": "Annual waste-heat estimate",
        "supermarkets": "Quarterly excess heat after internal heating loads",
        "wastewater": "Annual heat capacity from wastewater effluent systems",
        "arenas": "Excess heat after internal arena heating load",
        "metroStations": "Annual condenser heat (QH)",
    }
    dashboard_notes = {
        "dataCenters": (
            "The workbook estimates annual heat at a 25%-50% load factor. "
            "Household equivalents use the workbook's 15.8818 MWh/year assumption. "
            "Heat streams are not disaggregated, and recoverable potential and avoided CO2 are not calculated."
        ),
        "supermarkets": (
            "Annual estimates sum quarterly excess heat after internal heating loads. "
            "Household equivalents use 15.8818 MWh/year; the seasonal profile is derived "
            "from quarterly lower-bound totals. These are modeled estimates, not metered values."
        ),
        "arenas": (
            "These are modeled workbook estimates, not metered measurements. Annual available heat "
            "is excess heat after internal heating demand; two records have no area-based estimate."
        ),
        "metroStations": (
            "Annual heat by metro system is converted to megawatt-hours for comparison. "
            "The workbook does not report equivalent homes, avoided CO2, or a monthly heat profile."
        ),
    }
    quarterly_notes = {
        "dataCenters": (
            "Quarterly estimates distribute annual heat evenly using the workbook's 25% "
            "per-quarter assumption; values are not metered."
        ),
        "supermarkets": (
            "Quarterly estimates sum workbook excess heat after internal heating loads; "
            "values are modeled, not metered."
        ),
        "wastewater": (
            "Quarterly estimates use the workbook's seasonal temperature-difference "
            "assumptions; values are modeled, not metered."
        ),
        "arenas": (
            "Quarterly estimates are excess heat after internal heating loads; "
            "values are modeled, not metered."
        ),
        "metroStations": (
            "Quarterly heat is calculated from the workbook's monthly capture periods "
            "and is not metered."
        ),
    }
    sources = []

    for filename in source_files:
        config = _read_config(filename)
        source = config["source"]
        lower, upper = _heat_range(source)
        homes_lower, homes_upper = _equivalent_homes(source, lower, upper)
        source_id = source["id"]
        quarterly_heat = [
            {
                "name": quarter,
                "lower": source["quarterlyHeatAvailableRange"][quarter]["lower"],
                "upper": source["quarterlyHeatAvailableRange"][quarter]["upper"],
            }
            for quarter in ("Q1", "Q2", "Q3", "Q4")
        ]
        status = "Illustrative only" if config["dataStatus"] == "illustrative" else (
            "Workbook data" if source_id == "metroStations" else "Workbook estimate"
        )

        if source_id == "dataCenters":
            count = source["assumptions"]["dataCenterCount"]
            count_note = f"Calculated rows; {source['assumptions']['workbookBuildingCount']:,} buildings listed"
            coverage = f"Canada-wide · {count:,} calculated rows"
        elif source_id == "supermarkets":
            count = source["storeCount"]
            count_note = "Supermarket calculation rows"
            coverage = "Canada-wide · workbook locations"
        elif source_id == "arenas":
            count = source["arenaCount"]
            count_note = "Arena records; two lack area-based estimates"
            coverage = f"{len(source['provincesAndTerritories'])} provinces and territories"
        elif source_id == "metroStations":
            count = len(source["transitSystems"])
            count_note = "Transit systems in the workbook"
            coverage = ", ".join(source["transitSystems"])
        elif source_id == "wastewater":
            count = source["calculatedFacilityCount"]
            count_note = (
                f"Facilities with modeled heat; {source['facilityCount']:,} workbook records listed"
            )
            coverage = "10 provinces and Yukon"
        else:
            count = "—"
            count_note = "Source count not specified"
            coverage = "No location breakdown in source config"

        sources.append(
            {
                "id": source_id,
                "name": source["name"],
                "lower": lower,
                "upper": upper,
                "count": count,
                "countNote": count_note,
                "coverage": coverage,
                "status": status,
                "qualityNote": (
                    "Placeholder; validate locally"
                    if status == "Illustrative only"
                    else "Calculated; not metered"
                    if source_id == "metroStations"
                    else "Modeled; not metered"
                ),
                "homesLower": homes_lower,
                "homesUpper": homes_upper,
                "quarters": quarterly_heat,
                "quarterlyNote": quarterly_notes[source_id],
                "description": descriptions[source_id],
                "note": source["note"] if "note" in source else dashboard_notes[source_id],
                "regions": [
                    {
                        "name": region["name"],
                        "mwh": region["annualHeatMWh"],
                        "facilityCount": region["calculatedFacilityCount"],
                        "facilityRecords": region["facilityRecords"],
                    }
                    for region in source.get("annualHeatByProvince", [])
                ],
            }
        )

    total_lower_heat = sum(source["lower"] for source in sources)
    if total_lower_heat <= 0:
        raise ValueError("Total lower-bound heat must be greater than zero")
    for source in sources:
        source["sharePercent"] = round(source["lower"] / total_lower_heat * 100, 2)

    return sources


def create_app():
    app = Flask(__name__)
    heat_sources = load_heat_sources()
    map_sites, map_stats = _load_map_sites()
    sources_by_id = {source["id"]: source for source in heat_sources}
    wastewater_regions = sources_by_id["wastewater"]["regions"]

    @app.get("/")
    def dashboard():
        selected_id = request.args.get("source", DEFAULT_SOURCE)
        selected = sources_by_id.get(selected_id)
        if selected is None:
            abort(404)
        return render_template(
            "index.html",
            heat_sources=heat_sources,
            metro_systems=METRO_SYSTEMS,
            map_sites=map_sites,
            map_stats=map_stats,
            wastewater_regions=wastewater_regions,
            selected=selected,
        )

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
