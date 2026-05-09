from core.cfg_parser import CfgParser


def discover_config_files(
    cfg_path: str,
    software_root: str
):

    parser = CfgParser(cfg_path)

    parser.parse()

    parser.check_files([software_root])

    return {
        "files": parser.files,
        "nodes": parser.nodes
    }