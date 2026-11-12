import unittest

from WHsourcedata import _load_map_sites, app, load_heat_sources


class DashboardTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def test_dashboard_compares_all_configured_sources(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        for source_name in (
            "Data centers",
            "Supermarkets",
            "Wastewater",
            "Arenas",
            "Metro stations",
        ):
            self.assertIn(source_name, page)

    def test_heat_sources_workspace_lists_all_sources_and_details(self):
        page = self.client.get("/").get_data(as_text=True)
        workspace = page.split('<section id="heat-sources-workspace"', 1)[1].split(
            "</section>", 1
        )[0]
        self.assertIn('id="heat-sources-nav"', page)
        self.assertIn("id=\"heat-sources-title\">Heat sources", workspace)
        self.assertEqual(workspace.count('class="card heat-source-card"'), 5)
        for content in (
            "Data centers",
            "Supermarkets",
            "Wastewater",
            "Arenas",
            "Metro stations",
            "Geographic detail",
            "Equivalent homes",
            "View in overview",
            "Edmonton, Montreal, Toronto, Calgary, Ottawa, Vancouver",
            "11 provinces and territories",
            "10 provinces and Yukon",
        ):
            self.assertIn(content, workspace)

    def test_source_can_be_selected_from_query_string(self):
        response = self.client.get("/?source=arenas")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"1,475,171", response.data)

    def test_unknown_source_returns_not_found(self):
        response = self.client.get("/?source=unknown")
        self.assertEqual(response.status_code, 404)

    def test_dashboard_only_displays_metro_heat_in_mwh(self):
        response = self.client.get("/?source=metroStations")
        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Annual heat (MWh)", page)
        self.assertNotIn("GJ", page)

    def test_workbook_sources_have_expected_heat_ranges(self):
        sources = {source["id"]: source for source in load_heat_sources()}
        self.assertEqual(sources["arenas"]["lower"], 1475171)
        self.assertEqual(sources["arenas"]["upper"], 3328908)
        self.assertEqual(sources["dataCenters"]["lower"], 10998509)
        self.assertEqual(sources["dataCenters"]["upper"], 21997018)
        self.assertEqual(sources["supermarkets"]["lower"], 5701415)
        self.assertEqual(sources["supermarkets"]["upper"], 16459828)
        self.assertEqual(sources["metroStations"]["lower"], 7933)
        self.assertEqual(sources["metroStations"]["status"], "Workbook data")
        self.assertEqual(sources["wastewater"]["status"], "Workbook estimate")
        self.assertEqual(sources["wastewater"]["lower"], 18067372.706)
        self.assertEqual(sources["wastewater"]["upper"], 18067372.706)
        self.assertEqual(sources["wastewater"]["count"], 1081)
        self.assertEqual(sources["wastewater"]["homesLower"], 868780)
        self.assertAlmostEqual(
            sum(region["mwh"] for region in sources["wastewater"]["regions"]),
            sources["wastewater"]["lower"],
            places=3,
        )
        self.assertEqual(
            sum(region["facilityCount"] for region in sources["wastewater"]["regions"]),
            1081,
        )

    def test_wastewater_selection_shows_workbook_regional_breakdown(self):
        response = self.client.get("/?source=wastewater")
        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("18,067,373", page)
        self.assertIn("868,780", page)
        self.assertIn("Annual heat by province or territory", page)
        self.assertIn('"name": "Ontario"', page)
        self.assertIn('"mwh": 6548992.071', page)
        self.assertIn("wastewaterRegionTable.append(row)", page)
        self.assertNotIn("illustrative placeholder", page.lower())

    def test_source_shares_use_the_combined_lower_bound_heat(self):
        sources = load_heat_sources()
        total_heat = sum(source["lower"] for source in sources)
        for source in sources:
            expected_share = round(source["lower"] / total_heat * 100, 2)
            self.assertEqual(source["sharePercent"], expected_share)

        page = self.client.get("/").get_data(as_text=True)
        self.assertIn("Share of heat", page)
        for source in sources:
            self.assertIn(f'"sharePercent": {source["sharePercent"]}', page)
        self.assertIn("Of combined lower-bound heat", page)

    def test_annual_heat_chart_compares_vertical_lower_and_upper_bounds(self):
        page = self.client.get("/").get_data(as_text=True)
        self.assertIn('viewBox="0 0 720 330"', page)
        self.assertIn("Vertical bar chart comparing lower and upper annual heat estimates", page)
        self.assertIn("Solid green shows the lower estimate; amber extends to the upper bound", page)
        self.assertIn("Range to upper bound", page)
        self.assertIn('id="annual-scale"', page)
        self.assertIn("Logarithmic scale: equal vertical steps represent 10× changes", page)
        self.assertIn("Math.log10", page)

    def test_quarterly_profiles_are_available_and_reconcile_to_annual_ranges(self):
        sources = load_heat_sources()
        for source in sources:
            with self.subTest(source=source["id"]):
                quarters = source["quarters"]
                self.assertEqual(
                    [quarter["name"] for quarter in quarters],
                    ["Q1", "Q2", "Q3", "Q4"],
                )
                self.assertAlmostEqual(
                    sum(quarter["lower"] for quarter in quarters),
                    source["lower"],
                    delta=1,
                )
                self.assertAlmostEqual(
                    sum(quarter["upper"] for quarter in quarters),
                    source["upper"],
                    delta=1,
                )

        page = self.client.get("/").get_data(as_text=True)
        self.assertIn('id="quarterly-chart"', page)
        self.assertIn("id=\"quarterly-table\"", page)
        self.assertIn("drawQuarterlyChart(selected)", page)
        self.assertIn(
            "25% per-quarter assumption",
            sources[0]["quarterlyNote"],
        )

    def test_map_contains_geolocated_heat_sites_and_source_filter(self):
        map_sites, map_stats = _load_map_sites()
        self.assertEqual(
            set(map_sites),
            {"dataCenters", "supermarkets", "wastewater", "arenas", "metroStations"},
        )
        for source_id, sites in map_sites.items():
            with self.subTest(source=source_id):
                self.assertGreater(len(sites), 0)
                self.assertEqual(map_stats[source_id]["mapped"], len(sites))
                for site in sites:
                    self.assertGreaterEqual(site["lat"], 41)
                    self.assertLessEqual(site["lat"], 84)
                    self.assertGreaterEqual(site["lon"], -142)
                    self.assertLessEqual(site["lon"], -52)
                    self.assertGreater(site["upper"], 0)

        self.assertEqual(map_stats["metroStations"]["mapped"], 6)
        self.assertIn("system total", map_sites["metroStations"][0]["locationNote"])
        page = self.client.get("/").get_data(as_text=True)
        self.assertIn('id="heat-map"', page)
        self.assertIn('id="map-source-filter"', page)
        self.assertIn("Plotly.restyle", page)
        self.assertIn("system-level heat totals, not station-level output", page)

    def test_comparison_table_shows_household_equivalents_without_coverage_or_quality(self):
        response = self.client.get("/")
        page = response.get_data(as_text=True)
        self.assertIn("<th scope=\"col\">Equivalent homes</th>", page)
        self.assertIn('"homesLower": 692523', page)
        self.assertIn('"homesUpper": 1385046', page)
        self.assertIn('"homesLower": 358991', page)
        self.assertIn('"homesUpper": 1036396', page)
        self.assertIn('"homesLower": 92884', page)
        self.assertIn('"homesUpper": 209605', page)
        self.assertIn("Not calculated", page)
        self.assertNotIn("source coverage, and data quality", page)
        self.assertNotIn("Coverage and estimate quality", page)
        table_header = page.split('<thead><tr><th scope="col">Heat source</th>', 1)[1].split(
            "</tr></thead>", 1
        )[0]
        self.assertNotIn("Coverage", table_header)
        self.assertNotIn("Data quality", table_header)


if __name__ == "__main__":
    unittest.main()
