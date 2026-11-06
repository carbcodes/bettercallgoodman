"""Strength checker (specs/03-strength.md).

Recomputes the answer to a strength task from task.yaml inputs alone, using
closed-form models. Units everywhere: mm, N, MPa, kg, degrees (N*mm for
moments, N*m / kg*cm only for servo torque, which is how servos are rated).

The checker returns, besides the headline values that claims are compared
against, every intermediate step (moment, Z, sigma_nom, Kt, ...) and a list of
"alternatives" per quantity: the value an answer would get by making a known
mistake (skipping Kt, using datasheet PLA strength, mixing kg*cm and N*m...).
verdict.py uses those to write a `why` that names the specific mistake.

Models (select with `model:` in task.yaml; otherwise inferred from inputs):
  cantilever_root_fillet  end-loaded cantilever, fillet where it meets its support
  cantilever_step         end-loaded cantilever, critical section at a shoulder step
  column                  axial compression: direct stress + Euler/Johnson buckling
  arm_torque              gravity torque of a horizontal arm vs. a servo rating
  cantilever_fatigue      round cantilever, fluctuating load: static + modified Goodman
  simple_beam             simply supported beam, centre load: stress + deflection
  thermal_column          axially restrained bar heated by dT: thermal stress + buckling
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import yaml

VERSION = "0.1"
G = 9.81  # m/s^2, same value the task loads were written with (3 kg -> 29.43 N)
NM_PER_KGCM = G * 0.01  # 1 kg*cm = 0.0981 N*m

_MATERIALS_PATH = Path(__file__).resolve().parent.parent / "materials.yaml"


def load_materials() -> dict:
    with open(_MATERIALS_PATH) as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------- sections

def rect_section(b: float, h: float) -> dict:
    """Rectangle, width b, depth h (h is in the bending plane)."""
    return {"A": b * h, "I": b * h**3 / 12, "Z": b * h**2 / 6, "c": h / 2, "r_gyr": h / math.sqrt(12)}


def round_section(d: float) -> dict:
    """Solid round bar of diameter d."""
    return {"A": math.pi * d**2 / 4, "I": math.pi * d**4 / 64, "Z": math.pi * d**3 / 32,
            "c": d / 2, "r_gyr": d / 4}


# ------------------------------------------------------ stress concentration

def kt_shoulder_bending(D: float, d: float, r: float) -> float:
    """Kt for a flat bar with opposite shoulder fillets, in-plane bending.

    Curve fit from Pilkey & Pilkey, *Peterson's Stress Concentration Factors*
    (3rd ed.), Chart 3.10 (also reproduced in the AMES Web calculator):
        Kt = C1 + C2(2h/D) + C3(2h/D)^2 + C4(2h/D)^3,  h = (D - d)/2
    Kt is referred to sigma_nom = 6M / (t d^2) at the small section.
    APPROXIMATION: the fit is quoted as within a few percent of the chart, and
    FEA studies (e.g. Tipton, Sorem & Schmidt) show the classic shoulder-fillet
    charts can be off by up to ~20%. Good enough to tell Kt ~1.1 from Kt ~2.5.
    """
    if D <= d or r <= 0:
        return 1.0
    h = (D - d) / 2
    hr = min(max(h / r, 0.1), 20.0)  # clamp to the fit's validity range
    s = math.sqrt(hr)
    if hr <= 2.0:
        c1 = 1.006 + 0.967 * s + 0.013 * hr
        c2 = -0.270 - 2.372 * s + 0.708 * hr
        c3 = 0.662 + 1.157 * s - 0.908 * hr
        c4 = -0.405 + 0.249 * s - 0.200 * hr
    else:
        c1 = 1.058 + 1.002 * s - 0.038 * hr
        c2 = -3.652 + 1.639 * s - 0.436 * hr
        c3 = 6.170 - 5.687 * s + 1.175 * hr
        c4 = -2.558 + 3.046 * s - 0.701 * hr
    x = 2 * h / D
    return max(1.0, c1 + c2 * x + c3 * x**2 + c4 * x**3)


# An inside corner where a bar meets a much larger body (the other leg of an
# L-bracket, a mounting plate) has no exact Peterson chart. We model it as a
# shoulder fillet with D/d = 2: for small r/d the bending curves have already
# saturated by D/d ~ 2 (D/d = 3 changes s01's Kt by < 1%), and at large r/d the
# polynomial fit misbehaves beyond D/d ~ 2 (it drops to Kt = 1.0 for s05's
# r/d = 0.63 at D/d = 3, which is non-physical). APPROXIMATION, flagged as such.
L_CORNER_D_OVER_D = 2.0


def kt_l_corner(d: float, r: float) -> float:
    return kt_shoulder_bending(L_CORNER_D_OVER_D * d, d, r)


# ----------------------------------------------------------------- buckling

K_FACTORS = {"pinned_pinned": 1.0, "fixed_fixed": 0.5, "fixed_pinned": 0.699, "fixed_free": 2.0}


def euler_load(E: float, I: float, L: float, K: float = 1.0) -> float:
    return math.pi**2 * E * I / (K * L) ** 2


def column_critical_load(E: float, Sy: float, A: float, I: float, L: float, K: float = 1.0) -> tuple[float, str, float, float]:
    """Euler for slender columns, Johnson parabola below the transition slenderness
    (Shigley 10th ed. §4-12/4-13). Returns (P_cr, mode, slenderness, transition)."""
    r = math.sqrt(I / A)
    slender = K * L / r
    transition = math.sqrt(2 * math.pi**2 * E / Sy)
    if slender >= transition:
        return euler_load(E, I, L, K), "euler", slender, transition
    p = A * (Sy - (Sy * slender / (2 * math.pi)) ** 2 / E)
    return p, "johnson", slender, transition


# ------------------------------------------------------------------- result

@dataclass
class StrengthResult:
    model: str
    verdict: str
    values: dict[str, float]                 # headline quantities claims are checked against
    steps: list[str]                          # the hand calc, line by line
    alternatives: dict[str, list[tuple[float, str]]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def _alt(alts: dict, q: str, value: float, why: str) -> None:
    alts.setdefault(q, []).append((value, why))


def _strength_for(inp: dict, mat: dict, layer_loading: str | None) -> tuple[float, str]:
    """Strength used for the safety factor and a label saying what it is."""
    if "yield_mpa" in inp:
        return float(inp["yield_mpa"]), f"yield {inp['yield_mpa']} MPa (given)"
    if mat.get("printed"):
        if layer_loading == "across_layers":
            return mat["across_layer_strength_mpa"], f"across-layer strength {mat['across_layer_strength_mpa']} MPa"
        return mat["in_layer_strength_mpa"], f"in-layer strength {mat['in_layer_strength_mpa']} MPa"
    return mat["yield_mpa"], f"yield {mat['yield_mpa']} MPa"


def _section(sec: dict) -> tuple[dict, float, float]:
    """Return (props, b, h). For rect: `depth_mm` (if given) is the bending depth and
    `thickness_mm` the width; otherwise `thickness_mm` is the bending depth and
    `width_mm` the width (matches the task wording: '8 mm thickness vertical')."""
    if sec["type"] == "round":
        d = sec["diameter_mm"]
        return round_section(d), d, d
    if "depth_mm" in sec:
        b, h = sec.get("thickness_mm", sec.get("width_mm")), sec["depth_mm"]
    else:
        b, h = sec["width_mm"], sec["thickness_mm"]
    return rect_section(b, h), b, h


# Print orientation -> how the critical bending stress meets the layers.
# For an L-bracket printed upright (vertical leg standing on the bed, layers
# horizontal), the critical section is the vertical leg at the corner; its
# bending stress runs vertically, i.e. it pulls the layers apart.
LAYER_LOADING = {
    "upright_layers_horizontal": "across_layers",
    "flat": "in_layer",
    "on_side": "in_layer",
}


# ------------------------------------------------------------------- models

def _cantilever(inp: dict, kt: float, kt_label: str, mats: dict, steps: list[str]) -> StrengthResult:
    mat = mats[inp["material"]]
    F, L = float(inp["load_n"]), float(inp["lever_mm"])
    props, b, h = _section(inp["section"])
    M = F * L
    s_nom = M / props["Z"]
    s_max = kt * s_nom
    layer = LAYER_LOADING.get(inp.get("print_orientation", ""), None) if mat.get("printed") else None
    strength, s_label = _strength_for(inp, mat, layer)
    sf = strength / s_max
    req = float(inp.get("required_safety_factor", 1.0))
    verdict = "safe" if sf >= req else "not_safe"
    steps += [
        f"M = F x L = {F:g} N x {L:g} mm = {M:.0f} N*mm",
        f"Z = b*h^2/6 = {b:g}*{h:g}^2/6 = {props['Z']:.1f} mm^3",
        f"sigma_nom = M/Z = {s_nom:.1f} MPa",
        f"Kt = {kt:.2f} ({kt_label})",
        f"sigma_max = Kt x sigma_nom = {s_max:.1f} MPa",
        f"strength = {s_label}" + (f" (print orientation {inp['print_orientation']} -> load {layer.replace('_', ' ')})" if layer else ""),
        f"SF = {strength:g} / {s_max:.1f} = {sf:.2f} vs required {req:g} -> {verdict}",
    ]
    values = {"moment_nmm": M, "max_stress_mpa": s_max, "nominal_stress_mpa": s_nom, "stress_concentration_kt": kt,
              "safety_factor": sf, "material_strength_mpa": strength, "load_n": F,
              "section_modulus_mm3": props["Z"]}
    alts: dict = {}
    _alt(alts, "max_stress_mpa", s_nom, f"matches nominal stress {s_nom:.1f} MPa: missed the stress concentration at the {kt_label.split(',')[0]} (Kt ~ {kt:.1f})")
    _alt(alts, "max_stress_mpa", kt * M / (b * h**2 / 12), "used Z = b*h^2/12 (wrong section modulus)")
    _alt(alts, "max_stress_mpa", kt * M / (h * b**2 / 6), f"bent the section the wrong way (used {b:g} mm as the depth)")
    _alt(alts, "moment_nmm", F * L / 1000, "moment in N*m, not N*mm (unit slip)")
    _alt(alts, "safety_factor", strength / s_nom, f"used nominal stress {s_nom:.1f} MPa: missed the stress concentration (Kt ~ {kt:.1f}); true SF {sf:.2f}")
    if mat.get("printed") and layer == "across_layers":
        s_in = mat["in_layer_strength_mpa"]
        for datasheet in sorted({s_in, 60.0}):
            _alt(alts, "safety_factor", datasheet / s_max,
                 f"used in-layer/datasheet PLA strength ({datasheet:g} MPa); printed upright, the bending load acts across layers (~{strength:g} MPa)")
            _alt(alts, "safety_factor", datasheet / s_nom,
                 f"used in-layer/datasheet PLA strength ({datasheet:g} MPa) and nominal stress: load acts across layers (~{strength:g} MPa) and missed Kt ~ {kt:.1f}")
            _alt(alts, "material_strength_mpa", datasheet,
                 f"used in-layer/datasheet PLA strength; printed upright, the load acts across layers (~{strength:g} MPa)")
    if "ultimate_mpa" in mat and "yield_mpa" in inp:
        _alt(alts, "safety_factor", mat["ultimate_mpa"] / s_max, f"used ultimate strength {mat['ultimate_mpa']} MPa instead of yield {strength:g} MPa")
        _alt(alts, "material_strength_mpa", mat["ultimate_mpa"], "used ultimate strength instead of yield")
    return StrengthResult(model="", verdict=verdict, values=values, steps=steps, alternatives=alts)


def model_cantilever_root_fillet(inp: dict, mats: dict) -> StrengthResult:
    props, b, h = _section(inp["section"])
    r = float(inp.get("fillet_mm", 0))
    kt = kt_l_corner(h, r) if r > 0 else 3.0
    label = (f"{r:g} mm fillet at the root corner, r/d = {r / h:.2f}; Peterson shoulder-fillet fit, "
             f"L-corner taken as D/d = {L_CORNER_D_OVER_D:g} (approximation)")
    res = _cantilever(inp, kt, label, mats, [])
    res.model = "cantilever_root_fillet"
    return res


def model_cantilever_step(inp: dict, mats: dict) -> StrengthResult:
    st = inp["step"]
    D, d, r = float(st["D_mm"]), float(st["d_mm"]), float(st["r_mm"])
    _, _, h = _section(inp["section"])
    notes = []
    if abs(h - d) > 1e-9:
        notes.append(f"section depth {h} differs from step d {d}; using the section")
    kt = kt_shoulder_bending(D, d, r)
    label = f"{r:g} mm radius step, D/d = {D / d:.2f}, r/d = {r / d:.3f}; Peterson shoulder-fillet fit (approximation)"
    res = _cantilever(inp, kt, label, mats, [])
    res.model, res.notes = "cantilever_step", notes
    return res


def model_column(inp: dict, mats: dict) -> StrengthResult:
    mat = mats.get(inp.get("material", ""), {})
    E = float(inp.get("E_mpa", mat.get("E_mpa")))
    Sy = float(inp.get("yield_mpa", mat.get("yield_mpa")))
    d, L, P = float(inp["diameter_mm"]), float(inp["length_mm"]), float(inp["load_n"])
    K = K_FACTORS[inp.get("end_condition", "pinned_pinned")]
    props = round_section(d)
    A, I = props["A"], props["I"]
    s = P / A
    sf_stress = Sy / s
    p_cr, mode, slender, trans = column_critical_load(E, Sy, A, I, L, K)
    sf_buckle = p_cr / P
    sf = min(sf_stress, sf_buckle)
    req = float(inp.get("required_safety_factor", 1.0))
    verdict = "safe" if sf >= req else "not_safe"
    steps = [
        f"A = pi*d^2/4 = {A:.1f} mm^2; sigma = P/A = {P:g}/{A:.1f} = {s:.1f} MPa -> stress SF = {sf_stress:.2f}",
        f"I = pi*d^4/64 = {I:.1f} mm^4; K = {K:g} ({inp.get('end_condition', 'pinned_pinned')})",
        f"slenderness KL/r = {slender:.0f} vs transition sqrt(2 pi^2 E/Sy) = {trans:.0f} -> {mode}",
        f"P_cr = {'pi^2*E*I/(KL)^2' if mode == 'euler' else 'Johnson'} = {p_cr:.0f} N -> buckling SF = {sf_buckle:.2f}",
        f"SF = min({sf_stress:.2f}, {sf_buckle:.2f}) = {sf:.2f} vs required {req:g} -> {verdict}",
    ]
    values = {"buckling_load_n": p_cr, "safety_factor": sf, "max_stress_mpa": s, "stress_safety_factor": sf_stress,
              "buckling_safety_factor": sf_buckle, "material_strength_mpa": Sy, "load_n": P, "slenderness": slender}
    alts: dict = {}
    _alt(alts, "safety_factor", sf_stress, f"checked compressive stress only (SF {sf_stress:.1f}); the rod buckles at {p_cr:.0f} N, below the {P:g} N load")
    for name, k in K_FACTORS.items():
        if k != K:
            _alt(alts, "buckling_load_n", euler_load(E, I, L, k), f"used {name} end conditions (K = {k:g}); the ends are {inp.get('end_condition')}")
    _alt(alts, "buckling_load_n", Sy * A, f"gave the squash (yield) load Sy*A = {Sy * A:.0f} N, not the buckling load")
    _alt(alts, "buckling_load_n", euler_load(E, math.pi * d**4 / 32, L, K), "used the polar moment J = pi*d^4/32 instead of I")
    _alt(alts, "buckling_load_n", euler_load(E, math.pi * (d / 2) ** 4 / 64, L, K), "used the radius as the diameter in I")
    return StrengthResult(model="column", verdict=verdict, values=values, steps=steps, alternatives=alts)


def model_arm_torque(inp: dict, mats: dict) -> StrengthResult:
    L = float(inp["arm_length_mm"]) / 1000  # m
    m_arm, m_tip = float(inp.get("arm_mass_kg", 0)), float(inp.get("tip_mass_kg", 0))
    stall_kgcm = float(inp["stall_torque_kgcm"])
    req = float(inp.get("required_margin", 1.0))
    t_tip = m_tip * G * L
    t_arm = m_arm * G * L / 2
    t_nm = t_tip + t_arm
    t_kgcm = t_nm / NM_PER_KGCM
    stall_nm = stall_kgcm * NM_PER_KGCM
    margin = stall_kgcm / t_kgcm
    verdict = "will_hold" if margin >= req else "wont_hold"
    steps = [
        f"tip: {m_tip:g} kg x {G} x {L:g} m = {t_tip:.3f} N*m",
        f"arm (uniform, CG at L/2): {m_arm:g} x {G} x {L / 2:g} = {t_arm:.3f} N*m",
        f"required torque = {t_nm:.3f} N*m = {t_kgcm:.1f} kg*cm (1 kg*cm = {NM_PER_KGCM:.4f} N*m)",
        f"stall {stall_kgcm:g} kg*cm = {stall_nm:.3f} N*m; margin = {stall_kgcm:g}/{t_kgcm:.1f} = {margin:.2f} "
        f"vs required {req:g} (needs {req * t_kgcm:.1f} kg*cm) -> {verdict}",
        "note: stall torque is not a usable holding torque, so the real margin is worse still",
    ]
    values = {"required_torque_nm": t_nm, "required_torque_kgcm": t_kgcm, "required_torque_nmm": t_nm * 1000,
              "moment_nmm": t_nm * 1000, "safety_factor": margin, "torque_margin": margin,
              "stall_torque_nm": stall_nm, "stall_torque_kgcm": stall_kgcm}
    alts: dict = {}
    t_tip_only = t_tip / NM_PER_KGCM
    t_arm_tip = (m_arm + m_tip) * G * L
    _alt(alts, "required_torque_kgcm", t_nm, f"gave the N*m value ({t_nm:.2f}) as kg*cm: unit mix-up (x{1 / NM_PER_KGCM:.1f})")
    _alt(alts, "required_torque_kgcm", t_nm * 100, "gave N*cm as kg*cm: dropped the factor g")
    _alt(alts, "required_torque_kgcm", t_tip_only, f"ignored the arm's own weight ({t_arm:.2f} N*m)")
    _alt(alts, "required_torque_kgcm", t_arm_tip / NM_PER_KGCM, "put the arm's mass at the tip instead of at L/2")
    _alt(alts, "required_torque_nm", t_kgcm, f"gave the kg*cm value ({t_kgcm:.1f}) as N*m: unit mix-up")
    _alt(alts, "required_torque_nm", t_tip, f"ignored the arm's own weight ({t_arm:.2f} N*m)")
    _alt(alts, "required_torque_nm", t_arm_tip, "put the arm's mass at the tip instead of at L/2")
    _alt(alts, "required_torque_nm", t_nm * NM_PER_KGCM, "converted N*m -> kg*cm the wrong way")
    _alt(alts, "stall_torque_nm", stall_kgcm / NM_PER_KGCM, "converted kg*cm -> N*m the wrong way")
    _alt(alts, "stall_torque_nm", stall_kgcm, "treated 11 kg*cm as 11 N*m")
    _alt(alts, "stall_torque_nm", stall_kgcm / 100, "treated kg*cm as N*cm (dropped g)")
    for q in ("safety_factor", "torque_margin"):
        _alt(alts, q, stall_kgcm / t_tip_only, f"ignored the arm's own weight; true margin {margin:.2f}")
        _alt(alts, q, stall_kgcm / t_nm, f"compared kg*cm stall to an N*m requirement (unit mix-up); true margin {margin:.2f}")
        _alt(alts, q, stall_kgcm / (t_nm * 100), f"compared kg*cm stall to an N*cm requirement (dropped g); true margin {margin:.2f}")
    return StrengthResult(model="arm_torque", verdict=verdict, values=values, steps=steps, alternatives=alts)


# ------------------------------------------- fatigue (s06), beam (s07), thermal (s08)

def marin_ka(sut: float, surface: str) -> float:
    """Marin surface factor ka = a * Sut^b (Shigley 10th ed. Table 6-2, Sut in MPa)."""
    a, b = {"ground": (1.58, -0.085), "machined": (4.51, -0.265), "cold_drawn": (4.51, -0.265),
            "hot_rolled": (57.7, -0.718), "as_forged": (272.0, -0.995)}[surface]
    return a * sut**b


def model_cantilever_fatigue(inp: dict, mats: dict) -> StrengthResult:
    """Round cantilever under a fluctuating tip load: static yield check plus
    modified-Goodman infinite-life check (Shigley 10th ed. Ch. 6).
    Se' = 0.5 Sut (Sut <= 1400 MPa), ka from Table 6-2; kb, kc, kd, ke taken as 1
    (matches the hand calc; kb for a 12 mm non-rotating bar is ~1, so this is a
    small simplification)."""
    mat = mats.get(inp.get("material", ""), {})
    sy = float(inp.get("yield_mpa", mat.get("yield_mpa")))
    sut = float(inp.get("ultimate_mpa", mat.get("ultimate_mpa")))
    d, L = float(inp["diameter_mm"]), float(inp["lever_mm"])
    fmin, fmax = float(inp.get("load_min_n", 0)), float(inp["load_max_n"])
    req = float(inp.get("required_safety_factor", 1.0))
    Z = round_section(d)["Z"]
    m_max, m_min = fmax * L, fmin * L
    s_max, s_min = m_max / Z, m_min / Z
    s_a, s_m = (s_max - s_min) / 2, (s_max + s_min) / 2
    sf_static = sy / s_max
    se_prime = 0.5 * sut
    ka = marin_ka(sut, inp.get("surface", "machined"))
    se = ka * se_prime
    n_goodman = 1 / (s_a / se + s_m / sut)
    # Gerber (Shigley Eq. 6-47), for reference only
    n_gerber = 0.5 * (sut / s_m) ** 2 * (s_a / se) * (-1 + math.sqrt(1 + (2 * s_m * se / (sut * s_a)) ** 2)) if s_m else se / s_a
    sf = min(sf_static, n_goodman)
    verdict = "safe" if sf >= req else "not_safe"
    hz = inp.get("frequency_hz")
    steps = [
        f"Z = pi*d^3/32 = {Z:.1f} mm^3; M_max = {fmax:g} x {L:g} = {m_max:.0f} N*mm -> sigma_max = {s_max:.1f} MPa",
        f"static SF = Sy/sigma_max = {sy:g}/{s_max:.1f} = {sf_static:.2f}",
        f"cycle {fmin:g} -> {fmax:g} N: sigma_a = {s_a:.1f} MPa, sigma_m = {s_m:.1f} MPa"
        + (f"; {hz:g} Hz x 8 h/day = {hz * 3600 * 8 * 365:.1e} cycles/year -> infinite life" if hz else ""),
        f"Se' = 0.5 Sut = {se_prime:.0f} MPa; ka ({inp.get('surface', 'machined')}) = {ka:.3f}; kb..ke ~ 1 -> Se = {se:.1f} MPa",
        f"Goodman: 1/n = {s_a:.1f}/{se:.1f} + {s_m:.1f}/{sut:g} = {1 / n_goodman:.3f} -> n_f = {n_goodman:.2f} (Gerber {n_gerber:.2f})",
        f"SF = min({sf_static:.2f}, {n_goodman:.2f}) = {sf:.2f} vs required {req:g} -> {verdict}",
    ]
    values = {"moment_nmm": m_max, "max_stress_mpa": s_max, "alternating_stress_mpa": s_a, "mean_stress_mpa": s_m,
              "static_safety_factor": sf_static, "stress_safety_factor": sf_static, "fatigue_safety_factor": n_goodman,
              "fatigue_sf": n_goodman, "safety_factor": sf, "endurance_limit_mpa": se, "material_strength_mpa": sy,
              "load_n": fmax, "section_modulus_mm3": Z}
    alts: dict = {}
    static_why = f"checked static stress only (SF {sf_static:.2f}); the 0-{fmax:g} N cycle fails Goodman fatigue (n_f {n_goodman:.2f})"
    _alt(alts, "safety_factor", sf_static, static_why)
    _alt(alts, "fatigue_safety_factor", sf_static, static_why)
    _alt(alts, "fatigue_sf", sf_static, static_why)
    for q in ("fatigue_safety_factor", "fatigue_sf", "safety_factor"):
        _alt(alts, q, 1 / (s_a / se_prime + s_m / sut), f"skipped the machined-surface factor (ka = {ka:.2f}), used Se = Se' = {se_prime:.0f} MPa")
        _alt(alts, q, n_gerber, f"used the Gerber criterion ({n_gerber:.2f}); the spec'd check is modified Goodman ({n_goodman:.2f})")
        _alt(alts, q, se / s_max, f"treated the 0-{fmax:g} N load as fully reversed (sigma_a = {s_max:.0f} MPa)")
        _alt(alts, q, se_prime / s_max, "treated the load as fully reversed and skipped the surface factor")
        _alt(alts, q, 1 / (s_a / se + s_m / sy), "used Soderberg (yield on the mean axis) instead of Goodman")
    _alt(alts, "max_stress_mpa", m_max / (math.pi * d**3 / 16), "used the polar section modulus pi*d^3/16")
    _alt(alts, "max_stress_mpa", s_a, f"gave the alternating stress ({s_a:.1f} MPa) as the peak")
    return StrengthResult(model="cantilever_fatigue", verdict=verdict, values=values, steps=steps, alternatives=alts,
                          notes=["kb (size), kc, kd, ke taken as 1, as in the hand calc"])


def model_simple_beam(inp: dict, mats: dict) -> StrengthResult:
    """Simply supported beam, central point load: M = PL/4, delta = PL^3/(48EI).
    Bending depth is the dimension in the load direction (depth_mm)."""
    mat = mats.get(inp.get("material", ""), {})
    E = float(inp.get("E_mpa", mat.get("E_mpa")))
    sy = float(inp.get("yield_mpa", mat.get("yield_mpa")))
    P, L = float(inp["load_n"]), float(inp["span_mm"])
    req = float(inp.get("required_safety_factor", 1.0))
    dmax = inp.get("max_deflection_mm")
    props, b, h = _section(inp["section"])
    M = P * L / 4
    s = M / props["Z"]
    sf = sy / s
    defl = P * L**3 / (48 * E * props["I"])
    ok_defl = dmax is None or defl <= float(dmax)
    verdict = "safe" if sf >= req and ok_defl else "not_safe"
    strong = rect_section(h, b)  # same bar turned on edge
    s_strong, d_strong = M / strong["Z"], P * L**3 / (48 * E * strong["I"])
    steps = [
        f"M = P*L/4 = {P:g}*{L:g}/4 = {M:.0f} N*mm",
        f"bending about the axis with depth h = {h:g} mm (b = {b:g}): Z = b*h^2/6 = {props['Z']:.1f} mm^3, I = b*h^3/12 = {props['I']:.1f} mm^4",
        f"sigma = M/Z = {s:.1f} MPa -> SF = {sy:g}/{s:.1f} = {sf:.2f} vs required {req:g}",
        f"delta = P*L^3/(48*E*I) = {defl:.1f} mm" + (f" vs limit {dmax:g} mm" if dmax is not None else ""),
        f"-> {verdict}" + ("" if ok_defl else " (deflection)") + ("" if sf >= req else " (stress)"),
    ]
    values = {"moment_nmm": M, "max_stress_mpa": s, "safety_factor": sf, "deflection_mm": defl,
              "material_strength_mpa": sy, "load_n": P, "section_modulus_mm3": props["Z"]}
    alts: dict = {}
    axis = f"used the {b:g} mm width as the bending depth (strong axis); lying flat, it bends about the weak axis (h = {h:g} mm)"
    _alt(alts, "max_stress_mpa", s_strong, axis)
    _alt(alts, "safety_factor", sy / s_strong, axis)
    _alt(alts, "deflection_mm", d_strong, axis)
    _alt(alts, "section_modulus_mm3", strong["Z"], axis)
    _alt(alts, "moment_nmm", P * L, "used the cantilever moment P*L; the bar is simply supported (P*L/4)")
    _alt(alts, "moment_nmm", P * L / 8, "used the uniformly-distributed-load moment (wL^2/8 form); the load is a point load at mid-span")
    _alt(alts, "max_stress_mpa", (P * L / 8) / props["Z"], "treated the point load as uniformly distributed (M = PL/8)")
    _alt(alts, "deflection_mm", 5 * P * L**3 / (384 * E * props["I"]), "used the uniform-load deflection 5PL^3/(384EI); the load is a point load")
    _alt(alts, "deflection_mm", P * L**3 / (3 * E * props["I"]), "used the cantilever deflection PL^3/(3EI)")
    return StrengthResult(model="simple_beam", verdict=verdict, values=values, steps=steps, alternatives=alts)


def model_thermal_column(inp: dict, mats: dict) -> StrengthResult:
    """Bar fully restrained axially and heated: sigma = E*alpha*dT, F = sigma*A,
    compared with yield and with the column buckling load for its end condition."""
    mat = mats.get(inp.get("material", ""), {})
    E = float(inp.get("E_mpa", mat.get("E_mpa")))
    sy = float(inp.get("yield_mpa", mat.get("yield_mpa")))
    alpha, dT = float(inp["alpha_per_c"]), float(inp["delta_t_c"])
    d, L = float(inp["diameter_mm"]), float(inp["length_mm"])
    end = inp.get("end_condition", "fixed_fixed")
    K = K_FACTORS[end]
    props = round_section(d)
    A, I = props["A"], props["I"]
    s_th = E * alpha * dT
    F = s_th * A
    p_cr, mode, slender, trans = column_critical_load(E, sy, A, I, L, K)
    dT_cr = p_cr / (E * alpha * A)
    sf_stress, sf_buckle = sy / s_th, p_cr / F
    sf = min(sf_stress, sf_buckle)
    req = float(inp.get("required_safety_factor", 1.0))
    verdict = "safe" if sf >= req else "not_safe"
    steps = [
        f"restrained: sigma = E*alpha*dT = {E:g}*{alpha:g}*{dT:g} = {s_th:.1f} MPa -> yield SF = {sf_stress:.2f}",
        f"A = pi*d^2/4 = {A:.1f} mm^2 -> axial force F = sigma*A = {F:.0f} N",
        f"I = pi*d^4/64 = {I:.1f} mm^4; K = {K:g} ({end}); KL/r = {slender:.0f} vs transition {trans:.0f} -> {mode}",
        f"P_cr = {p_cr:.0f} N -> buckling SF = {p_cr:.0f}/{F:.0f} = {sf_buckle:.2f}; buckles once dT > {dT_cr:.1f} C",
        f"SF = min({sf_stress:.2f}, {sf_buckle:.2f}) = {sf:.2f} vs required {req:g} -> {verdict}",
    ]
    values = {"thermal_stress_mpa": s_th, "max_stress_mpa": s_th, "thermal_force_n": F, "load_n": F,
              "buckling_load_n": p_cr, "critical_temperature_rise_c": dT_cr, "safety_factor": sf,
              "stress_safety_factor": sf_stress, "buckling_safety_factor": sf_buckle, "material_strength_mpa": sy,
              "slenderness": slender}
    alts: dict = {}
    only = f"checked thermal stress only (SF {sf_stress:.1f}); the {F:.0f} N restrained force exceeds the {p_cr:.0f} N buckling load"
    _alt(alts, "safety_factor", sf_stress, only)
    _alt(alts, "stress_safety_factor", sf_stress, only)
    for name, k in K_FACTORS.items():
        if k != K:
            pk = euler_load(E, I, L, k)
            why = f"used {name} end conditions (K = {k:g}); both ends are clamped ({end}, K = {K:g})"
            _alt(alts, "buckling_load_n", pk, why)
            _alt(alts, "critical_temperature_rise_c", pk / (E * alpha * A), why)
            _alt(alts, "buckling_safety_factor", pk / F, why)
    _alt(alts, "buckling_load_n", sy * A, f"gave the squash (yield) load Sy*A = {sy * A:.0f} N, not the buckling load")
    _alt(alts, "thermal_force_n", s_th * math.pi * d**2, "used pi*d^2 for the area (diameter as radius)")
    _alt(alts, "thermal_stress_mpa", s_th / 2, "halved the restrained thermal stress")
    _alt(alts, "thermal_stress_mpa", E * alpha * 50, "used the absolute temperature (50 C) instead of the 30 C rise")
    _alt(alts, "thermal_force_n", E * alpha * 50 * A, "used the absolute temperature (50 C) instead of the 30 C rise")
    return StrengthResult(model="thermal_column", verdict=verdict, values=values, steps=steps, alternatives=alts)


MODELS = {
    "cantilever_root_fillet": model_cantilever_root_fillet,
    "cantilever_step": model_cantilever_step,
    "column": model_column,
    "arm_torque": model_arm_torque,
    "cantilever_fatigue": model_cantilever_fatigue,
    "simple_beam": model_simple_beam,
    "thermal_column": model_thermal_column,
}


def infer_model(inp: dict) -> str:
    if "stall_torque_kgcm" in inp:
        return "arm_torque"
    if "delta_t_c" in inp:
        return "thermal_column"
    if "load_max_n" in inp:
        return "cantilever_fatigue"
    if "span_mm" in inp:
        return "simple_beam"
    if "end_condition" in inp or ("length_mm" in inp and "lever_mm" not in inp):
        return "column"
    if "step" in inp:
        return "cantilever_step"
    if "lever_mm" in inp:
        return "cantilever_root_fillet"
    raise ValueError(f"cannot infer a strength model from inputs {sorted(inp)}")


def check(task: dict) -> StrengthResult:
    """Run the strength model for one task (the parsed task.yaml)."""
    inp = task["inputs"]
    model = task.get("model") or inp.get("model") or infer_model(inp)
    return MODELS[model](inp, load_materials())


# The topics a strength answer might be required to mention (truth.must_mention)
MISSING_WHY = {
    "layer_direction_strength": "Answer never considers print orientation: the load acts across layers (~half the datasheet strength)",
    "stress_concentration": "Answer never accounts for the stress concentration at the corner/step radius",
    "buckling": "Answer checks stress only and never checks buckling (for a restrained, heated rod: the thermal force vs. the buckling load)",
    "fatigue": "Answer checks static stress only and never checks fatigue under the cyclic load (Goodman line)",
    "unit_conversion": "Answer never converts the kg*cm rating consistently",
}
