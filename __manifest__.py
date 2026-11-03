{
    'name': 'CRM Lead Scoring',
    'version': '19.0.1.0.0',
    'category': 'Sales/CRM',
    'summary': 'ML-powered lead scoring with behavioral telemetry and explainability',
    'description': """
        CRM Lead Scoring Module
        =======================
        * Public website: Home, Pricing, and Book-a-Demo pages
        * Behavioral telemetry tracking (pricing page visits, session time)
        * ML-based lead probability scoring (LightGBM)
        * AI explainability notes in lead chatter
        * Priority stars derived from ML probability
        * CNDP Law 09-08 data-processing consent
    """,
    'author': 'Lead Scoring Team',
    'license': 'LGPL-3',
    'depends': ['crm', 'website'],
    'data': [
        'security/ir.model.access.csv',
        'views/crm_lead_views.xml',
        'views/website_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'lead_scoring_crm/static/src/css/styles.css',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}

