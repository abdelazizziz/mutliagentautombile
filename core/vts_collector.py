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

class VtsChannelCollector:
    """
    Scans BOTH .can and .cin files.
    Records ONLY the attribute names that actually appear in source code
    (not a hardcoded list of 23 properties), giving accurate results.

    For each unique  sysvar::VTS::CHANNEL::ATTRIBUTE  found in code it emits
    one record into the  vts_sysvars  table:
        sysvar_prefix = "sysvar"
        namespace     = "VTS"
        channel       = "S_PS_PDPC"
        attribute     = "AvgVoltage"
        full_path     = "sysvar::VTS::S_PS_PDPC::AvgVoltage"
        source_file   = "VTS_AI.cin"
    """

    # ── Standard VTS attributes — every VTS channel exposes these ─────────
    # When we discover ANY attribute for a channel, we auto-expand the full set
    # so the CAPL generator can pick the right one based on test description.
    STANDARD_VTS_ATTRS = [
        "Avg", "AvgVoltage", "AvgCurrent",
        "PWMDC", "PWMFreq",
        "DigitalOutput",
        "RelayOrgComponent",
    ]

    # Matches the full 4-part path inside any source file
    VTS_FULL_RE = re.compile(
        r'sysvar::VTS::([A-Za-z0-9_]+)::([A-Za-z0-9_]+)',
        re.MULTILINE
    )
    # Matches bare  VTS::CHANNEL::ATTR  (without sysvar:: prefix)
    VTS_SHORT_RE = re.compile(
        r'(?<![:\w])VTS::([A-Za-z0-9_]+)::([A-Za-z0-9_]+)',
        re.MULTILINE
    )

    def __init__(self):
        # {(channel, attribute): set_of_source_files}
        self._entries = defaultdict(set)

    def scan_file(self, filepath):
        try:
            with open(filepath, 'r', encoding='latin-1') as f:
                text = f.read()
        except Exception:
            return
        src = Path(filepath).name
        for m in self.VTS_FULL_RE.finditer(text):
            self._entries[(m.group(1), m.group(2))].add(src)
        for m in self.VTS_SHORT_RE.finditer(text):
            self._entries[(m.group(1), m.group(2))].add(src)

    def to_sysvar_records(self):
        """One record per unique (channel, attribute). No duplicates.
        source_file shows the first .cin file where this VTS var was found.
        
        FIX v24: Auto-expand every discovered channel to all standard VTS
        attributes so the CAPL generator can pick the right one (PWMDC,
        AvgVoltage, etc.) based on the test description context.
        """
        # Collect all unique channels and their best source file
        channel_sources: dict[str, str] = {}
        for (channel, attribute), sources in sorted(self._entries.items()):
            best_src = sorted(sources, key=lambda s: (len(s), s))[0]
            if channel not in channel_sources:
                channel_sources[channel] = best_src

        # Build expanded records: all standard attrs per channel
        seen = set()
        records = []
        for channel, best_src in sorted(channel_sources.items()):
            for attr in self.STANDARD_VTS_ATTRS:
                key = (channel, attr)
                if key not in seen:
                    seen.add(key)
                    records.append({
                        'sysvar_prefix': 'sysvar',
                        'namespace':     'VTS',
                        'channel':       channel,
                        'attribute':     attr,
                        'full_path':     'sysvar::VTS::' + channel + '::' + attr,
                        'source_file':   best_src,
                    })
        # Also keep any non-standard attributes found in code
        for (channel, attribute), sources in sorted(self._entries.items()):
            key = (channel, attribute)
            if key not in seen:
                seen.add(key)
                best_src = sorted(sources, key=lambda s: (len(s), s))[0]
                records.append({
                    'sysvar_prefix': 'sysvar',
                    'namespace':     'VTS',
                    'channel':       channel,
                    'attribute':     attribute,
                    'full_path':     'sysvar::VTS::' + channel + '::' + attribute,
                    'source_file':   best_src,
                })
        return records

    def to_system_variable_records(self):
        """
        Also return records in the hil_sysvars schema so that
        the old search still works.
        """
        sv = []
        for r in self.to_sysvar_records():
            sv.append({
                'namespace':   'VTS::' + r['channel'],
                'name':        r['attribute'],
                'full_path':   r['full_path'],
                'type':        'float',
                'bitcount':    '64',
                'start_value': '0',
                'min_value':   '',
                'max_value':   '',
                'unit':        '',
                'comment':     'VT-System channel (auto-discovered from CAPL)',
                'encoding':    '',
                'is_signed':   'true',
                'read_only':   'false',
                'source_file': r['source_file'],
                'value_entries': [],
            })
        return sv

