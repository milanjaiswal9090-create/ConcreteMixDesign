"""
Deterministic concrete mix design calculator (IS 10262:2019 procedure + IS 456:2000 limits).

IMPORTANT: every lookup table below was encoded from working knowledge of the codes, NOT copied
from your licensed copy. Entries tagged VERIFY must be checked against your PDFs before you
treat the dataset as ground truth. All tables live in this one file so fixing a value and
re-running generate_dataset.py regenerates all 100 problems consistently.
"""
import math

# ---------------------------------------------------------------- tables ----------------
# IS 10262:2019 - assumed standard deviation (N/mm2)                         [VERIFY]
def std_dev(fck):
    if fck <= 15: return 3.5
    if fck <= 25: return 4.0
    return 5.0

# IS 10262:2019 - "X" in  f'ck = fck + X                                      [VERIFY]
def x_factor(fck):
    if fck <= 15: return 5.0
    if fck <= 25: return 5.5
    if fck <= 45: return 6.5
    return 8.0

# IS 10262:2019 Fig.1 (w/c vs 28-day strength by cement grade) approximated as f = A*exp(-B*w/c)
# Digitised approximately -> replace with your curve values.                  [VERIFY]
STRENGTH_CURVE = {33: (110.0, 2.40), 43: (129.0, 2.27), 53: (157.0, 2.32)}

# IS 456:2000 Table 5 - limits for exposure (20 mm aggregate): (max w/c, min cement kg/m3, min grade)
IS456_TABLE5_RCC = {
    "mild":        (0.55, 300, 20),
    "moderate":    (0.50, 300, 25),
    "severe":      (0.45, 320, 30),
    "very severe": (0.45, 340, 35),
    "extreme":     (0.40, 360, 40),
}
IS456_TABLE5_PCC = {
    "mild":        (0.60, 220, 15),
    "moderate":    (0.60, 240, 20),
    "severe":      (0.50, 250, 20),
    "very severe": (0.45, 260, 20),
    "extreme":     (0.40, 280, 25),
}
MAX_CEMENT = 450      # IS 456 cl.8.2.4.2, cement excluding SCM
MAX_CEMENTITIOUS = 550  # dataset convention for blended mixes                 [VERIFY]

# IS 10262:2019 - max water content (kg/m3) for 50 mm slump, angular aggregate, no admixture
WATER_50MM = {10: 208, 20: 186, 40: 165}
SLUMP_WATER_STEP = 0.03   # +3 % per 25 mm above 50 mm
# Entrapped air (% of concrete volume)                                         [VERIFY - 2009 used 3/2/1]
ENTRAPPED_AIR = {10: 1.5, 20: 1.0, 40: 0.8}
# Volume of coarse aggregate per unit volume of total aggregate at w/c = 0.50
CA_FRACTION = {
    10: {"IV": 0.50, "III": 0.48, "II": 0.46, "I": 0.44},
    20: {"IV": 0.66, "III": 0.64, "II": 0.62, "I": 0.60},
    40: {"IV": 0.75, "III": 0.73, "II": 0.71, "I": 0.69},
}
CA_FRACTION_PER_0_05_WC = 0.01   # +0.01 per 0.05 decrease in w/c (and vice versa)
PUMPING_CA_REDUCTION = 0.10      # reduce CA fraction by 10 % for pumpable concrete
# Cementitious uplift when SCMs used (dataset convention)                       [VERIFY]
SCM_UPLIFT = {"FA": 0.10, "GGBS": 0.05, "SF": 0.0}
SCM_SG = {"FA": 2.20, "GGBS": 2.90, "SF": 2.20}
SP_SG = 1.08


def _r(x, n=1):
    return round(x, n)


def design(p):
    """p: dict of inputs. Returns dict with steps, mix, checks."""
    steps = []

    def add(name, clause, value, note=""):
        steps.append({"step": name, "clause": clause, "value": value, "note": note})

    fck = p["fck"]
    exp = p["exposure"]
    member = p.get("member", "RCC")
    size = p["max_size"]
    slump = p["slump"]
    zone = p.get("zone", "II")
    grade = p.get("cement_grade", 43)
    sg_c = p.get("sg_cement", 3.15)
    sg_fa, sg_ca = p["sg_fa"], p["sg_ca"]
    scms = p.get("scm", [])            # list of (type, percent of total cementitious)
    sp_pct = p.get("sp_pct", 0.0)      # % by mass of cementitious
    sp_wr = p.get("sp_wr", 0.0)        # fractional water reduction from admixture
    pumped = p.get("pumped", False)
    special = p.get("special")         # None | "scc"
    advanced = p.get("advanced", False)

    # 1 target strength
    s, X = std_dev(fck), x_factor(fck)
    ft = max(fck + 1.65 * s, fck + X)
    add("Target mean strength", "IS 10262:2019 cl.4.2", _r(ft, 2),
        f"f'ck = max(fck+1.65s, fck+X) = max({fck}+1.65x{s}, {fck}+{X}) = {ft:.2f} N/mm2")

    # 2 w/c from strength
    A, B = STRENGTH_CURVE[grade]
    wc_strength = math.log(A / ft) / B
    add("w/c for target strength", "IS 10262:2019 Fig.1", _r(wc_strength, 3),
        f"{grade}-grade cement curve (approximated as f = {A}*exp(-{B}*w/c))")

    # 3 durability limit
    tbl = IS456_TABLE5_PCC if member == "PCC" else IS456_TABLE5_RCC
    wc_max, c_min, g_min = tbl[exp]
    add("Durability limits", "IS 456:2000 Table 5", {"max_wc": wc_max, "min_cement": c_min, "min_grade": g_min},
        f"{exp} exposure, {member}")
    wc = math.floor(min(wc_strength, wc_max) * 100) / 100
    gov = "durability" if wc_max < wc_strength else "strength"
    add("Adopted w/c", "IS 10262:2019 cl.5", wc, f"governed by {gov}")

    # 4 water content
    w0 = WATER_50MM[size]
    w = w0
    if slump > 50:
        w = w0 * (1 + SLUMP_WATER_STEP * (slump - 50) / 25)
    add("Water for slump (no admixture)", "IS 10262:2019 water-content table", _r(w, 1),
        f"{w0} kg at 50 mm, +3% per 25 mm to {slump} mm")
    if sp_wr:
        w = w * (1 - sp_wr)
        add("Water after superplasticiser", "IS 10262:2019 cl.5", _r(w, 1), f"{sp_wr*100:.0f}% reduction")
    if special == "scc":
        pass

    # 5 binder
    cementitious = w / wc
    if cementitious < c_min:
        cementitious = c_min
        note = f"raised to minimum cement content {c_min}"
    else:
        note = f"water/w-c = {w:.1f}/{wc}"
    if special == "scc":
        cementitious = max(cementitious, 450)
        note += "; SCC powder content >= 450"
    add("Cementitious (base)", "IS 10262:2019 cl.5", _r(cementitious, 0), note)
    if scms:
        uplift = max(SCM_UPLIFT[t] for t, _ in scms)
        cementitious *= (1 + uplift)
        add("Cementitious with SCM uplift", "dataset convention", _r(cementitious, 0), f"+{uplift*100:.0f}% for SCM")
    scm_mass = {t: cementitious * pct / 100 for t, pct in scms}
    cement = cementitious - sum(scm_mass.values())
    wcm_actual = w / cementitious
    add("Cement / SCM split", "IS 10262:2019 cl.5", {"cement": _r(cement, 0), **{k: _r(v, 0) for k, v in scm_mass.items()}},
        f"actual w/cm = {wcm_actual:.3f}")

    # 6 aggregate proportions
    frac = CA_FRACTION[size][zone]
    frac += CA_FRACTION_PER_0_05_WC * (0.50 - wcm_actual) / 0.05
    if pumped:
        frac *= (1 - PUMPING_CA_REDUCTION)
    if special == "scc":
        frac = 0.50
    frac = round(frac, 3)
    add("Coarse aggregate fraction of total aggregate (by volume)", "IS 10262:2019 aggregate-volume table",
        frac, f"zone {zone}, {size} mm; w/c corrected; pumped={pumped}")

    # 7 absolute volumes
    sp_mass = sp_pct / 100 * cementitious
    air = ENTRAPPED_AIR[size] / 100
    v_c = cement / (sg_c * 1000)
    v_scm = sum(m / (SCM_SG[t] * 1000) for t, m in scm_mass.items())
    v_w = w / 1000
    v_sp = sp_mass / (SP_SG * 1000)
    v_agg = 1 - (v_c + v_scm + v_w + v_sp + air)
    add("Volume of total aggregate", "IS 10262:2019 cl.5", round(v_agg, 4),
        f"1 - (cement {v_c:.4f} + SCM {v_scm:.4f} + water {v_w:.4f} + SP {v_sp:.4f} + air {air:.4f})")
    ca = v_agg * frac * sg_ca * 1000
    fa = v_agg * (1 - frac) * sg_fa * 1000
    add("Aggregate masses (SSD)", "IS 10262:2019 cl.5", {"fine": _r(fa, 0), "coarse": _r(ca, 0)}, "")

    # 8 field moisture adjustment
    fm_fa, fm_ca = p.get("fm_fa", 0.0), p.get("fm_ca", 0.0)
    w_adj = w - fa * fm_fa / 100 - ca * fm_ca / 100
    fa_adj = fa * (1 + fm_fa / 100)
    ca_adj = ca * (1 + fm_ca / 100)

    mix = {
        "cement": _r(cement, 0), "scm": {k: _r(v, 0) for k, v in scm_mass.items()},
        "water": _r(w, 1), "fine_aggregate_ssd": _r(fa, 0), "coarse_aggregate_ssd": _r(ca, 0),
        "admixture": _r(sp_mass, 2),
        "cementitious_total": _r(cementitious, 0), "w_cm": round(wcm_actual, 3),
        "ratio_by_mass_cementitious": f"1 : {fa/cementitious:.2f} : {ca/cementitious:.2f}",
        "field_adjusted": {"water": _r(w_adj, 1), "fine_aggregate": _r(fa_adj, 0), "coarse_aggregate": _r(ca_adj, 0)},
    }

    # 9 checks
    pred = A * math.exp(-B * wcm_actual)
    vol_sum = v_c + v_scm + v_w + v_sp + air + ca / (sg_ca * 1000) + fa / (sg_fa * 1000)
    max_c = 540 if advanced else MAX_CEMENT
    max_cm = 600 if advanced else MAX_CEMENTITIOUS
    checks = {
        "volume_sums_to_1": abs(vol_sum - 1) < 1e-6,
        "w_cm_within_durability_limit": wcm_actual <= wc_max + 1e-9,
        "min_cementitious_met": cementitious >= c_min - 1e-9,
        "cement_within_max": cement <= max_c,
        "cementitious_within_max": cementitious <= max_cm,
        "grade_meets_exposure_minimum": fck >= g_min,
        "predicted_strength_ge_target": pred >= ft,
        "aggregate_volume_positive": v_agg > 0.5,
    }
    return {
        "target_strength": round(ft, 2), "w_c_adopted": wc, "predicted_28d_mean": round(pred, 1),
        "mix_per_m3": mix, "steps": steps, "checks": checks, "all_checks_pass": all(checks.values()),
    }
