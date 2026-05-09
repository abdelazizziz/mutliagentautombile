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
from pathlib import Path
from datetime import datetime

try:
    import openpyxl
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False



class CaplNetworkScanner:
    """
    Scans CAPL/test files for CAN::NETNAME::FRAME::SIGNAL
    or LIN::NETNAME::FRAME::SIGNAL patterns.
    """

    NET_PATTERN = re.compile(
        r'\b(CAN|LIN)::([\w]+)::([\w]+)::([\w]+)'
    )

    def __init__(self):
        self._pairs = {}

    def scan_file(self, filepath):
        try:
            with open(filepath, "r", encoding="latin-1") as f:
                text = f.read()
        except Exception:
            return

        src = Path(filepath).name

        for m in self.NET_PATTERN.finditer(text):
            network_name = m.group(2)
            frame_name = m.group(3)

            key = (network_name, frame_name)

            if key not in self._pairs:
                self._pairs[key] = src

    def to_records(self):
        return [
            (network, frame, src)
            for (network, frame), src in sorted(self._pairs.items())
        ]    
# =============================================================================
# UTILITY — sysvar path normalization  (BUG-CA-03 FIX)
# Applied at every read point — does NOT modify stored DB values.
# =============================================================================
def _normalize_sysvar_path(raw: str) -> str:
    """
    Ensure a sysvar path always starts with 'sysvar::'.

    Examples
    --------
    'BRAIN_9::sysvar_Aprch_Imp'          → 'sysvar::BRAIN_9::sysvar_Aprch_Imp'
    'sysvar::BRAIN_9::sysvar_Aprch_Imp'  → unchanged (already correct)
    'EV_WL_AUTHORIZATION'                → unchanged (env-var, not sysvar)
    ''                                   → ''
    """
    if not raw:
        return raw
    if raw.startswith("sysvar::"):
        return raw
    if "::" in raw:
        return f"sysvar::{raw}"
    return raw



def _strip_block_comments(text: str) -> str:
    """BUG-CA-05 FIX: remove /* ... */ before applying regexes."""
    return re.sub(r'/\*.*?\*/', ' ', text, flags=re.DOTALL)


class CaplParser:
    SYSVAR_HANDLER    = re.compile(r'on\s+sysvar(?:_change)?\s+([\w:]+(?:::\w+)*)\s*\{', re.MULTILINE)
    ENVVAR_HANDLER    = re.compile(r'on\s+envVar\s+(\w+)\s*\{', re.MULTILINE)
    SET_SIGNAL        = re.compile(r'setSignal\s*\(\s*([\w]+)\s*,\s*([^)]+)\)')
    MSG_SIGNAL_ASSIGN = re.compile(r'(M_\w+)\.(\w+)\s*=\s*([^;]+)')
    PUT_VALUE         = re.compile(r'put[Vv]alue\s*\(\s*(EV_\w+|[\w]+)\s*,\s*([^)]+)\)')
    GET_VALUE         = re.compile(r'get[Vv]alue\s*\(\s*(EV_\w+|[\w]+)\s*\)')
    ENVVAR_DIRECT_WRITE = re.compile(r'@(EV_[\w]+)\s*=\s*([^;]+)')
    ENVVAR_DIRECT_READ  = re.compile(r'@(EV_[\w]+)(?!\s*=)')
    SYSVAR_REF          = re.compile(r'@sysvar::([\w:]+)')
    SYSVAR_DIRECT_WRITE = re.compile(r'@sysvar::([\w:]+)\s*=\s*([^;]+)')
    TESTCASE_DEF        = re.compile(r'testcase\s+(\w+)')
    MSG_DECL            = re.compile(r'message\s+(0x[0-9A-Fa-f]+)\s+(\w+)\s*;')

    def __init__(self):
        self.mappings              = []
        self.envvar_refs         = []
        self.sysvar_refs     = []
        self.message_declarations  = []
        self.testcases             = []

    def _extract_block(self, content, start):
        brace, pos = 1, start
        while pos < len(content) and brace > 0:
            if content[pos] == '{':
                brace += 1
            elif content[pos] == '}':
                brace -= 1
            pos += 1
        return content[start:pos - 1]

    def parse(self, filepath):
        try:
            with open(filepath, 'r', encoding='latin-1') as f:
                content = f.read()
        except Exception as e:
            raise RuntimeError(f"Cannot read {filepath}: {e}")
        # BUG-CA-05 FIX: strip block comments to avoid phantom regex matches
        content = _strip_block_comments(content)
        src = Path(filepath).name
        self._parse_sysvar_handlers(content, src)
        self._parse_envvar_handlers(content, src)
        self._parse_sysvar_refs(content, src)
        self._parse_message_declarations(content, src)
        self._parse_envvar_refs(content, src)
        # BUG-CA-07 FIX: parse test references (was missing)
        self._parse_test_references(content, src)
        return self.mappings

    def _parse_sysvar_handlers(self, content, src):
        for m in self.SYSVAR_HANDLER.finditer(content):
            sysvar_path = _normalize_sysvar_path(m.group(1).strip())  # BUG-CA-03 FIX
            block = self._extract_block(content, m.end())
            for sm in self.SET_SIGNAL.finditer(block):
                self.mappings.append({'sysvar_path': sysvar_path, 'signal_name': sm.group(1).strip(),
                    'mapping_type': 'sysvar_to_signal', 'direction': 'write',
                    'value_expr': sm.group(2).strip(), 'source_file': src,
                    'capl_handler': f'on sysvar {sysvar_path}', 'message_name': '', 'bus_type': 'LIN'})
            for mm in self.MSG_SIGNAL_ASSIGN.finditer(block):
                self.mappings.append({'sysvar_path': sysvar_path, 'signal_name': mm.group(2).strip(),
                    'mapping_type': 'sysvar_to_can_signal', 'direction': 'write',
                    'value_expr': mm.group(3).strip(), 'source_file': src,
                    'capl_handler': f'on sysvar {sysvar_path}', 'message_name': mm.group(1).strip(), 'bus_type': 'CAN'})
            for sv in self.SYSVAR_DIRECT_WRITE.finditer(block):
                tgt = sv.group(1).strip()
                self.mappings.append({'sysvar_path': sysvar_path, 'signal_name': tgt,
                    'mapping_type': 'sysvar_to_sysvar', 'direction': 'write',
                    'value_expr': sv.group(2).strip(), 'source_file': src,
                    'capl_handler': f'on sysvar {sysvar_path}', 'message_name': '',
                    'bus_type': 'VTS' if 'VTS::' in tgt else 'SYSVAR'})

    def _parse_envvar_handlers(self, content, src):
        for m in self.ENVVAR_HANDLER.finditer(content):
            ev = m.group(1).strip()
            block = self._extract_block(content, m.end())
            for sm in self.SET_SIGNAL.finditer(block):
                self.mappings.append({'sysvar_path': ev, 'signal_name': sm.group(1).strip(),
                    'mapping_type': 'envvar_to_signal', 'direction': 'write',
                    'value_expr': sm.group(2).strip(), 'source_file': src,
                    'capl_handler': f'on envVar {ev}', 'message_name': '', 'bus_type': 'LIN'})
            for mm in self.MSG_SIGNAL_ASSIGN.finditer(block):
                self.mappings.append({'sysvar_path': ev, 'signal_name': mm.group(2).strip(),
                    'mapping_type': 'envvar_to_can_signal', 'direction': 'write',
                    'value_expr': mm.group(3).strip(), 'source_file': src,
                    'capl_handler': f'on envVar {ev}', 'message_name': mm.group(1).strip(), 'bus_type': 'CAN'})
            self.envvar_refs.append({'name': ev, 'usage_type': 'handler', 'source_file': src, 'context': f'on envVar {ev}'})

    def _parse_sysvar_refs(self, content, src):
        for m in self.SYSVAR_REF.finditer(content):
            ls = content.rfind('\n', 0, m.start()) + 1
            le = content.find('\n', m.end())
            self.sysvar_refs.append({
                'sysvar_path': f"sysvar::{m.group(1)}", 'usage_type': 'read',
                'source_file': src, 'context': content[ls:le].strip()[:200]})

    def _parse_message_declarations(self, content, src):
        for m in self.MSG_DECL.finditer(content):
            self.message_declarations.append({'msg_id': m.group(1), 'msg_name': m.group(2), 'source_file': src})

    def _parse_envvar_refs(self, content, src):
        for m in self.PUT_VALUE.finditer(content):
            self.envvar_refs.append({'name': m.group(1), 'usage_type': 'putvalue', 'source_file': src,
                'context': f'putvalue({m.group(1)}, {m.group(2).strip()})'})
        for m in self.GET_VALUE.finditer(content):
            self.envvar_refs.append({'name': m.group(1), 'usage_type': 'getvalue', 'source_file': src,
                'context': f'getvalue({m.group(1)})'})
        for m in self.ENVVAR_DIRECT_WRITE.finditer(content):
            self.envvar_refs.append({'name': m.group(1), 'usage_type': 'direct_write', 'source_file': src,
                'context': f'@{m.group(1)} = {m.group(2).strip()[:50]}'})

    def _parse_test_references(self, content, src):
        for m in self.TESTCASE_DEF.finditer(content):
            self.testcases.append({'name': m.group(1), 'source_file': src})
        for m in self.ENVVAR_DIRECT_WRITE.finditer(content):
            self.envvar_refs.append({'name': m.group(1), 'usage_type': 'test_write', 'source_file': src,
                'context': f'@{m.group(1)} = {m.group(2).strip()[:50]}'})
        for m in self.SYSVAR_DIRECT_WRITE.finditer(content):
            self.sysvar_refs.append({'sysvar_path': f"sysvar::{m.group(1)}", 'usage_type': 'test_write',
                'source_file': src, 'context': f'@sysvar::{m.group(1)} = {m.group(2).strip()[:50]}'})
        for m in self.SYSVAR_REF.finditer(content):
            ls = content.rfind('\n', 0, m.start()) + 1
            le = content.find('\n', m.end())
            self.sysvar_refs.append({'sysvar_path': f"sysvar::{m.group(1)}", 'usage_type': 'test_read',
                'source_file': src, 'context': content[ls:le].strip()[:200]})

    def parse_test_file(self, filepath):
        try:
            with open(filepath, 'r', encoding='latin-1') as f:
                content = f.read()
        except Exception as e:
            raise RuntimeError(f"Cannot read {filepath}: {e}")
        self._parse_test_references(content, Path(filepath).name)
        return self.testcases
