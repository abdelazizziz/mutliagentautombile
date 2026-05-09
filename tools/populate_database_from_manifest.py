import json
from pathlib import Path

from core.database_builder import DatabaseBuilder
from core.dbc_parser import DbcParser
from core.ldf_parser import LdfParser
from core.vsysvar_parser import VsysvarParser
from core.capl_parser import CaplParser, CaplNetworkScanner
from core.vts_collector import VtsChannelCollector
from core.cdd_parser import CddParser


def _load_manifest(manifest_path: str) -> dict:
    with open(manifest_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_existing_files(manifest: dict, file_type: str) -> list[str]:
    """
    Retourne les absolute_path des fichiers existants pour un type donné.
    Supporte:
    - manifest["files"]["dbc"] = [{"absolute_path": "...", "exists": true}]
    - manifest["files"]["dbc"] = ["C:/.../file.dbc"]
    """
    files = manifest.get("files", {}).get(file_type, [])
    result = []

    for item in files:
        if isinstance(item, dict):
            path = item.get("absolute_path")
            exists = item.get("exists", True)
            if path and exists and Path(path).exists():
                result.append(path)
        elif isinstance(item, str):
            if Path(item).exists():
                result.append(item)

    return result


def populate_database_from_manifest(manifest_path: str, db_path: str) -> dict:
    """
    Remplit la base SQLite à partir du manifest.json.

    Tables remplies:
    - project_info
    - project_files
    - node_assignments
    - can_messages
    - can_signals
    - signal_values
    - env_variables
    - lin_frames
    - lin_signals
    - hil_sysvars
    - sysvar_values
    - capl_mappings
    - vts_sysvars
    - signal_path
    - cdd_did_lookup / cdd_dtc_lookup / cdd_did_fields si CDD existe
    """

    manifest = _load_manifest(manifest_path)

    db = DatabaseBuilder(db_path)
    db.conn = None
    db.create_database()

    stats = {
        "dbc_files": 0,
        "ldf_files": 0,
        "vsysvar_files": 0,
        "can_files": 0,
        "cin_files": 0,
        "cdd_files": 0,
        "warnings": [],
    }

    # =====================================================
    # 1. Project info + files + nodes
    # =====================================================

    cfg_path = manifest.get("cfg_path", "")
    software_root = manifest.get("software_root", "")

    try:
        db.insert_project_info(
            cfg_file=cfg_path,
            canoe_version=manifest.get("canoe_version", ""),
            project_dir=software_root,
        )
    except Exception as e:
        stats["warnings"].append(f"project_info insert failed: {e}")

    try:
        db.insert_project_files(manifest.get("files", {}))
    except Exception as e:
        stats["warnings"].append(f"project_files insert failed: {e}")

    try:
        db.insert_node_assignments(manifest.get("nodes", []))
    except Exception as e:
        stats["warnings"].append(f"node_assignments insert failed: {e}")

    # =====================================================
    # 2. VSYSVAR -> hil_sysvars + sysvar_values
    # =====================================================

    vsys_parser = VsysvarParser()

    for path in _get_existing_files(manifest, "vsysvar"):
        try:
            vsys_parser.parse(path)
            stats["vsysvar_files"] += 1
        except Exception as e:
            stats["warnings"].append(f"VSYSVAR parse failed {path}: {e}")

    try:
        db.insert_hil_sysvars(vsys_parser.variables)
    except Exception as e:
        stats["warnings"].append(f"hil_sysvars insert failed: {e}")

    # =====================================================
    # 3. VTS scan from CFG + CAN + CIN
    # =====================================================

    vts = VtsChannelCollector()

    if cfg_path and Path(cfg_path).exists():
        vts.scan_file(cfg_path)

    can_files = _get_existing_files(manifest, "can")
    cin_files = _get_existing_files(manifest, "cin")

    for path in can_files + cin_files:
        vts.scan_file(path)

    try:
        vts_records = vts.to_sysvar_records()
        db.insert_vts_sysvars(vts_records)

        # also insert VTS as hil_sysvars compatible records
        db.insert_hil_sysvars(vts.to_system_variable_records())
    except Exception as e:
        stats["warnings"].append(f"vts insert failed: {e}")

    # =====================================================
    # 4. Network scanner from CAN/CIN
    # =====================================================

    net_scanner = CaplNetworkScanner()

    for path in can_files + cin_files:
        try:
            net_scanner.scan_file(path)
        except Exception as e:
            stats["warnings"].append(f"Network scan failed {path}: {e}")

    try:
        db.insert_network_channels(net_scanner.to_records())
    except Exception as e:
        stats["warnings"].append(f"network_channels insert failed: {e}")

    # =====================================================
    # 5. CAPL/CIN -> mappings + sysvar_refs + envvar_refs
    # =====================================================

    capl_parser = CaplParser()

    for path in can_files:
        try:
            capl_parser.parse(path)
            stats["can_files"] += 1
        except Exception as e:
            stats["warnings"].append(f"CAN parse failed {path}: {e}")

    for path in cin_files:
        try:
            capl_parser.parse(path)
            stats["cin_files"] += 1
        except Exception as e:
            stats["warnings"].append(f"CIN parse failed {path}: {e}")

    try:
        db.insert_capl_mappings(capl_parser)
    except Exception as e:
        stats["warnings"].append(f"capl_mappings insert failed: {e}")

    # =====================================================
    # 6. DBC -> can_messages + can_signals + signal_values + env_variables
    # =====================================================

    for path in _get_existing_files(manifest, "dbc"):
        try:
            dbc = DbcParser()
            dbc.parse(path)
            db.insert_can_data(dbc)
            stats["dbc_files"] += 1
        except Exception as e:
            stats["warnings"].append(f"DBC parse failed {path}: {e}")

    # =====================================================
    # 7. LDF -> lin_frames + lin_signals
    # =====================================================

    for path in _get_existing_files(manifest, "ldf"):
        try:
            ldf = LdfParser()
            ldf.parse(path)
            db.insert_lin_data(ldf)
            stats["ldf_files"] += 1
        except Exception as e:
            stats["warnings"].append(f"LDF parse failed {path}: {e}")

    # =====================================================
    # 8. CDD optional -> diagnostics
    # =====================================================

    for path in _get_existing_files(manifest, "cdd"):
        try:
            cdd = CddParser()
            cdd.parse(path)
            db.insert_cdd_info(cdd)
            stats["cdd_files"] += 1
        except Exception as e:
            stats["warnings"].append(f"CDD parse failed {path}: {e}")

    # =====================================================
    # 9. Build unified signal_path
    # =====================================================

    try:
        signal_path_count = db.build_signal_path()
    except Exception as e:
        signal_path_count = 0
        stats["warnings"].append(f"signal_path build failed: {e}")

    # =====================================================
    # 10. Final stats
    # =====================================================

    try:
        table_stats = db.get_stats()
    except Exception:
        table_stats = {}

    db.close()

    return {
        "status": "success",
        "db_path": db_path,
        "manifest_path": manifest_path,
        "parsed_files": stats,
        "signal_path_count": signal_path_count,
        "table_stats": table_stats,
    }