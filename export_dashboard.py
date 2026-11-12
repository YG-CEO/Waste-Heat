from pathlib import Path

from WHsourcedata import app


if __name__ == "__main__":
    response = app.test_client().get("/")
    if response.status_code != 200:
        raise RuntimeError(f"Dashboard export failed with HTTP {response.status_code}")
    output_path = Path(__file__).resolve().parent / "waste-heat-dashboard.html"
    with output_path.open("w", encoding="utf-8", newline="") as dashboard_file:
        dashboard_file.write(response.get_data(as_text=True))
    print(f"Standalone dashboard written to {output_path}")
