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
# 2. VSYSVAR PARSER
# =============================================================================
class VsysvarParser:
    def __init__(self):
        self.variables   = []
        self.value_tables = []

    def parse(self, filepath):
        try:
            tree = ET.parse(filepath)
            root = tree.getroot()
        except ET.ParseError:
            with open(filepath, 'r', encoding='utf-8-sig') as f:
                content = f.read()
            root = ET.fromstring(content)
        src = Path(filepath).name
        self._parse_namespace(root, "", src)
        return self.variables

    def _parse_namespace(self, element, parent_ns, source_file):
        for child in element:
            if child.tag == 'namespace':
                ns_name = child.get('name', '')
                full_ns = f"{parent_ns}::{ns_name}" if parent_ns else ns_name
                for var in child.findall('variable'):
                    vi = {
                        'namespace':   full_ns,
                        'name':        var.get('name', ''),
                        'full_path':   f"sysvar::{full_ns}::{var.get('name','')}",  # sysvar:: guaranteed
                        'type':        var.get('type', ''),
                        'bitcount':    var.get('bitcount', ''),
                        'start_value': var.get('startValue', ''),
                        'min_value':   var.get('minValue', ''),
                        'max_value':   var.get('maxValue', ''),
                        'unit':        var.get('unit', ''),
                        'comment':     var.get('comment', ''),
                        'encoding':    var.get('encoding', ''),
                        'is_signed':   var.get('isSigned', 'false'),
                        'read_only':   var.get('readOnly', 'false'),
                        'source_file': source_file,
                        'value_entries': [],
                    }
                    for vt in var.findall('.//valuetable'):
                        for entry in vt.findall('valuetableentry'):
                            vte = {
                                'table_name':    vt.get('name', ''),
                                'value':         entry.get('value', ''),
                                'description':   entry.get('description', ''),
                                'display_string':entry.get('displayString', ''),
                                'lower_bound':   entry.get('lowerBound', ''),
                                'upper_bound':   entry.get('upperBound', ''),
                            }
                            vi['value_entries'].append(vte)
                            self.value_tables.append({
                                **vte,
                                'variable_name': vi['name'],
                                'namespace':     full_ns,
                                'source_file':   source_file,
                            })
                    self.variables.append(vi)
                self._parse_namespace(child, full_ns, source_file)

