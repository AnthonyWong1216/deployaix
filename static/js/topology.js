/* ============================================================
   PowerVM Virtualization Topology — engine
   Loaded on /topology.  Requires: vis-network, lucide (global).
   Mock datasets simulate parsed HMC `lshwres` / `lssyscfg` output.
============================================================ */
(function () {
  "use strict";

  // ---------- Palette (color-coded blocks) ----------
  const C = {
    vios:   { bg: "#dbeafe", border: "#2563eb", font: "#1e3a8a" }, // Blue  = VIOS
    client: { bg: "#dcfce7", border: "#16a34a", font: "#14532d" }, // Green = Client LPAR
    mid:    { bg: "#f1f5f9", border: "#94a3b8", font: "#334155" }, // Slate = intermediate
    vlan:   { bg: "#fef9c3", border: "#ca8a04", font: "#713f12" }, // Amber = VLAN/switch
    phys:   { bg: "#ede9fe", border: "#7c3aed", font: "#4c1d95" }, // Violet = physical
  };

  const COL = { left: -460, mid: 0, right: 460 };
  const NCOL = { client: -600, vlan: -180, vios: 240, phys: 620 };
  const ROW_GAP = 130;

  function rows(n, gap) {
    gap = gap || ROW_GAP;
    const start = -((n - 1) * gap) / 2;
    return Array.from({ length: n }, (_, i) => start + i * gap);
  }

  function box(id, label, kind, x, y, title) {
    const c = C[kind];
    return {
      id: id, label: label, x: x, y: y, title: title || undefined,
      shape: "box",
      color: { background: c.bg, border: c.border,
               highlight: { background: c.bg, border: c.border } },
      font: { color: c.font, size: 13, face: "Inter, sans-serif", multi: "html", align: "center" },
      borderWidth: 2,
      shapeProperties: { borderRadius: 8 },
      margin: 12,
      widthConstraint: { minimum: 150, maximum: 210 },
      _kind: kind,
    };
  }

  function edge(from, to, label, title) {
    return {
      from: from, to: to, label: label, title: title || undefined,
      arrows: { to: { enabled: true, scaleFactor: 0.6 } },
      color: { color: "#94a3b8", highlight: "#0f172a" },
      font: { size: 11, color: "#475569", strokeWidth: 4, strokeColor: "#ffffff", align: "middle" },
      smooth: { enabled: false },
      width: 1.5,
    };
  }

  /* ============================================================
     DATASET REGISTRY  (populated below)
  ============================================================ */
  const DATA = {};

  // expose to helper builder scope
  window.__TOPO = { C, COL, NCOL, rows, box, edge, DATA };

  /* ===== TAB 1 — NPIV ===== */
  function npivData_A() {
    const nodes = [], edges = [];
    const vy = rows(2, 200);
    nodes.push(box("v1", "<b>VIOS1</b>\nID 1 · vios1a", "vios", COL.left, vy[0], "Partition: vios1a\nLPAR ID: 1\nState: Running\nRMC: active"));
    nodes.push(box("v2", "<b>VIOS2</b>\nID 2 · vios2a", "vios", COL.left, vy[1], "Partition: vios2a\nLPAR ID: 2\nState: Running\nRMC: active"));
    // Fields mirror: lshwres -r virtualio --rsubtype fc --level lpar
    // slot_num       = VIOS server adapter slot  (sticks to VIOS arrow)
    // remote_slot_num= client adapter slot        (sticks to Client arrow)
    const midDefs = [
      { id: "m1", v: "v1", vid: 1, vfc: "vfchost0", fcs: "fcs0", loc: "U78D5.001.ABC-P1-C2-T1", slot: 15, c: "c1", rid: 16, rslot: 3, wwpns: "c0507609a1b20030" },
      { id: "m2", v: "v2", vid: 2, vfc: "vfchost0", fcs: "fcs0", loc: "U78D5.001.DEF-P1-C5-T1", slot: 15, c: "c1", rid: 16, rslot: 4, wwpns: "c0507609a1b20032" },
      { id: "m3", v: "v1", vid: 1, vfc: "vfchost1", fcs: "fcs1", loc: "U78D5.001.ABC-P1-C2-T2", slot: 16, c: "c2", rid: 17, rslot: 3, wwpns: "c0507609a1b20040" },
      { id: "m4", v: "v2", vid: 2, vfc: "vfchost1", fcs: "fcs1", loc: "U78D5.001.DEF-P1-C5-T2", slot: 16, c: "c2", rid: 17, rslot: 4, wwpns: "c0507609a1b20042" },
      { id: "m5", v: "v1", vid: 1, vfc: "vfchost2", fcs: "fcs2", loc: "U78D5.001.ABC-P1-C3-T1", slot: 17, c: "c3", rid: 18, rslot: 3, wwpns: "c0507609a1b20050" },
    ];
    const my = rows(midDefs.length, 118);
    midDefs.forEach((m, i) => {
      nodes.push(box(m.id, "<b>" + m.vfc + "</b>\n" + m.fcs + " · fabric\n<i>" + m.loc + "</i>", "mid", COL.mid, my[i],
        "adapter_type=server\nVirtual FC Host: " + m.vfc + "\nslot_num=" + m.slot +
        "\nBacking port: " + m.fcs + "\nPhysical loc: " + m.loc + "\nremote_slot_num=" + m.rslot + "\nFabric login: LOGGED_IN"));
      // VIOS → mapping : VIOS server-adapter slot_num sticks to the VIOS arrow
      edges.push(edge(m.v, m.id, "slot_num " + m.slot,
        "VIOS lpar_id=" + m.vid + "\nadapter_type=server\nslot_num=" + m.slot));
      // mapping → client : client remote_slot_num + WWPN sticks to the Client arrow
      edges.push(edge(m.id, m.c, "remote_slot_num " + m.rslot + "\nWWPN " + m.wwpns,
        "remote_lpar_id=" + m.rid + "\nremote_slot_num=" + m.rslot + "\nActive WWPN: " + m.wwpns + "\nNPIV: enabled"));
    });

    const cDefs = [
      { id: "c1", n: "aix-db-prod", lid: 11 },
      { id: "c2", n: "aix-app-prod", lid: 12 },
      { id: "c3", n: "linux-web01", lid: 13 },
    ];
    const cy = rows(cDefs.length, 170);
    cDefs.forEach((c, i) => nodes.push(box(c.id, "<b>" + c.n + "</b>\nLPAR ID " + c.lid, "client", COL.right, cy[i],
      "Client LPAR: " + c.n + "\nLPAR ID: " + c.lid + "\nOS: AIX / Linux\nBoot: SAN (NPIV)")));
    return { nodes: nodes, edges: edges };
  }

  function npivData_B() {
    const nodes = [], edges = [];
    const vy = rows(2, 180);
    nodes.push(box("v1", "<b>VIOS1</b>\nID 1 · vio1", "vios", COL.left, vy[0], "Partition: vio1\nLPAR ID: 1\nState: Running"));
    nodes.push(box("v2", "<b>VIOS2</b>\nID 2 · vio2", "vios", COL.left, vy[1], "Partition: vio2\nLPAR ID: 2\nState: Running"));
    const midDefs = [
      { id: "m1", v: "v1", vid: 1, vfc: "vfchost0", fcs: "fcs0", loc: "U78CB.001.XYZ-P1-C1-T1", slot: 12, c: "c1", rid: 21, rslot: 2, wwpns: "c0507601aa990010" },
      { id: "m2", v: "v2", vid: 2, vfc: "vfchost0", fcs: "fcs0", loc: "U78CB.001.WWW-P1-C1-T1", slot: 12, c: "c1", rid: 21, rslot: 5, wwpns: "c0507601aa990012" },
      { id: "m3", v: "v1", vid: 1, vfc: "vfchost1", fcs: "fcs1", loc: "U78CB.001.XYZ-P1-C1-T2", slot: 13, c: "c2", rid: 22, rslot: 2, wwpns: "c0507601aa990020" },
    ];
    const my = rows(midDefs.length, 140);
    midDefs.forEach((m, i) => {
      nodes.push(box(m.id, "<b>" + m.vfc + "</b>\n" + m.fcs + " · fabric\n<i>" + m.loc + "</i>", "mid", COL.mid, my[i],
        "adapter_type=server\nVirtual FC Host: " + m.vfc + "\nslot_num=" + m.slot +
        "\nBacking port: " + m.fcs + "\nPhysical loc: " + m.loc + "\nremote_slot_num=" + m.rslot));
      edges.push(edge(m.v, m.id, "slot_num " + m.slot, "VIOS lpar_id=" + m.vid + "\nadapter_type=server\nslot_num=" + m.slot));
      edges.push(edge(m.id, m.c, "remote_slot_num " + m.rslot + "\nWWPN " + m.wwpns,
        "remote_lpar_id=" + m.rid + "\nremote_slot_num=" + m.rslot + "\nActive WWPN: " + m.wwpns));
    });

    const cDefs = [{ id: "c1", n: "aix-erp-01", lid: 21 }, { id: "c2", n: "aix-erp-02", lid: 22 }];
    const cy = rows(cDefs.length, 200);
    cDefs.forEach((c, i) => nodes.push(box(c.id, "<b>" + c.n + "</b>\nLPAR ID " + c.lid, "client", COL.right, cy[i],
      "Client LPAR: " + c.n + "\nLPAR ID: " + c.lid + "\nBoot: SAN (NPIV)")));
    return { nodes: nodes, edges: edges };
  }

  /* ===== TAB 2 — vSCSI =====
   *
   * Mock data simulates a data-join of two real HMC command outputs:
   *
   *  SOURCE 1 — lshwres -r virtualio --rsubtype scsi
   *    Fields used: lpar_name (VIOS), slot_num (VIOS server adapter slot),
   *                 remote_lpar_name (Client LPAR), remote_slot_num (client slot → CXX)
   *
   *  SOURCE 2 — viosvrcmd -m <ms> -p <vios> -c "lsmap -all -fmt ,"
   *    Fields used: vhost (vhostX device name), svr_slot (VIOS slot — join key),
   *                 vtd (virtual target device), backing (hdiskX / lv_X / lu_X),
   *                 backing_type, status
   *
   * JOIN KEY: lshwres.slot_num  ==  lsmap.svr_slot  (both reference the VIOS
   *           server-adapter slot number).  This join resolves:
   *           vhostX + Backing  <—>  Client LPAR name + Client Slot (CXX)
   *
   * Middle node label format:  "Slot <N> (vhost<X>)\nBacking: <device>"
   * VIOS→Middle edge label:    "Slot <N>"    (VIOS server-adapter slot)
   * Middle→Client edge label:  "Slot C<N>"   (client adapter slot in CXX format)
   */

  /*
   * Internal helper: build vSCSI nodes/edges from a normalised midDefs array.
   *
   * Each midDef entry represents one row after joining lshwres + lsmap:
   *   id          – unique node id for this middle node
   *   v           – id of the VIOS node (left column)
   *   viosSlot    – VIOS server-adapter slot_num  (from lshwres / lsmap join)
   *   vhost       – vhostX device name            (from lsmap)
   *   vtd         – virtual target device         (from lsmap, e.g. vtscsi0)
   *   backing     – backing device                (from lsmap, e.g. hdisk10, lv_X)
   *   backingType – device type label
   *   c           – id of the Client LPAR node (right column)
   *   clientSlot  – remote_slot_num from lshwres  (rendered as CXX on the edge)
   *   status      – lsmap status field
   */
  function _buildVscsiGraph(viosDefs, midDefs, cDefs) {
    const nodes = [], edges = [];

    // Left column — VIOS nodes
    const vy = rows(viosDefs.length, 220);
    viosDefs.forEach((v, i) => {
      nodes.push(box(v.id, "<b>" + v.label + "</b>\n" + v.sub, "vios", COL.left, vy[i], v.tip));
    });

    // Middle column — one node per joined lshwres + lsmap row
    const my = rows(midDefs.length, 118);
    midDefs.forEach((m, i) => {
      // Middle label: "Slot <N> (vhostX)\nBacking: <device>"
      const midLabel = "<b>Slot " + m.viosSlot + " (" + m.vhost + ")</b>\nBacking: " + m.backing;
      const midTip =
        "━━ lshwres (scsi) ━━\n" +
        "VIOS: " + m.viosName + "\n" +
        "slot_num (server adapter): " + m.viosSlot + "\n" +
        "remote_lpar_name: " + m.clientName + "\n" +
        "remote_slot_num: " + m.clientSlot + "\n" +
        "━━ lsmap (join on slot_num=" + m.viosSlot + ") ━━\n" +
        "vhost: " + m.vhost + "\n" +
        "vtd: " + m.vtd + "\n" +
        "backing: " + m.backing + "\n" +
        "type: " + m.backingType + "\n" +
        "status: " + m.status;
      nodes.push(box(m.id, midLabel, "mid", COL.mid, my[i], midTip));

      // VIOS → Middle edge: label = "Slot <N>" (VIOS server-adapter slot from lshwres)
      edges.push(edge(m.v, m.id,
        "Slot " + m.viosSlot,
        "lshwres: slot_num=" + m.viosSlot + "\nlsmap: vhost=" + m.vhost + "\nJoin key: svr_slot=" + m.viosSlot));

      // Middle → Client edge: label = "Slot C<N>" (client slot in CXX format)
      edges.push(edge(m.id, m.c,
        "Slot C" + m.clientSlot,
        "lshwres: remote_slot_num=" + m.clientSlot + "\nClient adapter slot: C" + m.clientSlot +
        "\nvtd: " + m.vtd + "\nstatus: " + m.status));
    });

    // Right column — Client LPAR nodes
    const cy = rows(cDefs.length, 170);
    cDefs.forEach((c, i) => {
      nodes.push(box(c.id, "<b>" + c.n + "</b>\nLPAR ID " + c.lid, "client", COL.right, cy[i],
        "Client LPAR: " + c.n + "\nLPAR ID: " + c.lid + "\nStorage: vSCSI"));
    });

    return { nodes: nodes, edges: edges };
  }

  function vscsiData_A() {
    /*
     * Simulated lshwres -r virtualio --rsubtype scsi output (Server-9080-HEX-SN78ABCDE):
     *
     *   lpar_name  slot_num  remote_lpar_name   remote_slot_num
     *   vios1a        2      aix-db-prod             10
     *   vios2a        2      aix-db-prod             11
     *   vios1a        3      aix-app-prod            10
     *   vios2a        3      aix-app-prod            11
     *   vios1a        4      aix-nim-01              12
     *
     * Simulated lsmap -all -fmt , output per VIOS (viosvrcmd):
     *   vios1a:
     *     vhost0,slot=2,vtscsi0,hdisk10,physvol,Available
     *     vhost1,slot=3,vtscsi1,lv_app_rootvg,lvol,Available
     *     vhost2,slot=4,vtopt0,hdisk7,physvol,Defined
     *   vios2a:
     *     vhost0,slot=2,vtscsi0,lu_db_01,ssp_lu,Available
     *     vhost1,slot=3,vtscsi1,lu_app_02,ssp_lu,Available
     *
     * JOIN:  lshwres.slot_num == lsmap.slot
     *   vios1a slot 2  →  vhost0  / hdisk10      →  aix-db-prod   (C10)
     *   vios2a slot 2  →  vhost0  / lu_db_01     →  aix-db-prod   (C11)
     *   vios1a slot 3  →  vhost1  / lv_app_rootvg→  aix-app-prod  (C10)
     *   vios2a slot 3  →  vhost1  / lu_app_02    →  aix-app-prod  (C11)
     *   vios1a slot 4  →  vhost2  / hdisk7        →  aix-nim-01    (C12)
     */
    const viosDefs = [
      { id: "v1", label: "VIOS1", sub: "ID 1 · vios1a", tip: "Partition: vios1a\nLPAR ID: 1\nState: Running\nRMC: active" },
      { id: "v2", label: "VIOS2", sub: "ID 2 · vios2a", tip: "Partition: vios2a\nLPAR ID: 2\nState: Running\nRMC: active" },
    ];
    const midDefs = [
      { id: "m1", v: "v1", viosName: "vios1a", viosSlot: 2,  vhost: "vhost0", vtd: "vtscsi0", backing: "hdisk10",       backingType: "Physical Volume",   c: "c1", clientName: "aix-db-prod",  clientSlot: 10, status: "Available" },
      { id: "m2", v: "v2", viosName: "vios2a", viosSlot: 2,  vhost: "vhost0", vtd: "vtscsi0", backing: "lu_db_01",      backingType: "SSP Logical Unit",  c: "c1", clientName: "aix-db-prod",  clientSlot: 11, status: "Available" },
      { id: "m3", v: "v1", viosName: "vios1a", viosSlot: 3,  vhost: "vhost1", vtd: "vtscsi1", backing: "lv_app_rootvg", backingType: "Logical Volume",    c: "c2", clientName: "aix-app-prod", clientSlot: 10, status: "Available" },
      { id: "m4", v: "v2", viosName: "vios2a", viosSlot: 3,  vhost: "vhost1", vtd: "vtscsi1", backing: "lu_app_02",     backingType: "SSP Logical Unit",  c: "c2", clientName: "aix-app-prod", clientSlot: 11, status: "Available" },
      { id: "m5", v: "v1", viosName: "vios1a", viosSlot: 4,  vhost: "vhost2", vtd: "vtopt0",  backing: "hdisk7",        backingType: "Physical Volume",   c: "c3", clientName: "aix-nim-01",   clientSlot: 12, status: "Defined"   },
    ];
    const cDefs = [
      { id: "c1", n: "aix-db-prod",  lid: 11 },
      { id: "c2", n: "aix-app-prod", lid: 12 },
      { id: "c3", n: "aix-nim-01",   lid: 14 },
    ];
    return _buildVscsiGraph(viosDefs, midDefs, cDefs);
  }

  function vscsiData_B() {
    /*
     * Simulated lshwres -r virtualio --rsubtype scsi output (Server-9040-MR9-SN10FGHIJ):
     *
     *   lpar_name  slot_num  remote_lpar_name   remote_slot_num
     *   vio1          2      aix-erp-01              10
     *   vio1          3      aix-erp-02              10
     *
     * Simulated lsmap -all -fmt , output (viosvrcmd):
     *   vio1:
     *     vhost0,slot=2,vtscsi0,lv_rootvg_erp1,lvol,Available
     *     vhost1,slot=3,vtscsi1,hdisk9,physvol,Available
     *
     * JOIN:  lshwres.slot_num == lsmap.slot
     *   vio1 slot 2  →  vhost0  / lv_rootvg_erp1  →  aix-erp-01  (C10)
     *   vio1 slot 3  →  vhost1  / hdisk9           →  aix-erp-02  (C10)
     */
    const viosDefs = [
      { id: "v1", label: "VIOS1", sub: "ID 1 · vio1", tip: "Partition: vio1\nLPAR ID: 1\nState: Running\nRMC: active" },
    ];
    const midDefs = [
      { id: "m1", v: "v1", viosName: "vio1", viosSlot: 2, vhost: "vhost0", vtd: "vtscsi0", backing: "lv_rootvg_erp1", backingType: "Logical Volume",  c: "c1", clientName: "aix-erp-01", clientSlot: 10, status: "Available" },
      { id: "m2", v: "v1", viosName: "vio1", viosSlot: 3, vhost: "vhost1", vtd: "vtscsi1", backing: "hdisk9",         backingType: "Physical Volume", c: "c2", clientName: "aix-erp-02", clientSlot: 10, status: "Available" },
    ];
    const cDefs = [
      { id: "c1", n: "aix-erp-01", lid: 21 },
      { id: "c2", n: "aix-erp-02", lid: 22 },
    ];
    return _buildVscsiGraph(viosDefs, midDefs, cDefs);
  }

  /* ============================================================
     LIVE vSCSI BUILDER — from real lshwres / lsmap output
     Builds the VIOS → vSCSI Target → Client LPAR graph from
     the data returned by /api/.../vscsi-topology.

     Expected payload shape:
     {
       ok: true,
       scsi_adapters: [                 ← lshwres -r virtualio --rsubtype scsi
         { lpar_name, lpar_id, slot_num, remote_lpar_name, remote_lpar_id, remote_slot_num }, …
       ],
       lsmap: {                         ← viosvrcmd … lsmap -all -fmt ,
         "<vios_name>": [
           { vhost, svr_slot, vtd, backing, backing_type, status }, …
         ]
       }
     }

     JOIN KEY: scsi_adapters[i].slot_num  ==  lsmap[vios][j].svr_slot
  ============================================================ */
  function buildVscsiFromLive(payload) {
    const nodes = [], edges = [];
    const scsi   = (payload && payload.scsi_adapters) || [];
    const lsmap  = (payload && payload.lsmap)         || {};

    // Server (VIOS) rows only
    const serverRows = scsi.filter((r) => r.adapter_type === "server" || !r.adapter_type);

    // ---- VIOS nodes (left column) ----
    const viosNames = [];
    serverRows.forEach((r) => { if (r.lpar_name && viosNames.indexOf(r.lpar_name) < 0) viosNames.push(r.lpar_name); });
    (payload.vios || []).forEach((v) => { if (viosNames.indexOf(v) < 0) viosNames.push(v); });

    const viosIdOf = {};
    const vy = rows(Math.max(viosNames.length, 1), 200);
    viosNames.forEach((name, i) => {
      const id = "v" + i;
      viosIdOf[name] = id;
      nodes.push(box(id, "<b>" + name + "</b>\nVIO Server", "vios", COL.left, vy[i],
        "Partition: " + name + "\nRole: Virtual I/O Server"));
    });

    // ---- Client LPAR nodes (right column) ----
    const clientNames = [];
    serverRows.forEach((r) => { if (r.remote_lpar_name && clientNames.indexOf(r.remote_lpar_name) < 0) clientNames.push(r.remote_lpar_name); });

    const clientIdOf = {};
    const cy = rows(Math.max(clientNames.length, 1), 150);
    clientNames.forEach((name, i) => {
      const id = "c" + i;
      clientIdOf[name] = id;
      const sr = serverRows.find((r) => r.remote_lpar_name === name);
      nodes.push(box(id,
        "<b>" + name + "</b>" + (sr && sr.remote_lpar_id ? "\nLPAR ID " + sr.remote_lpar_id : ""),
        "client", COL.right, cy[i],
        "Client LPAR: " + name + (sr && sr.remote_lpar_id ? "\nLPAR ID: " + sr.remote_lpar_id : "") + "\nStorage: vSCSI"));
    });

    // ---- Middle nodes (one per server adapter row, enriched via lsmap) ----
    const midRowGap = serverRows.length > 10 ? 90 : 118;
    const midY = rows(Math.max(serverRows.length, 1), midRowGap);

    serverRows.forEach((r, i) => {
      const mid        = "m" + i;
      const viosNodeId = viosIdOf[r.lpar_name];
      const clientName = r.remote_lpar_name;
      const clientNodeId = clientName ? clientIdOf[clientName] : undefined;

      // JOIN: find the lsmap row for this VIOS whose svr_slot matches lshwres slot_num
      const vmaps = lsmap[r.lpar_name] || [];
      const match = r.slot_num
        ? vmaps.find((mp) => String(mp.svr_slot) === String(r.slot_num))
        : null;

      const vhost      = (match && match.vhost)        || ("vhost?");
      const vtd        = (match && match.vtd)          || "";
      const backing    = (match && match.backing)      || "unknown";
      const backType   = (match && match.backing_type) || "";
      const status     = (match && match.status)       || "";

      const viosSlot   = r.slot_num        || "?";
      const clientSlot = r.remote_slot_num || "?";

      // Middle label: "Slot <N> (vhostX)\nBacking: <device>"
      const midLabel = "<b>Slot " + viosSlot + " (" + vhost + ")</b>\nBacking: " + backing;
      const midTip =
        "━━ lshwres (scsi) ━━\n" +
        "VIOS: " + r.lpar_name + "\n" +
        "slot_num: " + viosSlot + "\n" +
        "remote_lpar_name: " + (clientName || "?") + "\n" +
        "remote_slot_num: " + clientSlot + "\n" +
        "━━ lsmap (join slot=" + viosSlot + ") ━━\n" +
        "vhost: " + vhost + "\n" +
        (vtd     ? "vtd: " + vtd + "\n"           : "") +
        "backing: " + backing + "\n" +
        (backType ? "type: " + backType + "\n"    : "") +
        (status   ? "status: " + status           : "");

      nodes.push(box(mid, midLabel, "mid", COL.mid, midY[i], midTip));

      // VIOS → Middle: "Slot <N>"
      if (viosNodeId) {
        edges.push(edge(viosNodeId, mid,
          "Slot " + viosSlot,
          "lshwres slot_num=" + viosSlot + "\nlsmap vhost=" + vhost));
      }

      // Middle → Client: "Slot C<N>"
      if (clientNodeId) {
        edges.push(edge(mid, clientNodeId,
          "Slot C" + clientSlot,
          "remote_slot_num=" + clientSlot + "\nClient adapter slot: C" + clientSlot +
          (vtd ? "\nvtd: " + vtd : "") +
          (status ? "\nstatus: " + status : "")));
      }
    });

    return { nodes: nodes, edges: edges };
  }

  /* ===== TAB 3 — Virtual Network (SEA Focus) =====
   *
   * Mock data faithfully simulates a 3-step data-join from real HMC/VIOS commands:
   *
   * STEP 1 — lshwres -r virtualio --rsubtype eth --level lpar
   *   Fields used: lpar_name, lpar_id, slot_num (client C-slot), adapter_type,
   *                vswitch, port_vlan_id (PVID), tagged_vlan_ids, is_trunk.
   *   Result: identifies ALL client LPARs with their Slot + PVID, AND the VIOS
   *           trunk adapter (adapter_type=server, is_trunk=1) which carries the
   *           vSwitch + trunk slot number.
   *
   * STEP 2 — viosvrcmd … lsdev  (filtered for "shared")
   *   Result: resolves the OS device name of the SEA on the VIOS,
   *           e.g. "ent5  Shared Ethernet Adapter  Available".
   *
   * STEP 3 — viosvrcmd … entstat -all <sea_device>
   *   Fields parsed: Real Adapter (backing EtherChannel/physical device),
   *                  Target Virtual Adapter Slot (VIOS trunk slot — join key
   *                  back to lshwres server-adapter slot_num),
   *                  Link Speed / status, bridged VLANs.
   *
   * JOIN KEY (Step 1 ↔ Step 3):
   *   lshwres server-adapter slot_num  ==  entstat "Target Virtual Adapter Slot"
   *   This resolves: which trunk slot on the VIOS feeds which SEA device.
   *
   * GRAPH LAYOUT — 3 columns (Left → Middle → Right):
   *
   *   LEFT    (-520)  Client LPARs  (from lshwres adapter_type=client)
   *   MIDDLE  (   0)  SEA Bridge node — one per SEA device discovered via lsdev/entstat
   *                   Label: "Slot <N> (ent5 — SEA)"   where <N> = trunk slot from lshwres
   *   RIGHT-A ( 380)  VIOS node  (the VIO Server that owns the SEA)
   *   RIGHT-B ( 760)  Physical Real Adapter node  (EtherChannel/hdisk from entstat)
   *
   * Client → SEA Bridge edge:  "Slot C<N>  (PVID <X>)"
   * SEA Bridge → VIOS edge:    "ent5 — SEA"
   * SEA Bridge → Physical edge:  "ent3 (EtherChannel)"  with speed from entstat
   */

  // Column X coordinates for the SEA topology (3+1 columns, left-to-right)
  const SCOL = { client: -520, sea: 0, vios: 380, phys: 760 };

  /*
   * Internal helper — builds the SEA graph from a normalised definition object.
   *
   * seaDef fields:
   *   viosName    – VIOS partition name (viosa51a)
   *   seaDevice   – OS device name of the SEA (ent5)      [lsdev Step 2]
   *   trunkSlot   – VIOS server-adapter slot_num          [lshwres Step 1 / entstat Step 3 join]
   *   vswitch     – virtual switch name                   [lshwres Step 1]
   *   realAdapter – backing physical/EtherChannel device  [entstat Step 3]
   *   linkSpeed   – link speed string                     [entstat Step 3]
   *   linkStatus  – Up / Down                             [entstat Step 3]
   *   physPorts   – physical port members                 [entstat Step 3]
   *   bridgedVlans– VLANs bridged by the SEA              [entstat Step 3]
   *
   * clientDefs fields (one entry per client LPAR):
   *   id          – node id
   *   name        – lpar_name
   *   lparId      – lpar_id
   *   clientSlot  – slot_num (CXX)                        [lshwres Step 1]
   *   pvid        – port_vlan_id                          [lshwres Step 1]
   *   vswitch     – vswitch                               [lshwres Step 1]
   */
  function _buildSeaGraph(seaDef, clientDefs) {
    const nodes = [], edges = [];

    // ── Left column: Client LPARs ──────────────────────────────────────────
    const ROW_GAP_CLIENT = 120;
    const cy = rows(clientDefs.length, ROW_GAP_CLIENT);
    clientDefs.forEach(function (c, i) {
      nodes.push(box(c.id,
        "<b>" + c.name + "</b>\nID " + c.lparId + " · Slot C" + c.clientSlot,
        "client",
        SCOL.client, cy[i],
        "━━ lshwres (eth) ━━\n" +
        "lpar_name: " + c.name + "\n" +
        "lpar_id: " + c.lparId + "\n" +
        "adapter_type: client\n" +
        "slot_num (CXX): C" + c.clientSlot + "\n" +
        "port_vlan_id (PVID): " + c.pvid + "\n" +
        "vswitch: " + c.vswitch
      ));
    });

    // ── Middle column: SEA Bridge node ─────────────────────────────────────
    // One node represents the virtual bridge discovered via entstat.
    // Label: "Slot <trunkSlot> (<seaDevice> — SEA)"
    // Position: vertically centred among all client LPARs.
    const seaNodeId = "sea_bridge";
    // Show Virtual Adapter name on the box if available and different from seaDevice
    const vaDisplay = (seaDef.virtualAdapter && seaDef.virtualAdapter !== "—" &&
                       seaDef.virtualAdapter !== seaDef.seaDevice)
      ? " · " + seaDef.virtualAdapter
      : "";
    nodes.push(box(seaNodeId,
      "<b>Slot " + seaDef.trunkSlot + " (" + seaDef.seaDevice + " \u2014 SEA)</b>\n" +
      (vaDisplay ? "Virtual Adapter: " + seaDef.virtualAdapter + "\n" : "") +
      "vSwitch: " + seaDef.vswitch + "\n" +
      "<i>VLANs: " + seaDef.bridgedVlans + "</i>",
      "mid",
      SCOL.sea, 0,
      "━━ lshwres (eth) server adapter ━━\n" +
      "adapter_type: server (trunk)\n" +
      "slot_num (trunk): " + seaDef.trunkSlot + "\n" +
      "vswitch: " + seaDef.vswitch + "\n" +
      "is_trunk: 1\n" +
      "addl_vlan_ids: " + seaDef.bridgedVlans + "\n\n" +
      "━━ lsdev | grep -i shared (Step 2) ━━\n" +
      "device: " + seaDef.seaDevice + "\n" +
      "description: Shared Ethernet Adapter\n\n" +
      "━━ entstat -all " + seaDef.seaDevice + " grep fields (Step 3) ━━\n" +
      "Real Adapter: " + seaDef.realAdapter + "\n" +
      "Virtual Adapter: " + (seaDef.virtualAdapter || seaDef.seaDevice) + "\n" +
      "Physical Port Link Status: " + seaDef.linkStatus + "\n" +
      (seaDef.logicalStatus && seaDef.logicalStatus !== "—"
        ? "Logical Port Link Status: " + seaDef.logicalStatus + "\n" : "") +
      "Physical Port Speed: " + seaDef.linkSpeed + "\n" +
      "Port VLAN ID: " + (seaDef.portVlan || seaDef.trunkSlot) + "\n" +
      "VLAN Tag IDs: " + (seaDef.vlanTagIds || seaDef.bridgedVlans)
    ));

    // Client LPAR → SEA Bridge edges
    clientDefs.forEach(function (c) {
      edges.push(edge(c.id, seaNodeId,
        "Slot C" + c.clientSlot + "\n(PVID " + c.pvid + ")",
        "━━ lshwres client adapter ━━\n" +
        "lpar_name: " + c.name + "\n" +
        "slot_num: C" + c.clientSlot + "\n" +
        "port_vlan_id (PVID): " + c.pvid + "\n" +
        "vswitch: " + c.vswitch + "\n" +
        "Frames tagged to SEA trunk slot " + seaDef.trunkSlot
      ));
    });

    // ── Right-A column: VIOS node ───────────────────────────────────────────
    const viosNodeId = "vios_node";
    nodes.push(box(viosNodeId,
      "<b>" + seaDef.viosName + "</b>\nVIO Server\n<i>hosts " + seaDef.seaDevice + "</i>",
      "vios",
      SCOL.vios, 0,
      "Partition: " + seaDef.viosName + "\n" +
      "Role: Virtual I/O Server\n" +
      "SEA device: " + seaDef.seaDevice + "\n" +
      "Trunk slot: " + seaDef.trunkSlot + "\n" +
      "vSwitch: " + seaDef.vswitch
    ));

    // SEA Bridge → VIOS edge
    edges.push(edge(seaNodeId, viosNodeId,
      seaDef.seaDevice + " \u2014 SEA",
      "SEA device " + seaDef.seaDevice + " owned by VIOS " + seaDef.viosName + "\n" +
      "Discovered via: viosvrcmd lsdev (Step 2)\n" +
      "State: Available"
    ));

    // ── Right-B column: Physical Real Adapter node ─────────────────────────

    // Color-code the node border and add a plain-text status indicator on the label.
    // vis.js HTML multi-mode does not support <font color> — use node border color instead.
    const physNodeId = "phys_node";
    const statusText = (seaDef.linkStatus || "").trim();
    const statusUpper = statusText.toUpperCase();
    // Status indicator: use Unicode thick arrows + colored node border.
    // vis.js does not support per-character color in labels, so we:
    //   • show ▲ UP (green border) or ▼ DOWN (red border) in the label
    //   • color the node border to reinforce the status visually
    let statusArrow, physBorderColor, physBgColor, physFontColor;
    if (statusUpper === "UP" || statusUpper.startsWith("UP")) {
      statusArrow    = "\u25b2 UP";          // ▲ UP
      physBorderColor = "#16a34a";           // green-600 border
      physBgColor     = "#f0fdf4";           // green-50 background tint
      physFontColor   = "#166534";           // green-800 text
    } else if (statusUpper === "DOWN" || statusUpper.startsWith("DOWN")) {
      statusArrow    = "\u25bc DOWN";        // ▼ DOWN
      physBorderColor = "#dc2626";           // red-600 border
      physBgColor     = "#fef2f2";           // red-50 background tint
      physFontColor   = "#991b1b";           // red-800 text
    } else if (statusText && statusText !== "—") {
      statusArrow    = "\u25cf " + statusText;
      physBorderColor = "#7c3aed";           // default phys violet
      physBgColor     = C.phys.bg;
      physFontColor   = C.phys.font;
    } else {
      statusArrow    = "\u25cf \u2014";
      physBorderColor = "#7c3aed";
      physBgColor     = C.phys.bg;
      physFontColor   = C.phys.font;
    }
    const physNodeObj = box(physNodeId,
      "<b>" + seaDef.realAdapter + "</b>\nEtherChannel / Physical\n" + statusArrow + "\n<i>" + seaDef.linkSpeed + "</i>",
      "phys",
      SCOL.phys, 0,
      "━━ entstat -all " + seaDef.seaDevice + " (Step 3) ━━\n" +
      "Real Adapter: " + seaDef.realAdapter + "\n" +
      "Physical Ports: " + seaDef.physPorts + "\n" +
      "Link Status: " + seaDef.linkStatus + "\n" +
      "Link Speed: " + seaDef.linkSpeed + "\n" +
      "Bridged VLANs: " + seaDef.bridgedVlans
    );
    // Override colors with status-driven values
    physNodeObj.color = {
      background: physBgColor,
      border:     physBorderColor,
      highlight:  { background: physBgColor, border: physBorderColor },
    };
    physNodeObj.font  = { color: physFontColor, size: 13, face: "Inter, sans-serif", multi: "html", align: "center" };
    physNodeObj.borderWidth = 3;
    nodes.push(physNodeObj);

    // VIOS → Physical Real Adapter edge
    edges.push(edge(viosNodeId, physNodeId,
      seaDef.realAdapter + "\n(Real Adapter)",
      "━━ entstat -all " + seaDef.seaDevice + " (Step 3) ━━\n" +
      "Real Adapter: " + seaDef.realAdapter + "\n" +
      "Physical Ports: " + seaDef.physPorts + "\n" +
      "Link Status: " + seaDef.linkStatus + "\n" +
      "Link Speed: " + seaDef.linkSpeed
    ));

    return { nodes: nodes, edges: edges };
  }

  function vnetData_A() {
    /*
     * Simulated output for Server-9105-22A-7892A51 / viosa51a
     *
     * STEP 1  lshwres -r virtualio --rsubtype eth --level lpar -m "Server-9105-22A-7892A51"
     *   lpar_name=aix-db-prod,  lpar_id=11, slot_num=2, adapter_type=client, vswitch=DefaultSwitch, port_vlan_id=100
     *   lpar_name=aix-app-prod, lpar_id=12, slot_num=2, adapter_type=client, vswitch=DefaultSwitch, port_vlan_id=100
     *   lpar_name=linux-web01,  lpar_id=13, slot_num=2, adapter_type=client, vswitch=DefaultSwitch, port_vlan_id=200
     *   lpar_name=aix-nim-01,   lpar_id=14, slot_num=2, adapter_type=client, vswitch=DefaultSwitch, port_vlan_id=200
     *   lpar_name=viosa51a,     lpar_id=1,  slot_num=20, adapter_type=server, vswitch=DefaultSwitch, is_trunk=1, tagged_vlan_ids=100,200
     *
     * STEP 2  viosvrcmd … lsdev | grep -i shared
     *   ent5   Shared Ethernet Adapter   Available
     *
     * STEP 3  viosvrcmd … entstat -all ent5
     *   Real Adapter: ent3  (EtherChannel)
     *   Target Virtual Adapter Slot: 20        ← JOIN KEY back to lshwres slot_num=20
     *   Link Speed: 20000 Mb/s (2×10GbE LACP)
     *   Link Status: Up
     *   Physical Ports: ent0, ent1
     *   VLANs bridged: 100, 200
     *
     * JOIN: lshwres slot_num=20 (server/trunk)  ==  entstat Slot 20  → SEA = ent5
     */
    const seaDef = {
      viosName:     "viosa51a",
      seaDevice:    "ent5",
      trunkSlot:    20,
      vswitch:      "DefaultSwitch",
      realAdapter:  "ent3",
      linkSpeed:    "20 Gbps (2\u00d710GbE LACP)",
      linkStatus:   "Up",
      physPorts:    "ent0, ent1",
      bridgedVlans: "100, 200",
    };
    const clientDefs = [
      { id: "c1", name: "aix-db-prod",  lparId: 11, clientSlot: 2, pvid: 100, vswitch: "DefaultSwitch" },
      { id: "c2", name: "aix-app-prod", lparId: 12, clientSlot: 2, pvid: 100, vswitch: "DefaultSwitch" },
      { id: "c3", name: "linux-web01",  lparId: 13, clientSlot: 2, pvid: 200, vswitch: "DefaultSwitch" },
      { id: "c4", name: "aix-nim-01",   lparId: 14, clientSlot: 2, pvid: 200, vswitch: "DefaultSwitch" },
    ];
    return _buildSeaGraph(seaDef, clientDefs);
  }

  function vnetData_B() {
    /*
     * Simulated output for Server-9040-MR9-SN10FGHIJ / vio1
     *
     * STEP 1  lshwres -r virtualio --rsubtype eth --level lpar -m "Server-9040-MR9-SN10FGHIJ"
     *   lpar_name=aix-erp-01,  lpar_id=21, slot_num=2, adapter_type=client, vswitch=DefaultSwitch, port_vlan_id=300
     *   lpar_name=aix-erp-02,  lpar_id=22, slot_num=2, adapter_type=client, vswitch=DefaultSwitch, port_vlan_id=300
     *   lpar_name=aix-mgmt-01, lpar_id=23, slot_num=2, adapter_type=client, vswitch=MgmtSwitch,    port_vlan_id=999
     *   lpar_name=vio1,         lpar_id=1, slot_num=15, adapter_type=server, vswitch=DefaultSwitch, is_trunk=1, tagged_vlan_ids=300
     *   lpar_name=vio1,         lpar_id=1, slot_num=16, adapter_type=server, vswitch=MgmtSwitch,   is_trunk=1, tagged_vlan_ids=999
     *
     * STEP 2  viosvrcmd … lsdev | grep -i shared
     *   ent4   Shared Ethernet Adapter   Available
     *   ent6   Shared Ethernet Adapter   Available
     *
     * STEP 3  viosvrcmd … entstat -all ent4
     *   Real Adapter: ent0
     *   Target Virtual Adapter Slot: 15
     *   Link Speed: 10 Gbps
     *   Physical Ports: ent0
     *   VLANs bridged: 300
     *
     * (For simplicity this demo shows the primary SEA ent4 serving VLAN 300/999
     *  via a single real adapter — real deployments would show two SEA entries.)
     *
     * JOIN: lshwres slot_num=15 (server/trunk)  ==  entstat Slot 15  → SEA = ent4
     */
    const seaDef = {
      viosName:     "vio1",
      seaDevice:    "ent4",
      trunkSlot:    15,
      vswitch:      "DefaultSwitch",
      realAdapter:  "ent0",
      linkSpeed:    "10 Gbps",
      linkStatus:   "Up",
      physPorts:    "ent0",
      bridgedVlans: "300, 999",
    };
    const clientDefs = [
      { id: "c1", name: "aix-erp-01",  lparId: 21, clientSlot: 2, pvid: 300, vswitch: "DefaultSwitch" },
      { id: "c2", name: "aix-erp-02",  lparId: 22, clientSlot: 2, pvid: 300, vswitch: "DefaultSwitch" },
      { id: "c3", name: "aix-mgmt-01", lparId: 23, clientSlot: 2, pvid: 999, vswitch: "MgmtSwitch"    },
    ];
    return _buildSeaGraph(seaDef, clientDefs);
  }

  /* ============================================================
     LIVE NPIV BUILDER — from real lshwres / lsmap output
     Builds the VIOS → vFC Mapping → Client LPAR graph out of the
     data returned by /api/.../vfc-topology.
  ============================================================ */
  function buildNpivFromLive(payload) {
    const nodes = [], edges = [];
    const fc = (payload && payload.fc_adapters) || [];
    const lsmap = (payload && payload.lsmap) || {};

    // Group server (VIOS) adapters and client adapters
    const serverRows = fc.filter((r) => r.adapter_type === "server");
    const clientRows = fc.filter((r) => r.adapter_type === "client");

    // ---- VIOS nodes (left column) ----
    const viosNames = [];
    serverRows.forEach((r) => { if (r.lpar_name && viosNames.indexOf(r.lpar_name) < 0) viosNames.push(r.lpar_name); });
    (payload.vios || []).forEach((v) => { if (viosNames.indexOf(v) < 0) viosNames.push(v); });

    const viosIdOf = {};
    const vy = rows(Math.max(viosNames.length, 1), 200);
    viosNames.forEach((name, i) => {
      const id = "v" + i;
      viosIdOf[name] = id;
      nodes.push(box(id, "<b>" + name + "</b>\nVIO Server", "vios", COL.left, vy[i],
        "Partition: " + name + "\nRole: Virtual I/O Server"));
    });

    // ---- Client LPAR nodes (right column) ----
    const clientNames = [];
    clientRows.forEach((r) => { if (r.lpar_name && clientNames.indexOf(r.lpar_name) < 0) clientNames.push(r.lpar_name); });
    // Also pick up client names discovered from lsmap.
    // Trim clntname to guard against space-only values (e.g. " " returned for
    // NOT_LOGGED_IN entries) which are truthy in JS but represent no client.
    Object.keys(lsmap).forEach((v) => (lsmap[v] || []).forEach((m) => {
      const cname = (m.clntname || "").trim();
      if (cname && clientNames.indexOf(cname) < 0) clientNames.push(cname);
    }));

    const clientIdOf = {};
    const cy = rows(Math.max(clientNames.length, 1), 150);
    clientNames.forEach((name, i) => {
      const id = "c" + i;
      clientIdOf[name] = id;
      const cr = clientRows.find((r) => r.lpar_name === name);
      nodes.push(box(id, "<b>" + name + "</b>" + (cr && cr.lpar_id ? "\nLPAR ID " + cr.lpar_id : ""), "client", COL.right, cy[i],
        "Client LPAR: " + name + (cr && cr.lpar_id ? "\nLPAR ID: " + cr.lpar_id : "") + "\nBoot: SAN (NPIV)"));
    });

    // ---- Sort serverRows to minimise edge crossings ----
    // Primary sort: VIOS name order (preserves left-column sequence).
    // Secondary sort: client LPAR name (groups all connections to the same
    // client together so edges from one VIOS fan out without crossing).
    const viosOrder = {};
    viosNames.forEach((n, i) => { viosOrder[n] = i; });
    serverRows.sort((a, b) => {
      const vd = (viosOrder[a.lpar_name] || 0) - (viosOrder[b.lpar_name] || 0);
      if (vd !== 0) return vd;
      return (a.remote_lpar_name || "").localeCompare(b.remote_lpar_name || "");
    });

    // Re-derive clientNames in the order they first appear in the sorted
    // serverRows so the right column aligns with the middle column.
    const clientNamesSorted = [];
    serverRows.forEach((r) => {
      if (r.remote_lpar_name && clientNamesSorted.indexOf(r.remote_lpar_name) < 0)
        clientNamesSorted.push(r.remote_lpar_name);
    });
    // Append any remaining client names not referenced by a server row.
    clientNames.forEach((n) => { if (clientNamesSorted.indexOf(n) < 0) clientNamesSorted.push(n); });

    // Update clientIdOf with re-ordered positions.
    const clientIdOfSorted = {};
    const cySorted = rows(Math.max(clientNamesSorted.length, 1), 150);
    // Rebuild client nodes with sorted y positions.
    // Remove the previously added client nodes and re-add with correct y.
    clientNamesSorted.forEach((name, i) => {
      const id = clientIdOf[name] || ("c" + i);
      clientIdOfSorted[name] = id;
      // Update position of existing node.
      const existingIdx = nodes.findIndex((n) => n.id === id);
      if (existingIdx >= 0) nodes[existingIdx].y = cySorted[i];
    });
    // Patch clientIdOf so mid-node creation uses the right IDs.
    clientNamesSorted.forEach((name) => { clientIdOf[name] = clientIdOfSorted[name]; });

    // ---- Build a lsmap lookup by (vios, vfchost/clntname) for enrichment ----
    // Index lsmap rows by VIOS name for vfchost/fcs matching.
    // ---- vFC Mapping nodes (middle) — one per server adapter ----
    // Use tighter row gap for large sets to keep graph compact.
    const midRowGap = serverRows.length > 10 ? 90 : 118;
    const midY = rows(Math.max(serverRows.length, 1), midRowGap);
    serverRows.forEach((r, i) => {
      const mid = "m" + i;
      const viosNodeId = viosIdOf[r.lpar_name];
      const clientName = r.remote_lpar_name;
      const clientNodeId = clientName ? clientIdOf[clientName] : undefined;

      // Enrich with lsmap data on this VIOS. Each vfchost is uniquely
      // identified by the VIOS server-adapter slot number: the lshwres
      // server adapter `slot_num` equals the "-C" slot in the vfchost's
      // physloc reported by lsmap. Match STRICTLY on that slot so every
      // mapping gets its own distinct vfchost (never a shared/first row).
      let vfchost = "", fcs = "", fcloc = "", status = "";
      let clientSlotMap = "";
      const vmaps = lsmap[r.lpar_name] || [];
      let match = null;
      if (r.slot_num) {
        match = vmaps.find((mp) => String(mp.vios_slot) === String(r.slot_num));
      }
      // Only if the VIOS slot is unavailable do we fall back to matching by
      // the unique client id + client slot pair.
      if (!match && r.remote_lpar_id && r.remote_slot_num) {
        match = vmaps.find((mp) =>
          String(mp.clntid) === String(r.remote_lpar_id) &&
          String(mp.client_slot) === String(r.remote_slot_num));
      }
      let vfcclient = "";
      if (match) {
        vfchost = match.vfchost || "";
        fcs = match.fc || "";
        fcloc = match.fcphysloc || "";
        status = match.status || "";
        clientSlotMap = match.client_slot || "";  // slot num after "-C" of client physloc
        vfcclient = match.vfcclient || "";        // client LPAR logical FC adapter (fcsX)
      }

      // The VIOS slot is authoritative from lshwres (the server adapter slot).
      // The client slot comes from lshwres remote_slot_num, or the lsmap "-C".
      const viosSlot = r.slot_num || "?";
      const clientSlot = r.remote_slot_num || clientSlotMap || "?";


      // Prefer the wwpns from the client LPAR's own adapter row (adapter_type=client,
      // lpar_name == clientName); fall back to the server adapter row's wwpns field
      // which also carries the NPIV WWPN(s) assigned to the client.
      const clientRow = clientName ? clientRows.find((cr) => cr.lpar_name === clientName &&
        (r.remote_slot_num ? String(cr.slot_num) === String(r.remote_slot_num) : true)) : null;
      const wwpns = ((clientRow && clientRow.wwpns) || r.wwpns || "").replace(/\s+/g, "");
      const midLabel = "<b>" + (vfchost || "vFC slot " + viosSlot) + "</b>" +
        (fcs ? "\n" + fcs + " · fabric" : "") +
        (fcloc ? "\n<i>" + fcloc + "</i>" : "");
      nodes.push(box(mid, midLabel, "mid", COL.mid, midY[i],
        "adapter_type=server\nVIOS: " + r.lpar_name +
        (vfchost ? "\nVirtual FC Host: " + vfchost : "") +
        "\nVIOS slot (‑C): " + viosSlot +
        (fcs ? "\nBacking port: " + fcs : "") +
        (fcloc ? "\nPhysical loc: " + fcloc : "") +
        (status ? "\nStatus: " + status : "") +
        "\nremote_lpar=" + (r.remote_lpar_name || "?") +
        "\nClient LPAR slot (‑C): " + clientSlot));

      if (viosNodeId) {
        edges.push(edge(viosNodeId, mid, "VIOS slot " + viosSlot,
          "VIOS " + r.lpar_name + "\nadapter_type=server\nVIOS slot (from vfchost -C): " + viosSlot +
          (vfchost ? "\nvfchost: " + vfchost : "")));
      }
      if (clientNodeId) {
        edges.push(edge(mid, clientNodeId,
          "LPAR slot " + clientSlot +
          (vfcclient ? "\n" + vfcclient : "") +
          (wwpns ? "\nWWPN " + wwpns : ""),
          "remote_lpar_id=" + (r.remote_lpar_id || "?") +
          "\nClient LPAR slot (from client -C): " + clientSlot +
          (vfcclient ? "\nClient FC adapter: " + vfcclient : "") +
          (wwpns ? "\nWWPN: " + wwpns : "")));
      }

    });

    return { nodes: nodes, edges: edges };
  }

  /* ============================================================
     COMMAND OUTPUT PANEL — renders raw HMC command results
  ============================================================ */
  function escapeHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function renderCommandPanel(commands) {
    const panel = document.getElementById("cmd-output-panel");
    const body = document.getElementById("cmd-output-body");
    const statusEl = document.getElementById("cmd-status");
    if (!panel || !body) return;

    if (!commands || !commands.length) {
      panel.classList.add("hidden");
      body.innerHTML = "";
      return;
    }

    const okCount = commands.filter((c) => c.ok).length;
    statusEl.textContent = "· " + okCount + "/" + commands.length + " command(s) succeeded";

    body.innerHTML = commands.map((c) => {
      const badge = c.ok
        ? '<span style="color:#16a34a;font-weight:600;">✓ ok</span>'
        : '<span style="color:#dc2626;font-weight:600;">✕ failed</span>';
      // Inline all critical styles on pre.cmd-out so they cannot be overridden by
      // any outer stylesheet cascade (Tailwind base resets, etc.).
      return '<div style="border:1px solid #e2e8f0;border-radius:.5rem;margin-bottom:0;">' +
        '<div style="display:flex;align-items:center;gap:.5rem;padding:.4rem .75rem;font-size:12px;font-weight:600;background:#f8fafc;border-bottom:1px solid #e2e8f0;color:#334155;border-radius:.5rem .5rem 0 0;">' +
        '<span style="color:#64748b;">›</span> ' +
        escapeHtml(c.title) + " " + badge + "</div>" +
        '<div style="font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11.5px;color:#0f172a;background:#eef2ff;padding:.35rem .75rem;white-space:pre-wrap;word-break:break-all;border-bottom:1px solid #e2e8f0;">' +
        '# ' + escapeHtml(c.command) + "</div>" +
        '<pre style="margin:0;padding:.6rem .75rem;min-height:80px;max-height:320px;overflow-y:scroll;overflow-x:auto;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11.5px;line-height:1.5;background:#0b1020 !important;color:#d1fae5 !important;white-space:pre;border-radius:0 0 .5rem .5rem;display:block;width:100%;box-sizing:border-box;tab-size:4;">' + escapeHtml(c.output) + "</pre>" +
        "</div>";
    }).join("");

    panel.classList.remove("hidden");
    if (window.lucide) lucide.createIcons();
  }

  function hideCommandPanel() {
    const panel = document.getElementById("cmd-output-panel");
    if (panel) panel.classList.add("hidden");
  }

  // Cache of live payloads keyed by "hmcId::systemId"
  const LIVE_NPIV  = {};
  const LIVE_VSCSI = {};
  const LIVE_VNET  = {};

  /* ===== populate registry ===== */
  DATA["Server-9080-HEX-SN78ABCDE"] = { npiv: npivData_A(), vscsi: vscsiData_A(), vnet: vnetData_A() };
  DATA["Server-9040-MR9-SN10FGHIJ"] = { npiv: npivData_B(), vscsi: vscsiData_B(), vnet: vnetData_B() };


  /* ============================================================
     RENDERING ENGINE
  ============================================================ */
  const VIS_OPTIONS = {
    physics: false,
    interaction: { hover: true, tooltipDelay: 120, dragNodes: true, dragView: true, zoomView: true, navigationButtons: false },
    nodes: { shadow: { enabled: true, size: 6, x: 0, y: 2, color: "rgba(15,23,42,0.12)" } },
    edges: { selectionWidth: 2 },
  };

  const FLOW_LABELS = {
    npiv: "VIOS  →  Virtual FC Mapping  →  Client LPAR",
    vscsi: "VIOS  →  Virtual SCSI Target  →  Client LPAR",
    vnet: "Client LPAR  →  vSwitch / VLAN  →  VIOS (SEA)  →  Physical Network",
  };

  const LEGENDS = {
    npiv: [["vios", "VIOS"], ["mid", "vFC Mapping"], ["client", "Client LPAR"]],
    vscsi: [["vios", "VIOS"], ["mid", "vSCSI Target"], ["client", "Client LPAR"]],
    vnet: [["client", "Client LPAR"], ["vlan", "VLAN / vSwitch"], ["vios", "VIOS (SEA)"], ["phys", "Physical"]],
  };

  const NET = { npiv: null, vscsi: null, vnet: null };
  let currentTab = "npiv";

  // Demo datasets used as a fallback when the selected managed system has
  // no pre-built topology in DATA (i.e. a real system pulled from the HMC).
  const DEMO_KEYS = Object.keys(DATA);
  let demoIndex = 0;

  function currentMS() { return document.getElementById("ms-selector").value; }
  function setStatus(msg) { document.getElementById("status-bar").textContent = msg; }

  function liveKey() { return (localHMCId || "") + "::" + currentMS(); }

  // Resolve the dataset for the current managed system. If the exact system
  // isn't in DATA, round-robin over the demo datasets so real HMC systems
  // still render a representative topology.
  function datasetFor(tab) {
    const ms = currentMS();
    // Live graph built from real HMC output takes precedence over mock data.
    if (tab === "npiv") {
      const live = LIVE_NPIV[liveKey()];
      if (live && live.graph) return live.graph;
    }
    if (tab === "vscsi") {
      const live = LIVE_VSCSI[liveKey()];
      if (live && live.graph) return live.graph;
    }
    if (tab === "vnet") {
      const live = LIVE_VNET[liveKey()];
      if (live && live.graph) return live.graph;
    }
    if (ms && DATA[ms]) return DATA[ms][tab];
    const key = DEMO_KEYS[demoIndex % DEMO_KEYS.length];
    return DATA[key][tab];
  }

  /* ============================================================
     LIVE Virtual Network (SEA) BUILDER  — multi-SEA edition
     Builds the Client LPAR → SEA Bridge → VIOS → Physical graph
     from the data returned by /api/.../vnet-topology.

     All SEA devices returned by lsdev are rendered — one SEA Bridge
     node per (viosName, seaDevice) pair.  Client LPARs are connected
     to every SEA whose vswitch matches or whose bridged VLANs include
     the client's PVID.

     Payload shape:
     {
       ok: true,
       vios: ["viosa51a", …],
       eth_adapters: [                 ← lshwres --rsubtype eth
         { lpar_name, lpar_id, slot_num, adapter_type, vswitch,
           port_vlan_id, tagged_vlan_ids, is_trunk, trunk_priority }, …
       ],
       sea_devices: {                  ← lsdev (Step 2)
         "viosa51a": ["ent5"], …
       },
       entstat: {                      ← entstat -all (Step 3)
         "viosa51a::ent5": {
           real_adapter, trunk_slot, link_speed, link_status,
           phys_ports, bridged_vlans, virtual_adapter, port_vlan,
           vlan_tag_ids, phys_speed, phys_link, logical_link
         }, …
       }
     }

     JOIN KEY (Step 1 ↔ Step 3):
       eth_adapters[trunk row].slot_num  ==  entstat.trunk_slot
  ============================================================ */
  function buildVnetFromLive(payload) {
    var nodes = [], edges = [];
    var ethAdapters = (payload && payload.eth_adapters) || [];
    var seaDevices  = (payload && payload.sea_devices)  || {};
    var entstat     = (payload && payload.entstat)      || {};

    // ── Separate rows ────────────────────────────────────────────────────────
    var clientRows = ethAdapters.filter(function (r) {
      return r.adapter_type === "client";
    });

    var trunkRows = ethAdapters.filter(function (r) {
      return r.is_trunk === "1";
    });
    var serverRows = trunkRows.length > 0 ? trunkRows :
      ethAdapters.filter(function (r) { return r.adapter_type === "server"; });

    // ── Build SEA entries for ALL discovered SEA devices ────────────────────
    // seaEntries[i] = { viosName, seaDevice, trunkSlot, vswitch, realAdapter,
    //                   linkSpeed, linkStatus, logicalStatus, virtualAdapter,
    //                   portVlan, vlanTagIds, physPorts, bridgedVlans,
    //                   allBridgedVlans[] }
    var seaEntries = [];
    Object.keys(seaDevices).forEach(function (viosName) {
      var devList = seaDevices[viosName] || [];
      devList.forEach(function (dev) {
        var ekey = viosName + "::" + dev;
        var info = entstat[ekey] || {};

        // Best-match trunk row: prefer the one whose slot_num == info.trunk_slot
        var trunkRow = serverRows.find(function (r) {
          return r.lpar_name === viosName &&
            info.trunk_slot && String(r.slot_num) === String(info.trunk_slot);
        }) || serverRows.find(function (r) {
          return r.lpar_name === viosName;
        });

        var bridgedVlans = info.bridged_vlans ||
                           info.vlan_tag_ids   ||
                           (trunkRow && trunkRow.addl_vlan_ids) ||
                           (trunkRow && trunkRow.port_vlan_id)  || "—";

        // Collect all numeric VLAN IDs that this SEA bridges so we can route clients
        var allBridgedVlans = [];
        (bridgedVlans !== "—" ? bridgedVlans : "").split(/[\s,]+/).forEach(function (v) {
          var n = parseInt(v, 10);
          if (!isNaN(n)) allBridgedVlans.push(String(n));
        });
        // Also include port VLAN
        var portVlanStr = info.port_vlan || (trunkRow && trunkRow.port_vlan_id) || "";
        portVlanStr.split(/[\s,]+/).forEach(function (v) {
          var n = parseInt(v, 10);
          if (!isNaN(n) && allBridgedVlans.indexOf(String(n)) < 0) allBridgedVlans.push(String(n));
        });

        seaEntries.push({
          viosName:       viosName,
          seaDevice:      dev,
          trunkSlot:      info.trunk_slot  || (trunkRow && trunkRow.slot_num)  || "?",
          vswitch:        (trunkRow && trunkRow.vswitch) || "DefaultSwitch",
          realAdapter:    info.real_adapter   || "unknown",
          linkSpeed:      info.phys_speed     || info.link_speed   || "—",
          linkStatus:     info.phys_link      || info.link_status  || "—",
          logicalStatus:  info.logical_link   || "—",
          virtualAdapter: info.virtual_adapter || "—",
          portVlan:       info.port_vlan      || (trunkRow && trunkRow.port_vlan_id) || "—",
          vlanTagIds:     info.vlan_tag_ids   || "—",
          physPorts:      info.phys_ports     || "—",
          bridgedVlans:   bridgedVlans,
          allBridgedVlans: allBridgedVlans,
        });
      });
    });

    // If no SEA entries discovered, build a single placeholder so the graph
    // still renders with client LPARs visible.
    if (seaEntries.length === 0) {
      seaEntries.push({
        viosName:       (serverRows[0] && serverRows[0].lpar_name) || "VIOS",
        seaDevice:      "ent?",
        trunkSlot:      (serverRows[0] && serverRows[0].slot_num)  || "?",
        vswitch:        (serverRows[0] && serverRows[0].vswitch)   || "DefaultSwitch",
        realAdapter:    "unknown",
        linkSpeed:      "—", linkStatus: "—", logicalStatus: "—",
        virtualAdapter: "—", portVlan: "—", vlanTagIds: "—",
        physPorts:      "—",
        bridgedVlans:   (serverRows[0] && serverRows[0].addl_vlan_ids) || "—",
        allBridgedVlans: [],
      });
    }

    // ── Column X coordinates ─────────────────────────────────────────────────
    // client(-560) → sea_bridge(−140) → phys(+160)
    // SEA and Physical nodes are ~300px apart; group box wraps both.
    var MX = { client: -560, sea: -140, vios: 200, phys: 160 };

    // ── Deduplicate client LPARs ─────────────────────────────────────────────
    var seenClients = {};
    var uniqueClients = [];
    clientRows.forEach(function (r) {
      if (r.lpar_name && !seenClients[r.lpar_name]) {
        seenClients[r.lpar_name] = true;
        uniqueClients.push({
          id:         "vc_" + r.lpar_name.replace(/[^a-zA-Z0-9]/g, "_"),
          name:       r.lpar_name,
          lparId:     r.lpar_id      || "?",
          clientSlot: r.slot_num     || "?",
          pvid:       r.port_vlan_id || "?",
          vswitch:    r.vswitch      || "DefaultSwitch",
        });
      }
    });
    if (uniqueClients.length === 0) {
      uniqueClients.push({
        id: "vc_placeholder", name: "(no client LPARs found)", lparId: "—",
        clientSlot: "?", pvid: "?", vswitch: seaEntries[0].vswitch,
      });
    }

    // ── LEFT column: Client LPAR nodes ──────────────────────────────────────
    var clientGap = uniqueClients.length > 12 ? 90 : 120;
    var cy = rows(uniqueClients.length, clientGap);
    uniqueClients.forEach(function (c, i) {
      nodes.push(box(c.id,
        "<b>" + c.name + "</b>\nID " + c.lparId + " · Slot C" + c.clientSlot,
        "client",
        MX.client, cy[i],
        "━━ lshwres (eth) ━━\n" +
        "lpar_name: " + c.name + "\n" +
        "lpar_id: " + c.lparId + "\n" +
        "adapter_type: client\n" +
        "slot_num (CXX): C" + c.clientSlot + "\n" +
        "port_vlan_id (PVID): " + c.pvid + "\n" +
        "vswitch: " + c.vswitch
      ));
    });

    // ── Collect unique VIOS names (for group-box rendering) ─────────────────
    var viosNames = [];
    seaEntries.forEach(function (sea) {
      if (viosNames.indexOf(sea.viosName) < 0) viosNames.push(sea.viosName);
    });

    // ── Layout: place SEA + Physical nodes grouped per VIOS ─────────────────
    // Each VIOS gets a vertical band of rows. Within that band:
    //   • SEA bridge node(s) in the MIDDLE column (MX.sea)
    //   • Physical adapter node(s) in the RIGHT column (MX.phys)
    // The band is separated by a small gap between VIOS groups.
    var SEA_ROW_H  = 140;   // vertical pixels per row within a VIOS group
    var GROUP_PAD  = 30;    // extra padding above/below nodes inside the group box
    var GROUP_GAP  = 50;    // gap between two consecutive VIOS group boxes

    // Assign Y positions per VIOS group, stacking groups top-to-bottom.
    // viosGroupInfo[viosName] = { seaNodeIds[], physNodeIds[], startY, endY }
    var viosGroupInfo = {};
    var cursorY = 0;

    viosNames.forEach(function (vname, vi) {
      if (vi > 0) cursorY += GROUP_GAP;
      var seas  = seaEntries.filter(function (s) { return s.viosName === vname; });
      // Collect unique physical adapters for this VIOS
      var physKeys = [];
      seas.forEach(function (s) {
        var pk = vname + "::" + s.realAdapter;
        if (physKeys.indexOf(pk) < 0) physKeys.push(pk);
      });
      var nRows = Math.max(seas.length, physKeys.length);
      // Centre the group around cursorY
      var groupHeight = (nRows - 1) * SEA_ROW_H;
      var topY        = cursorY - groupHeight / 2;

      viosGroupInfo[vname] = {
        seaEntries:  seas,
        physKeys:    physKeys,
        seaNodeIds:  [],
        physNodeIds: [],
        topY:        topY,
        bottomY:     topY + groupHeight,
        nRows:       nRows,
      };
      cursorY += groupHeight / 2;
      // Next group starts below this one
      cursorY += groupHeight / 2;
    });

    // ── MIDDLE column: SEA Bridge nodes (one per discovered SEA) ────────────
    var seaNodeIds = {};

    viosNames.forEach(function (vname) {
      var grp = viosGroupInfo[vname];
      var seaRowYs = rows(grp.seaEntries.length, SEA_ROW_H);
      // Map seaRowYs relative to group centre
      var groupCentreY = (grp.topY + grp.bottomY) / 2;

      grp.seaEntries.forEach(function (sea, i) {
        var seaNodeId = "sea_" + vname.replace(/[^a-zA-Z0-9]/g, "_") + "_" + sea.seaDevice;
        seaNodeIds[vname + "::" + sea.seaDevice] = seaNodeId;
        grp.seaNodeIds.push(seaNodeId);

        var vaDisplay = (sea.virtualAdapter && sea.virtualAdapter !== "—" &&
                         sea.virtualAdapter !== sea.seaDevice)
          ? " · " + sea.virtualAdapter : "";

        var statusUpper = (sea.linkStatus || "").trim().toUpperCase();
        var statusArrow, seaBorderColor, seaBgColor, seaFontColor;
        if (statusUpper === "UP" || statusUpper.startsWith("UP")) {
          statusArrow    = "\u25b2 UP";
          seaBorderColor = "#94a3b8"; seaBgColor = C.mid.bg; seaFontColor = C.mid.font;
        } else if (statusUpper === "DOWN" || statusUpper.startsWith("DOWN")) {
          statusArrow    = "\u25bc DOWN";
          seaBorderColor = "#dc2626"; seaBgColor = "#fef2f2"; seaFontColor = "#991b1b";
        } else {
          statusArrow    = "";
          seaBorderColor = C.mid.border; seaBgColor = C.mid.bg; seaFontColor = C.mid.font;
        }

        // SEA label — no VIOS name (VIOS shown in the group box label instead)
        var seaLabel =
          "<b>Slot " + sea.trunkSlot + " (" + sea.seaDevice + " \u2014 SEA)</b>\n" +
          (vaDisplay ? "Virtual: " + sea.virtualAdapter + "\n" : "") +
          "vSwitch: " + sea.vswitch + "\n" +
          (statusArrow ? statusArrow + "  " : "") +
          "<i>VLANs: " + sea.bridgedVlans + "</i>";

        var seaTip =
          "━━ lshwres (eth) server adapter ━━\n" +
          "adapter_type: server (trunk)\n" +
          "VIOS: " + vname + "\n" +
          "slot_num (trunk): " + sea.trunkSlot + "\n" +
          "vswitch: " + sea.vswitch + "\n" +
          "is_trunk: 1\n" +
          "addl_vlan_ids: " + sea.bridgedVlans + "\n\n" +
          "━━ lsdev | grep -i shared (Step 2) ━━\n" +
          "device: " + sea.seaDevice + "\n" +
          "description: Shared Ethernet Adapter\n\n" +
          "━━ entstat -all " + sea.seaDevice + " grep fields (Step 3) ━━\n" +
          "Real Adapter: " + sea.realAdapter + "\n" +
          "Virtual Adapter: " + (sea.virtualAdapter !== "—" ? sea.virtualAdapter : sea.seaDevice) + "\n" +
          "Physical Port Link Status: " + sea.linkStatus + "\n" +
          (sea.logicalStatus !== "—" ? "Logical Port Link Status: " + sea.logicalStatus + "\n" : "") +
          "Physical Port Speed: " + sea.linkSpeed + "\n" +
          "Port VLAN ID: " + sea.portVlan + "\n" +
          "VLAN Tag IDs: " + sea.vlanTagIds;

        var nodeY = groupCentreY + seaRowYs[i];
        var seaNode = box(seaNodeId, seaLabel, "mid", MX.sea, nodeY, seaTip);
        seaNode.color = {
          background: seaBgColor, border: seaBorderColor,
          highlight: { background: seaBgColor, border: seaBorderColor },
        };
        seaNode.font = { color: seaFontColor, size: 13, face: "Inter, sans-serif", multi: "html", align: "center" };
        // Tag node with group membership so afterDrawing can find it
        seaNode._viosGroup = vname;
        nodes.push(seaNode);
      });
    });

    // ── RIGHT column: Physical Real Adapter nodes (deduplicated per VIOS+adapter) ─
    var physNodeIdOf = {};

    viosNames.forEach(function (vname) {
      var grp = viosGroupInfo[vname];
      var physRows = rows(grp.physKeys.length, SEA_ROW_H);
      var groupCentreY = (grp.topY + grp.bottomY) / 2;

      grp.physKeys.forEach(function (pkey, i) {
        // Find the SEA entry whose realAdapter matches this physKey
        var sea = seaEntries.find(function (s) { return (vname + "::" + s.realAdapter) === pkey; });
        if (!sea) return;

        var physNodeId = "phys_" + vname.replace(/[^a-zA-Z0-9]/g, "_") +
                         "_" + sea.realAdapter.replace(/[^a-zA-Z0-9]/g, "_");
        physNodeIdOf[pkey] = physNodeId;
        grp.physNodeIds.push(physNodeId);

        var statusText  = (sea.linkStatus || "").trim();
        var statusUpper = statusText.toUpperCase();
        var statusArrow, physBorderColor, physBgColor, physFontColor;
        if (statusUpper === "UP" || statusUpper.startsWith("UP")) {
          statusArrow     = "\u25b2 UP";
          physBorderColor = "#16a34a"; physBgColor = "#f0fdf4"; physFontColor = "#166534";
        } else if (statusUpper === "DOWN" || statusUpper.startsWith("DOWN")) {
          statusArrow     = "\u25bc DOWN";
          physBorderColor = "#dc2626"; physBgColor = "#fef2f2"; physFontColor = "#991b1b";
        } else {
          statusArrow     = "\u25cf \u2014";
          physBorderColor = "#7c3aed"; physBgColor = C.phys.bg; physFontColor = C.phys.font;
        }

        var nodeY = groupCentreY + physRows[i];
        var physNode = box(physNodeId,
          "<b>" + sea.realAdapter + "</b>\nEtherChannel / Physical\n" + statusArrow + "\n<i>" + sea.linkSpeed + "</i>",
          "phys",
          MX.phys, nodeY,
          "━━ entstat -all " + sea.seaDevice + " (Step 3) ━━\n" +
          "Real Adapter: " + sea.realAdapter + "\n" +
          "Physical Ports: " + sea.physPorts + "\n" +
          "Link Status: " + sea.linkStatus + "\n" +
          "Link Speed: " + sea.linkSpeed + "\n" +
          "Bridged VLANs: " + sea.bridgedVlans
        );
        physNode.color = {
          background: physBgColor, border: physBorderColor,
          highlight: { background: physBgColor, border: physBorderColor },
        };
        physNode.font = { color: physFontColor, size: 13, face: "Inter, sans-serif", multi: "html", align: "center" };
        physNode.borderWidth = 3;
        // Tag node with group membership
        physNode._viosGroup = vname;
        nodes.push(physNode);
      });
    });

    // ── EDGES ────────────────────────────────────────────────────────────────

    // Helper: check whether a client LPAR should connect to a given SEA.
    function clientMatchesSea(client, sea) {
      if (client.vswitch !== sea.vswitch) return false;
      if (sea.allBridgedVlans.length === 0) return true;
      return sea.allBridgedVlans.indexOf(String(client.pvid)) >= 0;
    }

    // Client LPAR → SEA Bridge edges
    uniqueClients.forEach(function (c) {
      var connected = false;
      seaEntries.forEach(function (sea) {
        var seaNodeId = seaNodeIds[sea.viosName + "::" + sea.seaDevice];
        if (clientMatchesSea(c, sea)) {
          edges.push(edge(c.id, seaNodeId,
            "Slot C" + c.clientSlot + "\n(PVID " + c.pvid + ")",
            "━━ lshwres client adapter ━━\n" +
            "lpar_name: " + c.name + "\n" +
            "slot_num: C" + c.clientSlot + "\n" +
            "port_vlan_id (PVID): " + c.pvid + "\n" +
            "vswitch: " + c.vswitch + "\n" +
            "Frames tagged to SEA trunk slot " + sea.trunkSlot
          ));
          connected = true;
        }
      });
      if (!connected) {
        seaEntries.forEach(function (sea) {
          if (c.vswitch === sea.vswitch) {
            var seaNodeId = seaNodeIds[sea.viosName + "::" + sea.seaDevice];
            edges.push(edge(c.id, seaNodeId,
              "Slot C" + c.clientSlot + "\n(PVID " + c.pvid + ")",
              "━━ lshwres client adapter ━━\n" +
              "lpar_name: " + c.name + "\n" +
              "slot_num: C" + c.clientSlot + "\n" +
              "port_vlan_id (PVID): " + c.pvid + "\n" +
              "vswitch: " + c.vswitch
            ));
            connected = true;
          }
        });
      }
      if (!connected) {
        seaEntries.forEach(function (sea) {
          var seaNodeId = seaNodeIds[sea.viosName + "::" + sea.seaDevice];
          edges.push(edge(c.id, seaNodeId,
            "Slot C" + c.clientSlot + "\n(PVID " + c.pvid + ")",
            "lpar_name: " + c.name + "\nslot_num: C" + c.clientSlot + "\npvid: " + c.pvid
          ));
        });
      }
    });

    // SEA → Physical edges (direct, no intermediate VIOS node)
    seaEntries.forEach(function (sea) {
      var seaNodeId  = seaNodeIds[sea.viosName + "::" + sea.seaDevice];
      var pkey       = sea.viosName + "::" + sea.realAdapter;
      var physNodeId = physNodeIdOf[pkey];
      if (seaNodeId && physNodeId) {
        var edgeId = "ep_sea_" + seaNodeId + "_" + physNodeId;
        if (!edges.find(function (e) { return e.id === edgeId; })) {
          edges.push(Object.assign(edge(seaNodeId, physNodeId,
            sea.realAdapter + "\n(Real Adapter)",
            "━━ entstat -all " + sea.seaDevice + " (Step 3) ━━\n" +
            "SEA: " + sea.seaDevice + "\n" +
            "Real Adapter: " + sea.realAdapter + "\n" +
            "Physical Ports: " + sea.physPorts + "\n" +
            "Link Status: " + sea.linkStatus + "\n" +
            "Link Speed: " + sea.linkSpeed
          ), { id: edgeId }));
        }
      }
    });

    // ── Return nodes, edges AND viosGroupInfo for the group-box renderer ─────
    return { nodes: nodes, edges: edges, viosGroupInfo: viosGroupInfo, groupPad: GROUP_PAD };
  }

  // Fetch the live Virtual Network (SEA) topology for the selected managed system.
  async function loadLiveVnet() {
    const ms = currentMS();
    if (!localHMCId || !ms || DATA[ms]) {
      // Demo system — use static SEA command reference panel (already shown)
      return;
    }
    const key = liveKey();

    // Replace static sea-cmd-panel with the live cmd-output-panel
    hideSeaCmdPanel();
    const statusEl = document.getElementById("cmd-status");
    document.getElementById("cmd-output-panel").classList.remove("hidden");
    if (statusEl) statusEl.textContent = "· running lshwres / lsdev / entstat (SEA) on the HMC…";
    document.getElementById("cmd-output-body").innerHTML =
      '<div class="text-sm text-slate-500 p-2">Executing 3-step SEA discovery — please wait…</div>';

    let payload = null;
    try {
      payload = await fetch("/api/hmcs/" + localHMCId +
        "/managed-systems/" + encodeURIComponent(ms) + "/vnet-topology").then((r) => r.json());
    } catch (e) {
      payload = { ok: false, commands: [{ title: "vnet-topology", command: "(request failed)", output: String(e), ok: false }] };
    }

    // Always show the raw command output
    renderCommandPanel(payload && payload.commands);

    const ethAdapters = (payload && payload.eth_adapters) || [];
    const seaDevices  = (payload && payload.sea_devices)  || {};
    const hasSea = Object.values(seaDevices).some(function (devList) { return devList && devList.length > 0; });

    if (payload && payload.ok && ethAdapters.length > 0) {
      LIVE_VNET[key] = { payload: payload, graph: buildVnetFromLive(payload) };
      if (currentTab === "vnet") buildNetwork("vnet");
      setStatus(
        "Virtual Network (SEA) topology built from live HMC output \u2014 " +
        ethAdapters.length + " eth adapter(s), " +
        (hasSea ? Object.values(seaDevices).flat().length + " SEA device(s)" : "no SEA devices found") +
        ". Click any node to isolate its path."
      );
    } else {
      LIVE_VNET[key] = null;
      const reason = (payload && payload.ok)
        ? "lshwres returned no ethernet adapter rows for this managed system."
        : (payload && payload.commands && payload.commands.length
            ? "Command execution failed \u2014 see output above."
            : "No response from server.");
      setStatus(
        "No virtual ethernet adapters found \u2014 " + reason +
        " Showing representative demo topology."
      );
    }
  }

  // Fetch the live vSCSI topology (lshwres --rsubtype scsi + lsmap) for the
  // currently-selected HMC + managed system, render the command output panel,
  // and rebuild the vSCSI graph from the joined data.
  async function loadLiveVscsi() {
    const ms = currentMS();
    if (!localHMCId || !ms || DATA[ms]) {
      // Demo system or nothing selected — no live commands to show.
      hideCommandPanel();
      return;
    }
    const key = liveKey();
    const statusEl = document.getElementById("cmd-status");
    document.getElementById("cmd-output-panel").classList.remove("hidden");
    if (statusEl) statusEl.textContent = "· running lshwres / lsmap (scsi) on the HMC…";
    document.getElementById("cmd-output-body").innerHTML =
      '<div class="text-sm text-slate-500 p-2">Executing HMC commands — please wait…</div>';

    let payload = null;
    try {
      payload = await fetch("/api/hmcs/" + localHMCId +
        "/managed-systems/" + encodeURIComponent(ms) + "/vscsi-topology").then((r) => r.json());
    } catch (e) {
      payload = { ok: false, commands: [{ title: "vscsi-topology", command: "(request failed)", output: String(e), ok: false }] };
    }

    // Always render the command output panel so the raw HMC output is visible
    renderCommandPanel(payload && payload.commands);

    const scsiAdapters = (payload && payload.scsi_adapters) || [];
    const serverScsi = scsiAdapters.filter(function (r) {
      return r.adapter_type === "server" || !r.adapter_type;
    });

    if (payload && payload.ok && scsiAdapters.length > 0) {
      LIVE_VSCSI[key] = { payload: payload, graph: buildVscsiFromLive(payload) };
      if (currentTab === "vscsi") buildNetwork("vscsi");
      setStatus(
        "vSCSI topology built from live HMC output \u2014 " +
        scsiAdapters.length + " adapter row(s), " +
        serverScsi.length + " server-side. Click any node to isolate its path."
      );
    } else {
      LIVE_VSCSI[key] = null;
      const reason = (payload && payload.ok)
        ? "lshwres returned no vSCSI adapter rows for this managed system."
        : (payload && payload.commands && payload.commands.length
            ? "Command execution failed \u2014 see output above."
            : "No response from server.");
      setStatus(
        "No virtual SCSI adapters found \u2014 " + reason +
        " Showing representative demo topology."
      );
    }
  }

  // Fetch the live Virtual Fibre Channel topology (lshwres + lsmap) for the
  // currently-selected HMC + managed system, render the command output above
  // the graph, and rebuild the NPIV graph from the parsed data.
  async function loadLiveNpiv() {
    const ms = currentMS();
    if (!localHMCId || !ms || DATA[ms]) {
      // Demo system or nothing selected — no live commands to show.
      hideCommandPanel();
      return;
    }
    const key = liveKey();
    const statusEl = document.getElementById("cmd-status");
    document.getElementById("cmd-output-panel").classList.remove("hidden");
    if (statusEl) statusEl.textContent = "· running lshwres / lsmap -npiv on the HMC…";
    document.getElementById("cmd-output-body").innerHTML =
      '<div class="text-sm text-slate-500 p-2">Executing HMC commands — please wait…</div>';

    let payload = null;
    try {
      payload = await fetch("/api/hmcs/" + localHMCId +
        "/managed-systems/" + encodeURIComponent(ms) + "/vfc-topology").then((r) => r.json());
    } catch (e) {
      payload = { ok: false, commands: [{ title: "vfc-topology", command: "(request failed)", output: String(e), ok: false }] };
    }

    // Always render the command output panel so the raw HMC output is visible
    renderCommandPanel(payload && payload.commands);

    const adapters = (payload && payload.fc_adapters) || [];
    // Filter to server-side rows to see if any NPIV paths actually exist
    const serverAdapters = adapters.filter(function (r) {
      return r.adapter_type === "server" || !r.adapter_type;
    });

    if (payload && payload.ok && serverAdapters.length > 0) {
      // Live data available — build and render the real topology
      LIVE_NPIV[key] = { payload: payload, graph: buildNpivFromLive(payload) };
      if (currentTab === "npiv") buildNetwork("npiv");
      setStatus(
        "Virtual Fibre Channel topology built from live HMC output \u2014 " +
        serverAdapters.length + " server adapter(s) on " +
        (payload.vios || []).length + " VIOS. Click any node to isolate its path."
      );
    } else if (payload && payload.ok && adapters.length > 0) {
      // Data returned but no server-side (VIOS) adapter rows — show client-only view
      LIVE_NPIV[key] = { payload: payload, graph: buildNpivFromLive(payload) };
      if (currentTab === "npiv") buildNetwork("npiv");
      setStatus(
        "Virtual Fibre Channel topology built from live HMC output \u2014 " +
        adapters.length + " adapter row(s) found. Click any node to isolate its path."
      );
    } else {
      LIVE_NPIV[key] = null;
      const reason = (payload && payload.ok)
        ? "lshwres returned no FC adapter rows for this managed system."
        : (payload && payload.commands && payload.commands.length
            ? "Command execution failed \u2014 see output above."
            : "No response from server.");
      setStatus(
        "No Virtual Fibre Channel adapters found \u2014 " + reason +
        " Showing representative demo topology."
      );
    }
  }


  // Track whether a linear-focus is active per tab.
  const FOCUS_MODE = { npiv: false, vscsi: false, vnet: false };

  function buildNetwork(tab) {
    const src = datasetFor(tab);

    const container = document.getElementById("net-" + tab);
    const nodes = new vis.DataSet(src.nodes.map((n) => Object.assign({}, n)));
    // All built-in edge rendering is suppressed — we draw 90° elbows in afterDrawing.
    // Store the original label/color/width on a private _orig field so the canvas
    // renderer can read them, while vis-network itself renders nothing.
    const edges = new vis.DataSet(src.edges.map((e, i) => Object.assign({}, e, {
      id: "e" + tab + i,
      _orig: { label: e.label || "", color: (e.color && e.color.color) || "#94a3b8", width: e.width || 1.5 },
      color: { color: "rgba(0,0,0,0)", highlight: "rgba(0,0,0,0)", hover: "rgba(0,0,0,0)", opacity: 0 },
      font:  { color: "rgba(0,0,0,0)", strokeColor: "rgba(0,0,0,0)" },
      width: 0,
      label: "",
      arrows: { to: { enabled: false } },
    })));
    // Store vnet group-box metadata (from buildVnetFromLive) on the NET entry
    // so the afterDrawing handler can access it for transparent VIOS group boxes.
    const srcGroupInfo = (tab === "vnet" && src.viosGroupInfo) ? src.viosGroupInfo : null;
    const srcGroupPad  = (tab === "vnet" && src.groupPad)     ? src.groupPad      : 30;

    if (NET[tab] && NET[tab].network) { NET[tab].network.destroy(); }
    FOCUS_MODE[tab] = false;
    const network = new vis.Network(container, { nodes: nodes, edges: edges }, VIS_OPTIONS);
    network.on("selectNode", (params) => {
      // Single-click: highlight connected path (dim others).
      if (!FOCUS_MODE[tab]) isolate(tab, params.nodes[0]);
    });
    network.on("deselectNode", () => { if (!FOCUS_MODE[tab]) resetHighlight(tab); });
    network.on("click", (params) => {
      if (params.nodes.length === 0) resetHighlight(tab);
    });
    network.on("doubleClick", (params) => {
      if (params.nodes.length > 0) {
        const nodeId = params.nodes[0];
        const nd = nodes.get(nodeId);
        if (nd && nd._kind === "mid") {
          // Double-click on a vfchost mapping node → single linear path.
          linearFocus(tab, nodeId);
        } else if (nd && nd._kind === "client") {
          // Double-click on a Client LPAR → show all connected vfchosts + their VIOS.
          lparFocus(tab, nodeId);
        } else {
          // Double-click on VIOS or empty: reset to full view.
          resetHighlight(tab);
        }
      } else {
        resetHighlight(tab);
      }
    });
    /* ── Custom orthogonal (90°-elbow) edge renderer ──────────────────
       vis-network's built-in edges are set to smooth:false (straight).
       We hide them by making them transparent and redraw every edge as a
       true L-shaped elbow using the afterDrawing canvas hook.

       Routing rule (matches the image: go-right then turn-down-or-up):
         1. Start from the right-centre of the source node.
         2. Travel horizontally to the midpoint X between source and target.
         3. Turn 90° and travel vertically to the target's Y.
         4. Travel horizontally to the left-centre of the target node.
         5. Draw a filled arrowhead pointing right into the target.

       Label text is drawn at the midpoint of the horizontal segment
       closest to the target (segment 3→4 midpoint).
    ── */
    network.on("afterDrawing", function (ctx) {
      const allEdges  = edges.get().filter((e) => !e.hidden);
      const allNodes  = nodes.get();
      const nodeMap   = {};
      allNodes.forEach((n) => { nodeMap[n.id] = n; });

      // ── VIOS Group Boxes (vnet tab only) ──────────────────────────────────
      // Draw a transparent rounded-rectangle behind the SEA + Physical nodes
      // that belong to each VIOS, with the VIOS name at the bottom of the box.
      // This replaces the standalone VIOS node column.
      if (srcGroupInfo) {
        Object.keys(srcGroupInfo).forEach(function (vname) {
          var grp = srcGroupInfo[vname];
          // Collect real-time bounding boxes for all nodes in this group.
          var allGroupNodeIds = grp.seaNodeIds.concat(grp.physNodeIds);
          var minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
          var anyVisible = false;
          allGroupNodeIds.forEach(function (nid) {
            var nd = nodeMap[nid];
            if (!nd || nd.hidden) return;
            var bb = network.getBoundingBox(nid);
            if (!bb) return;
            anyVisible = true;
            if (bb.left   < minX) minX = bb.left;
            if (bb.right  > maxX) maxX = bb.right;
            if (bb.top    < minY) minY = bb.top;
            if (bb.bottom > maxY) maxY = bb.bottom;
          });
          if (!anyVisible) return;

          // Expand by padding
          var PAD  = srcGroupPad;
          var LABEL_H = 22;     // reserve space at bottom for the VIOS name label
          var rx = minX - PAD;
          var ry = minY - PAD;
          var rw = (maxX - minX) + PAD * 2;
          var rh = (maxY - minY) + PAD * 2 + LABEL_H;
          var radius = 14;

          ctx.save();

          // Transparent filled rounded rect — light blue tint (VIOS colour family)
          ctx.beginPath();
          ctx.moveTo(rx + radius, ry);
          ctx.lineTo(rx + rw - radius, ry);
          ctx.arcTo(rx + rw, ry,           rx + rw, ry + radius,      radius);
          ctx.lineTo(rx + rw, ry + rh - radius);
          ctx.arcTo(rx + rw, ry + rh,      rx + rw - radius, ry + rh, radius);
          ctx.lineTo(rx + radius, ry + rh);
          ctx.arcTo(rx,      ry + rh,      rx, ry + rh - radius,      radius);
          ctx.lineTo(rx, ry + radius);
          ctx.arcTo(rx,      ry,           rx + radius, ry,            radius);
          ctx.closePath();

          // Fill: very faint blue — almost transparent so nodes show through
          ctx.fillStyle = "rgba(219,234,254,0.22)";   // ~blue-100 @ 22% opacity
          ctx.fill();

          // Border: dashed blue line
          ctx.strokeStyle = "rgba(37,99,235,0.45)";   // blue-600 @ 45%
          ctx.lineWidth   = 1.5;
          ctx.setLineDash([6, 4]);
          ctx.stroke();
          ctx.setLineDash([]);

          // VIOS name label — bottom-centre of the box
          var labelX = rx + rw / 2;
          var labelY = ry + rh - 5;

          // White halo
          ctx.font         = "bold 12px Inter, sans-serif";
          ctx.textAlign    = "center";
          ctx.textBaseline = "bottom";
          ctx.lineWidth    = 3;
          ctx.strokeStyle  = "rgba(255,255,255,0.9)";
          ctx.strokeText(vname, labelX, labelY);

          // Blue text
          ctx.fillStyle = "#1e40af";   // blue-800
          ctx.fillText(vname, labelX, labelY);

          ctx.restore();
        });
      }
      // ── end VIOS Group Boxes ──────────────────────────────────────────────

      // ── Fan-out: when multiple edges share the same source OR target node,
      //    spread their attachment points vertically so legs don't overlap.
      //
      //    For a given node N with k outgoing edges (from=N), assign each edge
      //    a source-side offset: offsets = [-(k-1)/2, ..., 0, ..., (k-1)/2] × STEP.
      //    Do the same for incoming edges (to=N) on the target side.
      //
      //    Edges are ordered by the Y of the OTHER endpoint so the offsets
      //    follow the natural top-to-bottom order of the connected nodes,
      //    which minimises visual crossings.
      const STEP = 14; // pixels in graph units between fan lanes

      // Build per-node edge lists
      const outEdges = {};  // nodeId → [ edgeId, … ]
      const inEdges  = {};
      allEdges.forEach((e) => {
        (outEdges[e.from] = outEdges[e.from] || []).push(e.id);
        (inEdges [e.to  ] = inEdges [e.to  ] || []).push(e.id);
      });

      // Assign source-side (sy) offsets.
      // VIOS nodes (kind=vios) fan out NATURALLY because each of their outgoing
      // edges already targets a DIFFERENT middle node at a different Y — so the
      // elbow already lands at the correct target Y without any source offset.
      // Applying a source offset on VIOS nodes would make the horizontal leg
      // leave at a wrong height and create visual overlap.
      // Only apply source fan-out for non-VIOS source nodes.
      const srcOff = {};   // edgeId → dy offset at source
      Object.keys(outEdges).forEach((nid) => {
        const srcNode = nodeMap[nid];
        const isVios  = srcNode && srcNode._kind === "vios";
        const eids = outEdges[nid];
        // VIOS source: no fan-out — each elbow departs at the natural node centre.
        if (isVios || eids.length <= 1) {
          eids.forEach((id) => { srcOff[id] = 0; });
          return;
        }
        // Non-VIOS source with multiple outgoing edges: fan out.
        eids.sort((a, b) => {
          const ea = allEdges.find((e) => e.id === a);
          const eb = allEdges.find((e) => e.id === b);
          const pa = network.getPosition(ea.to);
          const pb = network.getPosition(eb.to);
          return (pa ? pa.y : 0) - (pb ? pb.y : 0);
        });
        const half = (eids.length - 1) / 2;
        eids.forEach((id, i) => { srcOff[id] = (i - half) * STEP; });
      });

      // Assign target-side (ty) offsets, sorted by source Y
      const tgtOff = {};   // edgeId → dy offset at target
      Object.keys(inEdges).forEach((nid) => {
        const eids = inEdges[nid];
        if (eids.length <= 1) { eids.forEach((id) => { tgtOff[id] = 0; }); return; }
        eids.sort((a, b) => {
          const ea = allEdges.find((e) => e.id === a);
          const eb = allEdges.find((e) => e.id === b);
          const pa = network.getPosition(ea.from);
          const pb = network.getPosition(eb.from);
          return (pa ? pa.y : 0) - (pb ? pb.y : 0);
        });
        const half = (eids.length - 1) / 2;
        eids.forEach((id, i) => { tgtOff[id] = (i - half) * STEP; });
      });

      // ── Draw each edge ──
      allEdges.forEach((e) => {
        const fromPos = network.getPosition(e.from);
        const toPos   = network.getPosition(e.to);
        if (!fromPos || !toPos) return;

        const orig   = e._orig || {};
        const active = e._active;

        // Half-width of a node box in graph units.
        // Use the actual bounding box if available, otherwise default to 117.
        const srcBB = network.getBoundingBox(e.from);
        const tgtBB = network.getBoundingBox(e.to);
        const srcHW = srcBB ? (srcBB.right - srcBB.left) / 2 : 117;
        const tgtHW = tgtBB ? (tgtBB.right - tgtBB.left) / 2 : 117;

        // Apply fan-out offsets to the attachment Y values.
        const sx = fromPos.x + srcHW;
        const sy = fromPos.y + (srcOff[e.id] || 0);
        const tx = toPos.x   - tgtHW;
        const ty = toPos.y   + (tgtOff[e.id] || 0);

        // Elbow X midpoint between source right edge and target left edge.
        // Guard: if target is left of source (reversed edge), swap.
        const ex = (sx + tx) / 2;
        // Skip invisible edges where nodes overlap
        if (Math.abs(tx - sx) < 4 && Math.abs(ty - sy) < 4) return;

        // Colour / thickness based on isolation state.
        // active=true  → bright green highlight (connected path)
        // active=false → very dim grey (unrelated edges)
        // active=null  → normal slate colour
        let col, lw;
        if (active === null || active === undefined) {
          col = orig.color || "#94a3b8";
          lw  = orig.width || 1.5;
        } else if (active) {
          col = "#16a34a";   // green-600 — bright highlight
          lw  = 2.5;
        } else {
          col = "rgba(148,163,184,0.18)";  // very faint slate
          lw  = 1;
        }

        ctx.save();
        ctx.strokeStyle = col;
        ctx.fillStyle   = col;
        ctx.lineWidth   = lw;
        ctx.lineCap     = "square";
        ctx.lineJoin    = "miter";

        // L-shaped elbow: horizontal → vertical → horizontal.
        ctx.beginPath();
        ctx.moveTo(sx, sy);
        ctx.lineTo(ex, sy);
        ctx.lineTo(ex, ty);
        ctx.lineTo(tx, ty);
        ctx.stroke();

        // Arrowhead at target end (pointing right).
        const aLen = 10, aHalf = 5;
        ctx.beginPath();
        ctx.moveTo(tx,        ty);
        ctx.lineTo(tx - aLen, ty - aHalf);
        ctx.lineTo(tx - aLen, ty + aHalf);
        ctx.closePath();
        ctx.fill();

        // Edge label — on the final horizontal segment, centred, above the line.
        const label = ((e._orig && e._orig.label) || "").replace(/<[^>]*>/g, "");
        if (label) {
          const lines = label.split("\n");
          const lineH = 13;
          // Position label above the horizontal-to-target segment.
          const lx = (ex + tx) / 2;
          // Start Y: place last line just above the wire.
          const baseY = ty - 4;

          ctx.font = "11px Inter, sans-serif";
          ctx.textAlign = "center";
          ctx.textBaseline = "bottom";

          // Draw white halo for active/normal labels; skip halo for dimmed labels.
          const isDimmed = active === false;
          if (!isDimmed) {
            ctx.lineWidth   = 3;
            ctx.strokeStyle = "#ffffff";
            lines.forEach((line, li) => {
              ctx.strokeText(line, lx, baseY - (lines.length - 1 - li) * lineH);
            });
          }

          // Active: dark text. Inactive (dimmed): nearly invisible. Normal: slate.
          ctx.fillStyle = isDimmed
            ? "rgba(148,163,184,0.20)"
            : active
              ? "#0f172a"
              : "#475569";
          ctx.lineWidth = lw;
          lines.forEach((line, li) => {
            ctx.fillText(line, lx, baseY - (lines.length - 1 - li) * lineH);
          });
        }

        ctx.restore();
      });

    });  // end afterDrawing

    NET[tab] = { network: network, nodes: nodes, edges: edges };
    requestAnimationFrame(() => network.fit({ animation: false }));
    return NET[tab];
  }

  /* ---- Linear focus: double-click on a vfchost box ----
     Hides every node/edge not connected to this vfchost and
     repositions the three connected nodes into a horizontal line:
       VIOS (left) ──► vfchost (centre) ──► Client LPAR (right)
  */
  function linearFocus(tab, midId) {
    const nodes = NET[tab].nodes;
    const edges = NET[tab].edges;
    FOCUS_MODE[tab] = true;

    // Collect the edges that touch this mid node.
    const connEdges = edges.get().filter((e) => e.from === midId || e.to === midId);
    const connNodeIds = new Set([midId]);
    connEdges.forEach((e) => { connNodeIds.add(e.from); connNodeIds.add(e.to); });

    // Hide unrelated nodes (make them invisible via hidden:true).
    nodes.update(nodes.get().map((n) => {
      if (connNodeIds.has(n.id)) return { id: n.id, hidden: false };
      return { id: n.id, hidden: true };
    }));

    // Hide unrelated edges.
    edges.update(edges.get().map((e) => {
      const rel = connNodeIds.has(e.from) && connNodeIds.has(e.to);
      return { id: e.id, hidden: !rel };
    }));

    // Determine VIOS node (kind=vios), client node (kind=client) among connected.
    let viosId = null, clientId = null;
    connNodeIds.forEach((id) => {
      if (id === midId) return;
      const n = nodes.get(id);
      if (n && n._kind === "vios") viosId = id;
      if (n && n._kind === "client") clientId = id;
    });

    // Reposition into a horizontal line: VIOS left, vfchost centre, LPAR right.
    const LX = -480, MX = 0, RX = 480, LY = 0;
    const updates = [{ id: midId, x: MX, y: LY, fixed: { x: true, y: true } }];
    if (viosId) updates.push({ id: viosId, x: LX, y: LY, fixed: { x: true, y: true } });
    if (clientId) updates.push({ id: clientId, x: RX, y: LY, fixed: { x: true, y: true } });
    nodes.update(updates);

    const net = NET[tab].network;
    requestAnimationFrame(() => net.fit({ animation: { duration: 400, easingFunction: "easeInOutQuad" } }));

    const midLabel = (nodes.get(midId).label || "").replace(/<[^>]+>/g, "").split("\n")[0];
    setStatus("Linear view: " + midLabel + "  ·  Double-click another vfchost or click empty space to reset.");
  }

  /* ---- LPAR focus: double-click on a Client LPAR box ----
     Shows all vfchost mapping nodes connected to this LPAR, plus
     each of their parent VIOS nodes. Hides everything else.
     Layout (columnar, near-linear):
       VIOS column (left, -480)  |  vfchost column (mid, 0)  |  LPAR (right, +480)
     VIOS nodes are stacked at rows matching their connected vfchost.
  */
  function lparFocus(tab, clientId) {
    const nodes = NET[tab].nodes;
    const edges = NET[tab].edges;
    FOCUS_MODE[tab] = true;

    // Find all mid (vfchost) nodes directly connected to this LPAR.
    const allEdges = edges.get();
    const midIds = [];
    allEdges.forEach((e) => {
      if (e.from === clientId || e.to === clientId) {
        const otherId = e.from === clientId ? e.to : e.from;
        const nd = nodes.get(otherId);
        if (nd && nd._kind === "mid" && midIds.indexOf(otherId) < 0) midIds.push(otherId);
      }
    });

    // For each vfchost, find its connected VIOS node.
    const viosIds = [];
    const midToVios = {};
    midIds.forEach((midId) => {
      allEdges.forEach((e) => {
        if (e.from === midId || e.to === midId) {
          const otherId = e.from === midId ? e.to : e.from;
          if (otherId === clientId) return;
          const nd = nodes.get(otherId);
          if (nd && nd._kind === "vios") {
            midToVios[midId] = otherId;
            if (viosIds.indexOf(otherId) < 0) viosIds.push(otherId);
          }
        }
      });
    });

    // Build the full set of visible node IDs.
    const visibleIds = new Set([clientId]);
    midIds.forEach((id) => visibleIds.add(id));
    viosIds.forEach((id) => visibleIds.add(id));

    // Hide unrelated nodes and edges.
    nodes.update(nodes.get().map((n) => ({
      id: n.id, hidden: !visibleIds.has(n.id),
    })));
    edges.update(allEdges.map((e) => ({
      id: e.id, hidden: !(visibleIds.has(e.from) && visibleIds.has(e.to)),
    })));

    // Position nodes into columns.
    // vfchost nodes: stacked vertically in the middle column.
    // VIOS nodes: aligned to the y of their connected vfchost.
    // LPAR: single node centred on the right.
    const ROW = 140;
    const nMid = midIds.length;
    const midYs = rows(nMid, ROW);
    const updates = [];

    // LPAR centred vertically among all vfchosts.
    updates.push({ id: clientId, x: 480, y: 0, fixed: { x: true, y: true } });

    midIds.forEach((midId, i) => {
      updates.push({ id: midId, x: 0, y: midYs[i], fixed: { x: true, y: true } });
      const viosId = midToVios[midId];
      if (viosId) {
        // If multiple vfchosts share the same VIOS, average their y positions.
        const sharedMids = midIds.filter((m) => midToVios[m] === viosId);
        const avgY = sharedMids.reduce((sum, m, _) => sum + midYs[midIds.indexOf(m)], 0) / sharedMids.length;
        // Only push once per unique VIOS.
        if (!updates.find((u) => u.id === viosId)) {
          updates.push({ id: viosId, x: -480, y: avgY, fixed: { x: true, y: true } });
        }
      }
    });

    nodes.update(updates);

    const net = NET[tab].network;
    requestAnimationFrame(() => net.fit({ animation: { duration: 400, easingFunction: "easeInOutQuad" } }));

    const lparLabel = (nodes.get(clientId).label || "").replace(/<[^>]+>/g, "").split("\n")[0];
    setStatus("LPAR view: " + lparLabel + "  (" + midIds.length + " vfchost path(s), " + viosIds.length + " VIOS)  ·  Click empty space to reset.");
  }

  /* connectedSet — returns the clicked node PLUS every node that shares
     a direct edge with it (1-hop only).  Edges that connect those pairs
     are the "active" edges; everything else is dimmed.
     This gives the "highlight only the directly-connected path" behaviour:
       click VIOS1  → highlight VIOS1 + its middle-adapter nodes + those edges
       click mid    → highlight that mid + VIOS + client + both edges
       click client → highlight client + its middle-adapter nodes + those edges
  */
  function connectedSet(tab, startId) {
    const edges = NET[tab].edges;
    const directNeighbours = new Set([startId]);
    edges.get().forEach((e) => {
      if (e.from === startId) directNeighbours.add(e.to);
      if (e.to   === startId) directNeighbours.add(e.from);
    });
    return directNeighbours;
  }

  function isolate(tab, startId) {
    const nodes = NET[tab].nodes, edges = NET[tab].edges;
    const keep = connectedSet(tab, startId);
    nodes.update(nodes.get().map((n) => {
      const active = keep.has(n.id);
      const c = C[n._kind];
      return {
        id: n.id, opacity: active ? 1 : 0.15,
        // Active nodes: thicker border + yellow highlight ring so they stand out.
        // Inactive nodes: washed-out background and very light border.
        color: {
          background: active ? c.bg   : "#f8fafc",
          border:     active ? "#eab308" : "#e2e8f0",   // yellow-500 for active
          highlight:  { background: c.bg, border: "#eab308" },
        },
        borderWidth: active ? 3 : 1,
        font: { color: active ? c.font : "#cbd5e1" },
      };
    }));
    // Mark edges active/inactive for the canvas renderer via _active flag.
    // Keep vis color always transparent so no diagonal arrows appear.
    edges.update(edges.get().map((e) => ({
      id: e.id,
      _active: keep.has(e.from) && keep.has(e.to),
      color: { color: "rgba(0,0,0,0)", highlight: "rgba(0,0,0,0)", hover: "rgba(0,0,0,0)", opacity: 0 },
      font:  { color: "rgba(0,0,0,0)", strokeColor: "rgba(0,0,0,0)" },
      width: 0,
    })));
    if (NET[tab].network) NET[tab].network.redraw();
    const label = nodes.get(startId).label.replace(/<[^>]+>/g, "").split("\n")[0];
    setStatus("Isolated path for \u201c" + label + "\u201d \u2014 " + keep.size + " connected node(s) highlighted.");
  }

  function resetHighlight(tab) {
    if (!NET[tab]) return;
    const nodes = NET[tab].nodes, edges = NET[tab].edges;
    const wasFocused = FOCUS_MODE[tab];
    FOCUS_MODE[tab] = false;

    nodes.update(nodes.get().map((n) => {
      const c = C[n._kind];
      const update = {
        id: n.id, hidden: false, opacity: 1,
        color: { background: c.bg, border: c.border },
        font: { color: c.font },
      };
      if (wasFocused) update.fixed = { x: false, y: false };
      return update;
    }));
    // Reset all edges: un-hide, clear _active, keep vis rendering transparent.
    edges.update(edges.get().map((e) => ({
      id: e.id, hidden: false, _active: null,
      color: { color: "rgba(0,0,0,0)", highlight: "rgba(0,0,0,0)", hover: "rgba(0,0,0,0)", opacity: 0 },
      font:  { color: "rgba(0,0,0,0)", strokeColor: "rgba(0,0,0,0)" },
      width: 0,
    })));

    if (wasFocused && NET[tab].network) {
      requestAnimationFrame(() => NET[tab].network.fit({ animation: { duration: 400, easingFunction: "easeInOutQuad" } }));
    }
    setStatus("Click any node to isolate its virtualization path. Double-click a vFC mapping box to enter linear view.");
  }

  function renderLegend(tab) {
    document.getElementById("legend").innerHTML = LEGENDS[tab].map((pair) =>
      '<span class="flex items-center gap-1.5"><span class="legend-swatch" style="background:' +
      C[pair[0]].bg + ";border:2px solid " + C[pair[0]].border + '"></span>' + pair[1] + "</span>").join("");
  }

  // Show/hide the SEA command reference panel (Tab 3 only)
  function showSeaCmdPanel() {
    const panel = document.getElementById("sea-cmd-panel");
    if (panel) panel.classList.remove("hidden");
  }

  function hideSeaCmdPanel() {
    const panel = document.getElementById("sea-cmd-panel");
    if (panel) panel.classList.add("hidden");
  }

  function showTab(tab) {
    currentTab = tab;
    document.querySelectorAll(".topo-tab-btn").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
    document.querySelectorAll("#topology-app .tab-pane").forEach((p) => p.classList.toggle("active", p.id === "pane-" + tab));
    document.getElementById("flow-label").innerHTML =
      '<i data-lucide="git-branch" class="w-4 h-4"></i><span>' + FLOW_LABELS[tab] + "</span>";
    renderLegend(tab);
    if (window.lucide) lucide.createIcons();
    buildNetwork(tab);

    // Show the appropriate command panel per tab.
    // Tab 1 (NPIV): live HMC lshwres+lsmap command output.
    // Tab 2 (vSCSI): live HMC lshwres+lsmap (scsi) command output.
    // Tab 3 (Virtual Network / SEA):
    //   - Real HMC system: fires loadLiveVnet() which fetches live data and
    //     renders the 3-step SEA command output via the shared cmd-output-panel.
    //   - Demo system: shows the static SEA command reference panel.
    if (tab === "npiv") {
      hideSeaCmdPanel();
      loadLiveNpiv();
    } else if (tab === "vscsi") {
      hideSeaCmdPanel();
      loadLiveVscsi();
    } else if (tab === "vnet") {
      const isDemo = !localHMCId || DATA[currentMS()];
      if (isDemo) {
        hideCommandPanel();
        showSeaCmdPanel();
        setStatus("Demo topology \u2014 3-step SEA data join (lshwres eth \u2192 lsdev \u2192 entstat). Select a live HMC system to fetch real data.");
      } else {
        hideSeaCmdPanel();
        loadLiveVnet();
      }
    } else {
      hideCommandPanel();
      hideSeaCmdPanel();
    }
  }


  /* ============================================================
     REAL HMC / MANAGED SYSTEM SELECTORS
     Mirrors lpars.html: /api/hmcs  ->  /api/hmcs/<id>/managed-systems
  ============================================================ */
  let localHMCId = null;

  function rebuildCurrent() {
    Object.keys(NET).forEach((t) => { if (NET[t] && NET[t].network) NET[t].network.destroy(); NET[t] = null; });
    buildNetwork(currentTab);
    // Refresh live HMC commands + graph when the active tab supports live data.
    if (currentTab === "npiv") {
      hideSeaCmdPanel();
      loadLiveNpiv();
    } else if (currentTab === "vscsi") {
      hideSeaCmdPanel();
      loadLiveVscsi();
    } else if (currentTab === "vnet") {
      const isDemo = !localHMCId || DATA[currentMS()];
      if (isDemo) {
        hideCommandPanel();
        showSeaCmdPanel();
        setStatus("Demo topology \u2014 3-step SEA data join (lshwres eth \u2192 lsdev \u2192 entstat). Select a live HMC system to fetch real data.");
      } else {
        hideSeaCmdPanel();
        loadLiveVnet();
      }
    } else {
      hideCommandPanel();
      hideSeaCmdPanel();
    }
  }


  async function initSelectors() {
    const hmcSel = document.getElementById("hmc-local-selector");
    let hmcs = [];
    try {
      hmcs = await fetch("/api/hmcs").then((r) => r.json());
    } catch (e) { hmcs = []; }

    if (!Array.isArray(hmcs) || hmcs.length === 0) {
      // No HMC configured — keep demo systems selectable so the page still works.
      populateDemoSystems();
      return;
    }

    hmcSel.innerHTML = '<option value="">— select HMC —</option>' +
      hmcs.map((h) => '<option value="' + h.id + '">' + (h.name || h.host) + " (" + h.host + ")</option>").join("");

    // Pre-select an active HMC if one exists globally
    const preHmc = window.activeHMCId || sessionStorage.getItem("activeHMCId");
    if (preHmc) { hmcSel.value = preHmc; localHMCId = preHmc; }

    hmcSel.addEventListener("change", () => {
      localHMCId = hmcSel.value || null;
      if (localHMCId) {
        window.activeHMCId = localHMCId;
        sessionStorage.setItem("activeHMCId", localHMCId);
        loadSystems();
      } else {
        populateDemoSystems();
      }
    });

    if (localHMCId) { await loadSystems(); } else { populateDemoSystems(); }
  }

  function populateDemoSystems() {
    const sel = document.getElementById("ms-selector");
    sel.innerHTML = '<option value="">— demo systems —</option>' +
      DEMO_KEYS.map((k) => '<option value="' + k + '">' + k + "</option>").join("");
    if (DEMO_KEYS.length) sel.value = DEMO_KEYS[0];
    setStatus("No live HMC data — showing demonstration topology. Click any node to isolate its path.");
    rebuildCurrent();
  }

  async function loadSystems() {
    const sel = document.getElementById("ms-selector");
    sel.innerHTML = '<option value="">— loading… —</option>';
    let d = { ok: false };
    try {
      d = await fetch("/api/hmcs/" + localHMCId + "/managed-systems?method=auto").then((r) => r.json());
    } catch (e) { d = { ok: false }; }

    if (d.ok && Array.isArray(d.data) && d.data.length) {
      sel.innerHTML = "";
      d.data.forEach((s) => sel.add(new Option((s.name || s.id) + (s.state ? "  (" + s.state + ")" : ""), s.id)));
      sel.value = d.data[0].id;
      setStatus("Loaded " + d.data.length + " managed system(s) from HMC. Topology shown is representative sample data.");
    } else {
      populateDemoSystems();
      return;
    }
    rebuildCurrent();
  }

  function init() {
    if (window.lucide) lucide.createIcons();
    document.querySelectorAll(".topo-tab-btn").forEach((btn) =>
      btn.addEventListener("click", () => showTab(btn.dataset.tab)));
    document.getElementById("ms-selector").addEventListener("change", rebuildCurrent);
    document.getElementById("reset-btn").addEventListener("click", () => {
      resetHighlight(currentTab);
      if (NET[currentTab]) NET[currentTab].network.fit({ animation: { duration: 400 } });
    });
    // Center & fit the graph within the visible canvas
    const centerBtn = document.getElementById("center-btn");
    if (centerBtn) {
      centerBtn.addEventListener("click", () => {
        if (NET[currentTab]) NET[currentTab].network.fit({ animation: { duration: 400 } });
      });
    }
    // Zoom controls
    function zoomBy(factor) {
      if (!NET[currentTab]) return;
      const net = NET[currentTab].network;
      net.moveTo({ scale: net.getScale() * factor, animation: { duration: 200 } });
    }
    const zoomInBtn = document.getElementById("zoom-in-btn");
    const zoomOutBtn = document.getElementById("zoom-out-btn");
    if (zoomInBtn) zoomInBtn.addEventListener("click", () => zoomBy(1.25));
    if (zoomOutBtn) zoomOutBtn.addEventListener("click", () => zoomBy(0.8));

    // Collapse / expand the NPIV/vSCSI command output panel body
    const cmdToggle = document.getElementById("cmd-toggle");
    if (cmdToggle) {
      cmdToggle.addEventListener("click", () => {
        const bodyEl = document.getElementById("cmd-output-body");
        const collapsed = bodyEl.classList.toggle("hidden");
        cmdToggle.querySelector("span").textContent = collapsed ? "Show" : "Hide";
        const icon = cmdToggle.querySelector("[data-lucide]");
        if (icon) { icon.setAttribute("data-lucide", collapsed ? "chevron-down" : "chevron-up"); }
        if (window.lucide) lucide.createIcons();
      });
    }

    // Collapse / expand the SEA command reference panel body (Tab 3)
    const seaCmdToggle = document.getElementById("sea-cmd-toggle");
    if (seaCmdToggle) {
      seaCmdToggle.addEventListener("click", () => {
        const bodyEl = document.getElementById("sea-cmd-body");
        const collapsed = bodyEl.classList.toggle("hidden");
        seaCmdToggle.querySelector("span").textContent = collapsed ? "Show" : "Hide";
        const icon = seaCmdToggle.querySelector("[data-lucide]");
        if (icon) { icon.setAttribute("data-lucide", collapsed ? "chevron-down" : "chevron-up"); }
        if (window.lucide) lucide.createIcons();
      });
    }

    window.addEventListener("resize", () => {
      if (NET[currentTab]) { NET[currentTab].network.redraw(); NET[currentTab].network.fit({ animation: false }); }
    });
    showTab("npiv");
    initSelectors();
  }


  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();




