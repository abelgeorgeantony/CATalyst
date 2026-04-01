#!/usr/bin/env python
import os
import json
import glob

def build_metadata():
    # 1. Get the absolute path of the directory containing this script (e.g., /.../CATalyst/scripts)
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    # 2. Go one level up to find the project root (e.g., /.../CATalyst)
    PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

    # 3. Build your asset paths absolutely from the project root
    DATA_DIR = os.path.join(PROJECT_ROOT, "assets", "data")
    JSON_DIR = os.path.join(DATA_DIR, "json")
    # Define paths relative to the repository root
    metadata_filepath = os.path.join(JSON_DIR, 'metadata.json')
    
    all_metadata = []
    
    # Iterate through all JSON files in the directory
    for filepath in glob.glob(os.path.join(JSON_DIR, '*.json')):
        filename = os.path.basename(filepath)
        
        # Skip the output file itself and the schema
        if filename in ['metadata.json', 'pyq_schema.json']:
            continue
            
        with open(filepath, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
                if "paper_metadata" in data:
                    meta = data["paper_metadata"]
                    # Inject the filename into the metadata block for frontend routing
                    meta["filename"] = filename
                    all_metadata.append(meta)
            except json.JSONDecodeError:
                print(f"Warning: Could not parse {filename}")

    # Optional: Sort the metadata by year (descending)
    all_metadata.sort(key=lambda x: x.get('year', 0), reverse=True)

    # Write the aggregated data back to the same directory
    with open(metadata_filepath, 'w', encoding='utf-8') as f:
        json.dump(all_metadata, f, indent=4)
        
    print(f"Success: Generated metadata.json with {len(all_metadata)} paper entries.")

if __name__ == '__main__':
    build_metadata()