#!/usr/bin/env python3
"""
Foresight Mega-Analysis: CLA + Signals + Voros Future Cone
Extracts data from multiple SQLite databases, performs analysis,
and generates JSON for the dashboard.
"""

import sqlite3
import json
import os
import re
from collections import defaultdict, Counter
from pathlib import Path

BASE = Path(os.path.expanduser("~"))
OUT = Path(__file__).parent / "data"

# ── Database paths ──
CLA_DB = BASE / "projects/research/pestle-signal-db/data/cla.db"
SIGNAL_DB = BASE / "projects/research/pestle-signal-db/data/signal.db"
PESTLE_DB = BASE / "projects/research/pestle-signal-db/data/pestle.db"
FORESIGHT_DB = BASE / "projects/research/foresight-knowledge-base/foresight.db"
INSIGHT_DB = BASE / "projects/apps/future-insight-app/data/future_insight.db"

def db(path):
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn

# ═══════════════════════════════════════════════
# PART 1: CLA Analysis — Historical Transitions
# ═══════════════════════════════════════════════

def extract_cla_data():
    print("[Part 1] Extracting CLA data...")
    conn = db(CLA_DB)

    # 1a. All analyses (36 years + quarterly)
    analyses = conn.execute("""
        SELECT period, period_type, pestle_category,
               litany, systemic_causes, worldview, myth_metaphor,
               key_tension, emerging_narrative
        FROM analyses ORDER BY period, pestle_category
    """).fetchall()

    # 1b. Paradigm shifts
    shifts = conn.execute("""
        SELECT id, region, period, name, description
        FROM paradigm_shifts ORDER BY period
    """).fetchall()

    # 1c. Syntheses
    syntheses = conn.execute("""
        SELECT period, period_type, synthesis
        FROM syntheses ORDER BY period
    """).fetchall()

    # 1d. Myths timeline
    myths = conn.execute("""
        SELECT id, region, era, myth
        FROM myths_timeline ORDER BY id
    """).fetchall()

    # 1e. Layer keywords (for word frequency analysis)
    keywords = conn.execute("""
        SELECT period, pestle_category, layer, keyword
        FROM layer_keywords ORDER BY period, layer
    """).fetchall()

    conn.close()

    # ── Structure by period ──
    periods = {}
    for a in analyses:
        p = a["period"]
        if p not in periods:
            periods[p] = {"period": p, "type": a["period_type"], "categories": {}}
        periods[p]["categories"][a["pestle_category"]] = {
            "litany": a["litany"],
            "systemic": a["systemic_causes"],
            "worldview": a["worldview"],
            "myth": a["myth_metaphor"],
            "tension": a["key_tension"],
            "emerging": a["emerging_narrative"],
        }

    # ── Build era classification ──
    eras = [
        {"start": "1990", "end": "1995", "name": "冷戦終結とグローバリズムの勃興", "myth": "歴史の終わり・自由市場の勝利"},
        {"start": "1996", "end": "2001", "name": "帝国的秩序と文明の衝突", "myth": "一極支配・テロとの戦い"},
        {"start": "2002", "end": "2008", "name": "多極化と金融危機", "myth": "成長神話の破綻・BRICsの台頭"},
        {"start": "2009", "end": "2015", "name": "デジタル支配とリベラル秩序の動揺", "myth": "プラットフォーム民主化・格差拡大"},
        {"start": "2016", "end": "2019", "name": "ポピュリズムと秩序の断片化", "myth": "ポスト真実・国家主義の復活"},
        {"start": "2020", "end": "2026", "name": "複合危機と文明的転換", "myth": "パンデミック・AI革命・地政学再編"},
    ]

    # ── Extract layer evolution per era per category ──
    layer_evolution = []
    for era in eras:
        era_periods = [p for p in sorted(periods.keys())
                       if p >= era["start"] and p <= era["end"]]
        era_data = {"era": era, "period_count": len(era_periods)}

        # Aggregate dominant themes per layer
        for layer in ["litany", "systemic", "worldview", "myth"]:
            texts = []
            for p in era_periods:
                if p in periods:
                    for cat, data in periods[p]["categories"].items():
                        if data.get(layer):
                            texts.append(data[layer][:200])
            era_data[f"{layer}_sample_count"] = len(texts)

        layer_evolution.append(era_data)

    # ── Current position analysis (2025-Q4 to 2026-Q2) ──
    current_periods = ["2025-Q4", "2026-Q1", "2026-Q2"]
    current_position = {}
    for p in current_periods:
        if p in periods:
            current_position[p] = periods[p]

    # ── Build keyword frequency by era ──
    kw_by_era = defaultdict(lambda: defaultdict(lambda: Counter()))
    for k in keywords:
        period = k["period"]
        layer = k["layer"]
        for era in eras:
            if period >= era["start"] and period <= era["end"]:
                kw_by_era[era["name"]][layer][k["keyword"]] += 1
                break

    kw_top = {}
    for era_name, layers in kw_by_era.items():
        kw_top[era_name] = {}
        for layer, counter in layers.items():
            kw_top[era_name][layer] = counter.most_common(15)

    result = {
        "periods": {k: v for k, v in periods.items()},
        "paradigm_shifts": [dict(s) for s in shifts],
        "syntheses": [dict(s) for s in syntheses],
        "myths_timeline": [dict(m) for m in myths],
        "eras": eras,
        "layer_evolution": layer_evolution,
        "current_position": current_position,
        "keyword_top_by_era": kw_top,
        "stats": {
            "total_periods": len(periods),
            "yearly_count": sum(1 for p in periods.values() if p["type"] == "yearly"),
            "quarterly_count": sum(1 for p in periods.values() if p["type"] == "quarterly"),
            "shift_count": len(shifts),
        }
    }

    print(f"  → {len(periods)} periods, {len(shifts)} paradigm shifts, {len(syntheses)} syntheses")
    return result


# ═══════════════════════════════════════════════
# PART 2: Signal Extraction & Bottom-Up Clustering
# ═══════════════════════════════════════════════

def extract_signals():
    print("[Part 2] Extracting signals...")
    conn = db(SIGNAL_DB)

    signals = conn.execute("""
        SELECT id, signal_name, description, signal_type, pestle_categories,
               potential_impact, time_horizon, ansoff_level, three_horizons,
               cla_depth, novelty_score, disruption_score, connectivity_score,
               credibility_score, early_stage_score, composite_score,
               noise_flag, detected_date
        FROM signals WHERE noise_flag = 0
        ORDER BY composite_score DESC
    """).fetchall()

    alerts = conn.execute("""
        SELECT alert_type, level, topic, alert_title, description,
               mentions, ratio, categories, detected_date
        FROM alerts ORDER BY detected_date DESC
    """).fetchall()

    conn.close()

    signal_list = []
    for s in signals:
        cats = s["pestle_categories"]
        if cats:
            try:
                cats = json.loads(cats)
            except:
                cats = [c.strip().strip('"[]') for c in cats.split(",")]
        else:
            cats = []

        signal_list.append({
            "id": s["id"],
            "name": s["signal_name"],
            "description": s["description"],
            "type": s["signal_type"],
            "pestle": cats,
            "impact": s["potential_impact"],
            "horizon": s["time_horizon"],
            "ansoff": s["ansoff_level"],
            "three_h": s["three_horizons"],
            "cla_depth": s["cla_depth"],
            "scores": {
                "novelty": s["novelty_score"],
                "disruption": s["disruption_score"],
                "connectivity": s["connectivity_score"],
                "credibility": s["credibility_score"],
                "early_stage": s["early_stage_score"],
                "composite": s["composite_score"],
            },
            "date": s["detected_date"],
        })

    # ── Bottom-up clustering by keyword extraction ──
    # Simple TF approach: extract key terms from signal names and descriptions
    stop_words = set("の、は、が、を、に、で、と、も、や、から、まで、へ、より、による、として、における、をめぐる、に対する、に関する".split("、"))
    stop_words.update({"a","an","the","and","or","of","in","to","for","by","with","from","that","this","is","are","was","were","be","been","being","have","has","had","do","does","did","will","would","could","should","may","might","can","shall","must","not","no"})

    # Extract key phrases from signal names
    term_signals = defaultdict(list)
    for s in signal_list:
        name = s["name"]
        # Extract terms by splitting on particles
        terms = re.split(r'[のはがをにでともやから、。・「」（）\s]+', name)
        for t in terms:
            t = t.strip()
            if len(t) >= 2 and t not in stop_words:
                term_signals[t].append(s["id"])

    # ── Thematic clustering using co-occurrence ──
    # Group signals by dominant theme
    theme_keywords = {
        "AI・知能・認知": ["AI", "人工知能", "知能", "超知能", "認知", "思考", "意識", "LLM", "機械学習", "ニューラル", "言語モデル"],
        "地政学・権力": ["地政学", "覇権", "帝国", "主権", "国家", "軍事", "戦争", "安全保障", "NATO", "中東", "イラン"],
        "気候・環境": ["気候", "環境", "温暖化", "CO2", "排出", "再生可能", "エネルギー", "脱炭素", "氷床", "融解", "生態"],
        "経済・金融": ["経済", "金融", "市場", "資本", "投資", "インフレ", "債務", "通貨", "GDP", "貿易", "関税"],
        "テクノロジー・デジタル": ["技術", "デジタル", "プラットフォーム", "量子", "ブロックチェーン", "半導体", "ロボット", "自動化", "宇宙"],
        "社会・人口": ["社会", "人口", "移民", "世代", "格差", "不平等", "労働", "雇用", "教育", "福祉", "健康"],
        "法・ガバナンス": ["法", "規制", "法律", "憲法", "司法", "プライバシー", "著作権", "監視", "データ保護", "コンプライアンス"],
        "生命科学・身体": ["生命", "バイオ", "遺伝", "ゲノム", "医療", "健康", "パンデミック", "ウイルス", "脳", "身体", "寿命"],
        "情報・メディア": ["情報", "メディア", "フェイク", "ディスインフォ", "SNS", "ジャーナリズム", "言論", "検閲", "プロパガンダ"],
        "文化・価値観": ["文化", "価値", "アイデンティティ", "宗教", "倫理", "多様性", "ジェンダー", "民主主義", "自由", "権利"],
        "食・農業": ["食", "農業", "食料", "飢餓", "栄養", "土壌", "水", "漁業"],
        "都市・インフラ": ["都市", "インフラ", "住宅", "交通", "物流", "建築", "スマートシティ"],
    }

    # Assign each signal to clusters
    signal_clusters = defaultdict(list)
    unclustered = []
    for s in signal_list:
        text = s["name"] + " " + (s["description"] or "")
        matched = []
        for theme, kws in theme_keywords.items():
            score = sum(1 for kw in kws if kw in text)
            if score > 0:
                matched.append((theme, score))

        if matched:
            matched.sort(key=lambda x: -x[1])
            primary = matched[0][0]
            signal_clusters[primary].append({
                **s,
                "cluster_scores": {m[0]: m[1] for m in matched}
            })
        else:
            unclustered.append(s)

    # Re-cluster unclustered via PESTLE
    pestle_to_theme = {
        "政治": "地政学・権力",
        "経済": "経済・金融",
        "社会": "社会・人口",
        "技術": "テクノロジー・デジタル",
        "法律": "法・ガバナンス",
        "環境": "気候・環境",
    }
    still_unclustered = []
    for s in unclustered:
        if s["pestle"]:
            theme = pestle_to_theme.get(s["pestle"][0])
            if theme:
                signal_clusters[theme].append(s)
            else:
                still_unclustered.append(s)
        else:
            still_unclustered.append(s)

    if still_unclustered:
        signal_clusters["その他・横断的"].extend(still_unclustered)

    # Build cluster summary
    cluster_summary = {}
    for theme, sigs in sorted(signal_clusters.items(), key=lambda x: -len(x[1])):
        impacts = Counter(s["impact"] for s in sigs)
        horizons = Counter(s["horizon"] for s in sigs)
        avg_composite = sum(s["scores"]["composite"] for s in sigs) / len(sigs) if sigs else 0
        pestle_dist = Counter()
        for s in sigs:
            for p in s.get("pestle", []):
                pestle_dist[p] += 1

        cluster_summary[theme] = {
            "count": len(sigs),
            "avg_composite": round(avg_composite, 2),
            "impact_dist": dict(impacts),
            "horizon_dist": dict(horizons),
            "pestle_dist": dict(pestle_dist),
            "top_signals": [
                {"name": s["name"], "composite": s["scores"]["composite"],
                 "impact": s["impact"], "type": s["type"]}
                for s in sorted(sigs, key=lambda x: -x["scores"]["composite"])[:5]
            ],
        }

    result = {
        "total_signals": len(signal_list),
        "clusters": cluster_summary,
        "cluster_signals": {theme: [
            {"id": s["id"], "name": s["name"], "description": s["description"][:200],
             "type": s["type"], "pestle": s["pestle"], "impact": s["impact"],
             "horizon": s["horizon"], "scores": s["scores"], "date": s["date"]}
            for s in sorted(sigs, key=lambda x: -x["scores"]["composite"])
        ] for theme, sigs in signal_clusters.items()},
        "alerts": [dict(a) for a in alerts[:30]],
    }

    print(f"  → {len(signal_list)} signals in {len(signal_clusters)} clusters")
    return result


# ═══════════════════════════════════════════════
# PART 3: Voros Future Cone — 8-Quadrant Classification
# ═══════════════════════════════════════════════

def extract_foresight():
    print("[Part 3] Extracting foresight data for Voros cone...")
    conn = db(FORESIGHT_DB)

    # Get predictions with voros_layer
    predictions = conn.execute("""
        SELECT id, statement, statement_ja, domain, subdomain,
               prediction_type, time_horizon_year, confidence_level,
               voros_layer, knowledge_type, epistemic_confidence,
               temporal_structure, source_id
        FROM predictions
        WHERE voros_layer IS NOT NULL
        ORDER BY domain, voros_layer
    """).fetchall()

    # Get theme taxonomy
    taxonomy = conn.execute("""
        SELECT id, level, parent_id, code, name_en, name_ja,
               description_en, vesteg_primary
        FROM theme_taxonomy
        ORDER BY level, code
    """).fetchall()

    # Get prediction themes (join with theme_taxonomy for names)
    pred_themes = conn.execute("""
        SELECT pt.prediction_id, tt.name_en as theme_name
        FROM prediction_themes pt
        LEFT JOIN theme_taxonomy tt ON pt.theme_id = tt.id
    """).fetchall()

    # Get scenarios with desirability
    scenarios = conn.execute("""
        SELECT id, name, name_ja, description, description_ja,
               scenario_type, axes, probability_assessment, desirability
        FROM scenarios
        WHERE description IS NOT NULL AND description != ''
        LIMIT 2000
    """).fetchall()

    # Get theme clusters
    theme_clusters = conn.execute("""
        SELECT id, name, name_ja, description, keywords,
               prediction_count, convergence_score
        FROM theme_clusters
        ORDER BY prediction_count DESC
        LIMIT 50
    """).fetchall()

    # Get convergence analyses
    convergence = conn.execute("""
        SELECT id, theme_cluster_id, analysis_type, consensus_level,
               description, implications
        FROM convergence_analysis
        LIMIT 50
    """).fetchall()

    # Get trends
    trends = conn.execute("""
        SELECT id, name, name_ja, description, trend_type,
               domains, mention_count
        FROM trends
        ORDER BY mention_count DESC
        LIMIT 100
    """).fetchall()

    # Sources
    sources = conn.execute("""
        SELECT s.id, s.name, s.type as source_type, s.organization,
               COUNT(r.id) as report_count
        FROM sources s
        LEFT JOIN reports r ON s.id = r.source_id
        GROUP BY s.id
        ORDER BY report_count DESC
        LIMIT 50
    """).fetchall()

    conn.close()

    # Build theme lookup
    theme_lookup = defaultdict(list)
    for pt in pred_themes:
        theme_lookup[pt["prediction_id"]].append(pt["theme_name"])

    # ── Desirability classification ──
    # Since predictions don't have desirability directly, we classify based on:
    # 1. Keywords in statement suggesting positive/negative outcomes
    # 2. Domain-specific heuristics

    positive_markers = [
        "improve", "advance", "benefit", "opportunity", "growth", "innovation",
        "sustainable", "clean", "equity", "inclusive", "health", "education",
        "cooperation", "peace", "resilience", "progress", "empower",
        "改善", "向上", "機会", "成長", "革新", "持続可能", "健康", "教育",
        "協力", "平和", "レジリエンス", "進歩", "支援",
    ]
    negative_markers = [
        "risk", "threat", "crisis", "decline", "collapse", "conflict",
        "inequality", "pollution", "displacement", "surveillance", "weaponiz",
        "exploit", "destabili", "disrupt", "loss", "erosion", "authoritarian",
        "リスク", "脅威", "危機", "衰退", "崩壊", "紛争", "格差", "汚染",
        "監視", "搾取", "不安定", "侵害", "喪失", "権威主義",
    ]

    def classify_desirability(statement):
        if not statement:
            return "neutral"
        text = statement.lower()
        pos = sum(1 for m in positive_markers if m.lower() in text)
        neg = sum(1 for m in negative_markers if m.lower() in text)
        if pos > neg + 1:
            return "desirable"
        elif neg > pos + 1:
            return "undesirable"
        else:
            return "ambiguous"

    # ── 8-Quadrant mapping ──
    # Voros layers: projected, probable, plausible, possible
    # × desirable / undesirable
    # (preferable is a cross-cutting concept — mapped to desirable)

    quadrants = {
        "projected_desirable": [], "projected_undesirable": [],
        "probable_desirable": [], "probable_undesirable": [],
        "plausible_desirable": [], "plausible_undesirable": [],
        "possible_desirable": [], "possible_undesirable": [],
    }

    # Also track ambiguous
    ambiguous = defaultdict(list)

    domain_ja = {
        "technology": "テクノロジー", "governance": "ガバナンス",
        "economy": "経済", "environment": "環境", "society": "社会",
        "food": "食", "health": "健康", "politics": "政治",
        "education": "教育", "energy": "エネルギー",
    }

    pred_list = []
    for p in predictions:
        voros = p["voros_layer"]
        if voros == "preferable":
            voros = "plausible"  # Map preferable to plausible-desirable
            desirability = "desirable"
        else:
            stmt = (p["statement"] or "") + " " + (p["statement_ja"] or "")
            desirability = classify_desirability(stmt)

        themes = theme_lookup.get(p["id"], [])

        entry = {
            "id": p["id"],
            "statement": (p["statement_ja"] or p["statement"] or "")[:300],
            "domain": p["domain"],
            "domain_ja": domain_ja.get(p["domain"], p["domain"]),
            "subdomain": p["subdomain"],
            "voros": voros,
            "desirability": desirability,
            "prediction_type": p["prediction_type"],
            "time_horizon": p["time_horizon_year"],
            "confidence": p["confidence_level"],
            "themes": themes[:3],
            "knowledge_type": p["knowledge_type"],
            "epistemic": p["epistemic_confidence"],
        }

        if desirability in ("desirable", "undesirable"):
            key = f"{voros}_{desirability}"
            if key in quadrants:
                quadrants[key].append(entry)
        else:
            ambiguous[voros].append(entry)

        pred_list.append(entry)

    # ── Bottom-up domain classification within each quadrant ──
    quadrant_domains = {}
    for qname, items in quadrants.items():
        domain_groups = defaultdict(list)
        for item in items:
            # Use subdomain for finer grouping
            group_key = item["subdomain"] or item["domain_ja"]
            domain_groups[group_key].append(item)

        # Aggregate to broader themes
        broad_themes = defaultdict(lambda: {"count": 0, "subdomains": defaultdict(int), "samples": []})
        for item in items:
            theme = item["domain_ja"]
            broad_themes[theme]["count"] += 1
            if item["subdomain"]:
                broad_themes[theme]["subdomains"][item["subdomain"]] += 1
            if len(broad_themes[theme]["samples"]) < 3:
                broad_themes[theme]["samples"].append(item["statement"][:150])

        quadrant_domains[qname] = {
            "total": len(items),
            "themes": {
                k: {
                    "count": v["count"],
                    "subdomains": dict(sorted(v["subdomains"].items(), key=lambda x: -x[1])[:5]),
                    "samples": v["samples"],
                }
                for k, v in sorted(broad_themes.items(), key=lambda x: -x[1]["count"])
            }
        }

    # ── Scenario analysis ──
    scenario_analysis = {"exploratory": [], "normative": [], "predictive": []}
    for sc in scenarios:
        desc = sc["description_ja"] or sc["description"] or ""
        if len(desc) < 20:
            continue
        entry = {
            "name": sc["name_ja"] or sc["name"],
            "description": desc[:300],
            "type": sc["scenario_type"],
            "desirability": sc["desirability"],
            "axes": sc["axes"],
        }
        if sc["scenario_type"] in scenario_analysis:
            if len(scenario_analysis[sc["scenario_type"]]) < 50:
                scenario_analysis[sc["scenario_type"]].append(entry)

    result = {
        "total_predictions": len(pred_list),
        "voros_distribution": {
            "projected": sum(1 for p in pred_list if p["voros"] == "projected"),
            "probable": sum(1 for p in pred_list if p["voros"] == "probable"),
            "plausible": sum(1 for p in pred_list if p["voros"] == "plausible"),
            "possible": sum(1 for p in pred_list if p["voros"] == "possible"),
        },
        "desirability_distribution": {
            "desirable": sum(1 for p in pred_list if p["desirability"] == "desirable"),
            "undesirable": sum(1 for p in pred_list if p["desirability"] == "undesirable"),
            "ambiguous": sum(1 for p in pred_list if p["desirability"] == "ambiguous"),
        },
        "quadrants": quadrant_domains,
        "quadrant_counts": {k: len(v) for k, v in quadrants.items()},
        "domain_distribution": dict(Counter(p["domain_ja"] for p in pred_list).most_common()),
        "taxonomy": [dict(t) for t in taxonomy if t["level"] <= 1],
        "trends_top": [{"name": t["name_ja"] or t["name"], "type": t["trend_type"],
                        "mentions": t["mention_count"]} for t in trends[:30]],
        "scenario_summary": {k: len(v) for k, v in scenario_analysis.items()},
        "scenarios_sample": scenario_analysis,
        "convergence": [dict(c) for c in convergence[:20]],
        "sources_top": [{"name": s["name"], "type": s["source_type"] or "",
                         "org": s["organization"] or "",
                         "reports": s["report_count"]} for s in sources[:20]],
    }

    print(f"  → {len(pred_list)} predictions across 8 quadrants")
    print(f"  → Quadrant counts: {result['quadrant_counts']}")
    return result


# ═══════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("Foresight Mega-Analysis")
    print("=" * 60)

    cla = extract_cla_data()
    signals = extract_signals()
    foresight = extract_foresight()

    # Save combined data
    combined = {
        "generated_at": "2026-04-23",
        "cla": cla,
        "signals": signals,
        "foresight": foresight,
    }

    out_path = OUT / "analysis.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(combined, f, ensure_ascii=False, indent=1)

    print(f"\n✓ Saved to {out_path} ({out_path.stat().st_size / 1024 / 1024:.1f} MB)")
    print("Done.")
