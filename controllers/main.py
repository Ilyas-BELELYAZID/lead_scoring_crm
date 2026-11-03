from odoo import http
from odoo.http import request


class LeadScoringWebsite(http.Controller):
    """Public-facing website: Home, Pricing, Demo form."""

    # ── Home Page ───────────────────────────────────────────────────────
    @http.route('/', type='http', auth='public', website=True)
    def homepage(self, **kwargs):
        return request.render('lead_scoring_crm.homepage')

    # ── Pricing Page ────────────────────────────────────────────────────
    @http.route('/pricing', type='http', auth='public', website=True)
    def pricing(self, **kwargs):
        # Flag the session so we know this visitor saw pricing
        request.session['visited_pricing_page'] = True
        return request.render('lead_scoring_crm.pricing_page')

    # ── Demo Form (GET) ─────────────────────────────────────────────────
    @http.route('/demo', type='http', auth='public', website=True)
    def demo_form(self, **kwargs):
        return request.render('lead_scoring_crm.demo_form')

    # ── Demo Form Submission (POST to /submit-lead or /demo/submit) ─────
    @http.route(['/submit-lead', '/demo/submit'], type='http', auth='public', website=True,
                methods=['POST'], csrf=True)
    def submit_lead(self, **post):
        # 1. Read Telemetry from Form POST (or Session Fallback)
        try:
            pricing_views = int(post.get('pricing_page_visits') or 0)
        except (ValueError, TypeError):
            pricing_views = 0

        try:
            time_on_site = int(post.get('time_on_site') or 0)
        except (ValueError, TypeError):
            time_on_site = 0

        visited_pricing = pricing_views > 0 or request.session.get('visited_pricing_page', False)
        pricing_time = time_on_site or request.session.get('pricing_page_time', 0)
        downloaded_report = request.session.get('downloaded_report', False)

        # 2. Extract Qualification Attributes
        contact_name = post.get('contact_name') or post.get('name') or ''
        company_name = post.get('partner_name') or post.get('company') or ''
        email = post.get('email_from') or post.get('email') or ''
        phone = post.get('phone') or ''
        role = post.get('job_seniority') or post.get('role') or ''
        size = post.get('company_size') or ''
        industry = post.get('industry') or ''
        crm_stack = post.get('existing_crm') or ''

        # 3. Calculate Baseline Heuristic Score
        manual_score = 0
        role_scores = {
            'c_level': 40, 'director': 30, 'manager': 20,
            'individual': 10, 'other': 5,
        }
        size_scores = {
            '1000_plus': 30, '251_1000': 25, '201_1000': 25, '51_250': 20, '51_200': 20,
            '11_50': 15, '1_10': 10,
        }
        manual_score += role_scores.get(role, 0)
        manual_score += size_scores.get(size, 0)
        if visited_pricing:
            manual_score += 15
        if downloaded_report:
            manual_score += 10

        industry_scores = {
            'fintech_banking': 35,
            'it_offshoring': 30,
            'telecom': 25,
            'manufacturing': 20,
            'healthcare': 15,
            'other': 5,
        }
        manual_score += industry_scores.get(industry, 0)

        # 4. Find or Create Partner so prospect appears in Contacts & Customers
        partner = False
        if email:
            partner = request.env['res.partner'].sudo().search([('email', '=', email)], limit=1)
        if not partner and (contact_name or company_name):
            partner_vals = {
                'name': contact_name or company_name,
                'email': email,
                'phone': phone,
                'company_type': 'person' if contact_name else 'company',
            }
            partner = request.env['res.partner'].sudo().create(partner_vals)

        # 5. ORM Create in crm.lead
        lead_vals = {
            'name': f"Demo Request - {company_name or contact_name or 'Prospect'}",
            'partner_id': partner.id if partner else False,
            'contact_name': contact_name,
            'email_from': email,
            'phone': phone,
            'partner_name': company_name,
            'x_job_seniority': role or False,
            'x_company_size': size or False,
            'x_pricing_views': pricing_views,
            'x_time_on_site': time_on_site,
            'lead_role': role or False,
            'company_size': size or False,
            'industry': industry or False,
            'existing_crm': crm_stack or False,
            'description': post.get('message', ''),
            'visited_pricing_page': visited_pricing,
            'pricing_page_time': pricing_time,
            'downloaded_report': downloaded_report,
            'cndp_consent': bool(post.get('cndp_consent')),
            'manual_score': manual_score,
            'priority': '0',        # Starts at 0 stars (unscored)
            'probability': 0.0,     # Starts at 0.0%
            'type': 'opportunity',
        }
        # Assign to the first available salesperson so it appears in CRM pipeline
        default_user = request.env['res.users'].sudo().search([
            ('share', '=', False),
            ('active', '=', True),
        ], limit=1)
        if default_user:
            lead_vals['user_id'] = default_user.id
            if default_user.sale_team_id:
                lead_vals['team_id'] = default_user.sale_team_id.id

        # Default to first stage ('New') if available
        first_stage = request.env['crm.stage'].sudo().search([], order='sequence asc', limit=1)
        if first_stage:
            lead_vals['stage_id'] = first_stage.id

        request.env['crm.lead'].sudo().create(lead_vals)

        # Clear session telemetry
        request.session.pop('visited_pricing_page', None)
        request.session.pop('pricing_page_time', None)
        request.session.pop('downloaded_report', None)

        # Redirect to /demo?success=1 to show the success banner
        return request.redirect('/demo?success=1')

    # ── Telemetry Endpoint (AJAX from JS) ───────────────────────────────
    @http.route('/telemetry/pricing', type='json', auth='public', website=True)
    def track_pricing_telemetry(self, **kwargs):
        time_spent = kwargs.get('time_spent', 0)
        request.session['pricing_page_time'] = int(time_spent)
        request.session['visited_pricing_page'] = True
        return {'status': 'ok'}

    @http.route('/telemetry/report', type='json', auth='public', website=True)
    def track_report_telemetry(self, **kwargs):
        request.session['downloaded_report'] = True
        return {'status': 'ok', 'message': 'Report download logged in telemetry'}

