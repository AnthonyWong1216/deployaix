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
      smooth: { enabled: true, type: "cubicBezier", roundness: 0.4 },
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

  /* ===== TAB 2 — vSCSI ===== */
  function vscsiData_A() {
    const nodes = [], edges = [];
    const vy = rows(2, 220);
    nodes.push(box("v1", "<b>VIOS1</b>\nID 1 · vios1a", "vios", COL.left, vy[0], "Partition: vios1a\nLPAR ID: 1\nState: Running"));
    nodes.push(box("v2", "<b>VIOS2</b>\nID 2 · vios2a", "vios", COL.left, vy[1], "Partition: vios2a\nLPAR ID: 2\nState: Running"));
    const midDefs = [
      { id: "m1", v: "v1", vhost: "vhost0", back: "LV lv_prod_db", vtd: "vtscsi0", type: "Logical Volume", c: "c1", slot: "C10", run: "Available" },
      { id: "m2", v: "v2", vhost: "vhost0", back: "LU lu_db_01", vtd: "vtscsi0", type: "SSP Logical Unit", c: "c1", slot: "C11", run: "Available" },
      { id: "m3", v: "v1", vhost: "vhost1", back: "hdisk4", vtd: "vtscsi1", type: "Physical Volume", c: "c2", slot: "C10", run: "Available" },
      { id: "m4", v: "v2", vhost: "vhost1", back: "LU lu_app_02", vtd: "vtscsi1", type: "SSP Logical Unit", c: "c2", slot: "C11", run: "Available" },
      { id: "m5", v: "v1", vhost: "vhost2", back: "hdisk7 (rootvg)", vtd: "vtopt0", type: "Physical Volume", c: "c3", slot: "C12", run: "Defined" },
    ];
    const my = rows(midDefs.length, 118);
    midDefs.forEach((m, i) => {
      nodes.push(box(m.id, "<b>" + m.vhost + "</b>\n" + m.vtd + " → " + m.back + "\n<i>" + m.type + "</i>", "mid", COL.mid, my[i],
        "Server SCSI adapter: " + m.vhost + "\nVirtual target device: " + m.vtd + "\nBacking: " + m.back + "\nType: " + m.type + "\nStatus: " + m.run));
      edges.push(edge(m.v, m.id, "", m.vhost + " on VIOS"));
      edges.push(edge(m.id, m.c, "Slot " + m.slot + " · " + m.run,
        "Client vSCSI slot: " + m.slot + "\nTarget device: " + m.vtd + "\nRuntime: " + m.run));
    });
    const cDefs = [
      { id: "c1", n: "aix-db-prod", lid: 11 },
      { id: "c2", n: "aix-app-prod", lid: 12 },
      { id: "c3", n: "aix-nim-01", lid: 14 },
    ];
    const cy = rows(cDefs.length, 170);
    cDefs.forEach((c, i) => nodes.push(box(c.id, "<b>" + c.n + "</b>\nLPAR ID " + c.lid, "client", COL.right, cy[i],
      "Client LPAR: " + c.n + "\nLPAR ID: " + c.lid + "\nBoot: vSCSI")));
    return { nodes: nodes, edges: edges };
  }

  function vscsiData_B() {
    const nodes = [], edges = [];
    nodes.push(box("v1", "<b>VIOS1</b>\nID 1 · vio1", "vios", COL.left, 0, "Partition: vio1\nLPAR ID: 1\nState: Running"));
    const midDefs = [
      { id: "m1", v: "v1", vhost: "vhost0", back: "LV rootvg_erp1", vtd: "vtscsi0", type: "Logical Volume", c: "c1", slot: "C10", run: "Available" },
      { id: "m2", v: "v1", vhost: "vhost1", back: "hdisk9", vtd: "vtscsi1", type: "Physical Volume", c: "c2", slot: "C10", run: "Available" },
    ];
    const my = rows(midDefs.length, 150);
    midDefs.forEach((m, i) => {
      nodes.push(box(m.id, "<b>" + m.vhost + "</b>\n" + m.vtd + " → " + m.back + "\n<i>" + m.type + "</i>", "mid", COL.mid, my[i],
        "Server SCSI adapter: " + m.vhost + "\nBacking: " + m.back + "\nType: " + m.type + "\nStatus: " + m.run));
      edges.push(edge(m.v, m.id, ""));
      edges.push(edge(m.id, m.c, "Slot " + m.slot + " · " + m.run, "Client vSCSI slot: " + m.slot + "\nRuntime: " + m.run));
    });
    const cDefs = [{ id: "c1", n: "aix-erp-01", lid: 21 }, { id: "c2", n: "aix-erp-02", lid: 22 }];
    const cy = rows(cDefs.length, 150);
    cDefs.forEach((c, i) => nodes.push(box(c.id, "<b>" + c.n + "</b>\nLPAR ID " + c.lid, "client", COL.right, cy[i],
      "Client LPAR: " + c.n + "\nLPAR ID: " + c.lid + "\nBoot: vSCSI")));
    return { nodes: nodes, edges: edges };
  }

  /* ===== TAB 3 — Virtual Network (SEA / SR-IOV) ===== */
  function vnetData_A() {
    const nodes = [], edges = [];
    const cDefs = [
      { id: "c1", n: "aix-db-prod", lid: 11, vlan: 100 },
      { id: "c2", n: "aix-app-prod", lid: 12, vlan: 100 },
      { id: "c3", n: "linux-web01", lid: 13, vlan: 200 },
      { id: "c4", n: "aix-nim-01", lid: 14, vlan: 200 },
    ];
    const cy = rows(cDefs.length, 130);
    cDefs.forEach((c, i) => nodes.push(box(c.id, "<b>" + c.n + "</b>\nLPAR ID " + c.lid + " · ent0", "client", NCOL.client, cy[i],
      "Client LPAR: " + c.n + "\nLPAR ID: " + c.lid + "\nVirtual adapter: ent0\nPVID: " + c.vlan)));
    const vlanDefs = [
      { id: "g1", vlan: 100, sw: "DefaultSwitch", sea: "s1" },
      { id: "g2", vlan: 200, sw: "DefaultSwitch", sea: "s1" },
    ];
    const gy = rows(vlanDefs.length, 260);
    vlanDefs.forEach((g, i) => nodes.push(box(g.id, "<b>VLAN " + g.vlan + "</b>\nvSwitch: " + g.sw, "vlan", NCOL.vlan, gy[i],
      "VLAN ID: " + g.vlan + "\nVirtual Switch: " + g.sw + "\nMode: VEB (bridged)")));
    cDefs.forEach((c) => {
      const g = vlanDefs.find((v) => v.vlan === c.vlan);
      edges.push(edge(c.id, g.id, "PVID " + c.vlan, "Client " + c.n + "\nVirtual adapter ent0\nPVID: " + c.vlan + "\nvSwitch: " + g.sw));
    });
    nodes.push(box("s1", "<b>vios1a</b>\nSEA ent4\n<i>ent3 (trunk)</i>", "vios", NCOL.vios, 0,
      "VIO Server: vios1a\nShared Ethernet Adapter: ent4\nVirtual trunk: ent3 (trunk)\nHA mode: Sharing"));
    vlanDefs.forEach((g) => edges.push(edge(g.id, g.sea, "bridge", "VLAN " + g.vlan + " bridged via SEA")));
    nodes.push(box("p1", "<b>EtherChannel</b>\nent0 + ent1\n<i>Link Aggregation</i>", "phys", NCOL.phys, 0,
      "Physical adapter: ent0 + ent1\nMode: 802.3ad (LACP)\nSpeed: 2x25 Gbps\nUplink: core-switch-a/b"));
    edges.push(edge("s1", "p1", "ent4 → phys", "SEA backed by physical EtherChannel"));
    return { nodes: nodes, edges: edges };
  }

  function vnetData_B() {
    const nodes = [], edges = [];
    const cDefs = [
      { id: "c1", n: "aix-erp-01", lid: 21, vlan: 300 },
      { id: "c2", n: "aix-erp-02", lid: 22, vlan: 300 },
      { id: "c3", n: "aix-mgmt-01", lid: 23, vlan: 999 },
    ];
    const cy = rows(cDefs.length, 150);
    cDefs.forEach((c, i) => nodes.push(box(c.id, "<b>" + c.n + "</b>\nLPAR ID " + c.lid + " · ent0", "client", NCOL.client, cy[i],
      "Client LPAR: " + c.n + "\nLPAR ID: " + c.lid + "\nVirtual adapter: ent0\nPVID: " + c.vlan)));
    const vlanDefs = [
      { id: "g1", vlan: 300, sw: "DefaultSwitch", sea: "s1" },
      { id: "g2", vlan: 999, sw: "MgmtSwitch", sea: "s1" },
    ];
    const gy = rows(vlanDefs.length, 220);
    vlanDefs.forEach((g, i) => nodes.push(box(g.id, "<b>VLAN " + g.vlan + "</b>\nvSwitch: " + g.sw, "vlan", NCOL.vlan, gy[i],
      "VLAN ID: " + g.vlan + "\nVirtual Switch: " + g.sw)));
    cDefs.forEach((c) => {
      const g = vlanDefs.find((v) => v.vlan === c.vlan);
      edges.push(edge(c.id, g.id, "PVID " + c.vlan, "Client " + c.n + "\nPVID: " + c.vlan));
    });
    nodes.push(box("s1", "<b>vio1</b>\nSEA ent5\n<i>ent2 (trunk)</i>", "vios", NCOL.vios, 0,
      "VIO Server: vio1\nShared Ethernet Adapter: ent5\nVirtual trunk: ent2\nHA mode: Auto"));
    vlanDefs.forEach((g) => edges.push(edge(g.id, g.sea, "bridge", "VLAN " + g.vlan + " bridged via SEA")));
    nodes.push(box("p1", "<b>Physical</b>\nent0\n<i>Single link</i>", "phys", NCOL.phys, 0,
      "Physical adapter: ent0\nSpeed: 10 Gbps\nUplink: tor-switch-1"));
    edges.push(edge("s1", "p1", "ent5 → phys", "SEA backed by physical adapter"));
    return { nodes: nodes, edges: edges };
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
    // Also pick up client names discovered from lsmap
    Object.keys(lsmap).forEach((v) => (lsmap[v] || []).forEach((m) => {
      if (m.clntname && clientNames.indexOf(m.clntname) < 0) clientNames.push(m.clntname);
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
        ? '<span class="cmd-badge-ok">✓ ok</span>'
        : '<span class="cmd-badge-err">✕ failed</span>';
      return '<div class="cmd-block">' +
        '<div class="cmd-head"><i data-lucide="chevron-right" class="w-3.5 h-3.5"></i>' +
        escapeHtml(c.title) + " " + badge + "</div>" +
        '<div class="cmd-cmd"># ' + escapeHtml(c.command) + "</div>" +
        '<pre class="cmd-out">' + escapeHtml(c.output) + "</pre>" +
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
  const LIVE_NPIV = {};

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
    // Live NPIV built from real lshwres / lsmap output takes precedence.
    if (tab === "npiv") {
      const live = LIVE_NPIV[liveKey()];
      if (live && live.graph) return live.graph;
    }
    if (ms && DATA[ms]) return DATA[ms][tab];
    const key = DEMO_KEYS[demoIndex % DEMO_KEYS.length];
    return DATA[key][tab];
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
    if (statusEl) statusEl.textContent = "· running lshwres / lsmap on the HMC…";
    document.getElementById("cmd-output-body").innerHTML =
      '<div class="text-sm text-slate-500">Executing HMC commands…</div>';

    let payload = null;
    try {
      payload = await fetch("/api/hmcs/" + localHMCId +
        "/managed-systems/" + encodeURIComponent(ms) + "/vfc-topology").then((r) => r.json());
    } catch (e) {
      payload = { ok: false, commands: [{ title: "vfc-topology", command: "(request failed)", output: String(e), ok: false }] };
    }

    renderCommandPanel(payload && payload.commands);

    if (payload && payload.ok && Array.isArray(payload.fc_adapters) && payload.fc_adapters.length) {
      LIVE_NPIV[key] = { payload: payload, graph: buildNpivFromLive(payload) };
      if (currentTab === "npiv") buildNetwork("npiv");
      setStatus("Virtual Fibre Channel topology built from live HMC output. Click any node to isolate its path.");
    } else {
      LIVE_NPIV[key] = null;
      setStatus("No virtual FC adapters returned — showing representative topology.");
    }
  }


  // Track whether a linear-focus is active per tab.
  const FOCUS_MODE = { npiv: false, vscsi: false, vnet: false };

  function buildNetwork(tab) {
    const src = datasetFor(tab);

    const container = document.getElementById("net-" + tab);
    const nodes = new vis.DataSet(src.nodes.map((n) => Object.assign({}, n)));
    const edges = new vis.DataSet(src.edges.map((e, i) => Object.assign({ id: "e" + tab + i }, e)));
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

  function connectedSet(tab, startId) {
    const edges = NET[tab].edges;
    const adj = {};
    edges.get().forEach((e) => {
      (adj[e.from] = adj[e.from] || []).push(e.to);
      (adj[e.to] = adj[e.to] || []).push(e.from);
    });
    const seen = new Set([startId]);
    const stack = [startId];
    while (stack.length) {
      const cur = stack.pop();
      (adj[cur] || []).forEach((nb) => { if (!seen.has(nb)) { seen.add(nb); stack.push(nb); } });
    }
    return seen;
  }

  function isolate(tab, startId) {
    const nodes = NET[tab].nodes, edges = NET[tab].edges;
    const keep = connectedSet(tab, startId);
    nodes.update(nodes.get().map((n) => {
      const active = keep.has(n.id);
      const c = C[n._kind];
      return {
        id: n.id, opacity: active ? 1 : 0.18,
        color: { background: active ? c.bg : "#f8fafc", border: active ? c.border : "#e2e8f0" },
        font: { color: active ? c.font : "#cbd5e1" },
      };
    }));
    edges.update(edges.get().map((e) => {
      const active = keep.has(e.from) && keep.has(e.to);
      return {
        id: e.id,
        color: { color: active ? "#0f172a" : "#e2e8f0", opacity: active ? 1 : 0.25 },
        width: active ? 2.5 : 1,
        font: { color: active ? "#0f172a" : "#e2e8f0", strokeColor: "#ffffff", strokeWidth: 4 },
      };
    }));
    const label = nodes.get(startId).label.replace(/<[^>]+>/g, "").split("\n")[0];
    setStatus("Isolated path for “" + label + "” — " + keep.size + " connected node(s) highlighted.");
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
      // Release fixed positions only when coming out of linear-focus mode.
      if (wasFocused) update.fixed = { x: false, y: false };
      return update;
    }));
    edges.update(edges.get().map((e) => ({
      id: e.id, hidden: false,
      color: { color: "#94a3b8", opacity: 1 }, width: 1.5,
      font: { color: "#475569", strokeColor: "#ffffff", strokeWidth: 4 },
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

  function showTab(tab) {
    currentTab = tab;
    document.querySelectorAll(".topo-tab-btn").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
    document.querySelectorAll("#topology-app .tab-pane").forEach((p) => p.classList.toggle("active", p.id === "pane-" + tab));
    document.getElementById("flow-label").innerHTML =
      '<i data-lucide="git-branch" class="w-4 h-4"></i><span>' + FLOW_LABELS[tab] + "</span>";
    renderLegend(tab);
    if (window.lucide) lucide.createIcons();
    buildNetwork(tab);

    // The HMC command output only applies to the Virtual Fibre Channel tab.
    if (tab === "npiv") {
      loadLiveNpiv();
    } else {
      hideCommandPanel();
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
    // Refresh the live VFC commands + graph whenever the selection changes
    // while the NPIV tab is active.
    if (currentTab === "npiv") {
      loadLiveNpiv();
    } else {
      hideCommandPanel();
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

    // Collapse / expand the command output panel body
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




