"""Generate 100 concrete mix design problems with worked IS 10262:2019 solutions.
Distribution: 30 conventional / 15 exposure / 15 pumped / 15 SCM / 15 aggregate / 10 advanced."""
import csv, json, random, os, sys
from is10262 import design, IS456_TABLE5_RCC, IS456_TABLE5_PCC

rng = random.Random(2026)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(OUT, exist_ok=True)

ELEMENTS = {
    "mild": ["residential slabs and beams", "internal columns of a school building", "office floor slabs", "compound wall footings"],
    "moderate": ["RCC frame of a commercial building", "beams and slabs of a hospital block", "column footings in non-aggressive soil", "parking structure slabs under cover"],
    "severe": ["coastal-zone residential columns", "water-retaining structure walls", "bridge piers in a humid region", "industrial floor exposed to alternate wetting and drying"],
    "very severe": ["jetty deck beams subject to sea-water spray", "foundations in sulphate-bearing soil", "bridge deck exposed to de-icing salts", "effluent treatment plant tank walls"],
    "extreme": ["marine tidal-zone piles", "sea-wall elements in the tidal zone", "offshore platform deck members"],
}


def statement(p, group, flavour):
    scm = ", ".join(f"{t} at {pct}% of total cementitious" for t, pct in p.get("scm", []))
    base = (f"Design a concrete mix of grade M{p['fck']} for {p['element']}. Exposure condition is {p['exposure']} ({p['member']}). "
            f"Maximum nominal aggregate size is {p['max_size']} mm (angular, crushed), required workability is a slump of {p['slump']} mm. "
            f"Cement: {'OPC' if not p.get('cement_type') else p['cement_type']} {p['cement_grade']} grade, SG {p['sg_cement']}. "
            f"Fine aggregate: Zone {p['zone']}, SG {p['sg_fa']}, water absorption {p['abs_fa']}%, free surface moisture {p['fm_fa']}%. "
            f"Coarse aggregate: SG {p['sg_ca']}, water absorption {p['abs_ca']}%, free surface moisture {p['fm_ca']}%. ")
    if p.get("sp_pct"):
        base += f"A superplasticiser (SG 1.08) is used at {p['sp_pct']}% by mass of cementitious, giving about {int(p['sp_wr']*100)}% water reduction. "
    if scm:
        base += f"Supplementary cementitious materials: {scm}. "
    if p.get("pumped"):
        base += "The concrete will be placed by pump. "
    if p.get("special") == "scc":
        base += "The mix is self-compacting; target slump flow 650-700 mm. "
    base += "Quality control is good; use IS 10262:2019 with IS 456:2000 durability limits. Give mix proportions per m3 and the field-adjusted quantities."
    return base


def agg_props(zone=None, sg_fa=None, sg_ca=None):
    return dict(
        zone=zone or rng.choices(["II", "III", "I", "IV"], [70, 18, 6, 6])[0],
        sg_fa=sg_fa or round(rng.uniform(2.60, 2.68), 2),
        sg_ca=sg_ca or round(rng.uniform(2.68, 2.80), 2),
        abs_fa=round(rng.uniform(0.5, 1.5), 1), abs_ca=round(rng.uniform(0.3, 1.0), 1),
        fm_fa=rng.choice([0.0, 1.0, 2.0, 3.0]), fm_ca=rng.choice([0.0, 0.0, 0.5]),
        sg_cement=rng.choice([3.12, 3.15, 3.15, 3.14]),
    )


def pick_element(exp):
    return rng.choice(ELEMENTS[exp])


def build(group, make, n, flavour_fn=lambda p: "", advanced=False, max_tries=4000):
    out, seen, tries = [], set(), 0
    while len(out) < n and tries < max_tries:
        tries += 1
        p = make()
        key = json.dumps({k: v for k, v in p.items() if k != "element"}, sort_keys=True)
        if key in seen:
            continue
        p["advanced"] = advanced
        r = design(p)
        if not r["all_checks_pass"]:
            continue
        seen.add(key)
        out.append((p, r))
    if len(out) < n:
        sys.exit(f"group {group}: only {len(out)}/{n} valid problems")
    return out


# ---- group A: conventional (30)
def make_A():
    member = rng.choices(["RCC", "PCC"], [80, 20])[0]
    exp = rng.choice(["mild", "moderate"])
    tbl = IS456_TABLE5_PCC if member == "PCC" else IS456_TABLE5_RCC
    gmin = tbl[exp][2]
    fck = rng.choice([g for g in (15, 20, 25, 30, 35, 40) if g >= gmin and (member == "RCC" or g <= 25)])
    size = rng.choices([10, 20, 40], [15, 60, 25])[0]
    p = dict(fck=fck, exposure=exp, member=member, max_size=size, slump=rng.choice([25, 50, 75, 100]),
             cement_grade=53 if fck >= 35 else rng.choice([43, 43, 53]), element=pick_element(exp), **agg_props())
    return p

# ---- group B: exposure / durability (15)
def make_B():
    exp = rng.choice(["severe", "very severe", "extreme", "severe", "very severe"])
    gmin = IS456_TABLE5_RCC[exp][2]
    fck = rng.choice([g for g in (30, 35, 40, 45, 50) if g >= gmin])
    sp = rng.random() < 0.5
    slump = rng.choice([75, 100, 125]) if sp else rng.choice([50, 75, 100])
    p = dict(fck=fck, exposure=exp, member="RCC", max_size=rng.choice([20, 20, 20, 10, 40]), slump=slump,
             cement_grade=53, element=pick_element(exp), **agg_props(zone=rng.choice(["II", "II", "III"])))
    if sp:
        p.update(sp_pct=round(rng.choice([0.6, 0.8, 1.0]), 1), sp_wr=0.15)
    return p

# ---- group C: pumped / workability (15)
def make_C():
    exp = rng.choice(["moderate", "severe", "moderate"])
    fck = rng.choice([25, 30, 35, 40, 45])
    p = dict(fck=fck, exposure=exp, member="RCC", max_size=rng.choice([20, 20, 20, 10]),
             slump=rng.choice([100, 125, 150, 175, 200]), cement_grade=53 if fck >= 35 else 43,
             pumped=True, sp_pct=round(rng.choice([0.8, 1.0, 1.2, 1.5]), 1), sp_wr=0.20,
             element=rng.choice(["pumped high-rise core walls", "pumped raft foundation", "congested pumped column-beam joints", "pumped transfer slab"]),
             **agg_props(zone=rng.choice(["II", "II", "III"])))
    return p

# ---- group D: fly ash / GGBS blends (15)
def make_D():
    exp = rng.choice(["moderate", "severe", "very severe", "moderate"])
    gmin = IS456_TABLE5_RCC[exp][2]
    fck = rng.choice([g for g in (25, 30, 35, 40, 45) if g >= gmin])
    typ = rng.choice(["FA", "FA", "GGBS"])
    pct = rng.choice([20, 25, 30, 35]) if typ == "FA" else rng.choice([30, 40, 50, 60])
    sp = rng.random() < 0.6
    p = dict(fck=fck, exposure=exp, member="RCC", max_size=rng.choice([20, 20, 10, 40]),
             slump=rng.choice([75, 100, 125]) if sp else rng.choice([50, 75, 100]), cement_grade=53,
             scm=[(typ, pct)], element=pick_element(exp), **agg_props(zone="II"))
    if sp:
        p.update(sp_pct=round(rng.choice([0.6, 0.8, 1.0]), 1), sp_wr=0.15)
    return p

# ---- group E: aggregate properties and grading zones (15): systematic zone x size, varied SG
E_COMBOS = [(z, s) for z in ("I", "II", "III", "IV") for s in (10, 20, 40)]
E_COMBOS += [("II", 20), ("III", 20), ("II", 40)]
E_I = iter(E_COMBOS)
def make_E():
    z, s = next(E_I)
    fck = rng.choice([25, 30])
    sg_fa, sg_ca = round(rng.uniform(2.55, 2.70), 2), round(rng.uniform(2.60, 2.95), 2)
    p = dict(fck=fck, exposure="moderate", member="RCC", max_size=s, slump=rng.choice([50, 75, 100]),
             cement_grade=43, element=pick_element("moderate"), **agg_props(zone=z, sg_fa=sg_fa, sg_ca=sg_ca))
    p["fm_fa"] = rng.choice([1.0, 2.0, 3.0, 4.0]); p["fm_ca"] = rng.choice([0.0, 0.5, 1.0])
    return p

# ---- group F: advanced / special (10) - fixed list
def F_list():
    base = dict(member="RCC", cement_grade=53, **dict(abs_fa=0.8, abs_ca=0.5, fm_fa=2.0, fm_ca=0.0, sg_cement=3.15))
    L = []
    for g, sf, sl in [(55, 8, 100), (60, 10, 125), (65, 10, 150), (70, 10, 175)]:
        L.append(dict(base, fck=g, exposure="severe", max_size=20, slump=sl, zone="II", sg_fa=2.64, sg_ca=2.78,
                      scm=[("SF", sf)], sp_pct=1.5, sp_wr=0.30, element=f"high-strength columns of a tall building (M{g})"))
    L.append(dict(base, fck=30, exposure="moderate", max_size=10, slump=175, zone="II", sg_fa=2.64, sg_ca=2.74,
                  scm=[("FA", 30)], sp_pct=1.5, sp_wr=0.25, special="scc", element="congested precast beam-column joints (self-compacting)"))
    L.append(dict(base, fck=40, exposure="severe", max_size=10, slump=175, zone="II", sg_fa=2.64, sg_ca=2.74,
                  scm=[("FA", 25)], sp_pct=1.6, sp_wr=0.25, special="scc", element="architectural SCC panels (self-compacting)"))
    L.append(dict(base, fck=25, exposure="moderate", max_size=40, slump=50, zone="II", sg_fa=2.64, sg_ca=2.70,
                  scm=[("FA", 30)], sp_pct=0.0, sp_wr=0.0, element="mass concrete gravity dam block (low heat)"))
    L.append(dict(base, fck=40, exposure="extreme", max_size=20, slump=100, zone="II", sg_fa=2.64, sg_ca=2.74,
                  scm=[("GGBS", 50)], sp_pct=1.0, sp_wr=0.20, element="marine tidal-zone piles with GGBS blend"))
    L.append(dict(base, fck=50, exposure="severe", max_size=20, slump=75, zone="II", sg_fa=2.64, sg_ca=2.76,
                  scm=[("FA", 15), ("SF", 5)], sp_pct=1.2, sp_wr=0.25, element="precast prestressed girders (ternary blend)"))
    L.append(dict(base, fck=35, exposure="severe", max_size=40, slump=100, zone="II", sg_fa=2.64, sg_ca=2.72,
                  scm=[("FA", 25)], sp_pct=0.8, sp_wr=0.15, element="thick basement raft (3 m, low heat of hydration)"))
    return L


def finalize(group, items, offset):
    recs = []
    for i, (p, r) in enumerate(items):
        pid = f"P{offset + i + 1:03d}"
        p = dict(p); p.setdefault("zone", "II"); p.setdefault("cement_type", None)
        rec = {
            "id": pid, "group": group,
            "problem_statement": statement(p, group, ""),
            "inputs": {k: v for k, v in p.items() if k != "advanced"},
            "target_strength_MPa": r["target_strength"], "w_c_adopted": r["w_c_adopted"],
            "predicted_28d_mean_MPa": r["predicted_28d_mean"],
            "mix_per_m3": r["mix_per_m3"], "solution_steps": r["steps"], "checks": r["checks"],
            "verification_status": ("computed_indicative_needs_trial_mix" if group.startswith("F") else "computed_checked_against_code_rules"),
            "codes": ["IS 10262:2019", "IS 456:2000"],
            "source": "synthetic, generated by is10262.py calculator (not a textbook problem)",
        }
        m = rec["mix_per_m3"]
        rec["retrieval_text"] = (
            f"{rec['problem_statement']} RESULT: target {rec['target_strength_MPa']} MPa, w/c {rec['w_c_adopted']}, "
            f"cement {m['cement']} kg, SCM {m['scm']}, water {m['water']} kg, FA {m['fine_aggregate_ssd']} kg, "
            f"CA {m['coarse_aggregate_ssd']} kg, admixture {m['admixture']} kg, ratio {m['ratio_by_mass_cementitious']}.")
        recs.append(rec)
    return recs


def main():
    A = build("A_conventional", make_A, 30)
    B = build("B_exposure_durability", make_B, 15)
    C = build("C_pumped_workability", make_C, 15)
    D = build("D_fly_ash_ggbs_blends", make_D, 15)
    E = build("E_aggregate_zones", make_E, 15)
    F = []
    for p in F_list():
        p["advanced"] = True
        r = design(p)
        if not r["all_checks_pass"]:
            print("F-group fail:", p["element"], {k: v for k, v in r["checks"].items() if not v}, r["mix_per_m3"])
        F.append((p, r))
    recs, off = [], 0
    for g, items in [("A_conventional", A), ("B_exposure_durability", B), ("C_pumped_workability", C),
                     ("D_fly_ash_ggbs_blends", D), ("E_aggregate_zones", E), ("F_advanced_special", F)]:
        recs += finalize(g, items, off); off += len(items)
    assert len(recs) == 100, len(recs)
    with open(os.path.join(OUT, "mix_problems.jsonl"), "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(os.path.join(OUT, "mix_summary.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "group", "grade", "exposure", "member", "max_size_mm", "slump_mm", "zone", "cement_grade", "scm",
                    "sp_pct", "target_MPa", "w_cm", "cement", "scm_kg", "water", "fine_agg_ssd", "coarse_agg_ssd", "admixture", "status", "all_checks_pass"])
        for r in recs:
            i, m = r["inputs"], r["mix_per_m3"]
            w.writerow([r["id"], r["group"], f"M{i['fck']}", i["exposure"], i["member"], i["max_size"], i["slump"], i["zone"], i["cement_grade"],
                        ";".join(f"{t}{p}" for t, p in i.get("scm", [])), i.get("sp_pct", 0), r["target_strength_MPa"], m["w_cm"],
                        m["cement"], sum(m["scm"].values()), m["water"], m["fine_aggregate_ssd"], m["coarse_aggregate_ssd"], m["admixture"],
                        r["verification_status"], all(r["checks"].values())])
    from collections import Counter
    print(Counter(r["group"] for r in recs))
    print("all checks pass:", sum(all(r["checks"].values()) for r in recs), "/ 100")


if __name__ == "__main__":
    main()
