from pathlib import Path

from tools.discover_config_files import (
    discover_config_files
)

from tools.create_database_schema import (
    create_database_schema
)

from tools.populate_database_from_manifest import (
    populate_database_from_manifest
)

from tools.validate_database import (
    validate_database
)


# =====================================================
# CHANGE THESE PATHS
# =====================================================

CFG_PATH = r"C:\Users\abboushi\Desktop\MDOOR_DEV_SPx_Baie2_v11 1\MDOOR_DEV_SPx_Baie2_v11\Stellantis_1605_MDOOR_V2_CANoev11.cfg"

SOFTWARE_ROOT = r"C:\Users\abboushi\Desktop\MDOOR_DEV_SPx_Baie2_v11 1\MDOOR_DEV_SPx_Baie2_v11"

DB_PATH = r"outputs\project_analysis.db"

MANIFEST_PATH = r"outputs\manifest.json"


# =====================================================
# STEP 1 — DISCOVER FILES
# =====================================================

print("\n[1] Discovering software files...\n")

manifest = discover_config_files(
    cfg_path=CFG_PATH,
    software_root=SOFTWARE_ROOT
)

print(manifest)


# save manifest json if you want
import json

Path("outputs").mkdir(exist_ok=True)

with open(MANIFEST_PATH, "w") as f:
    json.dump(manifest, f, indent=2)


# =====================================================
# STEP 2 — CREATE DATABASE
# =====================================================

print("\n[2] Creating database schema...\n")

db_result = create_database_schema(
    db_path=DB_PATH
)

print(db_result)


# =====================================================
# STEP 3 — POPULATE DATABASE
# =====================================================

print("\n[3] Populating database...\n")

populate_result = populate_database_from_manifest(
    manifest_path=MANIFEST_PATH,
    db_path=DB_PATH
)

print(populate_result)


# =====================================================
# STEP 4 — VALIDATE DATABASE
# =====================================================

print("\n[4] Validating database...\n")

validation = validate_database(
    db_path=DB_PATH,
    manifest_path=MANIFEST_PATH
)

print(validation)

print("\nDONE.\n")