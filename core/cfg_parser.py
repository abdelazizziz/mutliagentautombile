import os
import re
import sys
import sqlite3
import csv
import xml.etree.ElementTree as ET
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from pathlib import Path
from collections import defaultdict
import threading
from datetime import datetime

try:
    import openpyxl
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False





# =============================================================================
# 1. CFG PARSER
# =============================================================================
class CfgParser:
    FILE_PATTERNS = {
        'dbc':     re.compile(r'<VFileName[^>]*>\s*\d+\s*"([^"]*\.dbc)"',     re.IGNORECASE),
        'ldf':     re.compile(r'<VFileName[^>]*>\s*\d+\s*"([^"]*\.ldf)"',     re.IGNORECASE),
        'vsysvar': re.compile(r'<VFileName[^>]*>\s*\d+\s*"([^"]*\.vsysvar)"', re.IGNORECASE),
        'can':     re.compile(r'<VFileName[^>]*>\s*\d+\s*"([^"]*\.can)"',     re.IGNORECASE),
        'xvp':     re.compile(r'<VFileName[^>]*>\s*\d+\s*"([^"]*\.xvp)"',     re.IGNORECASE),
        # FIX: also discover .cin include files
        'cin':     re.compile(r'<VFileName[^>]*>\s*\d+\s*"([^"]*\.cin)"',     re.IGNORECASE),
    }

    def __init__(self, cfg_path):
        self.cfg_path    = Path(cfg_path)
        self.project_dir = self.cfg_path.parent
        self.files       = defaultdict(list)
        self.nodes       = []
        self.canoe_version = ""

    def parse(self):
        with open(self.cfg_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        ver = re.search(r';CANoe Version[^\n]*', content)
        if ver:
            self.canoe_version = ver.group(0).strip()
        for ftype, pat in self.FILE_PATTERNS.items():
            for m in pat.finditer(content):
                rel  = m.group(1).replace('\\', os.sep)
                absp = self.project_dir / rel
                self.files[ftype].append({
                    'relative_path': rel,
                    'absolute_path': str(absp),
                    'exists':        absp.exists(),
                    'filename':      Path(rel).name,
                })
        self._parse_nodes(content)
        # FIX: also discover .cin files by walking the project tree
        self._discover_cin_files()
        return self.files

    def _discover_cin_files(self):
        """Walk project directory and find ALL .cin files not already listed."""
        known_cin = {f['absolute_path'] for f in self.files.get('cin', [])}
        for root, _, files in os.walk(self.project_dir):
            for fn in files:
                if fn.lower().endswith('.cin'):
                    absp = os.path.abspath(os.path.join(root, fn))
                    if absp not in known_cin:
                        rel = os.path.relpath(absp, self.project_dir)
                        self.files['cin'].append({
                            'relative_path': rel,
                            'absolute_path': absp,
                            'exists':        True,
                            'filename':      fn,
                        })
                        known_cin.add(absp)

    def _parse_nodes(self, content):
        lines = content.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if 'VSimulationNode' in line and 'Begin_Of_Object' in line:
                capl_file = node_name = db_name = ""
                j = i + 1
                while j < len(lines) and 'End_Of_Object VSimulationNode' not in lines[j]:
                    sl = lines[j].strip()
                    cm = re.search(r'"([^"]*\.can)"', sl)
                    if cm:
                        capl_file = cm.group(1).replace('\\', '/')
                        k, found_cbf = j + 1, False
                        while k < len(lines) and k < j + 10:
                            kl = lines[k].strip()
                            if '.cbf' in kl.lower():
                                found_cbf = True
                            elif found_cbf and kl and not kl.startswith('<') and not kl.startswith('End_'):
                                if not node_name:
                                    node_name = kl
                                elif not db_name:
                                    db_name = kl
                                    break
                            k += 1
                    j += 1
                if capl_file:
                    self.nodes.append({'capl_file': capl_file, 'node_name': node_name, 'database': db_name})
                i = j
            else:
                i += 1

    def check_files(self, search_dirs=None):
        if not search_dirs:
            search_dirs = []
        for ftype in self.files:
            for fi in self.files[ftype]:
                if fi['exists']:
                    continue
                for sd in search_dirs:
                    for root, _, fnames in os.walk(sd):
                        if fi['filename'] in fnames:
                            fi['absolute_path'] = os.path.join(root, fi['filename'])
                            fi['exists'] = True
                            break
                    if fi['exists']:
                        break
        return self.files

    def get_summary(self):
        s = {"found": [], "missing": []}
        for ftype in self.files:
            for fi in self.files[ftype]:
                e = f"[{ftype.upper()}] {fi['filename']}"
                (s["found"] if fi['exists'] else s["missing"]).append(e)
        return s