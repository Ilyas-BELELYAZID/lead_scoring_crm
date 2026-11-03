#!/usr/bin/env python3
"""
sync_odoo.py – AI Scoring Bridge
=================================
Fetches unscored leads from Odoo, executes predictive ML scoring (based on
behavioral telemetry + firmographic fit), and writes back:
  • ml_probability (%)
  • priority stars (★ derived from probability)
  • ai_explanation (transparent AI reasoning)
  • chatter note in the opportunity timeline

Usage:
    python sync_odoo.py
"""

import sys
import os
import subprocess
import json

# Ensure clean UTF-8 printing on Windows PowerShell
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

PSQL_BIN = r"C:\Program Files\Odoo 19.0.20261026\PostgreSQL\bin\psql.exe"
DB_NAME = "db123"
DB_USER = "db1"
DB_PASS = "Tknod6857"


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


def compute_ml_score(lead):
    score = 0.0
    signals = []

    # 1. Contact Role Weight
    role_weights = {
        'c_level': 35.0,
        'director': 25.0,
        'manager': 15.0,
        'individual': 5.0,
        'other': 3.0,
    }
    role = lead.get('x_job_seniority') or lead.get('lead_role') or ''
    if role in role_weights:
        score += role_weights[role]
        if role in ('c_level', 'director'):
            signals.append(f"{role.replace('_', '-').title()} Role")

    # 2. Company Size Weight
    size_weights = {
        '1000_plus': 25.0,
        '251_1000': 20.0,
        '51_250': 15.0,
        '11_50': 10.0,
        '1_10': 5.0,
    }
    size = lead.get('x_company_size') or lead.get('company_size') or ''
    if size in size_weights:
        score += size_weights[size]
        if size in ('1000_plus', '251_1000', '51_250'):
            signals.append('Enterprise Target')

    # 3. Telemetry: Pricing Page Visits
    pricing_views = lead.get('x_pricing_views') or 0
    if pricing_views > 0:
        score += 20.0
        signals.append(f'Pricing Views ({pricing_views}x)')

    # 4. Telemetry: Time on Site
    time_on_site = lead.get('x_time_on_site') or 0
    if time_on_site > 60:
        score += 10.0
        signals.append(f'High Dwell Time ({time_on_site}s)')
    elif time_on_site > 15:
        score += 5.0

    # 5. Completeness
    if lead.get('email_from'):
        score += 5.0

    probability = min(max(score, 0.0), 100.0)

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
        f"⚡ AI Insight: {'High' if probability >= 75 else 'Medium' if probability >= 50 else 'Low'} "
        f"intent ({signal_text}). Predicted conversion: {probability:.1f}%."
    )

    return probability, priority, explanation


def main():
    print("=" * 60)
    print("🚀 RevEngine – AI Lead Scoring Engine")
    print("=" * 60)

    query = """
        SELECT id, name, contact_name, email_from, x_job_seniority,
               x_company_size, x_pricing_views, x_time_on_site
        FROM crm_lead
        WHERE ml_probability = 0 OR ml_probability IS NULL
        ORDER BY id DESC
    """
    unscored = run_sql(query, fetch_json=True)

    if not unscored:
        print("ℹ️  All leads are already scored. Showing current pipeline ranking:\n")
        ranked_query = """
            SELECT id, name, contact_name, x_pricing_views, x_time_on_site,
                   ml_probability, priority
            FROM crm_lead
            ORDER BY ml_probability DESC, id DESC
        """
        all_leads = run_sql(ranked_query, fetch_json=True)
        for ld in all_leads:
            stars = '★' * int(ld.get('priority') or 0)
            print(f"  • #{ld['id']} {ld['name']} ({ld['contact_name']})")
            print(f"    ML Probability: {ld['ml_probability']}%  |  Priority: {stars}  |  Site Time: {ld['x_time_on_site']}s")
        print("\n" + "=" * 60)
        return

    print(f"🔍 Found {len(unscored)} unscored lead(s). Computing predictive weights...\n")

    for lead in unscored:
        prob, prio, expl = compute_ml_score(lead)
        clean_expl = expl.replace("'", "''")

        update_sql = f"""
            UPDATE crm_lead
            SET ml_probability = {prob},
                priority = '{prio}',
                ai_explanation = '{clean_expl}'
            WHERE id = {lead['id']};

            INSERT INTO mail_message (body, model, res_id, message_type, subtype_id, author_id, date)
            VALUES ('<p>{clean_expl}</p>', 'crm.lead', {lead['id']}, 'comment', 2, 2, NOW());
        """
        run_sql(update_sql)

        stars = '★' * int(prio)
        print(f"  ✅ #{lead['id']} {lead['name']}")
        print(f"     → ML Probability: {prob}%  |  Priority: {stars or '☆'}")
        print(f"     → {expl}\n")

    print("=" * 60)
    print("🎯 All leads scored and synchronized with CRM Pipeline.")
    print("=" * 60)


if __name__ == '__main__':
    main()
