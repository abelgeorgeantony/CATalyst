#!/usr/bin/env python
import json
from path_utils import find_project_root

PROJECT_ROOT = find_project_root(__file__)
DATA_DIR = PROJECT_ROOT / "assets" / "data"
JSON_DIR = DATA_DIR / "json"


def build_metadata():
    metadata_filepath = JSON_DIR / "metadata.json"
    all_metadata = []

    for filepath in sorted(JSON_DIR.glob("*.json")):
        filename = filepath.name

        # Skip the output file itself and the schema
        if filename in ["metadata.json", "pyq_schema.json"]:
            continue

        with filepath.open("r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                if "paper_metadata" in data:
                    meta = dict(data["paper_metadata"])
                    # Inject the filename into the metadata block for frontend routing
                    meta["filename"] = filename
                    all_metadata.append(meta)
            except json.JSONDecodeError:
                print(f"Warning: Could not parse {filename}")

    # Optional: Sort the metadata by year (descending)
    all_metadata.sort(key=lambda x: x.get("year", 0), reverse=True)

    # Write the aggregated data back to the same directory
    with metadata_filepath.open("w", encoding="utf-8") as f:
        json.dump(all_metadata, f, indent=4)

    print(f"Success: Generated metadata.json with {len(all_metadata)} paper entries.")


if __name__ == "__main__":
    build_metadata()
