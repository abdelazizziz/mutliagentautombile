
import sqlite3

# =============================================================================
# 7. DATABASE BUILDER  -  new vts_sysvars table added
# =============================================================================
class DatabaseBuilder:
    def __init__(self, db_path):
        self.db_path = db_path
        self.conn    = None

    def create_database(self):
        self.conn = sqlite3.connect(self.db_path)
        cur = self.conn.cursor()

        cur.executescript('''
        CREATE TABLE IF NOT EXISTS project_info (
            id INTEGER PRIMARY KEY, cfg_file TEXT, canoe_version TEXT,
            parse_date TEXT, project_dir TEXT);

        CREATE TABLE IF NOT EXISTS project_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_type TEXT, filename TEXT, relative_path TEXT,
            absolute_path TEXT, exists_on_disk INTEGER, parsed INTEGER DEFAULT 0);

        CREATE TABLE IF NOT EXISTS node_assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            capl_file TEXT, node_name TEXT, database_name TEXT);

        CREATE TABLE IF NOT EXISTS can_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            msg_id INTEGER, msg_id_hex TEXT, name TEXT, dlc INTEGER,
            transmitter TEXT, is_extended INTEGER, source_file TEXT);

        CREATE TABLE IF NOT EXISTS can_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, message_name TEXT, message_id INTEGER,
            start_bit INTEGER, bit_length INTEGER, byte_order TEXT,
            is_signed INTEGER, factor REAL, "offset" REAL,
            min_value TEXT, max_value TEXT, unit TEXT,
            receivers TEXT, mux_indicator TEXT, source_file TEXT);

        CREATE TABLE IF NOT EXISTS lin_frames (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, frame_id INTEGER, frame_id_hex TEXT,
            publisher TEXT, dlc INTEGER, source_file TEXT);

        CREATE TABLE IF NOT EXISTS lin_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, frame_name TEXT, frame_id INTEGER,
            bit_offset INTEGER, bit_length INTEGER,
            publisher TEXT, source_file TEXT);

        CREATE TABLE IF NOT EXISTS hil_sysvars (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            namespace TEXT, name TEXT, full_path TEXT, type TEXT,
            bitcount TEXT, start_value TEXT, min_value TEXT, max_value TEXT,
            unit TEXT, comment TEXT, is_signed TEXT, read_only TEXT, source_file TEXT);

        CREATE TABLE IF NOT EXISTS sysvar_values (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            variable_name TEXT, namespace TEXT, table_name TEXT,
            value TEXT, description TEXT, display_string TEXT, source_file TEXT);

        CREATE TABLE IF NOT EXISTS env_variables (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, type INTEGER, min_value TEXT, max_value TEXT,
            unit TEXT, initial_value TEXT, access_nodes TEXT, source_file TEXT);

        CREATE TABLE IF NOT EXISTS capl_mappings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sysvar_path TEXT, signal_name TEXT, mapping_type TEXT,
            direction TEXT, value_expr TEXT, capl_handler TEXT,
            source_file TEXT, message_name TEXT, bus_type TEXT);

        CREATE TABLE IF NOT EXISTS sysvar_refs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sysvar_path TEXT, usage_type TEXT, source_file TEXT, context TEXT);

        CREATE TABLE IF NOT EXISTS envvar_refs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, usage_type TEXT, source_file TEXT, context TEXT);

        CREATE TABLE IF NOT EXISTS signal_values (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER, signal_name TEXT, value INTEGER,
            description TEXT, source_file TEXT);

        

    

        CREATE TABLE IF NOT EXISTS cal_func_params (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cal_name TEXT, project_variant TEXT, value TEXT,
            description TEXT, values_definition TEXT, source_file TEXT);

    

       


        
        ''')

        # ---------------------------------------------------------------
        # network_channels — maps network name (ZCU_CL) to DBC file
        # Populated by scanning CAPL for CAN::NETNAME::FRAME::SIGNAL
        # This is the fix for the wrong ECU name bug
        # ---------------------------------------------------------------
        cur.execute('''
        CREATE TABLE IF NOT EXISTS network_channels (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            network_name TEXT,
            frame_name   TEXT,
            dbc_source   TEXT
        )''')

        cur.executescript('''
        CREATE INDEX IF NOT EXISTS idx_nc_frame   ON network_channels(frame_name);
        CREATE INDEX IF NOT EXISTS idx_nc_network ON network_channels(network_name);
        ''')

        # ---------------------------------------------------------------
        # NEW TABLE: vts_sysvars
        # ---------------------------------------------------------------
        cur.execute('''
        CREATE TABLE IF NOT EXISTS vts_sysvars (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            sysvar_prefix  TEXT DEFAULT "sysvar",
            namespace      TEXT DEFAULT "VTS",
            channel        TEXT,
            attribute      TEXT,
            full_path      TEXT,
            source_file    TEXT,
            UNIQUE(channel, attribute)
        )''')

        # Indexes
        cur.executescript('''
        CREATE INDEX IF NOT EXISTS idx_can_sig_name ON can_signals(name);
        CREATE INDEX IF NOT EXISTS idx_lin_sig_name ON lin_signals(name);
        CREATE INDEX IF NOT EXISTS idx_sv_fullpath  ON hil_sysvars(full_path);
        CREATE INDEX IF NOT EXISTS idx_ev_name      ON env_variables(name);
        CREATE INDEX IF NOT EXISTS idx_svd_signal   ON signal_values(signal_name);
        CREATE INDEX IF NOT EXISTS idx_svvt_var     ON sysvar_values(variable_name);
        CREATE INDEX IF NOT EXISTS idx_vts_channel  ON vts_sysvars(channel);
        CREATE INDEX IF NOT EXISTS idx_vts_attr     ON vts_sysvars(attribute);
        CREATE INDEX IF NOT EXISTS idx_vts_fullpath ON vts_sysvars(full_path);
        
        ''')

        # ---------------------------------------------------------------
        # signal_path  — THE unified view table:
        #   bus_type | ecu_name | frame_name | signal_name
        #   full_can_path (CAN::ZCU_CL::HS1_ZCU_CL_DATA_5::WL_AUTHORIZATION)
        #   env_var       (EV_WL_AUTHORIZATION — from DBC EV_ or CAPL mapping)
        #   hil_sysvar    (sysvar::HIL::ECU::FD::signal — from .vsysvar / CAPL)
        #   vts_sysvar    (sysvar::VTS::S_PS_PDPC::AvgVoltage — from vts_sysvars)
        #   capl_source   (which .can/.cin file created the mapping)
        # ---------------------------------------------------------------
        cur.execute('''
        CREATE TABLE IF NOT EXISTS signal_path (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            bus_type       TEXT,
            ecu_name       TEXT,
            frame_name     TEXT,
            signal_name    TEXT,
            full_can_path  TEXT,
            env_var        TEXT,
            hil_sysvar     TEXT,
            vts_sysvar     TEXT,
            capl_source    TEXT,
            dbc_source     TEXT
        )''')

        cur.executescript('''
        CREATE INDEX IF NOT EXISTS idx_sm_signal    ON signal_path(signal_name);
        CREATE INDEX IF NOT EXISTS idx_sm_path      ON signal_path(full_can_path);
        CREATE INDEX IF NOT EXISTS idx_sm_envvar    ON signal_path(env_var);
        CREATE INDEX IF NOT EXISTS idx_sm_vts       ON signal_path(vts_sysvar);
        ''')
        self.conn.commit()

    # -------- insert helpers (unchanged) --------

    def insert_project_info(self, cfg_file, canoe_version, project_dir):
        from datetime import datetime
        self.conn.execute(
            'INSERT INTO project_info (cfg_file,canoe_version,parse_date,project_dir) VALUES(?,?,?,?)',
            (cfg_file, canoe_version, datetime.now().isoformat(), project_dir))
        self.conn.commit()

    def insert_project_files(self, files_dict):
        for ftype, fl in files_dict.items():
            for f in fl:
                self.conn.execute(
                    'INSERT INTO project_files (file_type,filename,relative_path,absolute_path,exists_on_disk) VALUES(?,?,?,?,?)',
                    (ftype, f['filename'], f['relative_path'], f['absolute_path'], 1 if f['exists'] else 0))
        self.conn.commit()

    def insert_node_assignments(self, nodes):
        for n in nodes:
            self.conn.execute('INSERT INTO node_assignments (capl_file,node_name,database_name) VALUES(?,?,?)',
                (n['capl_file'], n['node_name'], n['database']))
        self.conn.commit()

    def insert_hil_sysvars(self, variables):
        cur = self.conn.cursor()
        for v in variables:
            cur.execute('''INSERT INTO hil_sysvars
                (namespace,name,full_path,type,bitcount,start_value,min_value,max_value,
                 unit,comment,is_signed,read_only,source_file)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (v['namespace'],v['name'],v['full_path'],v['type'],v['bitcount'],
                 v['start_value'],v['min_value'],v['max_value'],v['unit'],v['comment'],
                 v['is_signed'],v['read_only'],v['source_file']))
            for ve in v.get('value_entries', []):
                cur.execute('''INSERT INTO sysvar_values
                    (variable_name,namespace,table_name,value,description,display_string,source_file)
                    VALUES(?,?,?,?,?,?,?)''',
                    (v['name'],v['namespace'],ve['table_name'],ve['value'],
                     ve['description'],ve['display_string'],v['source_file']))
        self.conn.commit()

    def insert_vts_sysvars(self, records):
        cur = self.conn.cursor()
        # Clear existing entries so rebuilding does not accumulate duplicates
        cur.execute('DELETE FROM vts_sysvars')
        inserted = 0
        for r in records:
            try:
                cur.execute(
                    'INSERT OR IGNORE INTO vts_sysvars '
                    '(sysvar_prefix, namespace, channel, attribute, full_path, source_file) '
                    'VALUES (?,?,?,?,?,?)',
                    (r['sysvar_prefix'], r['namespace'], r['channel'],
                     r['attribute'], r['full_path'], r['source_file']))
                if cur.rowcount:
                    inserted += 1
            except Exception:
                pass
        self.conn.commit()
        return inserted

    def insert_network_channels(self, records):
        """
        records = list of (network_name, frame_name, dbc_source)
        Built by scanning CAPL for CAN::NETNAME::FRAME::SIGNAL
        """
        cur = self.conn.cursor()
        cur.execute('DELETE FROM network_channels')
        seen = set()
        for (net, frame, dbc) in records:
            key = (net.upper(), frame.upper())
            if key not in seen:
                seen.add(key)
                cur.execute(
                    'INSERT INTO network_channels (network_name,frame_name,dbc_source) VALUES(?,?,?)',
                    (net, frame, dbc))
        self.conn.commit()

    def build_signal_path(self):
        """
        Build the unified signal_path table.

        ECU name = transmitter field from DBC BO_ line (via JOIN with can_messages).
        Group by (transmitter, frame, signal) so every ECU keeps its signals:
          DCU_FD.dbc  -> DCU_FD rows
          DCU_FP.dbc  -> DCU_FP rows
          ZCU_CL.dbc  -> ZCU_CL rows   (all appear, no collapse)
        """
        cur = self.conn.cursor()
        cur.execute('DELETE FROM signal_path')

        # ── Step 1: CAN signals — one row per (transmitter, frame, signal) ──
        cur.execute('''
            INSERT INTO signal_path
              (bus_type, ecu_name, frame_name, signal_name, full_can_path, dbc_source)
            SELECT
              'CAN',
              cm.transmitter,
              cs.message_name,
              cs.name,
              'CAN::' || cm.transmitter || '::' || cs.message_name || '::' || cs.name,
              cs.source_file
            FROM can_signals cs
            JOIN can_messages cm
              ON UPPER(cm.name) = UPPER(cs.message_name)
             AND UPPER(cm.source_file) = UPPER(cs.source_file)
            WHERE cs.message_name IS NOT NULL AND cs.message_name != ''
              AND cm.transmitter IS NOT NULL AND cm.transmitter != ''
              AND cm.transmitter != 'Vector__XXX'
            GROUP BY UPPER(cm.transmitter), UPPER(cs.message_name), UPPER(cs.name)
        ''')

        # Fallback: signals whose message has no matching can_messages entry
        # (e.g. receive-only DBC), use DBC filename stem as ECU
        cur.execute('''
            INSERT OR IGNORE INTO signal_path
              (bus_type, ecu_name, frame_name, signal_name, full_can_path, dbc_source)
            SELECT
              'CAN',
              REPLACE(REPLACE(cs.source_file,'.dbc',''),'.DBC',''),
              cs.message_name,
              cs.name,
              'CAN::' || REPLACE(REPLACE(cs.source_file,'.dbc',''),'.DBC','')
                       || '::' || cs.message_name || '::' || cs.name,
              cs.source_file
            FROM can_signals cs
            WHERE cs.message_name IS NOT NULL AND cs.message_name != ''
              AND NOT EXISTS (
                SELECT 1 FROM signal_path sp2
                WHERE UPPER(sp2.frame_name)  = UPPER(cs.message_name)
                  AND UPPER(sp2.signal_name) = UPPER(cs.name)
              )
            GROUP BY UPPER(cs.source_file), UPPER(cs.message_name), UPPER(cs.name)
        ''')

        # ── Step 2: LIN signals ──────────────────────────────────────────────
        cur.execute('''
            INSERT INTO signal_path
              (bus_type, ecu_name, frame_name, signal_name, full_can_path, dbc_source)
            SELECT 'LIN',
              COALESCE(NULLIF(ls.publisher,''), REPLACE(REPLACE(ls.source_file,'.ldf',''),'.LDF','')),
              ls.frame_name,
              ls.name,
              'LIN::' ||
              COALESCE(NULLIF(ls.publisher,''), REPLACE(REPLACE(ls.source_file,'.ldf',''),'.LDF',''))
              || '::' || ls.frame_name || '::' || ls.name,
              ls.source_file
            FROM lin_signals ls
            WHERE ls.frame_name IS NOT NULL AND ls.frame_name != ''
            GROUP BY UPPER(ls.frame_name), UPPER(ls.name)
        ''')

        # ── Step 3: env_var — three-tier case-insensitive lookup ─────────────
        # Tier 1: env_variables table (DBC EV_ section)
        cur.execute('''
            UPDATE signal_path SET env_var = (
                SELECT ev.name FROM env_variables ev
                WHERE UPPER(ev.name) = 'EV_' || UPPER(signal_path.signal_name)
                   OR UPPER(ev.name) = UPPER(signal_path.signal_name)
                LIMIT 1)
        ''')
        # Tier 2: envvar_refs (CAPL @EV_xxx usages)
        cur.execute('''
            UPDATE signal_path SET env_var = COALESCE(env_var, (
                SELECT DISTINCT er.name FROM envvar_refs er
                WHERE UPPER(er.name) = 'EV_' || UPPER(signal_path.signal_name)
                LIMIT 1))
        ''')
        # Tier 3: capl_mappings envvar entries
        # BUG-CA-04 FIX: normalize sysvar:: prefix in the CASE expression
        cur.execute('''
            UPDATE signal_path SET env_var = COALESCE(env_var, (
                SELECT
                  CASE
                    WHEN cm2.sysvar_path LIKE 'sysvar::%' THEN cm2.sysvar_path
                    WHEN cm2.sysvar_path LIKE '%::%'
                         AND cm2.sysvar_path NOT LIKE 'EV_%'
                    THEN 'sysvar::' || cm2.sysvar_path
                    ELSE cm2.sysvar_path
                  END
                FROM capl_mappings cm2
                WHERE UPPER(cm2.signal_name) = UPPER(signal_path.signal_name)
                  AND (cm2.mapping_type LIKE '%envvar%'
                       OR cm2.sysvar_path LIKE 'EV_%'
                       OR cm2.sysvar_path LIKE 'sysvar::%'
                       OR cm2.sysvar_path LIKE '%::%')
                LIMIT 1))
        ''')

        # ── Step 4: CAPL source file ─────────────────────────────────────────
        cur.execute('''
            UPDATE signal_path SET capl_source = (
                SELECT cm2.source_file FROM capl_mappings cm2
                WHERE UPPER(cm2.signal_name) = UPPER(signal_path.signal_name)
                LIMIT 1)
        ''')

        # ── Step 4a: sysvar_ prefix-aware HIL sysvar join ────────────────────
        # Populates hil_sysvar column — the HIL system variable path for each signal.
        # Handles the 'sysvar_' prefix convention in HIL table.
        cur.execute('''
            UPDATE signal_path SET hil_sysvar = COALESCE(hil_sysvar, (
                SELECT
                  CASE WHEN hs.full_path LIKE 'sysvar::%'
                       THEN hs.full_path
                       ELSE 'sysvar::' || hs.full_path
                  END
                FROM hil_sysvars hs
                WHERE UPPER(hs.name) = UPPER(signal_path.signal_name)
                   OR UPPER(hs.name) = UPPER('sysvar_' || signal_path.signal_name)
                   OR UPPER(REPLACE(REPLACE(hs.name,'sysvar_',''),'SYSVAR_',''))
                      = UPPER(signal_path.signal_name)
                LIMIT 1))
        ''')

        # ── Step 4b: VTS sysvar join ─────────────────────────────────────────
        # Populates vts_sysvar column — picks the Avg path as default reference.
        # The CAPL generator queries vts_sysvars directly for all attributes
        # when it needs to choose the right one (PWMDC, AvgVoltage, etc.)
        cur.execute('''
            UPDATE signal_path SET vts_sysvar = COALESCE(vts_sysvar, (
                SELECT vs.full_path FROM vts_sysvars vs
                WHERE UPPER(vs.channel) = UPPER(signal_path.signal_name)
                  AND vs.attribute = 'Avg'
                LIMIT 1))
        ''')
        # Fallback: if no Avg, use any available attribute
        cur.execute('''
            UPDATE signal_path SET vts_sysvar = COALESCE(vts_sysvar, (
                SELECT vs.full_path FROM vts_sysvars vs
                WHERE UPPER(vs.channel) = UPPER(signal_path.signal_name)
                LIMIT 1))
        ''')
        # Also try with S_ prefix (VTS channels often have S_ prefix)
        cur.execute('''
            UPDATE signal_path SET vts_sysvar = COALESCE(vts_sysvar, (
                SELECT vs.full_path FROM vts_sysvars vs
                WHERE UPPER(vs.channel) = UPPER('S_' || signal_path.signal_name)
                  AND vs.attribute = 'Avg'
                LIMIT 1))
        ''')

        self.conn.commit()
        cur.execute('SELECT COUNT(*) FROM signal_path')
        return cur.fetchone()[0]

    def _has_column(self, table, column):
        cur = self.conn.cursor()
        cur.execute('PRAGMA table_info(%s)' % table)
        return any(row[1] == column for row in cur.fetchall())

    def insert_capl_mappings(self, parser):
        cur = self.conn.cursor()
        for m in parser.mappings:
            cur.execute('''INSERT INTO capl_mappings
                (sysvar_path,signal_name,mapping_type,direction,value_expr,capl_handler,
                 source_file,message_name,bus_type) VALUES(?,?,?,?,?,?,?,?,?)''',
                (m['sysvar_path'],m['signal_name'],m['mapping_type'],m['direction'],
                 m['value_expr'],m['capl_handler'],m['source_file'],
                 m.get('message_name',''),m.get('bus_type','')))
        for r in parser.sysvar_refs:
            cur.execute('INSERT INTO sysvar_refs (sysvar_path,usage_type,source_file,context) VALUES(?,?,?,?)',
                (r['sysvar_path'],r['usage_type'],r['source_file'],r['context']))
        for e in parser.envvar_refs:
            cur.execute('INSERT INTO envvar_refs (name,usage_type,source_file,context) VALUES(?,?,?,?)',
                (e['name'],e['usage_type'],e['source_file'],e['context']))
        self.conn.commit()

    def insert_capl_references(self, parser):
        cur = self.conn.cursor()
        for r in parser.sysvar_refs:
            cur.execute('INSERT INTO sysvar_refs (sysvar_path,usage_type,source_file,context) VALUES(?,?,?,?)',
                (r['sysvar_path'],r['usage_type'],r['source_file'],r['context']))
        for e in parser.envvar_refs:
            cur.execute('INSERT INTO envvar_refs (name,usage_type,source_file,context) VALUES(?,?,?,?)',
                (e['name'],e['usage_type'],e['source_file'],e['context']))
        self.conn.commit()

    def insert_can_data(self, parser):
        cur = self.conn.cursor()
        for m in parser.messages:
            cur.execute('INSERT INTO can_messages (msg_id,msg_id_hex,name,dlc,transmitter,is_extended,source_file) VALUES(?,?,?,?,?,?,?)',
                (m['msg_id'],m['msg_id_hex'],m['name'],m['dlc'],m['transmitter'],m['is_extended'],m['source_file']))
        for s in parser.signals:
            cur.execute('''INSERT INTO can_signals
                (name,message_name,message_id,start_bit,bit_length,byte_order,is_signed,
                 factor,"offset",min_value,max_value,unit,receivers,mux_indicator,source_file)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (s['name'],s['message_name'],s['message_id'],s['start_bit'],s['bit_length'],
                 s['byte_order'],s['is_signed'],s['factor'],s['offset'],s['min_value'],
                 s['max_value'],s['unit'],s['receivers'],s.get('mux_indicator',''),s['source_file']))
        for ev in parser.env_variables:
            cur.execute('INSERT INTO env_variables (name,type,min_value,max_value,unit,initial_value,access_nodes,source_file) VALUES(?,?,?,?,?,?,?,?)',
                (ev['name'],ev['type'],ev['min_value'],ev['max_value'],ev['unit'],ev['initial_value'],ev['access_nodes'],ev['source_file']))
        for key, vd in parser.value_descriptions.items():
            for e in vd['entries']:
                cur.execute('INSERT INTO signal_values (message_id,signal_name,value,description,source_file) VALUES(?,?,?,?,?)',
                    (vd['message_id'],vd['signal_name'],e['value'],e['description'],vd['source_file']))
        self.conn.commit()

    def insert_lin_data(self, parser):
        cur = self.conn.cursor()
        for f in parser.frames:
            cur.execute('INSERT INTO lin_frames (name,frame_id,frame_id_hex,publisher,dlc,source_file) VALUES(?,?,?,?,?,?)',
                (f['name'],f['frame_id'],f['frame_id_hex'],f['publisher'],f['dlc'],f['source_file']))
        for s in parser.signals:
            if 'frame_name' in s:
                cur.execute('INSERT INTO lin_signals (name,frame_name,frame_id,bit_offset,bit_length,publisher,source_file) VALUES(?,?,?,?,?,?,?)',
                    (s['name'],s.get('frame_name',''),s.get('frame_id',0),s.get('bit_offset',0),s.get('bit_length',0),s.get('publisher',''),s['source_file']))
        self.conn.commit()

    def insert_dtc_data(self, parser):
        for d in parser.dtcs:
            self.conn.execute('''INSERT INTO dtc_matrix
                (assigned_to,hex_value,hex_code,j2012_format,description,occurrence_fault,
                 warning_indicator,warning_type,priority,healing_criteria,enable_conditions,
                 mature_threshold,monitor_type,engineering_notes,customer_symptom,
                 possible_causes,repair_action,dtc_byte1,dtc_byte2,dtc_byte3,
                 dtc_int,version_tag,source_file)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (d['assigned_to'],d['hex_value'],d['hex_code'],d['j2012_format'],d['description'],
                 d['occurrence_fault'],d['warning_indicator'],d['warning_type'],d['priority'],
                 d['healing_criteria'],d['enable_conditions'],d['mature_threshold'],d['monitor_type'],
                 d.get('engineering_notes'),d.get('customer_symptom'),d.get('possible_causes'),
                 d.get('repair_action'),d.get('dtc_byte1'),d.get('dtc_byte2'),d.get('dtc_byte3'),
                 d.get('dtc_int'),d['version_tag'],d['source_file']))
        self.conn.commit()

    def insert_calibration_data(self, parser):
        for p in parser.cal_params:
            self.conn.execute('INSERT INTO cal_params (cal_name,unit,function,sub_function,description,responsible,default_value,source_file) VALUES(?,?,?,?,?,?,?,?)',
                (p['cal_name'],p['unit'],p['function'],p['sub_function'],p['description'],p['responsible'],p['default_value'],p['source_file']))
        for fp in parser.func_params:
            self.conn.execute('INSERT INTO cal_func_params (cal_name,project_variant,value,description,values_definition,source_file) VALUES(?,?,?,?,?,?)',
                (fp['cal_name'],fp['project_variant'],fp['value'],fp['description'],fp['values_definition'],fp['source_file']))
        for cr in parser.change_requests:
            self.conn.execute('INSERT INTO cal_changes (request_number,date,state,emitter,actor,carline,cal_name,old_value,new_value,justification,source_file) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                (cr['request_number'],cr['date'],cr['state'],cr['emitter'],cr['actor'],cr['carline'],cr.get('cal_name'),cr.get('old_value'),cr.get('new_value'),cr.get('justification'),cr['source_file']))
        self.conn.commit()


    def insert_cdd_info(self, parser):
        i = parser.info
        self.conn.execute("DELETE FROM cdd_info")
        self.conn.execute(
            "INSERT INTO cdd_info "
            "(cdd_file,cdd_db_path,import_date,ecu_name,manufacturer,protocol,"
            "spec_owner,dtd_version,save_number,diag_instances,services,data_types) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (i.get("cdd_file",""), i.get("cdd_db_path",""), i.get("import_date",""),
             i.get("ecu_name",""), i.get("manufacturer",""), i.get("protocol",""),
             i.get("spec_owner",""), i.get("dtd_version",""), i.get("save_number",""),
             i.get("diag_instances",0), i.get("services",0), i.get("data_types",0)))
        self.conn.execute("DELETE FROM cdd_services")
        for s in parser.services:
            self.conn.execute(
                "INSERT INTO cdd_services (oid,qual,name,functional,physical,req,may_be_exec,source_file) VALUES (?,?,?,?,?,?,?,?)",
                (s["oid"],s["qual"],s["name"],s["functional"],s["physical"],s["req"],s["may_be_exec"],s["source_file"]))
        self.conn.execute("DELETE FROM cdd_diaginst")
        for d in parser.diaginst:
            self.conn.execute("INSERT INTO cdd_diaginst (oid,qual,name,source_file) VALUES (?,?,?,?)",
                (d["oid"],d["qual"],d["name"],d["source_file"]))

        # DTC lookup from CDD
        self.conn.execute("DELETE FROM cdd_dtc_lookup")
        for d in parser.dtc_lookup:
            self.conn.execute(
                "INSERT INTO cdd_dtc_lookup (hex_value,hex_raw,j2012,description,enable_condition,source_file) "
                "VALUES (?,?,?,?,?,?)",
                (d["hex_value"],d["hex_raw"],d["j2012"],d["description"],d["enable_condition"],d["source_file"]))

        # DID lookup from CDD
        self.conn.execute("DELETE FROM cdd_did_lookup")
        for d in parser.did_lookup:
            self.conn.execute(
                "INSERT INTO cdd_did_lookup (did_hex,did_raw,sid,qual,name,desc,source_file) "
                "VALUES (?,?,?,?,?,?,?)",
                (d["did_hex"],d["did_raw"],d["sid"],d["qual"],d["name"],d["desc"],d["source_file"]))

        # DID byte-level fields from CDD (NEW v23)
        self.conn.execute("DELETE FROM cdd_did_fields")
        for f in parser.did_fields:
            self.conn.execute(
                "INSERT INTO cdd_did_fields "
                "(did_hex,field_index,byte_index,byte_size,field_name,"
                "bit_start,bit_end,bit_length,field_type,encoding,"
                "display_format,datatype_name,datatype_tag,unit,"
                "lin_factor,lin_offset,values_json,source_file) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (f["did_hex"],f["field_index"],f["byte_index"],f["byte_size"],
                 f["field_name"],f["bit_start"],f["bit_end"],f["bit_length"],
                 f["field_type"],f["encoding"],f["display_format"],
                 f["datatype_name"],f["datatype_tag"],f["unit"],
                 f["lin_factor"],f["lin_offset"],f["values_json"],
                 f["source_file"]))

        self.conn.commit()

    def get_stats(self):
        cur = self.conn.cursor()
        stats = {}
        tables = ['can_messages','can_signals','lin_frames','lin_signals',
                  'hil_sysvars','sysvar_values','env_variables',
                  'capl_mappings','sysvar_refs','envvar_refs',
                  'signal_values','project_files','node_assignments',
                  'dtc_matrix','cal_params','cal_func_params',
                  'cal_changes','cdd_info','cdd_services',
                  'cdd_diaginst','cdd_dtc_lookup','cdd_did_lookup',
                  'cdd_did_fields','vts_sysvars','signal_path']
        for t in tables:
            try:
                cur.execute('SELECT COUNT(*) FROM ' + t)
                stats[t] = cur.fetchone()[0]
            except:
                stats[t] = 0
        return stats

    def close(self):
        if self.conn: self.conn.close()

