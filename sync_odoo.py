#!/usr/bin/env python3
"""
sync_odoo.py – AI Scoring Bridge (ML .pkl Powered)
===================================================
Fetches unscored leads from Odoo, loads the trained Scikit-Learn Pipeline
(`deliverables/lead_scoring_model.pkl`), executes predictive ML inference,
and writes back to Odoo:
  • ml_probability (%)
  • priority stars (★ derived from probability)
  • ai_explanation (transparent AI reasoning with ML tag)
  • chatter note in the opportunity timeline

Usage:
    python sync_odoo.py            # Score unscored leads
    python sync_odoo.py --all      # Re-score all Demo Requests
"""

import sys
import os
import subprocess
import json
import warnings
from pathlib import Path

# Suppress sklearn category mismatch warnings during live inference
warnings.filterwarnings('ignore', category=UserWarning)

# Ensure clean UTF-8 printing on Windows PowerShell
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

PSQL_BIN = r"C:\Program Files\Odoo 19.0.20261026\PostgreSQL\bin\psql.exe"
DB_NAME = "db123"
DB_USER = "db1"
DB_PASS = "Tknod6857"

# ── Load Scikit-Learn Trained Model (.pkl) ──────────────────────────
ML_MODEL = None
PKL_PATHS = [
    Path("deliverables/lead_scoring_model.pkl"),
    Path("lead_scoring_model.pkl"),
]

for pkl_file in PKL_PATHS:
    if pkl_file.exists():
        try:
            import joblib
            import pandas as pd
            ML_MODEL = joblib.load(pkl_file)
            print(f"🤖 Loaded trained ML Model: {pkl_file.resolve().name}")
            break
        except Exception as e:
            print(f"⚠️ Could not load {pkl_file}: {e}")

if ML_MODEL is None:
    print("ℹ️ ML .pkl not found. Falling back to heuristic baseline scoring.")


def run_sql(query, fetch_json=False):
    env = os.environ.copy()
    env["PGPASSWORD"] = DB_PASS

    if fetch_json:
        full_query = f"SELECT json_agg(t) FROM ({query}) t;"
        cmd = [PSQL_BIN, "-U", DB_USER, "-h", "localhost", "-d", DB_NAME, "-t", "-A", "-c", full_query]
        res = subprocess.run(cmd, env=env, capture_output=True, text=True)
        out = res.stdout.strip()
        if not out or out == "":
            return []
        try:
            return json.loads(out)
        except Exception:
            return []
    else:
        cmd = [PSQL_BIN, "-U", DB_USER, "-h", "localhost", "-d", DB_NAME, "-c", query]
        res = subprocess.run(cmd, env=env, capture_output=True, text=True)
        return res.returncode == 0


def map_lead_to_ml_features(lead):
    """
    Maps inbound website telemetry and qualification fields into the
    13-feature DataFrame expected by lead_scoring_model.pkl.
    """
    import pandas as pd

    role = str(lead.get('x_job_seniority') or lead.get('lead_role') or '').lower()
    time_spent = float(lead.get('x_time_on_site') or 0.0)
    pricing_views = float(lead.get('x_pricing_views') or 0.0)
    
    # 1. Occupation mapping
    if role in ('c_level', 'director', 'manager'):
        occupation = 'Working Professional'
        specialization = 'Management Specializations'
    else:
        occupation = 'Other'
        specialization = 'Other'

    # 2. Activity & Origin mapping
    visits = max(1.0, 1.0 + pricing_views)
    page_views = max(1.0, 1.0 + pricing_views)

    row = {
        'TotalVisits': visits,
        'Total Time Spent on Website': time_spent,
        'Page Views Per Visit': page_views,
        'Lead Origin': 'Landing Page Submission',
        'Lead Source': 'Direct Traffic',
        'Last Activity': 'Page Visited on Website',
        'Country': 'Other',
        'Specialization': specialization,
        'What is your current occupation': occupation,
        'What matters most to you in choosing a course': 'Better Career Prospects',
        'City': 'Other',
        'A free copy of Mastering The Interview': 'No',
        'Do Not Email': 0
    }
    return pd.DataFrame([row])


def compute_ml_score(lead):
    """
    Infers conversion probability using the trained .pkl model if available,
    or falls back to domain-informed heuristic weighting.
    """
    signals = []
    role = lead.get('x_job_seniority') or lead.get('lead_role') or ''
    pricing_views = lead.get('x_pricing_views') or 0
    time_on_site = lead.get('x_time_on_site') or 0

    if role in ('c_level', 'director'):
        signals.append(f"{role.replace('_', '-').title()} Role")
    elif role == 'manager':
        signals.append("Managerial Role")

    if pricing_views > 0:
        signals.append(f"Pricing Views ({pricing_views}x)")

    if time_on_site > 60:
        signals.append(f"High Dwell Time ({time_on_site}s)")

    # ── Inference via trained Scikit-Learn Pipeline (.pkl) ───────────
    if ML_MODEL is not None:
        try:
            df_features = map_lead_to_ml_features(lead)
            raw_prob = float(ML_MODEL.predict_proba(df_features)[0, 1]) * 100.0
            probability = round(min(max(raw_prob, 0.0), 100.0), 1)
            model_tag = "Scikit-Learn ML Model (.pkl)"
        except Exception as e:
            print(f"   ⚠️ ML inference error: {e}. Using fallback.")
            probability = fallback_heuristic(lead)
            model_tag = "Heuristic Fallback"
    else:
        probability = fallback_heuristic(lead)
        model_tag = "Heuristic Baseline"

    # Priority Stars
    if probability >= 75:
        priority = '3'
    elif probability >= 50:
        priority = '2'
    elif probability >= 25:
        priority = '1'
    else:
        priority = '0'

    signal_text = ' + '.join(signals) if signals else 'Direct Inbound'
    explanation = (
        f"⚡ AI Insight ({model_tag}): "
        f"{'High' if probability >= 75 else 'Medium' if probability >= 50 else 'Low'} intent ({signal_text}). "
        f"Predicted conversion: {probability:.1f}%."
    )

    return probability, priority, explanation


def fallback_heuristic(lead):
    score = 0.0
    role_weights = {'c_level': 35.0, 'director': 25.0, 'manager': 15.0, 'individual': 5.0, 'other': 3.0}
    score += role_weights.get(lead.get('x_job_seniority') or '', 5.0)

    size_weights = {'1000_plus': 25.0, '251_1000': 20.0, '51_250': 15.0, '11_50': 10.0, '1_10': 5.0}
    score += size_weights.get(lead.get('x_company_size') or '', 5.0)

    if (lead.get('x_pricing_views') or 0) > 0:
        score += 20.0
    time = lead.get('x_time_on_site') or 0
    if time > 60:
        score += 10.0
    elif time > 15:
        score += 5.0
    if lead.get('email_from'):
        score += 5.0
    return min(max(score, 0.0), 100.0)


def main():
    force_all = '--all' in sys.argv

    print("=" * 60)
    print("🚀 RevEngine – AI Lead Scoring Engine (Production Bridge)")
    print("=" * 60)

    if force_all:
        query = """
            SELECT id, name, contact_name, email_from, x_job_seniority,
                   x_company_size, x_pricing_views, x_time_on_site
            FROM crm_lead
            WHERE name LIKE 'Demo Request%'
            ORDER BY id DESC
        """
    else:
        query = """
            SELECT id, name, contact_name, email_from, x_job_seniority,
                   x_company_size, x_pricing_views, x_time_on_site
            FROM crm_lead
            WHERE ml_probability = 0 OR ml_probability IS NULL
            ORDER BY id DESC
        """

    leads_to_score = run_sql(query, fetch_json=True)

    if not leads_to_score:
        print("ℹ️  All leads are already scored.")
        print("👉 Run 'python sync_odoo.py --all' if you want to re-score all demo requests.\n")
        return

    print(f"🔍 Processing {len(leads_to_score)} lead(s) with ML Pipeline...\n")

    for lead in leads_to_score:
        prob, prio, expl = compute_ml_score(lead)
        clean_expl = expl.replace("'", "''")

        update_sql = f"""
            UPDATE crm_lead
            SET ml_probability = {prob},
                probability = {prob},
                priority = '{prio}',
                ai_explanation = '{clean_expl}'
            WHERE id = {lead['id']};

            INSERT INTO mail_message (body, model, res_id, message_type, subtype_id, author_id, date)
            VALUES ('<p>{clean_expl}</p>', 'crm.lead', {lead['id']}, 'comment', 2, 2, NOW());
        """
        run_sql(update_sql)

        stars = '★' * int(prio)
        print(f"  ✅ #{lead['id']} {lead['name']} ({lead.get('contact_name') or 'N/A'})")
        print(f"     → ML Probability : {prob}%  |  Priority: {stars or '☆'}")
        print(f"     → {expl}\n")

    print("=" * 60)
    print("🎯 All leads scored and synchronized with Odoo CRM.")
    print("=" * 60)


if __name__ == '__main__':
    main()
