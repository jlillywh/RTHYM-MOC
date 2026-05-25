# Copyright (c) 2026 Jason Lillywhite <jason@lillywhitewater.com>
# SPDX-License-Identifier: MIT
# Author: Jason Lillywhite <jason@lillywhitewater.com>
"""rthym_moc.epanet
~~~~~~~~~~~~~~~~
Parse an EPANET .inp network file and return a configured MOCSolver.

Public API
----------
>>> solver = rthym_moc.load_inp("network.inp")
>>> results = solver.run(total_time=10.0, dt=0.01)

Supported sections
------------------
 [JUNCTIONS]   → Junction nodes
 [RESERVOIRS]  → PressureBoundary nodes
 [TANKS]       → Tank nodes
 [PIPES]       → PipeInput  (H-W, D-W, and C-M roughness)
 [PUMPS]       → Pump node  + two stub pipes (H-Q curve via [CURVES])
 [VALVES]      → Valve node + two stub pipes (TCV, PRV, PSV, PBV)
 [CURVES]      → Pump H-Q curves
 [STATUS]      → Per-link status overrides (OPEN / CLOSED / CV)
 [OPTIONS]     → Units, Headloss formula
 [RTHYM]       → Surge-control component overrides (Standpipe, HydropneumaticTank, AirValve)

Ignored sections
----------------
PATTERNS, CONTROLS, RULES, DEMANDS, EMITTERS, QUALITY, REACTIONS,
ENERGY, COORDINATES, VERTICES, LABELS, BACKDROP, TITLE.

Initial flows
-------------
EPANET .inp files do not store computed steady-state flows.  When
``use_wntr=True`` (default) and ``wntr`` is installed, a single-period
hydraulic simulation is run to populate pipe flows.  You can also supply
flows explicitly via the ``initial_flows`` keyword.  Without either,
flows default to 0 and a UserWarning is emitted.

    pip install wntr          # or: pip install 'rthym-moc[inp]'

Pump / valve topology
---------------------
EPANET treats pumps and valves as *links* (connecting two existing nodes).
rthym_moc requires them to be *nodes*.  Each pump/valve link is replaced by:

    Node1 ──[_P_<id>_up: stub pipe]──> _PUMP_<id> or _VALVE_<id>
          ──[_P_<id>_dn: stub pipe]──> Node2

Stub pipes are ``_STUB_LEN_FT`` ft long (40 ft → 1 segment at dt=0.01 s)
"""
from __future__ import annotations

import math
import os
import warnings
from typing import Optional

from . import MOCSolver, NodeInput, PipeInput

# ── Physical constant ─────────────────────────────────────────────────────────
_M3S_TO_GPM = 15_850.3   # m³/s → US GPM

# Stub pipe length (ft).  Must satisfy L = n * a*dt for integer n, so that
# the MOC grid preserves the wave speed exactly in the stub.
# At a=4000 ft/s, dt=0.01 s: dx = 40 ft.
#   40 ft → round(40/40)=1 seg → a_stub = 40/0.01 = 4000 ft/s  ✓
#   80 ft → round(80/40)=2 seg → a_stub = (80/2)/0.01 = 4000 ft/s  also ✓
#
# We prefer 40 ft (1 segment) because a single-segment stub has NO interior
# nodes: the C+/C- boundary characteristics use the actual pipe-endpoint HGL
# values directly.  With 2 segments, the intermediate node is initialised at
# the mid-point of the upstream-to-downstream HGL gradient across the valve
# (up to ~37 ft for a 75 ft head-drop valve), which injects a spurious
# pressure pulse into the transient at t=0.
_STUB_LEN_FT = 40.0

# ── EPANET unit-system tables ─────────────────────────────────────────────────
_US_UNITS = {"GPM", "CFS", "MGD", "IMGD", "AFD"}
_SI_UNITS = {"LPS", "LPM", "MLD", "CMH", "CMD"}

# Flow → GPM
_FLOW_TO_GPM: dict[str, float] = {
    "GPM":  1.0,
    "CFS":  448.831,
    "MGD":  694.444,
    "IMGD": 832.674,
    "AFD":  226.286,
    "LPS":  15.8503,
    "LPM":  0.264172,
    "MLD":  183.453,
    "CMH":  4.40287,
    "CMD":  0.183453,
}

# Length, elevation, head → ft  (US = ft, SI = m)
_LEN_TO_FT: dict[str, float] = {
    **{k: 1.0     for k in _US_UNITS},
    **{k: 3.28084 for k in _SI_UNITS},
}

# Pipe diameter → inches  (US = in, SI = mm)
_DIAM_TO_IN: dict[str, float] = {
    **{k: 1.0     for k in _US_UNITS},
    **{k: 0.039370 for k in _SI_UNITS},
}

# Tank diameter → ft  (US = ft, SI = m)
_TANK_DIAM_TO_FT: dict[str, float] = dict(_LEN_TO_FT)

# Pressure setpoint (PRV/PSV setting) → ft  (US = psi → ft, SI = m → ft)
_PRES_TO_FT: dict[str, float] = {
    **{k: 2.31    for k in _US_UNITS},
    **{k: 3.28084 for k in _SI_UNITS},
}

# Valve types that use pressure setpoints (not % open)
_PRESSURE_VALVE_TYPES = {"PRV", "PSV", "PBV"}
# Valve types with no direct rthym_moc equivalent
_UNSUPPORTED_VALVE_TYPES = {"FCV", "GPV"}


# ── INP parser ────────────────────────────────────────────────────────────────

def _parse_inp(path: str) -> dict[str, list[list[str]]]:
    """Return {SECTION_NAME: [[token, ...], ...]} for all sections.

    Also parses the custom ``[RTHYM]`` section used by the R-THYM app to
    annotate nodes with their actual component type and parameters::

        [RTHYM]
        ; NodeID          Type                  param=value …
        SP1               Standpipe             tank_area=10.0
        HPT1              HydropneumaticTank    gas_volume=20.0 tank_volume=50.0

    The ``[RTHYM]`` section is silently ignored by EPANET simulators, so the
    file remains fully valid EPANET .inp format.
    """
    sections: dict[str, list[list[str]]] = {}
    current: Optional[str] = None
    with open(path, encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.split(";")[0].strip()
            if not line:
                continue
            if line.startswith("["):
                current = line.strip("[]").upper().strip()
                sections.setdefault(current, [])
            elif current is not None:
                tokens = line.split()
                if tokens:
                    sections[current].append(tokens)
    return sections


def _get_option(sec: dict, key: str, default: str) -> str:
    """Look up a keyword in [OPTIONS]; return default if absent."""
    for row in sec.get("OPTIONS", []):
        if row and row[0].upper() == key.upper() and len(row) >= 2:
            return row[1].upper()
    return default


# ── [RTHYM] section parser ────────────────────────────────────────────────────

# NodeType strings that map to surge-control components
_RTHYM_SURGE_TYPES = {"Standpipe", "HydropneumaticTank", "AirValve"}

def _parse_rthym_overrides(
    sec: dict,
    lf: float,
) -> dict[str, dict]:
    """Parse the optional ``[RTHYM]`` section.

    Each row has the form::

        NodeID   NodeType   key=value …

    Supported types and their recognised ``key=value`` parameters
    (all numeric values already in US customary units as given in the file):

        **Standpipe** (R-THYM ``SurgeControl``):
            - ``tank_area`` — ft² cross-sectional area of the standpipe

        **HydropneumaticTank** (R-THYM ``SurgeTank``):
            - ``gas_volume``    — ft³ initial trapped gas
            - ``tank_volume``   — ft³ total vessel volume
            - ``polytropic_n``  — polytropic exponent (default 1.2)
            - ``loss_coeff_in`` — discharge coeff for inflow (default 0.7)
            - ``loss_coeff_out``— discharge coeff for outflow (default 0.7)
            - ``diameter``      — inches, orifice connection diameter

        **AirValve** (R-THYM ``AirValve``):
            - ``air_release_head``     — ft vent reference above node elevation
            - ``diameter``             — inches, large-orifice air-admission diameter
            - ``air_release_diameter`` — inches, small-orifice air-release diameter
            - ``gas_volume``           — ft³ initial trapped air-pocket volume
            - ``tank_volume``          — ft³ air-valve chamber volume
            - ``loss_coeff_in``        — admission discharge coefficient
            - ``loss_coeff_out``       — release discharge coefficient

    Returns
    -------
    dict
        ``{node_id: {"node_type": str, **params}}``
    """
    overrides: dict[str, dict] = {}
    for row in sec.get("RTHYM", []):
        if len(row) < 2:
            continue
        nid   = row[0]
        ntype = row[1]
        if ntype not in _RTHYM_SURGE_TYPES:
            warnings.warn(
                f"[RTHYM] section: node '{nid}' has unrecognised type '{ntype}'; "
                "row ignored.",
                UserWarning, stacklevel=4,
            )
            continue
        params: dict = {"node_type": ntype}
        for tok in row[2:]:
            if "=" in tok:
                k, _, v = tok.partition("=")
                try:
                    params[k.strip()] = float(v.strip())
                except ValueError:
                    pass
        overrides[nid] = params
    return overrides


# ── Roughness conversions ─────────────────────────────────────────────────────

def _hw_from_dw(epsilon_mm: float, diameter_mm: float) -> float:
    """Approximate Hazen-Williams C from Darcy-Weisbach ε [mm] at V=1 m/s."""
    D   = max(diameter_mm, 1.0) / 1000.0   # m
    eps = max(epsilon_mm,  1e-6) / 1000.0  # m
    nu  = 1.007e-6                          # m²/s  (20 °C)
    Re  = 1.0 * D / nu
    f   = 0.25 / (math.log10(eps / (3.7 * D) + 5.74 / Re**0.9))**2
    hf_per_m = f / D * 1.0**2 / (2.0 * 9.81)   # m head loss per m at V=1 m/s
    Q = math.pi * (D / 2.0)**2                   # m³/s at V=1 m/s
    denom = hf_per_m * D**4.87
    if denom <= 0.0:
        return 130.0
    C = (10.67 * Q**1.852 / denom) ** (1.0 / 1.852)
    return max(50.0, min(160.0, C))


def _hw_from_manning(n: float, diameter_in: float) -> float:
    """Approximate H-W C from Manning's n for a full circular pipe."""
    R = (diameter_in / 12.0) / 4.0   # hydraulic radius (ft), full pipe
    if n <= 0.0:
        return 130.0
    C = 0.849 * (R ** (1.0 / 6.0)) / n
    return max(50.0, min(160.0, C))


# ── Pump helpers ──────────────────────────────────────────────────────────────

def _parse_curves(sec: dict) -> dict[str, list[tuple[float, float]]]:
    """Parse [CURVES] → {curve_id: [(x, y), ...]} sorted ascending by x."""
    curves: dict[str, list[tuple[float, float]]] = {}
    for row in sec.get("CURVES", []):
        if len(row) < 3:
            continue
        try:
            x, y = float(row[1]), float(row[2])
        except ValueError:
            continue
        curves.setdefault(row[0], []).append((x, y))
    for cid in curves:
        curves[cid].sort()
    return curves


def _pump_design_point(
    pump_id: str,
    params: list[str],
    curves: dict[str, list[tuple[float, float]]],
    ff: float,
    lf: float,
) -> tuple[float, float]:
    """
    Return ``(design_head_ft, design_flow_gpm)`` for an EPANET pump link.
    *params* is every token after [Node1, Node2] on the [PUMPS] row.
    Uses the mid-curve point as an approximation of the BEP.
    """
    kw: dict[str, str] = {}
    i = 0
    while i + 1 < len(params):
        kw[params[i].upper()] = params[i + 1]
        i += 2

    if "HEAD" in kw:
        cid = kw["HEAD"]
        pts = curves.get(cid)
        if pts:
            mid = pts[len(pts) // 2]
            return float(mid[1]) * lf, float(mid[0]) * ff   # (head_ft, flow_gpm)
        warnings.warn(
            f"Pump '{pump_id}': HEAD curve '{cid}' not found in [CURVES]; "
            "using default design point (100 ft, 100 GPM).",
            UserWarning, stacklevel=4,
        )
    elif "POWER" in kw:
        warnings.warn(
            f"Pump '{pump_id}': uses POWER keyword (no H-Q curve); "
            "using default design point (100 ft, 100 GPM).",
            UserWarning, stacklevel=4,
        )
    else:
        warnings.warn(
            f"Pump '{pump_id}': cannot determine design point; "
            "using default (100 ft, 100 GPM).",
            UserWarning, stacklevel=4,
        )
    return 100.0, 100.0


# ── Valve helpers ─────────────────────────────────────────────────────────────

def _tcv_km_to_pct(km: float) -> float:
    """Convert EPANET TCV loss coefficient K_m → rthym_moc % open.

    rthym_moc valve model:  K = (100/s)² − 1  →  s = 100 / √(K+1)
    """
    return 100.0 / math.sqrt(max(km, 0.0) + 1.0)


# ── wntr steady-state solve ───────────────────────────────────────────────────

def _wntr_hydraulics(path: str) -> tuple[dict[str, float], dict[str, float]]:
    """Run wntr's EPANET solver; return ``({link_id: flow_gpm}, {node_id: head_ft})``.

    Returns empty dicts on ImportError or solver failure.
    wntr always reports flows in m³/s and heads in m, regardless of the
    .inp Units setting.
    """
    try:
        import wntr  # type: ignore[import]
    except ImportError:
        warnings.warn(
            "wntr is not installed — initial pipe flows will be 0.\n"
            "Install with:  pip install wntr\n"
            "          or:  pip install 'rthym-moc[inp]'",
            UserWarning, stacklevel=3,
        )
        return {}, {}
    try:
        wn  = wntr.network.WaterNetworkModel(path)
        sim = wntr.sim.EpanetSimulator(wn)
        res = sim.run_sim()
        flows = {str(lid): float(q) * _M3S_TO_GPM
                 for lid, q in res.link["flowrate"].iloc[0].items()}
        heads = {str(nid): float(h) / 0.3048          # m → ft
                 for nid, h in res.node["head"].iloc[0].items()}
        return flows, heads
    except Exception as exc:  # noqa: BLE001
        warnings.warn(
            f"wntr hydraulic solve failed ({exc}) — initial pipe flows will be 0.",
            UserWarning, stacklevel=3,
        )
        return {}, {}


# ── Public API ────────────────────────────────────────────────────────────────

def load_inp(
    path: str,
    *,
    use_wntr: bool = True,
    initial_flows: Optional[dict[str, float]] = None,
    initial_heads: Optional[dict[str, float]] = None,
    stub_length_ft: Optional[float] = None,
) -> MOCSolver:
    """Read an EPANET .inp file and return a configured :class:`MOCSolver`.

    Parameters
    ----------
    path : str
        Path to the EPANET .inp file.
    use_wntr : bool, optional
        When ``True`` (default), ``wntr`` is used (if installed) to run a
        single-period hydraulic simulation and populate initial steady-state
        pipe flows.  If wntr is unavailable or the solve fails, flows default
        to 0 and a ``UserWarning`` is emitted.
    initial_flows : dict[str, float] or None, optional
        Explicit ``{link_id: flow_gpm}`` overrides applied *after* any wntr
        result.  Useful when wntr is not installed or when you want to model
        a specific operating point that differs from the EPANET steady state.
        Sign convention: positive = flow in the ``from_node → to_node``
        direction as defined in the .inp file.

        Key convention:
        - For regular pipes: use the EPANET pipe ID (same as the rthym_moc pipe ID).
        - For pump/valve links: use the *original EPANET link ID* (e.g. ``"V1"``,
          not ``"_P_V1_up"``).  The supplied flow is applied to both stub pipes.
    initial_heads : dict[str, float] or None, optional
        Explicit ``{node_id: head_ft}`` overrides for the initial piezometric
        head (HGL in ft) at junction and inline valve/pump nodes.  Applied
        *after* any wntr result.  Use this when wntr is not available and you
        need to supply steady-state heads manually so the MOC grid is
        initialised correctly for networks where intermediate nodes are not
        connected to a reservoir on both sides.

        Key convention: use the EPANET node ID for junctions and the
        generated ``_VALVE_<id>`` / ``_PUMP_<id>`` ID for inline elements.
    stub_length_ft : float or None, optional
        Length (ft) of the fictitious stub pipes inserted on each side of
        every valve and pump node.  Must be a positive multiple of
        ``a * dt`` (wave speed × time step) so the MOC Courant condition is
        satisfied exactly.  Defaults to the module-level ``_STUB_LEN_FT``
        (40 ft at a=4000 ft/s, dt=0.01 s).

        **Choosing a value**: partial reflections from the stub/pipe diameter
        change attenuate the valve pressure rise whenever the stub is shorter
        than ``a * T_closure / 2``.  For fast closures (e.g. T_closure=0.35 s,
        a=4000 ft/s) set ``stub_length_ft ≥ 700`` ft to prevent reflected
        waves from returning during closure::

            stub_length_ft = ceil(a * T_closure / 2 / dx) * dx
            # e.g. ceil(4000 * 0.35 / 2 / 40) * 40 = 720 ft → use 800 ft

    Returns
    -------
    MOCSolver
        Fully populated solver.  Call ``solver.run()`` to execute a transient.

    Raises
    ------
    FileNotFoundError
        If *path* does not exist.
    ValueError
        If the ``Units`` keyword in ``[OPTIONS]`` is not recognised.

    Notes
    -----
    **Pump and valve links** are converted to inline nodes with two stub pipes
    each (see module docstring).  Generated IDs follow the pattern
    ``_PUMP_<id>``, ``_VALVE_<id>``, ``_P_<id>_up``, ``_P_<id>_dn``.

    **PRV / PSV / PBV** settings are pressure setpoints; they cannot be
    converted to a % open value without full system knowledge and are
    initialised at 100 % open (fully open) with a ``UserWarning``.

    **D-W and C-M roughness** values are converted to approximate H-W C
    values using the Swamee-Jain and Manning approximations respectively.

    **Minor losses** (column 7 of ``[PIPES]``) are imported as a dimensionless
    local-loss coefficient and distributed across the pipe for the transient
    resistance term.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"EPANET .inp file not found: {path!r}")

    _stub_len = float(stub_length_ft) if stub_length_ft is not None else _STUB_LEN_FT

    sec   = _parse_inp(path)
    units = _get_option(sec, "UNITS",    "GPM")
    hloss = _get_option(sec, "HEADLOSS", "H-W")

    if units not in _FLOW_TO_GPM:
        raise ValueError(
            f"Unrecognised EPANET Units value {units!r}. "
            f"Supported: {sorted(_FLOW_TO_GPM)}"
        )

    ff  = _FLOW_TO_GPM[units]           # flow     → GPM
    lf  = _LEN_TO_FT[units]             # length   → ft
    df  = _DIAM_TO_IN[units]            # pipe diam → in
    tdf = _TANK_DIAM_TO_FT[units]       # tank diam → ft

    if hloss not in ("H-W", "D-W", "C-M"):
        warnings.warn(
            f"Headloss formula {hloss!r} is not H-W, D-W, or C-M; "
            "roughness values will be passed through as H-W C.",
            UserWarning, stacklevel=2,
        )

    curves = _parse_curves(sec)
    rthym_overrides = _parse_rthym_overrides(sec, lf)

    # Per-link STATUS overrides from [STATUS] section
    status_map: dict[str, str] = {
        row[0].upper(): row[1].upper()
        for row in sec.get("STATUS", [])
        if len(row) >= 2
    }

    # ── Nodes ─────────────────────────────────────────────────────────────────
    nodes: dict[str, NodeInput] = {}

    for row in sec.get("JUNCTIONS", []):
        if len(row) < 2:
            continue
        nid  = row[0]
        elev = float(row[1]) * lf
        dem  = float(row[2]) * ff if len(row) >= 3 else 0.0
        n = NodeInput()
        n.id = nid;  n.type = "Junction"
        n.elevation = elev;  n.demand = dem
        nodes[nid] = n

    for row in sec.get("RESERVOIRS", []):
        if len(row) < 2:
            continue
        nid  = row[0]
        head = float(row[1]) * lf
        n = NodeInput()
        n.id = nid;  n.type = "PressureBoundary"
        n.elevation = 0.0;  n.head = head
        nodes[nid] = n

    for row in sec.get("TANKS", []):
        if len(row) < 6:
            continue
        nid       = row[0]
        elev      = float(row[1]) * lf
        init_lv   = float(row[2]) * lf
        max_lv    = float(row[4]) * lf
        diam_tank = float(row[5]) * tdf                    # ft
        area      = math.pi * (diam_tank / 2.0) ** 2      # ft²
        n = NodeInput()
        n.id = nid;  n.type = "Tank"
        n.elevation = elev
        n.head      = elev + init_lv    # HGL = bottom + current water level
        n.level     = (100.0 * init_lv / max_lv) if max_lv > 0.0 else 0.0
        n.max_level = max_lv
        n.tank_area = area
        nodes[nid] = n

    # ── Pipes ─────────────────────────────────────────────────────────────────
    pipes: list[PipeInput] = []
    check_valve_nodes: list[NodeInput] = []
    check_valve_stubs: list[PipeInput] = []
    check_valve_link_ids: list[str] = []

    for row in sec.get("PIPES", []):
        if len(row) < 6:
            continue
        pid   = row[0]
        frm   = row[1]
        to_   = row[2]
        L     = float(row[3]) * lf
        diam  = float(row[4]) * df      # → in
        rough = float(row[5])
        minor_loss = float(row[6]) if len(row) >= 7 else 0.0

        # Status: column 7 (index 7) may be OPEN / CLOSED / CV;
        # [STATUS] section overrides take precedence.
        status_col = row[7].upper() if len(row) >= 8 else "OPEN"
        eff_st = status_map.get(pid.upper(), status_col)

        if eff_st == "CLOSED":
            warnings.warn(
                f"Pipe '{pid}' is CLOSED — included with flow_gpm=0. "
                "Remove it from the solver after load_inp() if unintended.",
                UserWarning, stacklevel=2,
            )

        # Convert roughness to H-W C
        if hloss == "D-W":
            eps_mm  = rough if units in _SI_UNITS else rough * 0.3048 * 1000.0
            hw_c    = _hw_from_dw(eps_mm, diam * 25.4)
        elif hloss == "C-M":
            hw_c = _hw_from_manning(rough, diam)
        else:
            hw_c = rough    # already H-W C

        if eff_st == "CV":
            nid = f"_CHECKVALVE_{pid}"
            cn = NodeInput()
            cn.id = nid
            cn.type = "CheckValve"
            cn.elevation = nodes[frm].elevation if frm in nodes else 0.0
            cn.head = nodes[frm].head if frm in nodes else 100.0
            cn.diameter = diam
            check_valve_nodes.append(cn)
            check_valve_link_ids.append(pid)

            split_length = max(L / 2.0, 1.0)
            split_minor_loss = max(0.0, minor_loss) / 2.0

            up = PipeInput()
            up.id = f"_CV_{pid}_up"; up.from_node = frm; up.to_node = nid
            up.length = split_length; up.diameter = diam; up.roughness = hw_c
            up.minor_loss = split_minor_loss
            up.flow_gpm = 0.0

            dn = PipeInput()
            dn.id = f"_CV_{pid}_dn"; dn.from_node = nid; dn.to_node = to_
            dn.length = split_length; dn.diameter = diam; dn.roughness = hw_c
            dn.minor_loss = split_minor_loss
            dn.flow_gpm = 0.0

            check_valve_stubs.extend([up, dn])
            continue

        p = PipeInput()
        p.id = pid;  p.from_node = frm;  p.to_node = to_
        p.length    = max(L, 1.0)
        p.diameter  = diam
        p.roughness = hw_c
        p.minor_loss = max(0.0, minor_loss)
        p.flow_gpm  = 0.0   # populated below
        pipes.append(p)

    # ── Pumps (links → Pump node + 2 stub pipes) ──────────────────────────────
    pump_nodes:    list[NodeInput] = []
    pump_stubs:    list[PipeInput] = []
    pump_link_ids: list[str]       = []   # original EPANET link IDs (for flow lookup)

    for row in sec.get("PUMPS", []):
        if len(row) < 4:
            continue
        lid = row[0];  frm = row[1];  to_ = row[2]
        dh, qd = _pump_design_point(lid, row[3:], curves, ff, lf)

        nid = f"_PUMP_{lid}"
        pn  = NodeInput()
        pn.id = nid;  pn.type = "Pump"
        pn.elevation = nodes[frm].elevation if frm in nodes else 0.0
        pn.design_head = dh;  pn.design_flow = qd
        pn.current_speed = 100.0
        pump_nodes.append(pn)
        pump_link_ids.append(lid)

        up = PipeInput()
        up.id = f"_P_{lid}_up";  up.from_node = frm;  up.to_node = nid
        up.length = _stub_len;  up.diameter = 12.0;  up.roughness = 130.0

        dn = PipeInput()
        dn.id = f"_P_{lid}_dn";  dn.from_node = nid;  dn.to_node = to_
        dn.length = _stub_len;  dn.diameter = 12.0;  dn.roughness = 130.0

        pump_stubs.extend([up, dn])

    # ── Valves (links → Valve node + 2 stub pipes) ────────────────────────────
    valve_nodes:    list[NodeInput] = []
    valve_stubs:    list[PipeInput] = []
    valve_link_ids: list[str]       = []

    for row in sec.get("VALVES", []):
        if len(row) < 6:
            continue
        lid   = row[0];  frm = row[1];  to_ = row[2]
        diam  = float(row[3]) * df
        vtype = row[4].upper()
        setting = float(row[5])

        if vtype == "TCV":
            pct = _tcv_km_to_pct(setting)
        elif vtype in _PRESSURE_VALVE_TYPES:
            warnings.warn(
                f"Valve '{lid}' ({vtype}): setting is a pressure setpoint "
                f"({setting:.2f}), not a % open.  Initialised at 100 % open. "
                "Adjust current_setting on the returned solver if needed.",
                UserWarning, stacklevel=2,
            )
            pct = 100.0
        elif vtype in _UNSUPPORTED_VALVE_TYPES:
            warnings.warn(
                f"Valve '{lid}' (type {vtype}) is not supported; "
                "treated as a fully-open valve (100 %).",
                UserWarning, stacklevel=2,
            )
            pct = 100.0
        else:
            warnings.warn(
                f"Valve '{lid}': unrecognised type '{vtype}'; "
                f"treating as TCV with setting={setting}.",
                UserWarning, stacklevel=2,
            )
            pct = _tcv_km_to_pct(setting)

        nid = f"_VALVE_{lid}"
        vn  = NodeInput()
        vn.id = nid;  vn.type = "Valve"
        vn.elevation = nodes[frm].elevation if frm in nodes else 0.0
        vn.diameter = diam;  vn.current_setting = pct
        valve_nodes.append(vn)
        valve_link_ids.append(lid)

        up = PipeInput()
        up.id = f"_P_{lid}_up";  up.from_node = frm;  up.to_node = nid
        up.length = _stub_len;  up.diameter = diam;  up.roughness = 130.0

        dn = PipeInput()
        dn.id = f"_P_{lid}_dn";  dn.from_node = nid;  dn.to_node = to_
        dn.length = _stub_len;  dn.diameter = diam;  dn.roughness = 130.0

        valve_stubs.extend([up, dn])

    # ── Initial flows ─────────────────────────────────────────────────────────
    init_flows: dict[str, float] = {}
    init_heads: dict[str, float] = {}

    if use_wntr:
        init_flows, init_heads = _wntr_hydraulics(path)

    # User-supplied overrides applied last (highest priority)
    if initial_flows:
        init_flows.update(initial_flows)
    if initial_heads:
        init_heads.update(initial_heads)

    # ── Propagate initial piezometric heads to junction nodes ─────────────────
    # Junction nodes default to head=100 ft; update from wntr (or the caller's
    # initial_heads dict) so the MOC grid (initGrid) can correctly initialise
    # the HGL in pipes whose both endpoints are non-reservoir nodes (e.g.
    # valve/pump stub pipes).
    for jid, jn in nodes.items():
        if jn.type == "Junction" and jid in init_heads:
            jn.head = init_heads[jid]

    for tid, tn in nodes.items():
        if tn.type == "Tank" and tid in init_heads:
            tn.head = init_heads[tid]
            if tn.max_level > 0.0:
                tn.level = 100.0 * (tn.head - tn.elevation) / tn.max_level

    # For generated valve/pump inline nodes, prefer an explicit entry in
    # init_heads keyed by the generated ID; fall back to the upstream
    # junction's head.
    for i, (lid, vn) in enumerate(zip(valve_link_ids, valve_nodes)):
        row = next(
            r for r in sec.get("VALVES", []) if len(r) >= 2 and r[0] == lid
        )
        frm_nid = row[1]
        vn.head = init_heads.get(vn.id, init_heads.get(frm_nid, vn.head))

    for i, (lid, pn) in enumerate(zip(pump_link_ids, pump_nodes)):
        row = next(
            r for r in sec.get("PUMPS", []) if len(r) >= 2 and r[0] == lid
        )
        frm_nid = row[1]
        pn.head = init_heads.get(pn.id, init_heads.get(frm_nid, pn.head))

    for lid, cn in zip(check_valve_link_ids, check_valve_nodes):
        row = next(
            r for r in sec.get("PIPES", []) if len(r) >= 2 and r[0] == lid
        )
        frm_nid = row[1]
        cn.head = init_heads.get(cn.id, init_heads.get(frm_nid, cn.head))

    for p in pipes:
        p.flow_gpm = init_flows.get(p.id, p.flow_gpm)

    # Stub pipes inherit the flow of the corresponding pump/valve link
    for i, lid in enumerate(pump_link_ids):
        q = init_flows.get(lid, 0.0)
        pump_stubs[2 * i].flow_gpm     = q
        pump_stubs[2 * i + 1].flow_gpm = q

    for i, lid in enumerate(valve_link_ids):
        q = init_flows.get(lid, 0.0)
        valve_stubs[2 * i].flow_gpm     = q
        valve_stubs[2 * i + 1].flow_gpm = q

    for i, lid in enumerate(check_valve_link_ids):
        q = init_flows.get(lid, 0.0)
        check_valve_stubs[2 * i].flow_gpm     = q
        check_valve_stubs[2 * i + 1].flow_gpm = q

    # ── Apply [RTHYM] section overrides (Standpipe / HydropneumaticTank / AirValve) ──
    # These node types are exported to EPANET as plain Junctions for steady-state
    # compatibility.  The [RTHYM] section records their actual type and the
    # physical parameters the MOC solver needs.
    for nid, params in rthym_overrides.items():
        if nid not in nodes:
            warnings.warn(
                f"[RTHYM] section references node '{nid}' which is not found in "
                "[JUNCTIONS] or other node sections; skipped.",
                UserWarning, stacklevel=2,
            )
            continue
        n = nodes[nid]
        ntype = params["node_type"]
        n.type = ntype

        if ntype == "Standpipe":
            if "tank_area" in params:
                n.tank_area = params["tank_area"]
            # head was already populated from wntr (= initial water-surface elev)

        elif ntype == "HydropneumaticTank":
            if "gas_volume"    in params: n.gas_volume    = params["gas_volume"]
            if "tank_volume"   in params: n.tank_volume   = params["tank_volume"]
            if "polytropic_n"  in params: n.polytropic_n  = params["polytropic_n"]
            if "loss_coeff_in" in params: n.loss_coeff_in = params["loss_coeff_in"]
            if "loss_coeff_out"in params: n.loss_coeff_out= params["loss_coeff_out"]
            if "diameter"      in params: n.diameter      = params["diameter"]
            # head from wntr = steady-state pipeline head at the connection node

        elif ntype == "AirValve":
            if "air_release_head" in params:
                n.air_release_head = params["air_release_head"]
            if "diameter" in params:
                n.diameter = params["diameter"]
            if "air_release_diameter" in params:
                n.air_release_diameter = params["air_release_diameter"]
            if "gas_volume" in params:
                n.gas_volume = params["gas_volume"]
            if "tank_volume" in params:
                n.tank_volume = params["tank_volume"]
            if "loss_coeff_in" in params:
                n.loss_coeff_in = params["loss_coeff_in"]
            if "loss_coeff_out" in params:
                n.loss_coeff_out = params["loss_coeff_out"]

    # ── Assemble solver ────────────────────────────────────────────────────────
    solver = MOCSolver()

    for n in list(nodes.values()) + pump_nodes + valve_nodes + check_valve_nodes:
        solver.add_node(n)

    for p in pipes + pump_stubs + valve_stubs + check_valve_stubs:
        solver.add_pipe(p)

    return solver
