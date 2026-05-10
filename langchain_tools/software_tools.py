from langchain.tools import tool

from tools.discover_config_files import discover_config_files
from tools.create_database_schema import create_database_schema
from tools.populate_database_from_manifest import populate_database_from_manifest
from tools.validate_database import validate_database


@tool
def discover_config_tool(cfg_path: str, software_root: str) -> dict:
    """Discover CANoe software files from a .cfg and software root folder."""
    return discover_config_files(cfg_path, software_root)


@tool
def create_database_schema_tool(db_path: str) -> dict:
    """Create the MVP SQLite database schema."""
    return create_database_schema(db_path)


@tool
def populate_database_tool(manifest_path: str, db_path: str) -> dict:
    """Populate the SQLite database from manifest.json."""
    return populate_database_from_manifest(manifest_path, db_path)


@tool
def validate_database_tool(db_path: str, manifest_path: str) -> dict:
    """Validate the generated SQLite database and return statistics."""
    return validate_database(db_path, manifest_path)


software_tools = [
    discover_config_tool,
    create_database_schema_tool,
    populate_database_tool,
    validate_database_tool,
]