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
# 5. LDF PARSER
# =============================================================================
class LdfParser:
    def __init__(self):
        self.frames = []; self.signals = []; self.nodes = {'master': '', 'slaves': []}
        self.schedules = []

    def parse(self, filepath):
        with open(filepath, 'r', encoding='latin-1') as f:
            content = f.read()
        src = Path(filepath).name
        self._parse_nodes(content, src); self._parse_signals(content, src)
        self._parse_frames(content, src)
        return self.frames

    def _parse_nodes(self, content, src):
        m = re.search(r'Nodes\s*\{[^}]*Master\s*:\s*(\w+)[^;]*;([^}]*)\}', content, re.DOTALL)
        if m:
            self.nodes['master'] = m.group(1)
            sm = re.search(r'Slaves\s*:\s*(.*?);', m.group(2), re.DOTALL)
            if sm: self.nodes['slaves'] = [s.strip() for s in sm.group(1).split(',') if s.strip()]

    def _parse_signals(self, content, src):
        ss = re.search(r'\bSignals\s*\{(.*?)\}', content, re.DOTALL)
        if ss:
            for m in re.compile(r'(\w+)\s*:\s*(\d+)\s*,\s*(\w+)\s*,\s*(.*?)\s*;').finditer(ss.group(1)):
                self.signals.append({'name': m.group(1), 'bit_length': int(m.group(2)),
                    'init_value': m.group(3), 'publisher': m.group(4).strip().split(',')[0].strip(),
                    'source_file': src})

    def _parse_frames(self, content, src):
        fs = re.search(r'\bFrames\s*\{(.*?)\n\}', content, re.DOTALL)
        if not fs: return
        fp = re.compile(r'(\w+)\s*:\s*(0x[0-9A-Fa-f]+|\d+)\s*,\s*(\w+)\s*,\s*(\d+)\s*\{([^}]*)\}', re.DOTALL)
        sif = re.compile(r'(\w+)\s*,\s*(\d+)\s*;')
        for m in fp.finditer(fs.group(1)):
            fn = m.group(1); fid_s = m.group(2)
            fid = int(fid_s, 16) if fid_s.startswith('0x') else int(fid_s)
            pub = m.group(3); dlc = int(m.group(4))
            self.frames.append({'name': fn, 'frame_id': fid, 'frame_id_hex': f"0x{fid:02X}",
                'publisher': pub, 'dlc': dlc, 'source_file': src})
            for sm in sif.finditer(m.group(5)):
                si = next((s for s in self.signals if s['name'] == sm.group(1)), None)
                self.signals.append({'name': sm.group(1), 'frame_name': fn, 'frame_id': fid,
                    'bit_offset': int(sm.group(2)), 'bit_length': si['bit_length'] if si else 0,
                    'publisher': pub, 'source_file': src, 'bus_type': 'LIN'})


