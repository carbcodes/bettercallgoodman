"""Independent hand calcs for generated strength cases (does NOT import goodman).
Writes tasks/strength/g###-slug/{prompt.md,task.yaml,truth.yaml} from the case lists in c_*.py.

Usage (from the repo root): python scripts/generate_cases/gen.py
Regenerating deletes and rewrites every tasks/strength/g* folder. Then run scripts/check_cases.py."""
import json, math, sys, importlib
from pathlib import Path
import yaml

G = 9.81
REPO = Path(__file__).resolve().parents[2]
MATS = yaml.safe_load(open(REPO / "goodman/materials.yaml"))
PI = math.pi
END_SUMMARY = "End your answer with a short summary: your verdict (safe / not safe) and the key numbers you relied on."
END_SERVO = "End your answer with a short summary: your verdict (will hold / won't hold) and the key numbers you relied on."
END_OK = "End your answer with a short summary: your verdict (OK / not OK) and the key numbers you relied on."

# unit helpers (prompt units -> task units)
LBF = 4.44822
IN = 25.4
LB = 0.453592
PSI = 0.00689476
def kgf(m): return m * G

def r3(x):
    if x == 0: return 0
    return float(f"{x:.3g}") if abs(x) < 1e4 else float(round(x))

# ---------------- hand-calc building blocks (Shigley / Peterson / Roark formulas)
def kt_peterson_shoulder(D, d, r):
    """Peterson 3rd ed. Chart 3.10 polynomial fit (also Roark 7th Table 17.1): flat bar,
    opposite shoulder fillets, bending. Kt = C1 + C2 x + C3 x^2 + C4 x^3, x = 2t/D, t = (D-d)/2."""
    t = (D - d) / 2
    if t <= 0 or r <= 0: return 1.0
    q = min(max(t / r, 0.1), 20.0); s = math.sqrt(q)
    if q <= 2:
        C = (1.006 + 0.967*s + 0.013*q, -0.270 - 2.372*s + 0.708*q, 0.662 + 1.157*s - 0.908*q, -0.405 + 0.249*s - 0.200*q)
    else:
        C = (1.058 + 1.002*s - 0.038*q, -3.652 + 1.639*s - 0.436*q, 6.170 - 5.687*s + 1.175*q, -2.558 + 3.046*s - 0.701*q)
    x = 2 * t / D
    return max(1.0, C[0] + C[1]*x + C[2]*x**2 + C[3]*x**3)

def strength_of(inp, layer):
    m = MATS[inp["material"]] if inp.get("material") in MATS else {}
    if "yield_mpa" in inp:
        return inp["yield_mpa"], f"yield {inp['yield_mpa']:g} MPa"
    if m.get("printed"):
        if layer == "across":
            return m["across_layer_strength_mpa"], f"{inp['material']} across-layer strength {m['across_layer_strength_mpa']:g} MPa (materials.yaml)"
        return m["in_layer_strength_mpa"], f"{inp['material']} in-layer strength {m['in_layer_strength_mpa']:g} MPa (materials.yaml)"
    return m["yield_mpa"], f"{inp['material']} yield {m['yield_mpa']:g} MPa (materials.yaml)"

def rect_bh(sec):
    if "depth_mm" in sec: return sec.get("thickness_mm", sec.get("width_mm")), sec["depth_mm"]
    return sec["width_mm"], sec["thickness_mm"]

def calc_cantilever(inp, step):
    F, L = inp["load_n"], inp["lever_mm"]
    b, h = rect_bh(inp["section"])
    M = F * L; Z = b * h * h / 6; s_nom = M / Z
    lines = [f"M = F·L = {F:g} N × {L:g} mm = {M:.0f} N·mm.",
             f"Z = b·h²/6 = {b:g}·{h:g}²/6 = {Z:.1f} mm³ → σ_nom = M/Z = {s_nom:.1f} MPa."]
    if step:
        D, d, r = inp["step"]["D_mm"], inp["step"]["d_mm"], inp["step"]["r_mm"]
        kt = kt_peterson_shoulder(D, d, r)
        lines.append(f"Shoulder step D/d = {D:g}/{d:g} = {D/d:.2f}, r/d = {r:g}/{d:g} = {r/d:.3f} → Kt = {kt:.2f} "
                     f"(Peterson Chart 3.10 fit, bending) → σ_max = {kt:.2f}·{s_nom:.1f} = {kt*s_nom:.1f} MPa.")
    else:
        r = inp["fillet_mm"]
        kt = kt_peterson_shoulder(2 * h, h, r)
        lines.append(f"Root corner r/h = {r:g}/{h:g} = {r/h:.3f}; corner into a much larger body taken as a shoulder with D/d = 2 "
                     f"(Peterson Chart 3.10 fit) → Kt = {kt:.2f} → σ_max = {kt:.2f}·{s_nom:.1f} = {kt*s_nom:.1f} MPa.")
    s_max = kt * s_nom
    orient = inp.get("print_orientation")
    layer = None
    if MATS.get(inp["material"], {}).get("printed"):
        layer = "across" if orient == "upright_layers_horizontal" else "in"
    S, slabel = strength_of(inp, layer)
    sf = S / s_max; req = inp["required_safety_factor"]
    verdict = "safe" if sf >= req else "not_safe"
    lines.append(f"Strength: {slabel}. SF = {S:g}/{s_max:.1f} = {sf:.2f} vs required {req:g} → {verdict.replace('_', ' ')}.")
    vals = {"moment_nmm": (r3(M), 0.05), "max_stress_mpa": (r3(s_max), 0.2), "safety_factor": (r3(sf), 0.25)}
    f = dict(M=M, Z=Z, s_nom=s_nom, kt=kt, s_max=s_max, S=S, sf=sf, sf_nom=S / s_nom, req=req, b=b, h=h,
             sf_strong=S / (kt * M / (h * b * b / 6)))
    if layer == "across":
        Sin = MATS[inp["material"]]["in_layer_strength_mpa"]; f["Sin"] = Sin; f["sf_in"] = Sin / s_max
    return verdict, vals, lines, f

K_TABLE = {"pinned_pinned": 1.0, "fixed_fixed": 0.5, "fixed_pinned": 0.699, "fixed_free": 2.0}
END_WORDS = {"pinned_pinned": "pinned-pinned", "fixed_fixed": "fixed-fixed", "fixed_pinned": "fixed-pinned", "fixed_free": "fixed-free"}

def pcr_round(E, Sy, d, L, K):
    A = PI * d * d / 4; I = PI * d**4 / 64; r = d / 4
    sl = K * L / r; tr = math.sqrt(2 * PI**2 * E / Sy)
    if sl >= tr:
        return PI**2 * E * I / (K * L)**2, "Euler", sl, tr, A, I
    return A * (Sy - (Sy * sl / (2 * PI))**2 / E), "Johnson", sl, tr, A, I

def calc_column(inp):
    E, Sy, d, L, P = inp["E_mpa"], inp["yield_mpa"], inp["diameter_mm"], inp["length_mm"], inp["load_n"]
    end = inp["end_condition"]; K = K_TABLE[end]
    pcr, mode, sl, tr, A, I = pcr_round(E, Sy, d, L, K)
    s = P / A; sfs = Sy / s; sfb = pcr / P; sf = min(sfs, sfb); req = inp["required_safety_factor"]
    verdict = "safe" if sf >= req else "not_safe"
    lines = [f"A = π·{d:g}²/4 = {A:.1f} mm²; σ = P/A = {P:g}/{A:.1f} = {s:.1f} MPa → stress SF = {Sy:g}/{s:.1f} = {sfs:.2f}.",
             f"I = π·{d:g}⁴/64 = {I:.0f} mm⁴, r = d/4 = {d/4:g} mm; {END_WORDS[end]} → K = {K:g}; KL/r = {sl:.0f} vs transition √(2π²E/Sy) = {tr:.0f} → {mode}."]
    if mode == "Euler":
        lines.append(f"P_cr = π²·E·I/(K·L)² = π²·{E:g}·{I:.0f}/({K:g}·{L:g})² = {pcr:.0f} N → buckling SF = {pcr:.0f}/{P:g} = {sfb:.2f}.")
    else:
        lines.append(f"Johnson: P_cr = A·[Sy − (Sy·KL/r/(2π))²/E] = {pcr:.0f} N → buckling SF = {sfb:.2f}.")
    lines.append(f"SF = min({sfs:.2f}, {sfb:.2f}) = {sf:.2f} vs required {req:g} → {verdict.replace('_', ' ')}.")
    vals = {"buckling_load_n": (r3(pcr), 0.05), "max_stress_mpa": (r3(s), 0.05), "safety_factor": (r3(sf), 0.1)}
    f = dict(A=A, I=I, s=s, sfs=sfs, pcr=pcr, sfb=sfb, sf=sf, P=P, req=req, K=K, mode=mode)
    for k2, v2 in K_TABLE.items():
        f["pcr_" + k2] = PI**2 * E * I / (v2 * L)**2
    return verdict, vals, lines, f

def calc_arm(inp):
    L = inp["arm_length_mm"] / 1000; ma, mt = inp.get("arm_mass_kg", 0), inp.get("tip_mass_kg", 0)
    stall = inp["stall_torque_kgcm"]; req = inp["required_margin"]
    tt = mt * G * L; ta = ma * G * L / 2; t = tt + ta; tk = t / (G * 0.01); m = stall / tk
    verdict = "will_hold" if m >= req else "wont_hold"
    lines = [f"Tip: {mt:g} kg × 9.81 × {L:g} m = {tt:.3f} N·m. Arm (uniform, CG at L/2): {ma:g} × 9.81 × {L/2:g} = {ta:.3f} N·m.",
             f"Required = {t:.3f} N·m = {tk:.1f} kg·cm (1 kg·cm = 0.0981 N·m).",
             f"Rating {stall:g} kg·cm = {stall*G*0.01:.2f} N·m; margin = {stall:g}/{tk:.1f} = {m:.2f} vs required {req:g} "
             f"(needs {req*tk:.1f} kg·cm) → {'will hold' if m >= req else 'won’t hold'}."]
    vals = {"required_torque_nm": (r3(t), 0.05), "required_torque_kgcm": (r3(tk), 0.05), "torque_margin": (r3(m), 0.05)}
    f = dict(t=t, tk=tk, m=m, stall=stall, stall_nm=stall * G * 0.01, req=req, need=req * tk)
    return verdict, vals, lines, f

MARIN = {"ground": (1.58, -0.085), "machined": (4.51, -0.265), "cold_drawn": (4.51, -0.265), "hot_rolled": (57.7, -0.718), "as_forged": (272.0, -0.995)}

def calc_fatigue(inp):
    Sy, Sut, d, L = inp["yield_mpa"], inp["ultimate_mpa"], inp["diameter_mm"], inp["lever_mm"]
    fmin, fmax = inp.get("load_min_n", 0), inp["load_max_n"]; req = inp["required_safety_factor"]
    Z = PI * d**3 / 32; smax = fmax * L / Z; smin = fmin * L / Z
    sa, sm = (smax - smin) / 2, (smax + smin) / 2
    sfs = Sy / smax; surf = inp.get("surface", "machined"); a, b = MARIN[surf]
    ka = a * Sut**b; Se = ka * 0.5 * Sut
    n = 1 / (sa / Se + sm / Sut); sf = min(sfs, n)
    verdict = "safe" if sf >= req else "not_safe"
    if sm:
        ng = 0.5 * (Sut / sm)**2 * (sa / Se) * (-1 + math.sqrt(1 + (2 * sm * Se / (Sut * sa))**2))
    else:
        ng = Se / sa
    lines = [f"Z = π·d³/32 = π·{d:g}³/32 = {Z:.1f} mm³; M_max = {fmax:g} × {L:g} = {fmax*L:.0f} N·mm → σ_max = {smax:.1f} MPa.",
             f"Static SF = Sy/σ_max = {Sy:g}/{smax:.1f} = {sfs:.2f}.",
             f"Load {fmin:g} → {fmax:g} N: σ_a = {sa:.1f} MPa, σ_m = {sm:.1f} MPa.",
             f"Se' = 0.5·Sut = {0.5*Sut:.0f} MPa; ka ({surf.replace('_', ' ')}) = {a:g}·{Sut:g}^{b:g} = {ka:.3f}; kb..ke ≈ 1 → Se = {Se:.1f} MPa.",
             f"Modified Goodman: 1/n = {sa:.1f}/{Se:.1f} + {sm:.1f}/{Sut:g} = {1/n:.3f} → n_f = {n:.2f} (Gerber {ng:.2f}).",
             f"SF = min({sfs:.2f}, {n:.2f}) = {sf:.2f} vs required {req:g} → {verdict.replace('_', ' ')}."]
    vals = {"max_stress_mpa": (r3(smax), 0.05), "static_safety_factor": (r3(sfs), 0.05), "fatigue_safety_factor": (r3(n), 0.15)}
    f = dict(Z=Z, smax=smax, sa=sa, sm=sm, sfs=sfs, Se=Se, ka=ka, n=n, ng=ng, sf=sf, req=req)
    return verdict, vals, lines, f

def calc_beam(inp):
    E, Sy, P, L = inp["E_mpa"], inp["yield_mpa"], inp["load_n"], inp["span_mm"]
    b, h = inp["section"]["width_mm"], inp["section"]["depth_mm"]; req = inp["required_safety_factor"]
    dmax = inp.get("max_deflection_mm")
    M = P * L / 4; Z = b * h * h / 6; I = b * h**3 / 12; s = M / Z; sf = Sy / s
    dl = P * L**3 / (48 * E * I)
    ok = sf >= req and (dmax is None or dl <= dmax)
    verdict = "safe" if ok else "not_safe"
    lines = [f"Simply supported, centre load: M = P·L/4 = {P:g}·{L:g}/4 = {M:.0f} N·mm.",
             f"Bending depth is the dimension in the load direction, h = {h:g} mm (b = {b:g} mm): Z = b·h²/6 = {Z:.1f} mm³, I = b·h³/12 = {I:.1f} mm⁴.",
             f"σ = M/Z = {s:.1f} MPa → SF = {Sy:g}/{s:.1f} = {sf:.2f} vs required {req:g}.",
             f"δ = P·L³/(48·E·I) = {P:g}·{L:g}³/(48·{E:g}·{I:.1f}) = {dl:.2f} mm" + (f" vs limit {dmax:g} mm." if dmax is not None else ".")]
    why_bad = []
    if sf < req: why_bad.append("stress")
    if dmax is not None and dl > dmax: why_bad.append("deflection")
    lines.append(f"→ {verdict.replace('_', ' ')}" + (f" ({' and '.join(why_bad)})." if why_bad else "."))
    vals = {"moment_nmm": (r3(M), 0.05), "max_stress_mpa": (r3(s), 0.05), "safety_factor": (r3(sf), 0.05), "deflection_mm": (r3(dl), 0.1)}
    Zs = h * b * b / 6; Is = h * b**3 / 12
    f = dict(M=M, Z=Z, I=I, s=s, sf=sf, dl=dl, req=req, dmax=dmax, s_strong=M / Zs, sf_strong=Sy / (M / Zs),
             dl_strong=P * L**3 / (48 * E * Is), b=b, h=h, sf_fixed=2 * sf)
    return verdict, vals, lines, f

def calc_thermal(inp):
    E, Sy, al, dT = inp["E_mpa"], inp["yield_mpa"], inp["alpha_per_c"], inp["delta_t_c"]
    d, L, end = inp["diameter_mm"], inp["length_mm"], inp["end_condition"]; K = K_TABLE[end]
    req = inp.get("required_safety_factor", 1.0)
    s = E * al * dT
    pcr, mode, sl, tr, A, I = pcr_round(E, Sy, d, L, K)
    F = s * A; sfs = Sy / s; sfb = pcr / F; sf = min(sfs, sfb); dTc = pcr / (E * al * A)
    verdict = "safe" if sf >= req else "not_safe"
    lines = [f"Fully restrained: σ = E·α·ΔT = {E:g}·{al:g}·{dT:g} = {s:.1f} MPa → yield SF = {Sy:g}/{s:.1f} = {sfs:.2f}.",
             f"A = π·{d:g}²/4 = {A:.1f} mm² → axial force F = σ·A = {F:.0f} N.",
             f"I = π·{d:g}⁴/64 = {I:.0f} mm⁴; {END_WORDS[end]} → K = {K:g}; KL/r = {sl:.0f} vs transition {tr:.0f} → {mode}: P_cr = {pcr:.0f} N.",
             f"Buckling SF = {pcr:.0f}/{F:.0f} = {sfb:.2f}; the rod would bow once ΔT > P_cr/(E·α·A) = {dTc:.1f} °C.",
             f"SF = min({sfs:.2f}, {sfb:.2f}) = {sf:.2f} vs required {req:g} → {'OK' if verdict == 'safe' else 'not OK'}."]
    vals = {"thermal_stress_mpa": (r3(s), 0.05), "thermal_force_n": (r3(F), 0.05), "buckling_load_n": (r3(pcr), 0.05), "safety_factor": (r3(sf), 0.1)}
    f = dict(s=s, F=F, A=A, I=I, pcr=pcr, sfs=sfs, sfb=sfb, sf=sf, dTc=dTc, req=req, K=K, mode=mode)
    for k2, v2 in K_TABLE.items():
        f["pcr_" + k2] = PI**2 * E * I / (v2 * L)**2
    return verdict, vals, lines, f

CALC = {"cantilever_root_fillet": lambda i: calc_cantilever(i, False), "cantilever_step": lambda i: calc_cantilever(i, True),
        "column": calc_column, "arm_torque": calc_arm, "cantilever_fatigue": calc_fatigue,
        "simple_beam": calc_beam, "thermal_column": calc_thermal}

SOURCES = {
    "cantilever_root_fillet": "Shigley 10th ed. §3-10 (bending stress); Kt: Pilkey & Pilkey, Peterson's Stress Concentration Factors 3rd ed., Chart 3.10 (stepped flat bar in bending, polynomial fit also in Roark 7th ed. Table 17.1)",
    "cantilever_step": "Shigley 10th ed. §3-10 (bending stress); Kt: Pilkey & Pilkey, Peterson's Stress Concentration Factors 3rd ed., Chart 3.10 (stepped flat bar in bending, polynomial fit also in Roark 7th ed. Table 17.1)",
    "column": "Shigley 10th ed. §4-11 to 4-13 (Euler and Johnson columns, end-condition constants)",
    "arm_torque": "Statics (torque = weight × lever arm, uniform arm at L/2); 1 kg·cm = 0.0981 N·m",
    "cantilever_fatigue": "Shigley 10th ed. Ch. 6 (Se' = 0.5 Sut, Marin surface factor Table 6-2, modified Goodman Eq. 6-41, Gerber Eq. 6-42)",
    "simple_beam": "Shigley 10th ed. Table A-9 case 5 (simply supported, centre load: M = PL/4, δ = PL³/48EI)",
    "thermal_column": "Shigley 10th ed. §3-14 (restrained thermal stress σ = EαΔT) and §4-11 to 4-13 (column buckling)",
}

def ystr(s):  # double-quoted YAML scalar
    return json.dumps(s, ensure_ascii=False)

def flow(d):
    return yaml.safe_dump(d, default_flow_style=True, sort_keys=False, width=10000, allow_unicode=True).strip()

def build(case, idx, outdir):
    model = case["model"]; inp = case["inputs"]
    verdict, vals, lines, f = CALC[model](inp)
    if case.get("expect") and case["expect"] != verdict:
        print(f"!! {case['slug']}: expected {case['expect']} got {verdict}", file=sys.stderr)
    for k, v in case.get("vals_extra", {}).items():
        vals[k] = v
    for k in case.get("vals_drop", []):
        vals.pop(k, None)
    f.update(inp=inp)
    pre = [s.format(**f) for s in case.get("pre", [])]
    post = [s.format(**f) for s in case.get("post", [])]
    trap = case["trap"].format(**f)
    cid = f"g{idx:03d}-{case['slug']}"
    d = outdir / cid; d.mkdir(parents=True, exist_ok=True)
    end = {"arm_torque": END_SERVO, "thermal_column": END_OK}.get(model, END_SUMMARY)
    prompt = " ".join(case["prompt"].split())
    (d / "prompt.md").write_text(f"{prompt} {end}\n")
    task = [f"id: {cid}", "area: strength", f"title: {case['title']}", f"trap: {ystr(trap)}",
            f"control: {'true' if case.get('control') else 'false'}", f"model: {model}", f"inputs: {flow(inp)}"]
    (d / "task.yaml").write_text("\n".join(task) + "\n")
    t = [f"verdict: {verdict}", "values:"]
    for k, (v, tol) in vals.items():
        t.append(f"  {k}: {{value: {v:g}, tol: {tol:g}}}")
    if case.get("mm"):
        t.append(f"must_mention: [{', '.join(case['mm'])}]")
    t.append("why: |")
    for l in pre + lines + post:
        t.append("  " + l)
    src = SOURCES[model] + ("; " + case["src"] if case.get("src") else "")
    t.append(f"source: {ystr(src)}")
    (d / "truth.yaml").write_text("\n".join(t) + "\n")
    return cid, verdict, f

if __name__ == "__main__":
    out = REPO / "tasks/strength"
    mods = sys.argv[1:] or ["c_root", "c_step", "c_column", "c_arm", "c_fatigue", "c_beam", "c_thermal"]
    sys.path.insert(0, str(Path(__file__).parent))
    allc = []
    for m in mods:
        allc += [c for c in importlib.import_module(m).CASES if not c.get("drop")]
    for old in out.glob("g*"):
        import shutil; shutil.rmtree(old)
    for i, c in enumerate(allc, 1):
        cid, v, f = build(c, i, out)
        print(cid, v, f"sf={f.get('sf', f.get('m')):.2f}" if isinstance(f.get('sf', f.get('m')), float) else "")
