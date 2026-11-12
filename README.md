# Waste Heat Dashboard

The dashboard is available both as a standalone HTML file and as a local Flask app. Source figures are loaded from
`source-configs`.

## Open the standalone dashboard

Double-click `waste-heat-dashboard.html` to open it directly in a browser. To regenerate it after changing source
configs or the dashboard template, run:

```powershell
.\.venv\Scripts\python.exe export_dashboard.py
```

## Run on Windows

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe WHsourcedata.py
```

Open <http://127.0.0.1:5000> in a browser. Stop the local server with `Ctrl+C`.

To open a source as the initial selection, add its id to the URL, for example:
`http://127.0.0.1:5000/?source=arenas`.

The annual comparison chart can use a linear or logarithmic scale; the logarithmic view is labeled because equal
vertical steps represent tenfold changes and its axis starts at 1,000 MWh. The quarterly profile follows the selected
source and shows lower and upper workbook estimates where available. Data center quarterly values use the workbook's
equal 25%-per-quarter assumption. These are modeled or calculated estimates, not metered measurements; monthly
profile indices are not displayed as monthly energy.

The interactive Plotly map reads site coordinates and heat estimates from the workbook GIS sheets using `openpyxl`.
It omits records without usable Canadian coordinates or heat estimates. Metro markers show approximate system
locations with system-level heat, not station-level output. The map library and geographic outlines load from a CDN,
so the map requires internet access; the site data remains in the dashboard and is not sent to the map provider.

The wastewater source uses the annual heat and household-equivalent outputs from `Wastewaster calculations.xlsx`; its
regional breakdown is aggregated by province and territory in `source-configs/wastewater.yaml`.

The source-share percentages use each source's lower-bound annual heat divided by the combined lower-bound total.
Because some sources have estimate ranges, these percentages are a comparison basis rather than a single definitive
share of all possible heat.
