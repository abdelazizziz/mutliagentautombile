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
# 6b. CDD PARSER  (NEW — fixes the CDD upload bug)
# =============================================================================
class CddParser:
    """
    Parses a CANdela Studio .cdd file (XML-based).
    Populates:
      self.info       -> cdd_info table fields
      self.services   -> cdd_services table rows
      self.diaginst   -> cdd_diaginst table rows
    """
    def __init__(self):
        self.info       = {}
        self.services   = []
        self.diaginst   = []
        self.dtc_lookup = []   # DTCs extracted from CDD
        self.did_lookup = []   # DIDs extracted from CDD
        self.did_fields = []   # Byte-level DID field details (NEW v23)

    def parse(self, filepath):
        self.info["cdd_file"]    = Path(filepath).name
        self.info["cdd_db_path"] = str(filepath)
        self.info["import_date"] = datetime.now().isoformat(timespec="seconds")
        try:
            from datetime import datetime as _dt
        except ImportError:
            pass
        try:
            tree = ET.parse(filepath)
            root = tree.getroot()
        except ET.ParseError:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                raw = f.read()
            raw = re.sub(r"<!DOCTYPE[^>]*>", "", raw, count=1)
            root = ET.fromstring(raw)

        self.info["dtd_version"] = root.get("dtdvers", "")
        ecudoc = root.find("ECUDOC")
        if ecudoc is None:
            for k in ("ecu_name","manufacturer","protocol","spec_owner","save_number"):
                self.info[k] = ""
            for k in ("diag_instances","services","data_types"):
                self.info[k] = 0
            return self

        self.info["manufacturer"] = ecudoc.get("manufacturer", "")
        self.info["save_number"]  = ecudoc.get("saveno", "")

        proto = ecudoc.find("PROTOCOLSTANDARD")
        self.info["protocol"] = proto.text.strip() if proto is not None and proto.text else ""
        owner = ecudoc.find("SPECOWNER")
        self.info["spec_owner"] = owner.text.strip() if owner is not None and owner.text else ""

        # ECU name
        ecu_name = ""
        name_el = ecudoc.find("NAME")
        if name_el is not None:
            tuv = name_el.find("TUV")
            if tuv is not None and tuv.text:
                ecu_name = tuv.text.strip()
        if not ecu_name:
            qual_el = ecudoc.find("QUAL")
            if qual_el is not None and qual_el.text:
                ecu_name = qual_el.text.strip()
        self.info["ecu_name"] = ecu_name

        src = self.info["cdd_file"]

        # Services
        for svc in ecudoc.findall(".//SERVICE"):
            qual = svc.find("QUAL")
            q = qual.text.strip() if qual is not None and qual.text else ""
            nt = svc.find("NAME")
            nm = ""
            if nt is not None:
                tuv = nt.find("TUV")
                if tuv is not None and tuv.text:
                    nm = tuv.text.strip()
            self.services.append({
                "oid":        svc.get("oid",""),
                "qual":       q,
                "name":       nm or q,
                "functional": svc.get("func","0"),
                "physical":   svc.get("phys","0"),
                "req":        svc.get("req","0"),
                "may_be_exec":svc.get("mayBeExec",""),
                "source_file":src,
            })

        # DiagInst
        for di in ecudoc.findall(".//DIAGINST"):
            qual = di.find("QUAL")
            q = qual.text.strip() if qual is not None and qual.text else ""
            nt = di.find("NAME")
            nm = ""
            if nt is not None:
                tuv = nt.find("TUV")
                if tuv is not None and tuv.text:
                    nm = tuv.text.strip()
            self.diaginst.append({"oid": di.get("oid",""), "qual": q, "name": nm or q, "source_file": src})

        dt_root = ecudoc.find("DATATYPES")
        dt_count = len(list(dt_root)) if dt_root is not None else 0

        self.info["diag_instances"] = len(self.diaginst)
        self.info["services"]       = len(self.services)
        self.info["data_types"]     = dt_count

        # ── DTC lookup (RECORD elements with 6-char hex + description) ──
        raw_str = ET.tostring(ecudoc, encoding="unicode")
        self._parse_dtcs(raw_str)
        # ── DID lookup (DIAGINST with SHORTCUTQUAL pattern _SID_DID_Name) ──
        self._parse_dids(ecudoc)
        # ── Byte-level DID field extraction (NEW v23) ──
        self._build_dt_index(ecudoc)
        self._parse_did_fields(ecudoc)
        return self

    def _parse_dtcs(self, raw_str):
        """Extract all DTCs: hex_code, j2012, description, enable_condition."""
        import re as _re
        pat = _re.compile(
            r'<RECORD[^>]+>.*?<TUV xml:lang=.en-US.>([^<]+)</TUV>.*?'
            r'<TRRECORDITEM[^>]*>.*?<TUV xml:lang=.en-US.>([0-9A-Fa-f]{6})</TUV>.*?'
            r'<TRRECORDITEM[^>]*>.*?<TUV xml:lang=.en-US.>([^<]+)</TUV>',
            _re.DOTALL)
        seen = set()
        for m in pat.finditer(raw_str):
            desc = m.group(1).strip()
            hexv = m.group(2).strip().upper()
            cond = m.group(3).strip()
            if hexv in seen or hexv.startswith('00'): continue
            seen.add(hexv)
            try:
                val  = int(hexv, 16)
                b1   = (val >> 16) & 0xFF
                hi   = (b1 & 0xC0) >> 6
                j2012 = "%s%02X%02X-%02X" % (
                    ['P','C','B','U'][hi],
                    (b1 & 0x3F), (val >> 8) & 0xFF, val & 0xFF)
            except:
                j2012 = ""
            self.dtc_lookup.append({
                "hex_value":        "0x" + hexv,
                "hex_raw":          hexv,
                "j2012":            j2012.upper(),
                "description":      desc,
                "enable_condition": cond,
                "source_file":      self.info.get("cdd_file",""),
            })

    def _parse_dids(self, ecudoc):
        """
        v23.1 — Universal DID extraction (works with any CDD file).

        Discovery methods:
          1. STATICVALUE — accepts any value 0x0100..0xFFFF, but only if the
             DIAGINST contains a Read-type SERVICE (QUAL="Read" or
             SEMANTIC in {STOREDDATA, STOREDDATAREAD, IDENTIFICATION}).
             This filters out routines (0x31), WDBI-only, LIN commands, etc.
          2. SHORTCUTQUAL pattern  _SID_DID_Name  (secondary, catches remaining).

        Both methods deduplicate on (did_hex + sid).
        """
        import re as _re
        pat = _re.compile(r'_([0-9A-Fa-f]{2})([0-9A-Fa-f]{4})_(.+)')
        seen = set()

        _READ_SEMANTICS = {"STOREDDATA","STOREDDATAREAD","IDENTIFICATION"}

        def _has_read_service(di_el):
            """Return True if the DIAGINST has a Read-capable SERVICE."""
            for svc in di_el.findall('.//SERVICE'):
                # Check QUAL
                sq = svc.find('QUAL')
                if sq is not None and sq.text:
                    if sq.text.strip().lower() == 'read':
                        return True
                # Check SEMANTIC
                sem = svc.find('SEMANTIC')
                if sem is not None and sem.text:
                    if sem.text.strip() in _READ_SEMANTICS:
                        return True
            return False

        def _extract_meta(di_el):
            """Extract qual, name, desc from a DIAGINST element."""
            qual_el = di_el.find("QUAL")
            qual = qual_el.text.strip() if qual_el is not None and qual_el.text else ""
            name_el = di_el.find("NAME")
            name = ""
            if name_el is not None:
                tuv = name_el.find("TUV")
                if tuv is not None and tuv.text:
                    name = tuv.text.strip()
            desc_el = di_el.find("DESC")
            desc = ""
            if desc_el is not None:
                tuv = desc_el.find("TUV")
                if tuv is not None and tuv.text:
                    desc = tuv.text.strip()[:200]
            return qual, name, desc

        # ── pass 1: STATICVALUE — universal range with Read-service filter ──
        for di in ecudoc.findall('.//DIAGINST'):
            if not _has_read_service(di):
                continue
            qual, name, desc = _extract_meta(di)
            for sv in di.findall('.//STATICVALUE'):
                v = sv.get('v', '')
                try:
                    iv = int(v)
                    if 0x0100 <= iv <= 0xFFFF:
                        did_hex = f"0x{iv:04X}"
                        key     = did_hex + "22"
                        if key not in seen:
                            seen.add(key)
                            self.did_lookup.append({
                                "did_hex":   did_hex,
                                "did_raw":   f"{iv:04X}",
                                "sid":       "0x22",
                                "qual":      qual,
                                "name":      name,
                                "desc":      desc,
                                "source_file": self.info.get("cdd_file",""),
                            })
                except:
                    pass

        # ── pass 2: SHORTCUTQUAL pattern (secondary, catches remaining) ──
        for di in ecudoc.findall('.//DIAGINST'):
            qual, name, desc = _extract_meta(di)
            for sc in di.findall('.//SHORTCUTQUAL'):
                if not sc.text:
                    continue
                m = pat.match(sc.text)
                if m:
                    sid_hex = m.group(1).upper()
                    did_hex = m.group(2).upper()
                    key     = did_hex + sid_hex
                    if key in seen:
                        continue
                    seen.add(key)
                    self.did_lookup.append({
                        "did_hex":   "0x" + did_hex,
                        "did_raw":   did_hex,
                        "sid":       "0x" + sid_hex,
                        "qual":      qual,
                        "name":      name,
                        "desc":      desc,
                        "source_file": self.info.get("cdd_file",""),
                    })

    # ── v23: Build datatype index by XML id ──────────────────────────
    def _build_dt_index(self, ecudoc):
        """Build a lookup dict  { xml-id -> Element }  for all datatype elements."""
        self._dt_index = {}
        for el in ecudoc.iter():
            eid = el.get("id")
            if eid:
                self._dt_index[eid] = el

    # ── v23: Deep DID field extraction ───────────────────────────────
    def _parse_did_fields(self, ecudoc):
        """
        v23.1 — Enhanced byte-level DID field extraction.

        Handles:
          - Direct DATAOBJ under SIMPLECOMPCONT (simple flat DIDs)
          - STRUCT containers with nested DATAOBJ + GAPDATAOBJ (packed bit-fields)
          - Sub-byte fields (1, 2, 3, 4 bit data types)
          - GAPDATAOBJ reserved padding bits
          - Multiple STRUCTs per DID (multi-segment responses)

        Result is appended to self.did_fields (flat rows, DB-ready).
        """
        import json as _json

        # Map did_hex -> meta from did_lookup
        did_meta = {}
        for d in self.did_lookup:
            did_meta[d["did_hex"]] = d

        src = self.info.get("cdd_file", "")
        sc_pat = re.compile(r'_([0-9A-Fa-f]{2})([0-9A-Fa-f]{4})_(.+)')

        def _resolve_datatype(dtref):
            """Resolve a dtref to (bit_length, encoding, display_fmt, dt_name, dt_tag,
                                    field_type, unit, lin_factor, lin_offset, values_map)."""
            dt_el = self._dt_index.get(dtref)
            bl=8; enc="unknown"; dfmt="unknown"; dtn=""; dtt=""; ft="raw"
            unit=""; lf=None; lo=None; vm={}
            if dt_el is None:
                return bl,enc,dfmt,dtn,dtt,ft,unit,lf,lo,vm
            dtt = dt_el.tag
            q = dt_el.find("QUAL")
            dtn = q.text.strip() if q is not None and q.text else ""
            cv = dt_el.find("CVALUETYPE")
            if cv is not None:
                try:    bl = int(cv.get("bl","8"))
                except: bl = 8
                enc  = cv.get("enc","unknown")
                dfmt = cv.get("df","unknown")
                qty  = cv.get("qty","atom")
                try:    minsz = int(cv.get("minsz","1"))
                except: minsz = 1
                if qty == "field" and bl == 8:
                    bl = minsz * 8
            if dtt == "TEXTTBL":
                ft = "enum"
                for tm in dt_el.findall("TEXTMAP"):
                    s_val = tm.get("s","")
                    txt_el = None
                    for tuv in tm.findall("TEXT/TUV"):
                        if tuv.get("{http://www.w3.org/XML/1998/namespace}lang","")=="en-US":
                            txt_el = tuv; break
                    if txt_el is None:
                        for tuv in tm.findall("TEXT/TUV"):
                            txt_el = tuv; break
                    if txt_el is not None and txt_el.text:
                        vm[s_val] = txt_el.text.strip()
            elif dtt == "LINCOMP":
                ft = "linear"
                comp = dt_el.find("COMP")
                if comp is not None:
                    try:    lf = float(comp.get("f","1"))
                    except: lf = 1.0
                    try:    lo = float(comp.get("o","0"))
                    except: lo = 0.0
                pv = dt_el.find("PVALUETYPE")
                if pv is not None:
                    u_el = pv.find("UNIT")
                    if u_el is not None and u_el.text:
                        unit = u_el.text.strip()
            elif dtt == "IDENT":
                if enc == "asc":     ft = "ascii"
                elif enc == "bcd":   ft = "bcd"
                elif "reserved" in dtn.lower(): ft = "reserved"
                else:                ft = "raw"
            return bl,enc,dfmt,dtn,dtt,ft,unit,lf,lo,vm

        def _get_field_name(el):
            """Get field name from QUAL or NAME/TUV."""
            q = el.find("QUAL")
            if q is not None and q.text:
                return q.text.strip()
            n = el.find("NAME")
            if n is not None:
                tuv = n.find("TUV")
                if tuv is not None and tuv.text:
                    return tuv.text.strip()
            return ""

        for di in ecudoc.findall('.//DIAGINST'):
            # ── Resolve DID value ──
            did_hex = None
            sid_hex = "0x22"
            for sv in di.findall('.//STATICVALUE'):
                try:
                    iv = int(sv.get('v',''))
                    if 0x0100 <= iv <= 0xFFFF:
                        did_hex = f"0x{iv:04X}"; break
                except: pass
            if did_hex is None:
                for sc in di.findall('.//SHORTCUTQUAL'):
                    if sc.text:
                        m = sc_pat.match(sc.text)
                        if m:
                            sid_hex = "0x" + m.group(1).upper()
                            did_hex = "0x" + m.group(2).upper()
                            break
            if did_hex is None or did_hex not in did_meta:
                continue

            # ── Find the response SIMPLECOMPCONT ──
            simplecomps = di.findall('.//SIMPLECOMPCONT')
            if not simplecomps:
                continue
            resp_comp = simplecomps[0]

            # ── Gather all field-bearing children (DATAOBJ + STRUCT) in order ──
            # Iterate over direct children of resp_comp
            bit_cursor  = 0   # cumulative bit position within the DID response
            field_idx   = 0   # sequential field counter

            for child in resp_comp:
                if child.tag == "DATAOBJ":
                    # Direct flat field
                    dtref = child.get("dtref","")
                    (bl,enc,dfmt,dtn,dtt,ft,unit,lf,lo,vm) = _resolve_datatype(dtref)
                    fname = _get_field_name(child)
                    if "reserved" in fname.lower() and ft == "raw":
                        ft = "reserved"

                    byte_idx = bit_cursor // 8
                    bit_in_byte = bit_cursor % 8
                    byte_size = max(1, (bl + 7) // 8)
                    vj = _json.dumps(vm, ensure_ascii=False) if vm else ""

                    self.did_fields.append({
                        "did_hex": did_hex, "field_index": field_idx,
                        "byte_index": byte_idx, "byte_size": byte_size,
                        "field_name": fname,
                        "bit_start": bit_in_byte, "bit_end": bit_in_byte + bl - 1,
                        "bit_length": bl,
                        "field_type": ft, "encoding": enc, "display_format": dfmt,
                        "datatype_name": dtn, "datatype_tag": dtt,
                        "unit": unit, "lin_factor": lf, "lin_offset": lo,
                        "values_json": vj, "source_file": src,
                    })
                    field_idx += 1
                    bit_cursor += bl

                elif child.tag == "STRUCT":
                    # STRUCT container — walk its children (DATAOBJ + GAPDATAOBJ)
                    # The STRUCT's own dtref tells us the container byte size
                    struct_dtref = child.get("dtref","")
                    struct_name  = _get_field_name(child)

                    # Walk STRUCT's direct children in document order
                    for sitem in child:
                        if sitem.tag == "DATAOBJ":
                            dtref = sitem.get("dtref","")
                            (bl,enc,dfmt,dtn,dtt,ft,unit,lf,lo,vm) = _resolve_datatype(dtref)
                            fname = _get_field_name(sitem)
                            if "reserved" in fname.lower() and ft == "raw":
                                ft = "reserved"

                            byte_idx = bit_cursor // 8
                            bit_in_byte = bit_cursor % 8
                            byte_size = max(1, (bl + 7) // 8) if bl >= 8 else 0
                            # For sub-byte fields, byte_size = 0 means
                            # it shares the byte with adjacent fields
                            if bl < 8:
                                byte_size = 0  # packed within a byte
                            vj = _json.dumps(vm, ensure_ascii=False) if vm else ""

                            self.did_fields.append({
                                "did_hex": did_hex, "field_index": field_idx,
                                "byte_index": byte_idx, "byte_size": byte_size or 1,
                                "field_name": fname,
                                "bit_start": bit_in_byte,
                                "bit_end": bit_in_byte + bl - 1,
                                "bit_length": bl,
                                "field_type": ft, "encoding": enc,
                                "display_format": dfmt,
                                "datatype_name": dtn, "datatype_tag": dtt,
                                "unit": unit, "lin_factor": lf, "lin_offset": lo,
                                "values_json": vj, "source_file": src,
                            })
                            field_idx += 1
                            bit_cursor += bl

                        elif sitem.tag == "GAPDATAOBJ":
                            # Reserved padding bits
                            gap_bl = 8
                            try:
                                gap_bl = int(sitem.get("bl","8"))
                            except:
                                gap_bl = 8
                            gap_name = _get_field_name(sitem) or "(reserved)"

                            byte_idx = bit_cursor // 8
                            bit_in_byte = bit_cursor % 8

                            self.did_fields.append({
                                "did_hex": did_hex, "field_index": field_idx,
                                "byte_index": byte_idx, "byte_size": 0 if gap_bl < 8 else max(1,(gap_bl+7)//8),
                                "field_name": gap_name,
                                "bit_start": bit_in_byte,
                                "bit_end": bit_in_byte + gap_bl - 1,
                                "bit_length": gap_bl,
                                "field_type": "reserved", "encoding": "uns",
                                "display_format": "hex",
                                "datatype_name": "reserved", "datatype_tag": "GAP",
                                "unit": "", "lin_factor": None, "lin_offset": None,
                                "values_json": "", "source_file": src,
                            })
                            field_idx += 1
                            bit_cursor += gap_bl

                    # Align to byte boundary after a STRUCT
                    remainder = bit_cursor % 8
                    if remainder:
                        bit_cursor += (8 - remainder)
