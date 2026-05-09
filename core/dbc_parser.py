import re
from pathlib import Path
from collections import defaultdict
from datetime import datetime


# =============================================================================
# 4. DBC PARSER
# =============================================================================
class DbcParser:
    def __init__(self):
        self.messages = []; self.signals = []; self.env_variables = []
        self.value_descriptions = {}; self.attribute_definitions = []
        self.attribute_values = []; self.nodes = []

    def parse(self, filepath):
        with open(filepath, 'r', encoding='latin-1') as f:
            content = f.read()
        src = Path(filepath).name
        self._parse_nodes(content, src)
        self._parse_messages(content, src)
        self._parse_value_descriptions(content, src)
        self._parse_env_variables(content, src)
        return self.messages

    def _parse_nodes(self, content, src):
        m = re.search(r'^BU_\s*:\s*(.*?)$', content, re.MULTILINE)
        if m:
            for n in m.group(1).strip().split():
                if n: self.nodes.append({'name': n, 'source_file': src})

    def _parse_messages(self, content, src):
        msg_pat = re.compile(r'^BO_\s+(\d+)\s+(\w+)\s*:\s*(\d+)\s+(\w+)', re.MULTILINE)
        sig_pat = re.compile(
            r'^\s+SG_\s+(\w+)\s*(?:(\w+)\s*)?\s*:\s*(\d+)\|(\d+)@([01])([+-])'
            r'\s*\(\s*([^,]+)\s*,\s*([^)]+)\s*\)\s*\[\s*([^|]*)\|([^\]]*)\]\s*"([^"]*)"\s*(.*?)$',
            re.MULTILINE)
        for mm in msg_pat.finditer(content):
            mid = int(mm.group(1)); is_ext = (mid & 0x80000000) != 0
            can_id = mid & 0x7FFFFFFF
            self.messages.append({'msg_id': can_id, 'msg_id_hex': f"0x{can_id:03X}",
                'name': mm.group(2), 'dlc': int(mm.group(3)), 'transmitter': mm.group(4),
                'is_extended': is_ext, 'source_file': src})
            nxt = msg_pat.search(content, mm.end())
            blk = content[mm.start():(nxt.start() if nxt else len(content))]
            for sm in sig_pat.finditer(blk):
                self.signals.append({
                    'name': sm.group(1), 'mux_indicator': sm.group(2) or '',
                    'start_bit': int(sm.group(3)), 'bit_length': int(sm.group(4)),
                    'byte_order': 'Motorola' if sm.group(5) == '0' else 'Intel',
                    'is_signed': sm.group(6) == '-',
                    'factor': float(sm.group(7).strip()), 'offset': float(sm.group(8).strip()),
                    'min_value': sm.group(9).strip(), 'max_value': sm.group(10).strip(),
                    'unit': sm.group(11), 'receivers': sm.group(12).strip().rstrip(','),
                    'message_name': mm.group(2), 'message_id': can_id, 'source_file': src})

    def _parse_value_descriptions(self, content, src):
        vp = re.compile(r'^VAL_\s+(\d+)\s+(\w+)((?:\s+\d+\s+"[^"]*")*)\s*;', re.MULTILINE)
        ep = re.compile(r'(\d+)\s+"([^"]*)"')
        for m in vp.finditer(content):
            mid = int(m.group(1)) & 0x7FFFFFFF
            sig = m.group(2)
            entries = [{'value': int(e.group(1)), 'description': e.group(2)} for e in ep.finditer(m.group(3))]
            self.value_descriptions[f"{mid}_{sig}"] = {'message_id': mid, 'signal_name': sig,
                'entries': entries, 'source_file': src}

    def _parse_env_variables(self, content, src):
        evp = re.compile(
            r'^EV_\s+(\w+)\s*:\s*(\d+)\s*\[\s*([^|]*)\|([^\]]*)\]\s*"([^"]*)"\s*([^\s;]+)\s*(\d+)\s*([^;]*);',
            re.MULTILINE)
        for m in evp.finditer(content):
            self.env_variables.append({'name': m.group(1), 'type': int(m.group(2)),
                'min_value': m.group(3).strip(), 'max_value': m.group(4).strip(),
                'unit': m.group(5), 'initial_value': m.group(6).strip(),
                'ev_id': m.group(7), 'access_nodes': m.group(8).strip().rstrip(','),
                'source_file': src})
