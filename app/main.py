import hashlib
import json
import os
import re
import sys
import uuid
import sqlite3
from typing import Optional, Dict
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, urlencode

from app.db import (
    ensure_db, list_jobs, get_job, create_job, set_job_funded,
    set_job_paypal_error, add_delivery, get_deliveries, set_job_delivered,
    latest_verdict, get_verdicts, DELIVERIES_DIR,
    set_job_captured, set_job_settled, set_job_settle_error,
    update_payout_items, set_job_refunded, set_revision_used,
    set_job_state, add_event, get_events,
    get_party, list_parties, get_party_counters, store_reputation_event,
    create_party, get_party_events,
    _now, set_job_terms, set_job_checked, count_appeals,
    emit_verdict_events, set_job_trust_credit,
    set_checker_vesting, set_checker_released, set_checker_dispute_paid,
    set_dispute, emit_reputation_event_once,
    get_certificate_by_job, get_certificate, list_certificates_for_worker,
    log_service_call, get_service_calls, set_party_api_key_hash,
    get_party_by_api_key_hash, list_offers, get_offer,
    get_db_path,
)
from app.brain import decide_terms
from app.models import Criterion, Delivery, parse_price_cents
from app.templates import (render_job_board, render_post_job_form,
                           render_job_detail, render_party_page,
                           render_party_form, render_evidence_pack,
                           render_certificate, render_verify_page,
                           render_dashboard, money_state_of,
                           render_demo_page, render_demo_guide,
                           render_machine_view, _fmt_ts, _site_nav,
                           _event_summary, _escape, CSS, _fmt_cents)
from app.demo import (STORIES as DEMO_STORIES, DATA_DIR as DEMO_DATA_DIR,
                      active_demo_jobs, auto_seed_enabled,
                      auto_seed_status, ensure_demo_parties,
                      fixtures_for_job, history_jobs, load_demo_parties,
                      maybe_start_auto_seed, pop_seed_note,
                      post_ready_job, ready_job,
                      reset_demo, seed_history,
                      set_seed_note,
                      SAMPLE_TEMPLATES, sample_template, attach_sample_template)
from app.samplegen import generate_sample_delivery
from app.service import (
    ServiceError, create_job_action, fund_job_action,
    deliver_job_action, check_job_action, settle_job_action,
    job_status_dict, make_offer_action, accept_offer_action,
    reject_offer_action, withdraw_offer_action, price_agreed,
    split_items as _svc_split_items, do_payouts as _svc_do_payouts,
    start_vesting as _svc_start_vesting,
    release_vesting as _svc_release_vesting,
    maybe_release_vesting as _svc_maybe_release_vesting,
    maybe_advance_trust_credit as _svc_maybe_advance_trust_credit,
    do_refund as _svc_do_refund,
)
import secrets as _secrets
from app.checker import (
    run_check, can_check, CheckNotAllowedError,
    JUDGE_MODEL, JUDGE_FALLBACK_MODEL,
)
from types import SimpleNamespace
from app.paypal_client import (
    authorize_order, capture_authorization, capture_authorization_amount,
    create_payouts, create_or_adopt_payouts,
    get_payout_batch, get_payout_batch_items, void_authorization,
    refund_capture, get_authorization, get_order, PayPalError,
    credentials_present,
)
from app.config import (
    WORKER_SPLIT_PERCENT, CHECKER_SPLIT_PERCENT, PLATFORM_SPLIT_PERCENT,
    WORKER_RECEIVER_EMAIL, CHECKER_RECEIVER_EMAIL, PLATFORM_RECEIVER_EMAIL,
    CLIENT_RECEIVER_EMAIL,
)

BULWARK_PORT = int(os.environ.get('BULWARK_PORT', 8077))
HOST = '127.0.0.1'
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB per file (Slice 1.3)

def parse_criteria_from_form(form_data):
    criteria = []
    i = 0
    while True:
        name_key = f'check_{i}_name'
        op_key = f'check_{i}_operator'
        val_key = f'check_{i}_expected_value'
        type_key = f'check_{i}_type'
        
        if name_key not in form_data or op_key not in form_data or val_key not in form_data or type_key not in form_data:
            break
        
        name = form_data[name_key][0]
        operator = form_data[op_key][0]
        expected_value = form_data[val_key][0]
        criterion_type = form_data[type_key][0]
        
        if name and operator and expected_value and criterion_type:
            criteria.append(Criterion(
                name=name,
                operator=operator,
                expected_value=expected_value,
                criterion_type=criterion_type
            ))
        
        i += 1
    
    return criteria


def get_party_by_name(name: str) -> Optional[Dict]:
    conn = sqlite3.connect(get_db_path())
    row = conn.execute(
        "SELECT * FROM parties WHERE name = ?", (name,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return {
        "id": row[0],
        "name": row[1],
        "kind": row[2],
        "form": row[3],
        "payout_email": row[4],
        "created_at": row[5],
    }


def _parse_multipart_form(content_type: str, body: bytes) -> dict:
    """Parse a multipart/form-data body (stdlib only, cgi-free, binary-safe).

    Returns a dict mapping field name -> {'filename': str|None,
    'data': bytes, 'content_type': str|None}.
    Does NOT break urlencoded form handling — callers check the
    Content-Type header and route to this function only for multipart.
    """
    m = re.search(r'boundary=(?:"([^"]+)"|([^;,\s]+))', content_type)
    if not m:
        raise ValueError("No boundary found in Content-Type")
    boundary = (m.group(1) or m.group(2)).encode('ascii')
    delimiter = b'--' + boundary

    fields = {}
    parts = body.split(delimiter)
    for part in parts:
        # Skip preamble, epilogue, and the closing "--\r\n"
        if part in (b'', b'--\r\n', b'--', b'--\n', b'\r\n', b'\n'):
            continue
        # Each real part begins with CRLF after the delimiter
        part = part.lstrip(b'\r\n')
        if not part:
            continue
        if part.startswith(b'--'):  # closing boundary
            continue
        # Split headers from content: headers end at first blank line
        header_end = part.find(b'\r\n\r\n')
        if header_end == -1:
            header_end = part.find(b'\n\n')
            if header_end == -1:
                continue
            header_bytes = part[:header_end]
            content = part[header_end + 2:]
        else:
            header_bytes = part[:header_end]
            content = part[header_end + 4:]
        # Strip trailing CRLF that belongs to the boundary delimiter
        if content.endswith(b'\r\n'):
            content = content[:-2]
        elif content.endswith(b'\n'):
            content = content[:-1]

        name = None
        filename = None
        part_content_type = None
        for line in header_bytes.split(b'\r\n'):
            if b':' not in line:
                continue
            key, _, val = line.partition(b':')
            key_low = key.strip().lower()
            val = val.strip()
            if key_low == b'content-disposition':
                nm = re.search(rb'name="([^"]*)"', val)
                if nm:
                    name = nm.group(1).decode('utf-8', 'replace')
                fm = re.search(rb'filename="([^"]*)"', val)
                if fm:
                    filename = fm.group(1).decode('utf-8', 'replace')
            elif key_low == b'content-type':
                part_content_type = val.decode('utf-8', 'replace')
        if name is None:
            continue
        if name not in fields:
            fields[name] = {
                'filename': filename,
                'data': content,
                'content_type': part_content_type,
            }
    return fields


def _sanitize_filename(filename: str) -> str:
    """Strip path components and dangerous characters from a filename."""
    # Remove any directory components (handle both / and \)
    filename = os.path.basename(filename.replace('\\', '/'))
    # Remove control characters and null bytes
    filename = re.sub(r'[\x00-\x1f\x7f]', '_', filename)
    # Strip leading dots / dashes that could be dangerous
    filename = re.sub(r'^[.-]+', '', filename)
    if not filename:
        filename = 'upload'
    return filename

def backfill_events(job) -> None:
    """Slice 1.7: jobs created before the event table existed get their
    timeline synthesized ONCE from the stored fields (source='backfill',
    original timestamps preserved). No-op when events already exist."""
    if get_events(job.id):
        return
    add_event(job.id, 'posted', actor='client', source='backfill',
              detail={"price_cents": job.price_cents,
                      "currency": job.currency},
              created_at=job.created_at)
    if job.paypal_order_id:
        add_event(job.id, 'funded', actor='client', source='backfill',
                  detail={"order_id": job.paypal_order_id,
                          "authorization_id": job.paypal_authorization_id,
                          "authorization_status": job.authorization_status,
                          "amount_cents": job.funded_amount_cents,
                          "currency": job.funded_currency},
                  created_at=job.funded_at or job.created_at)
    for d in reversed(get_deliveries(job.id)):
        add_event(job.id, 'revised' if d.is_revision else 'delivered',
                  actor='worker', source='backfill',
                  detail={"files": [d.filename]},
                  created_at=d.uploaded_at)
    for v in reversed(get_verdicts(job.id)):
        add_event(job.id, 'verdict', actor='checker', source='backfill',
                  detail={"overall_pass": v["overall_pass"],
                          "judge_model": v.get("judged_model", "")},
                  created_at=v["checked_at"])
    if job.capture_id:
        add_event(job.id, 'captured', actor='client', source='backfill',
                  detail={"capture_id": job.capture_id,
                          "capture_status": job.capture_status,
                          "amount_cents": job.captured_amount_cents,
                          "currency": job.captured_currency},
                  created_at=job.captured_at or job.created_at)
    if job.payout_batch_id:
        add_event(job.id, 'settled', actor='client', source='backfill',
                  detail={"payout_batch_id": job.payout_batch_id},
                  created_at=job.settled_at or job.created_at)
    if job.refund_id:
        add_event(job.id, 'refunded', actor='client', source='backfill',
                  detail={"refund_id": job.refund_id,
                          "refund_status": job.refund_status},
                  created_at=job.refunded_at or job.created_at)


class BulwarkHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_path = urlparse(self.path)
        path = parsed_path.path

        if path == '/':
            self.serve_entry()
        elif path == '/verify':
            qs = parse_qs(parsed_path.query, keep_blank_values=True)
            self.serve_verify(qs.get('serial', [''])[0].strip(),
                              qs.get('code', [''])[0].strip(),
                              submitted=('serial' in qs
                                         or 'code' in qs))
        elif path == '/dashboard':
            self.serve_dashboard()
        elif path == '/demo':
            self.serve_demo()
        elif path.startswith('/demo/fixture/'):
            self.serve_demo_fixture(path)
        elif path == '/post':
            self.serve_post_form()
        elif path == '/party/new':
            self.serve_party_form()
        elif path.startswith('/party/'):
            self.serve_party_page(path)
        elif path.startswith('/api/v1/jobs/'):
            self.api_get_job(path)
        elif path.startswith('/job/') and path.endswith('/evidence'):
            self.serve_evidence(path)
        elif path.startswith('/job/') and path.endswith('/machine'):
            self.serve_machine(path)
        elif path.startswith('/job/') and path.endswith('/certificate'):
            self.serve_certificate(path)
        elif path.startswith('/job/') and \
                (path.endswith('/as/worker') or
                 path.endswith('/as/client')):
            self.serve_job_as_view(path)
        elif path.startswith('/job/'):
            self.serve_job_detail(path)
        elif path == '/certificates':
            self.serve_certificates()
        elif path == '/how':
            self.serve_how_it_works()
        elif path == '/view/client':
            self.send_response(302)
            self.send_header('Location', '/c')
            self.end_headers()
        elif path == '/view/worker':
            self.send_response(302)
            self.send_header('Location', '/w')
            self.end_headers()
        elif path == '/c':
            qs = parse_qs(parsed_path.query)
            state_filter = qs.get('state', [''])[0]
            self.serve_job_board(state_filter, variant='client')
        elif path == '/w':
            qs = parse_qs(parsed_path.query)
            state_filter = qs.get('state', [''])[0]
            self.serve_job_board(state_filter, variant='worker')
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Not Found')

    def do_POST(self):
        parsed_path = urlparse(self.path)
        path = parsed_path.path

        if path == '/demo/reset':
            self.handle_demo_reset()
        elif path == '/demo/seed-history':
            self.handle_demo_seed_history()
        elif path == '/demo/ready-job':
            self.handle_demo_ready_job()
        elif path == '/demo/actor':
            self.handle_demo_actor()
        elif path == '/api/v1/jobs':
            self.api_create_job()
        elif path.startswith('/api/v1/jobs/'):
            self.api_job_action(path)
        elif path.startswith('/party/') and path.endswith('/api-key'):
            self.handle_party_api_key(path)
        elif path == '/post':
            self.handle_post_form()
        elif path == '/parties':
            self.handle_party_create()
        elif path == '/webhooks/paypal':
            self.handle_webhook()
        elif path.startswith('/job/') and '/offer' in path:
            self.handle_offer(path)
        elif path.startswith('/job/') and path.endswith('/fund'):
            self.handle_fund(path)
        elif path.startswith('/job/') and path.endswith('/deliver'):
            self.handle_deliver(path)
        elif path.startswith('/job/') and path.endswith('/deliver-fixture'):
            self.handle_deliver_fixture(path)
        elif path.startswith('/job/') and path.endswith('/generate-deliver'):
            self.handle_generate_deliver(path)
        elif path.startswith('/job/') and path.endswith('/check'):
            self.handle_check(path)
        elif path.startswith('/job/') and path.endswith('/appeal'):
            self.handle_appeal(path)
        elif path.startswith('/job/') and path.endswith('/settle'):
            self.handle_settle(path)
        elif path.startswith('/job/') and path.endswith('/revise'):
            self.handle_revise(path)
        elif path.startswith('/job/') and path.endswith('/reject'):
            self.handle_reject(path)
        elif path.startswith('/job/') and path.endswith('/verify'):
            self.handle_verify(path)
        elif path.startswith('/job/') and path.endswith('/dispute/resolve'):
            self.handle_dispute_resolve(path)
        elif path.startswith('/job/') and path.endswith('/dispute'):
            self.handle_dispute_open(path)
        elif path.startswith('/job/') and path.endswith('/release-vesting'):
            self.handle_release_vesting(path)
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Not Found')

    def serve_dashboard(self):
        """Slice 2.7: money-state dashboard. Rows are prepared once,
        here, and are the single source for the AG Grid JSON, the
        server-rendered fallback table, and the per-state totals —
        so the three can never disagree."""
        jobs = list_jobs()
        view, seat = self._context_seat()
        if view != 'door':
            if seat is None:
                jobs = []
            elif view == 'client':
                jobs = [j for j in jobs if j.client_id == seat['id']]
            else:
                jobs = [j for j in jobs if j.worker_id == seat['id']]
        names = {}

        def pname(pid):
            if pid not in names:
                p = get_party(pid) if pid else None
                names[pid] = p['name'] if p else '—'
            return names[pid]

        rows = []
        for job in jobs:
            key, label = money_state_of(job.state)
            funded = int(job.funded_amount_cents or job.price_cents)
            captured = int(job.captured_amount_cents or 0)
            if job.trust_credit_state == 'advanced':
                captured += int(job.advanced_cents or 0)
            if key == 'posted':
                in_state = int(job.price_cents)
            elif key in ('funded-held', 'delivered', 'refunded'):
                in_state = funded
            else:  # checking / released: captured once it exists
                in_state = captured or funded
            paid = sum(int(it.get('amount_cents') or 0)
                       for it in (job.payout_items or []))
            paid += int(job.advanced_cents or 0)
            if job.checker_vesting_state in ('released',
                                             'paid_to_client'):
                paid += int(job.checker_vesting_amount_cents or 0)
            vesting_pending = job.checker_vesting_state == 'vesting'
            events = get_events(job.id)
            updated = _fmt_ts(events[-1]['created_at'] if events
                              else job.created_at)
            rows.append({
                'id': job.id,
                'title': job.title,
                'client': pname(job.client_id),
                'worker': pname(job.worker_id),
                'checker': pname(job.checker_id),
                'price_cents': int(job.price_cents),
                'price_mode': job.price_mode,
                'currency': job.currency or 'USD',
                'money_state_key': key,
                'money_state_label': label,
                'funded_cents': int(job.funded_amount_cents or 0),
                'captured_cents': captured,
                'paid_out_cents': paid,
                'vesting_cents': (int(job.checker_vesting_amount_cents
                                      or 0) if vesting_pending else 0),
                'vesting_pending': vesting_pending,
                'amount_in_state_cents': in_state,
                'updated': updated,
            })
        from app.templates import _MONEY_STATES
        totals = []
        for key, label in _MONEY_STATES:
            sel = [r for r in rows if r['money_state_key'] == key]
            totals.append((key, label, len(sel),
                           sum(r['amount_in_state_cents'] for r in sel)))
        
        # Collect transaction history for all jobs
        history = []
        for job in jobs:
            for event in get_events(job.id):
                history.append({
                    'ts': event['created_at'],
                    'job_title': job.title,
                    'text': _event_summary(event['kind'], event['detail']),
                    'amount_cents': event.get('detail', {}).get('amount_cents') or 
                                 event.get('detail', {}).get('price_cents') or 0
                })
        
        # Sort newest first and cap at 40
        history.sort(key=lambda x: x['ts'], reverse=True)
        history = history[:40]
        
        view_note = None
        if view != 'door' and seat is not None:
            nm = _escape(seat['name'])
            role = 'the client' if view == 'client' else 'the worker'
            view_note = (f'Showing payments for {nm} — the jobs '
                         f'where {nm} is {role}.')
        html = render_dashboard(rows, totals, history=history,
                                nav_view=view, view_note=view_note)
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))

    # -- Slice 2.8: demo cast --------------------------------------
    def _demo_actor(self):
        """The visitor's demo role, from the bw_actor cookie (set by
        the boards (/c, /w)). Bulwark has no accounts; the cookie
        picks the seat the visitor is playing, and since v5.7 the
        job page shows that side's controls at that side's desk —
        the service layer remains the only enforcement."""
        raw = self.headers.get('Cookie', '') or ''
        for part in raw.split(';'):
            part = part.strip()
            if part.startswith('bw_actor='):
                try:
                    party = get_party(int(part.split('=', 1)[1]))
                    if party and party['kind'] in ('client', 'worker', 'checker'):
                        return party
                    return None
                except (ValueError, TypeError):
                    return None
        return None

    def _current_view(self):
        """Get the visitor's view from the bw_view cookie (set by
        the one-click switcher on /c or /w). Bulwark has no
        accounts; since v5.7 the view also selects which side's
        controls a job page renders (UI separation only — the
        service layer enforces every action)."""
        raw = self.headers.get('Cookie', '') or ''
        for part in raw.split(';'):
            part = part.strip()
            if part.startswith('bw_view='):
                try:
                    return part.split('=', 1)[1]
                except (ValueError, TypeError):
                    return 'client'
        return 'client'

    def _context_view(self):
        """v5.1: the context a shared page inherits — the bw_view
        cookie when it names a board ('client'/'worker'), else
        'door'. Unlike _current_view this NEVER invents a role:
        no cookie means the neutral door context."""
        raw = self.headers.get('Cookie', '') or ''
        for part in raw.split(';'):
            part = part.strip()
            if part.startswith('bw_view='):
                v = part.split('=', 1)[1]
                return v if v in ('client', 'worker') else 'door'
        return 'door'

    def _context_seat(self):
        """(view, seat) for shared-page filtering. ('door', None)
        when the visitor carries no role; (view, party) with the
        seat from the existing _resolve_view_seat mechanism;
        (view, None) when no party qualifies (empty DB) — callers
        treat that as a context whose set is empty."""
        view = self._context_view()
        if view == 'door':
            return 'door', None
        try:
            return view, self._resolve_view_seat(view)
        except Exception:
            return view, None

    def _resolve_view_seat(self, view_kind):
        """Resolve the seat for a view (client or worker). Resolution order:
        1. ?party=<id> query param — use it if the party exists AND qualifies.
        2. The bw_actor cookie party (existing _demo_actor() mechanism) if it qualifies.
        3. Demo anchor by name: client view -> "Mira's Shop"; worker view -> "LinguaCert Agency".
        4. The lowest-id qualifying party.
        A bogus, unknown, non-numeric or non-qualifying party param falls through to next step.
        Never returns None — always returns a qualifying party.
        """
        from urllib.parse import parse_qs, urlparse
        qs = parse_qs(urlparse(self.path).query)
        party_param = qs.get('party', [''])[0].strip()
        
        # Step 1: Query param party
        if party_param:
            try:
                party_id = int(party_param)
                party = get_party(party_id) if party_id else None
                if party and self._party_qualifies_for_view(party, view_kind):
                    return party
            except (ValueError, TypeError):
                pass
        
        # Step 2: bw_actor cookie party
        cookie_party = self._demo_actor()
        if cookie_party and self._party_qualifies_for_view(cookie_party, view_kind):
            return cookie_party
        
        # Step 3: Demo anchor by name
        demo_anchor = self._get_demo_anchor_by_view(view_kind)
        if demo_anchor:
            return demo_anchor
        
        # Step 4: Lowest-id qualifying party
        all_parties = list_parties()
        qualifying = []
        for party in all_parties:
            if self._party_qualifies_for_view(party, view_kind):
                qualifying.append(party)
        
        if not qualifying:
            raise Exception(f"No qualifying party found for {view_kind} view")
        
        return min(qualifying, key=lambda p: p['id'])


    def _party_qualifies_for_view(self, party, view_kind):
        """Check if a party qualifies for a specific view."""
        if view_kind == 'client':
            return party['kind'] == 'client' or any(
                j.client_id == party['id'] and j.demo_tag != 'archived'
                for j in list_jobs()
            )
        else:  # worker view
            return party['kind'] == 'worker' or any(
                j.worker_id == party['id'] and j.demo_tag != 'archived'
                for j in list_jobs()
            )


    def _get_demo_anchor_by_view(self, view_kind):
        """Get the demo anchor party for a view."""
        from app.demo import load_demo_parties
        by_name = ensure_demo_parties()
        demo_parties = [by_name[s['name']]
                       for s in load_demo_parties()]
        
        if view_kind == 'client':
            for p in demo_parties:
                if p['name'] == "Mira's Shop":
                    return p
        else:  # worker view
            for p in demo_parties:
                if p['name'] == "LinguaCert Agency":
                    return p
        return None

    def _demo_guide(self, job) -> str:
        actor = self._demo_actor()
        cp = get_party(job.client_id) if job.client_id else None
        wp = get_party(job.worker_id) if job.worker_id else None
        return render_demo_guide(
            job, actor,
            cp['name'] if cp else 'the client',
            wp['name'] if wp else 'the worker',
            view=self._context_view())

    def serve_demo(self):
        maybe_start_auto_seed()
        by_name = ensure_demo_parties()
        demo_parties = [by_name[s['name']]
                        for s in load_demo_parties()]
        
        # Add the checker party if not already present
        checker_party = get_party_by_name('Verifier Prime')
        if checker_party and checker_party not in demo_parties:
            demo_parties.append(checker_party)
        
        note = pop_seed_note()
        if note is None:
            active, message = auto_seed_status()
            if active and message:
                note = message
        
        # Phase jobs for the "Try the flow" section.
        all_jobs = list_jobs()
        phase_jobs = [j for j in all_jobs
                      if j.demo_tag == 'phase']
        
        html = render_demo_page(demo_parties, DEMO_STORIES,
                                active_demo_jobs(), self._demo_actor(),
                                history=history_jobs(),
                                seed_note=note,
                                ready=ready_job(),
                                phase_jobs=phase_jobs)
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))

    def handle_demo_reset(self):
        reset_demo()
        self.send_response(302)
        self.send_header('Location', '/demo')
        self.end_headers()
        self.wfile.write(b'')

    def handle_demo_seed_history(self):
        # Plays the finished demo projects through the real flows;
        # can take a minute (several PayPal sandbox arcs).
        try:
            set_seed_note(seed_history())
        except Exception as e:
            set_seed_note(f"Seeding stopped: {type(e).__name__}: {e}")
        self.send_response(302)
        self.send_header('Location', '/demo')
        self.end_headers()
        self.wfile.write(b'')

    def handle_demo_ready_job(self):
        """Demo shortcut: post the ready-made job (or reuse the one
        already waiting) and land the visitor on its page, where the
        Fund step is the ordinary one."""
        job = post_ready_job()
        self.send_response(302)
        self.send_header('Location', f'/job/{job.id}')
        self.end_headers()
        self.wfile.write(b'')

    def handle_demo_actor(self):
        """POST /demo/actor — seat the visitor as one of the
        three demo cast parties (v5.3). The bw_actor cookie
        picks the seat being played (and, since v5.7, which
        side's desk the job pages render); the service layer
        enforces every action. Invalid ids change nothing."""
        length = int(self.headers.get('Content-Length', 0) or 0)
        form = parse_qs(self.rfile.read(length).decode('utf-8')) \
            if length else {}
        raw = (form.get('party_id') or [None])[0]
        party = None
        try:
            candidate = get_party(int(raw))
        except (TypeError, ValueError):
            candidate = None
        cast = {"Mira's Shop", "LinguaCert Agency",
                "Verifier Prime"}
        if candidate and candidate['name'] in cast:
            party = candidate
        self.send_response(302)
        self.send_header('Location', '/demo')
        if party is not None:
            self.send_header(
                'Set-Cookie',
                f'bw_actor={party["id"]}; Path=/; Max-Age=86400')
            if party['kind'] == 'client':
                self.send_header(
                    'Set-Cookie',
                    'bw_view=client; Path=/; Max-Age=86400')
            elif party['kind'] == 'worker':
                self.send_header(
                    'Set-Cookie',
                    'bw_view=worker; Path=/; Max-Age=86400')
            # checker: bw_view untouched
        self.end_headers()
        self.wfile.write(b'')

    def serve_demo_fixture(self, path):
        name = path.rstrip('/').split('/')[-1]
        safe = os.path.basename(name)
        full = os.path.join(DEMO_DATA_DIR, safe)
        if safe != name or not os.path.isfile(full):
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'No such fixture')
            return
        with open(full, 'rb') as f:
            data = f.read()
        self.send_response(200)
        self.send_header('Content-Type', 'text/csv; charset=utf-8')
        self.send_header('Content-Disposition',
                         f'attachment; filename="{safe}"')
        self.end_headers()
        self.wfile.write(data)

    def serve_job_board(self, state_filter: str = "", variant: str = "home"):
        # Self-healing demo: if the fallback builder is enabled and
        # the demo content is incomplete (e.g. a fresh deploy whose
        # bundled snapshot was missing), kick it off in the
        # background and say so on the page instead of showing a
        # bare empty board.
        maybe_start_auto_seed()
        # Slice 2.8: archived demo runs are hidden from the board.
        jobs = [j for j in list_jobs() if j.demo_tag != 'archived']
        if state_filter:
            jobs = [j for j in jobs
                    if j.state == state_filter
                    or (state_filter == 'checked'
                        and j.state in ('checked_pass', 'checked_fail',
                                        'revision'))]
        # Both boards list the SAME jobs (v5.7 role separation):
        # the worker board used to keep only posted jobs, which hid
        # a job's progress from the worker's desk — now each side
        # sees every job and advances it with its own controls on
        # the job page. Only the framing differs per variant.
        notice = None
        active, message = auto_seed_status()
        if active and message:
            notice = message
        elif not jobs and not state_filter and auto_seed_enabled():
            notice = ("Demo content is being prepared — the sample "
                      "projects will appear here shortly.")
        
        # Compute counters for the home page (Item D.1)
        # Mapping: Held = 'funded-held' + 'delivered'; Being checked = 'checking';
        # Paid out = 'released'; Refunded = 'refunded'
        held = 0
        checking = 0
        paid_out = 0
        refunded = 0
        
        for job in jobs:
            key, _ = money_state_of(job.state)
            if key in ('funded-held', 'delivered'):
                held += job.price_cents or 0
            elif key == 'checking':
                checking += job.price_cents or 0
            elif key == 'released':
                paid_out += job.price_cents or 0
            elif key == 'refunded':
                refunded += job.price_cents or 0
        
        counters = {
            'held': held,
            'checking': checking,
            'paid_out': paid_out,
            'refunded': refunded
        }
        
        # Compute latest certificate (Item D.2)
        latest_cert = None
        for job in jobs:
            cert = get_certificate_by_job(job.id)
            if cert and cert.get('issued_at'):
                if latest_cert is None or cert['issued_at'] > latest_cert['issued_at']:
                    latest_cert = dict(cert)
                    latest_cert['job_title'] = job.title
                    _wp = get_party(job.worker_id) if job.worker_id else None
                    latest_cert['worker_name'] = _wp['name'] if _wp else ''
        
        # Prepare card data structure for template compatibility
        counters_data = {
            'held': {'amount': held, 'formatted': _fmt_cents(held)},
            'checking': {'amount': checking, 'formatted': _fmt_cents(checking)},
            'paid_out': {'amount': paid_out, 'formatted': _fmt_cents(paid_out)},
            'refunded': {'amount': refunded, 'formatted': _fmt_cents(refunded)}
        }
        
        # Board role strip (v5.3): name the seat this board
        # shows — the board's own seating rule decides it.
        if variant == 'client':
            actor_party = get_party_by_name("Mira's Shop")
        elif variant == 'worker':
            actor_party = get_party_by_name("LinguaCert Agency")
        else:
            actor_party = self._demo_actor()
        actor_line = None
        if actor_party:
            actor_line = (
                f"You are: {actor_party['name']} "
                f"({actor_party['kind']}) — each job page "
                "says what your next step is from this seat.")
        html = render_job_board(jobs, state_filter=state_filter,
                                notice=notice, counters=counters_data,
                                latest_certificate=latest_cert, nav_view=variant if variant in ('client', 'worker') else 'client',
                                actor_line=actor_line)
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        if variant == 'client':
            self.send_header('Set-Cookie', 'bw_view=client; Path=/; Max-Age=86400')
            party = get_party_by_name("Mira's Shop")
            if party:
                self.send_header('Set-Cookie', f'bw_actor={party["id"]}; Path=/; Max-Age=86400')
        elif variant == 'worker':
            self.send_header('Set-Cookie', 'bw_view=worker; Path=/; Max-Age=86400')
            party = get_party_by_name("LinguaCert Agency")
            if party:
                self.send_header('Set-Cookie', f'bw_actor={party["id"]}; Path=/; Max-Age=86400')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))

    def serve_entry(self):
        """Slice 2: the entry page (door) — door nav, hero, chooser, counters grid,
        latest certificate card, footer lines. NO job list, NO filter chips, NO rails, NO Post a job.
        """
        maybe_start_auto_seed()
        jobs = [j for j in list_jobs() if j.demo_tag != 'archived']
        held = checking = paid_out = refunded = 0
        for job in jobs:
            key, _ = money_state_of(job.state)
            if key in ('funded-held', 'delivered'):
                held += job.price_cents or 0
            elif key == 'checking':
                checking += job.price_cents or 0
            elif key == 'released':
                paid_out += job.price_cents or 0
            elif key == 'refunded':
                refunded += job.price_cents or 0
        latest_cert = None
        for job in jobs:
            cert = get_certificate_by_job(job.id)
            if cert and cert.get('issued_at'):
                if latest_cert is None or cert['issued_at'] > latest_cert['issued_at']:
                    latest_cert = dict(cert)
                    latest_cert['job_title'] = job.title
                    _wp = get_party(job.worker_id) if job.worker_id else None
                    latest_cert['worker_name'] = _wp['name'] if _wp else ''
        nav = _site_nav('door')
        chooser = (
            '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px;margin:6px 0 26px">'
            '<a href="/c" style="text-decoration:none"><div class="counter-card" style="text-align:left;padding:22px">'
            '<div style="font-size:1.15rem;font-weight:700;color:var(--deep-blue)">I am here to hire</div>'
            '<p style="margin-top:6px">Post a job, fund it, and pay only for work that passes the check.</p>'
            '<div style="margin-top:10px;font-weight:600;color:var(--deep-blue)">Client view &rarr;</div></div></a>'
            '<a href="/w" style="text-decoration:none"><div class="counter-card" style="text-align:left;padding:22px">'
            '<div style="font-size:1.15rem;font-weight:700;color:var(--deep-blue)">I am here to work</div>'
            '<p style="margin-top:6px">Browse open jobs, make an offer, and get paid when your work passes.</p>'
            '<div style="margin-top:10px;font-weight:600;color:var(--deep-blue)">Worker view &rarr;</div></div></a></div>')
        parts = [
            '<!DOCTYPE html>', '<html lang="en">', '<head>',
            '<meta charset="UTF-8">', '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
            '<title>Bulwark</title>', f'<style>{CSS}</style>', '</head>',
            '<body>', '<div class="container">', nav,
            '<header>', '<h1>Bulwark</h1>',
            '<p>Hire any agent. Pay only for work that passes.</p>',
            '<p>Your money is held, the delivery is checked against your criteria, then released or refunded automatically.</p>',
            '</header>', chooser,
            '<div class="counters-grid">',
            f'<a href="/dashboard" class="counter-card"><div class="counter-value">{_fmt_cents(held)}</div><div class="counter-label">Held</div></a>',
            f'<a href="/dashboard" class="counter-card"><div class="counter-value">{_fmt_cents(checking)}</div><div class="counter-label">Being checked</div></a>',
            f'<a href="/dashboard" class="counter-card"><div class="counter-value">{_fmt_cents(paid_out)}</div><div class="counter-label">Paid out</div></a>',
            f'<a href="/dashboard" class="counter-card"><div class="counter-value">{_fmt_cents(refunded)}</div><div class="counter-label">Refunded</div></a>',
            '</div>',
        ]
        # Always show the latest-certificate card (Item D.2)
        # In empty DB show calm placeholder; in populated case show real certificate
        if latest_cert:
            parts.append(
                '<a href="/certificates" class="counter-card" style="display:block;text-align:left;margin-top:16px">'
                '<div style="font-weight:700;color:var(--deep-blue)">Latest certificate</div>'
                f'<p style="margin-top:4px">{_escape(latest_cert["job_title"])} — {_escape(latest_cert["worker_name"])}, checked and settled.</p></a>')
        else:
            parts.append(
                '<a href="/certificates" class="counter-card" style="display:block;text-align:left;margin-top:16px">'
                '<div style="font-weight:700;color:var(--deep-blue)">Latest certificate</div>'
                '<p style="margin-top:4px">Latest certificate - a settled job\'s certificate will appear here.</p></a>')
        parts += ['<footer>', '<p>Money is held via PayPal until the check passes. · Agents and people both work here.</p>', '</footer>', '</div>', '</body>', '</html>']
        html = ''.join(parts)
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))

    def serve_party_page(self, path):
        parts = path.strip('/').split('/')
        if len(parts) < 2:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Not Found')
            return
        party_id = int(parts[1])
        party = get_party(party_id)
        if party is None:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Party not found')
            return
        
        # Get parties of this kind for filtering
        all_parties = list_parties()
        same_kind = [p for p in all_parties if p['kind'] == party['kind']]
        
        # Get jobs for this party
        jobs = list_jobs()
        party_jobs = []
        for job in jobs:
            if (party['kind'] == 'client' and job.client_id == party_id) or \
               (party['kind'] == 'worker' and job.worker_id == party_id) or \
               (party['kind'] == 'checker' and job.checker_id == party_id) or \
               (party['kind'] == 'platform' and job.worker_id == party_id):
                party_jobs.append(job)
        
        # Get reputation events
        events = get_party_events(party_id)
        
        html = render_party_page(party, same_kind, party_jobs, events, nav_view=self._context_view())
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))
    
    def serve_post_form(self):
        parsed_path = urlparse(self.path)
        qs = parse_qs(parsed_path.query)
        template_param = qs.get('template', [''])[0]
        
        template_id = None
        prefilled_values = None
        
        if template_param:
            template = sample_template(template_param)
            if template:
                template_id = template['id']
                prefilled_values = {
                    'title': template['title'],
                    'description': template['description'],
                    'price': f"{template['price_cents'] / 100:.2f}",
                    'price_mode': 'fixed',
                }
                
                parties = ensure_demo_parties()
                client_party = parties.get(template['client'])
                worker_party = parties.get(template['worker'])
                checker_party = parties.get('Verifier Prime')
                
                if client_party and worker_party and checker_party:
                    prefilled_values.update({
                        'client_id': client_party['id'],
                        'worker_id': worker_party['id'],
                        'checker_id': checker_party['id']
                    })
                    
                    criteria = []
                    for criterion in template['criteria']:
                        criteria.append({
                            'name': criterion.name,
                            'operator': criterion.operator,
                            'expected_value': criterion.expected_value,
                            'type': criterion.criterion_type
                        })
                    prefilled_values['criteria'] = criteria
        
        html = render_post_job_form(list_parties(), templates=SAMPLE_TEMPLATES, 
                                   template_id=template_id, form_open=bool(template_param),
                                   values=prefilled_values, nav_view=self._context_view())
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))
    
    def serve_party_form(self):
        html = render_party_form(nav_view=self._context_view())
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))

    def handle_party_create(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length).decode('utf-8')
        form_data = parse_qs(post_data)
        name = form_data.get('name', [''])[0].strip()
        kind = form_data.get('kind', [''])[0].strip()
        form = form_data.get('form', [''])[0].strip()
        payout_email = form_data.get('payout_email', [''])[0].strip()
        errors = {}
        if not name:
            errors['name'] = "Missing: give the party a display name."
        if kind not in ('client', 'worker', 'checker'):
            errors['kind'] = ("Choose a kind: client, worker or "
                              "checker.")
        if form not in ('human', 'agent', 'company'):
            errors['form'] = ("Choose a form: human, agent or "
                              "company.")
        if errors:
            html = render_party_form(
                values={'name': name, 'kind': kind, 'form': form,
                        'payout_email': payout_email},
                errors=errors, nav_view=self._context_view())
            self.send_response(400)
            self.send_header('Content-Type',
                             'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html.encode('utf-8'))
            return
        party_id = create_party(name, kind, form, payout_email)
        self.send_response(302)
        self.send_header('Location', f'/party/{party_id}')
        self.end_headers()
        self.wfile.write(b'')

    def _sample_generator_visible(self, job) -> bool:
        """The demo sample generator: offered on EVERY funded job,
        whatever its demo tag and whoever the visitor is playing.
        Role separation is a rendering rule, not a visibility rule
        here — render_job_detail shows the whole delivery section
        (this button included) only in the worker view, so the
        button appears exactly where the worker's desk is."""
        return job.state == 'funded'

    def _render_detail(self, job, info_message: str = "",
                       offer_error=None, deliver_error: str = ""):
        job = self._maybe_release_vesting(job)
        deliveries = get_deliveries(job.id)
        job = self._refresh_payout_statuses(job)
        backfill_events(job)
        sync_note = self._reconcile(job, record=True)
        offers, offer_workers, offer_actor = self._offer_view_data(job)
        html = render_job_detail(job, info_message=info_message,
                                  deliveries=deliveries,
                                  verdict=latest_verdict(job.id),
                                  verdicts=get_verdicts(job.id),
                                  events=get_events(job.id),
                                  sync_note=sync_note,
                                  demo_fixtures=fixtures_for_job(job),
                                  sample_generator=
                                  self._sample_generator_visible(job),
                                  offers=offers,
                                  offer_workers=offer_workers,
                                  offer_actor=offer_actor,
                                  offer_error=offer_error,
                                   deliver_error=deliver_error,
                                   guide_html=self._demo_guide(job),
                                    nav_view=self._context_view(),
                                   price_agreed=price_agreed(job))
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))

    def serve_job_as_view(self, path):
        """GET /job/<id>/as/<client|worker>: switch the visitor's
        view (the bw_view cookie, with the same anchor seat the
        boards set) and land back on the SAME job. The job page's
        pointer lines use this, so a step that belongs to the other
        side is one tap away without losing the job. UI-level only:
        it sets the same cookies visiting /c or /w would set."""
        parts = path.strip('/').split('/')
        view = parts[-1] if parts else ''
        try:
            job_id = int(parts[1])
        except (ValueError, IndexError):
            job_id = None
        if view not in ('client', 'worker') or job_id is None \
                or get_job(job_id) is None:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Job not found')
            return
        self.send_response(302)
        self.send_header('Location', f'/job/{job_id}')
        self.send_header('Set-Cookie',
                         f'bw_view={view}; Path=/; Max-Age=86400')
        party = get_party_by_name(
            "Mira's Shop" if view == 'client'
            else "LinguaCert Agency")
        if party:
            self.send_header(
                'Set-Cookie',
                f'bw_actor={party["id"]}; Path=/; Max-Age=86400')
        self.end_headers()
        self.wfile.write(b'')

    def serve_job_detail(self, path):
        parts = path.strip('/').split('/')
        if len(parts) < 2:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Job not found')
            return
        job_id_str = parts[1]
        try:
            job_id = int(job_id_str)
        except ValueError:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Job not found')
            return
        job = get_job(job_id)
        
        if job is None:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Job not found')
            return
        
        job = self._maybe_release_vesting(job)
        deliveries = get_deliveries(job.id)
        job = self._refresh_payout_statuses(job)
        backfill_events(job)
        sync_note = self._reconcile(job, record=True)
        offers, offer_workers, offer_actor = self._offer_view_data(job)
        html = render_job_detail(job, deliveries=deliveries,
                                   verdict=latest_verdict(job.id),
                                   verdicts=get_verdicts(job.id),
                                   events=get_events(job.id),
                                   sync_note=sync_note,
                                   demo_fixtures=fixtures_for_job(job),
                                    sample_generator=
                                    self._sample_generator_visible(job),
                                    offers=offers,
                                     offer_workers=offer_workers,
                                     offer_actor=offer_actor,
                                     guide_html=self._demo_guide(job),
                                     nav_view=self._context_view(),
                                    price_agreed=price_agreed(job))
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))

    def serve_client_view(self):
        """Serve the client view page."""
        party = self._resolve_view_seat('client')
        self._render_view(party, 'client')

    def serve_worker_view(self):
        """Serve the worker view page."""
        party = self._resolve_view_seat('worker')
        self._render_view(party, 'worker')

    def _render_view(self, party, view_kind):
        """Render the view (client or worker) for the given party."""
        from app.templates import render_client_view, render_worker_view
        
        # Switcher: every qualifying party, demo cast first (in
        # cast order), then the rest by id. DB party dicts only —
        # the load_demo_parties() specs carry no 'id'.
        from app.demo import load_demo_parties
        cast_order = [spec['name'] for spec in load_demo_parties()]
        qualifying = [p for p in list_parties()
                      if self._party_qualifies_for_view(p, view_kind)]
        switcher_list = sorted(
            qualifying,
            key=lambda p: (cast_order.index(p['name'])
                           if p['name'] in cast_order
                           else len(cast_order), p['id']))
        
        # Get job set minus archived demo_tag
        jobs = [j for j in list_jobs() if j.demo_tag != 'archived']
        
        # Get jobs where the seat is the party
        seat_jobs = []
        for job in jobs:
            if (view_kind == 'client' and job.client_id == party['id']) or \
               (view_kind == 'worker' and job.worker_id == party['id']):
                seat_jobs.append(job)
        
        # Split jobs by stage
        seat_jobs_by_stage = {}
        for job in seat_jobs:
            stage = job.state
            if stage not in seat_jobs_by_stage:
                seat_jobs_by_stage[stage] = []
            seat_jobs_by_stage[stage].append(job)
        
        # For each settled job, get certificate
        settled_certificates = {}
        for job in seat_jobs:
            if job.state in ('settled', 'disputed_overturned', 'refunded'):
                cert = get_certificate_by_job(job.id)
                if cert:
                    settled_certificates[job.id] = cert
        
        # Render based on view type
        if view_kind == 'client':
            counters = get_party_counters(party['id'])
            certificates = list_certificates_for_worker(party['id'])
            html = render_client_view(
                party=party,
                jobs=seat_jobs,
                jobs_by_stage=seat_jobs_by_stage,
                certificates=settled_certificates,
                counters=counters,
                certificates_for_worker=certificates,
                switcher_list=switcher_list,
                nav_view=view_kind
            )
        else:
            counters = get_party_counters(party['id'])
            certificates = list_certificates_for_worker(party['id'])
            html = render_worker_view(
                party=party,
                jobs=seat_jobs,
                jobs_by_stage=seat_jobs_by_stage,
                certificates=settled_certificates,
                counters=counters,
                certificates_for_worker=certificates,
                switcher_list=switcher_list,
                nav_view=view_kind
            )
        
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))

    # -- Slice 1.5/1.7 helpers -------------------------------------------
    def _refresh_payout_statuses(self, job):
        """Refresh payout item statuses (and item ids) from PayPal
        (best effort; stored values are shown verbatim when the GET
        fails)."""
        if not job.payout_batch_id or not credentials_present():
            return job
        try:
            fresh = get_payout_batch_items(job.payout_batch_id,
                                           job.payout_items)
        except Exception:
            return job
        if not fresh:
            return job
        fresh_by_party = {f['party']: f for f in fresh}
        changed = False
        items = []
        for it in job.payout_items:
            it = dict(it)
            f = fresh_by_party.get(it.get('party', ''))
            if f:
                if f['status'] and f['status'] != it.get('status'):
                    it['status'] = f['status']
                    changed = True
                if f['payout_item_id'] and not it.get('payout_item_id'):
                    it['payout_item_id'] = f['payout_item_id']
                    changed = True
            items.append(it)
        if changed:
            update_payout_items(job.id, items)
            job = get_job(job.id)
        return job

    def _reconcile(self, job, record: bool = False) -> str:
        """Slice 1.7 fallback reconciliation: compare the local money
        state with PayPal's own record (cheap GETs only). Returns the
        sync note for the page; a contradiction is flagged as a
        timeline event, never silently overwritten."""
        from datetime import datetime, timezone
        if not job.paypal_authorization_id or not credentials_present():
            return ""
        try:
            auth = get_authorization(job.paypal_authorization_id)
        except Exception:
            return ""
        paypal_status = auth.get('status', '')
        now = datetime.now(timezone.utc).strftime("%d %b %Y at %H:%M UTC")
        expected = {
            'funded': 'CREATED', 'delivered': 'CREATED',
            'checked_pass': 'CREATED', 'checked_fail': 'CREATED',
            'revision': 'CREATED', 'settle_error': 'CAPTURED',
            'settled': 'CAPTURED', 'refunded': 'VOIDED',
        }.get(job.state)
        if job.state == 'refunded' and job.capture_id:
            expected = 'CAPTURED'  # refund-of-capture path
        if job.trust_credit_state == 'advanced' and job.state == 'checked_pass':
            # Slice 2.4: a trust-credit advance partially captures the
            # authorization at acceptance — PARTIALLY_CAPTURED is the
            # CORRECT PayPal state until settlement captures the rest.
            expected = 'PARTIALLY_CAPTURED'
        if expected and paypal_status and paypal_status != expected:
            note = (f"Discrepancy flagged: local state '{job.state}' "
                    f"expects authorization {expected} at PayPal, but "
                    f"PayPal reports {paypal_status}.")
            if record:
                sig = {"local_state": job.state,
                       "paypal_authorization_status": paypal_status}
                existing = [e for e in get_events(job.id)
                            if e['kind'] == 'discrepancy'
                            and e['detail'] == sig]
                if not existing:
                    add_event(job.id, 'discrepancy', actor='system',
                              source='reconcile', detail=sig)
            return note
        return f"State verified against PayPal at {now}."

    def handle_check(self, path):
        """Run the checker via the shared service layer (Slice 2.9):
        the same code path serves the JSON API. Refusals and verdict
        handling (dual mode, trust credit, final-FAIL auto-refund)
        live in app.service.check_job_action."""
        parts = path.strip('/').split('/')
        job_id = int(parts[1])
        job = get_job(job_id)
        if job is None:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Job not found')
            return
        try:
            check_job_action(job_id, via='ui', actor='checker (ui)',
                             endpoint=f'/job/{job_id}/check')
        except ServiceError as e:
            job = get_job(job_id)
            self._render_detail(job, info_message=e.message)
            return
        self.send_response(302)
        self.send_header('Location', f'/job/{job_id}')
        self.end_headers()
        self.wfile.write(b'')

    def handle_appeal(self, path):
        """Slice 2.3: ONE appeal after a final FAIL verdict. A senior
        re-check by the OTHER judge model decides; its verdict is
        final (a second appeal is refused with 409 and changes
        nothing)."""
        parts = path.strip('/').split('/')
        if len(parts) < 2:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Job not found')
            return
        try:
            job_id = int(parts[1])
        except ValueError:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Job not found')
            return
        job = get_job(job_id)
        if job is None:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Job not found')
            return
        verdicts = get_verdicts(job_id)
        latest = verdicts[0] if verdicts else None
        if (job.state != 'checked_fail' or latest is None
                or latest.get('overall_pass')):
            self._render_detail(job, info_message=(
                "Appeal is available only after a final FAIL verdict."))
            return
        if count_appeals(job_id) > 0:
            self.send_response(409)
            self.end_headers()
            self.wfile.write(b'This job has already been appealed; '
                             b'the appeal verdict is final.')
            return
        deciding = latest.get('judged_model') or JUDGE_MODEL
        senior = (JUDGE_FALLBACK_MODEL if deciding == JUDGE_MODEL
                  else JUDGE_MODEL)
        try:
            v = run_check(job_id, judge_model=senior, is_appeal=True,
                          suppress_first_events=True)
        except Exception as e:
            job = get_job(job_id)
            self._render_detail(job, info_message=(
                f"Appeal could not be completed: "
                f"{type(e).__name__}: {e}"))
            return
        if getattr(v, 'incomplete', False):
            # v5.6 (F1): the senior judge was unavailable — the
            # appeal is NOT decided and NOT consumed.
            job = get_job(job_id)
            self._render_detail(job, info_message=(
                "Appeal could not be completed — the AI judge is "
                "unavailable. Nothing was decided; the appeal "
                "remains available."))
            return
        add_event(job_id, 'appeal_decided', actor='worker (appeal)',
                  detail={"model": senior, "overall_pass": v.overall_pass})
        if v.overall_pass:
            emit_verdict_events(job_id, True)
            job = get_job(job_id)
            if job is not None:
                self._maybe_advance_trust_credit(job)
        self.send_response(302)
        self.send_header('Location', f'/job/{job_id}')
        self.end_headers()
        self.wfile.write(b'')


    def _maybe_advance_trust_credit(self, job):
        return _svc_maybe_advance_trust_credit(job)

    # -- Slice 1.5: settlement -------------------------------------------
    def _split_items(self, job, captured_cents: int):
        return _svc_split_items(job, captured_cents)

    def _do_payouts(self, job):
        return _svc_do_payouts(job)

    # -- Slice 2.5: checker-fee vesting + dispute window ------------------
    def _start_vesting(self, job, checker_amount_cents: int):
        return _svc_start_vesting(job, checker_amount_cents)

    def _release_vesting(self, job) -> bool:
        return _svc_release_vesting(job)

    def _maybe_release_vesting(self, job):
        return _svc_maybe_release_vesting(job)

    def handle_release_vesting(self, path):
        parts = path.strip('/').split('/')
        if len(parts) < 2:
            self.send_response(404); self.end_headers()
            self.wfile.write(b'Job not found'); return
        try:
            job_id = int(parts[1])
        except ValueError:
            self.send_response(404); self.end_headers()
            self.wfile.write(b'Job not found'); return
        job = get_job(job_id)
        if job is None:
            self.send_response(404); self.end_headers()
            self.wfile.write(b'Job not found'); return
        if job.checker_vesting_state != 'vesting':
            self._render_detail(job, info_message=(
                "No vesting checker fee is waiting on this job."))
            return
        if job.dispute_state == 'open':
            self._render_detail(job, info_message=(
                "A dispute is open — the vesting fee is frozen until "
                "the dispute is resolved."))
            return
        from datetime import datetime, timezone
        due = (datetime.fromisoformat(job.checker_release_at)
               if job.checker_release_at else None)
        if due and datetime.now(timezone.utc) < due:
            self._render_detail(job, info_message=(
                f"The checker fee is still vesting; it releases at "
                f"{job.checker_release_at}."))
            return
        if self._release_vesting(job):
            job = get_job(job_id)
            log_service_call(
                job_id, 'client (ui)', 'ui', 'release_vesting',
                f'/job/{job_id}/release-vesting',
                'checker fee released after the dispute window', 200,
                f"payout_batch={job.checker_released_batch_id}"
                if job else '')
            self.send_response(302)
            self.send_header('Location', f'/job/{job_id}')
            self.end_headers(); self.wfile.write(b'')
        else:
            job = get_job(job_id)
            self._render_detail(job, info_message=(
                "The vesting release failed; see the timeline for the "
                "recorded error."))

    def handle_dispute_open(self, path):
        parts = path.strip('/').split('/')
        if len(parts) < 2:
            self.send_response(404); self.end_headers()
            self.wfile.write(b'Job not found'); return
        try:
            job_id = int(parts[1])
        except ValueError:
            self.send_response(404); self.end_headers()
            self.wfile.write(b'Job not found'); return
        job = get_job(job_id)
        if job is None:
            self.send_response(404); self.end_headers()
            self.wfile.write(b'Job not found'); return
        length = int(self.headers.get('Content-Length', 0) or 0)
        form = parse_qs(self.rfile.read(length).decode('utf-8')) \
            if length else {}
        reason = (form.get('reason', [''])[0] or '').strip()
        if job.checker_vesting_state != 'vesting':
            self._render_detail(job, info_message=(
                "A dispute can only be opened while the checker fee "
                "is vesting."))
            return
        if job.dispute_state == 'open':
            self._render_detail(job, info_message=(
                "A dispute is already open on this job."))
            return
        if job.dispute_state:
            self._render_detail(job, info_message=(
                "This job's dispute window has already been used and "
                "resolved."))
            return
        set_dispute(job_id, 'open', reason=reason, opened_at=_now())
        add_event(job_id, 'dispute_opened', actor='client',
                  detail={"reason": reason})
        self.send_response(302)
        self.send_header('Location', f'/job/{job_id}')
        self.end_headers(); self.wfile.write(b'')

    def handle_dispute_resolve(self, path):
        parts = path.strip('/').split('/')
        if len(parts) < 2:
            self.send_response(404); self.end_headers()
            self.wfile.write(b'Job not found'); return
        try:
            job_id = int(parts[1])
        except ValueError:
            self.send_response(404); self.end_headers()
            self.wfile.write(b'Job not found'); return
        job = get_job(job_id)
        if job is None:
            self.send_response(404); self.end_headers()
            self.wfile.write(b'Job not found'); return
        if job.dispute_state != 'open':
            self._render_detail(job, info_message=(
                "No open dispute to resolve on this job."))
            return
        # Senior re-check: the judge model that did NOT issue the
        # latest verdict (the Slice 2.3 appeal machinery).
        verdicts = get_verdicts(job_id)
        last_model = verdicts[-1].get('judged_model', '') if verdicts else ''
        senior = (JUDGE_FALLBACK_MODEL if last_model == JUDGE_MODEL
                  else JUDGE_MODEL)
        try:
            verdict = run_check(job_id, judge_model=senior,
                                suppress_first_events=True, is_dispute=True)
        except Exception as e:
            self._render_detail(job, info_message=(
                f"Dispute re-check failed: {e}"))
            return
        if getattr(verdict, 'incomplete', False):
            # v5.6 (F1): the senior judge was unavailable — the
            # dispute stays open; nothing was decided or paid.
            self._render_detail(get_job(job_id), info_message=(
                "Dispute re-check could not be completed — the AI "
                "judge is unavailable. The dispute remains open; "
                "nothing was decided."))
            return
        job = get_job(job_id)
        if verdict.overall_pass:
            set_dispute(job_id, 'upheld_closed', resolved_at=_now())
            add_event(job_id, 'dispute_upheld', actor='system',
                      detail={"senior_model": senior,
                              "note": "the senior re-check passed the "
                                      "delivery; the dispute closes and "
                                      "vesting resumes"})
            job = self._maybe_release_vesting(get_job(job_id))
            self._render_detail(job, info_message=(
                "Dispute resolved: the senior re-check upheld the "
                "delivery. The checker fee resumes vesting."))
            return
        # Overturned: the unvested checker fee makes the client whole
        # first (recovery ladder step 1).
        set_dispute(job_id, 'overturned', resolved_at=_now())
        add_event(job_id, 'dispute_overturned', actor='system',
                  detail={"senior_model": senior,
                          "note": "the senior re-check failed the "
                                  "delivery; the unvested checker fee "
                                  "is paid to the client"})
        if job.checker_id:
            emit_reputation_event_once(
                job.checker_id, job_id, 'overturned',
                {"senior_model": senior})
        client_party = get_party(job.client_id) if job.client_id else None
        receiver = (client_party['payout_email']
                    if client_party and client_party.get('payout_email')
                    else CLIENT_RECEIVER_EMAIL)
        items = [{"party": "client", "receiver": receiver,
                  "amount_cents": job.checker_vesting_amount_cents}]
        items = [it for it in items if it["amount_cents"] > 0]
        if items:
            try:
                batch_id, paid, dispute_recovered = create_or_adopt_payouts(
                    str(job.id), items,
                    currency=job.captured_currency or job.currency or 'USD',
                    batch_tag='dispute-recovery')
                item_id = paid[0]['payout_item_id'] if paid else ''
                set_checker_dispute_paid(job.id, batch_id, item_id)
                add_event(job.id, 'checker_fee_paid_to_client', actor='system',
                          detail={"payout_batch_id": batch_id,
                                  "payout_item_id": item_id,
                                  "payouts_recovered": dispute_recovered,
                                  "amount_cents":
                                      job.checker_vesting_amount_cents,
                                  "receiver": receiver})
            except Exception as e:
                add_event(job.id, 'dispute_payout_error', actor='system',
                          detail={"error": str(e)})
        else:
            set_checker_dispute_paid(job.id, '', '')
            add_event(job.id, 'checker_fee_nothing_to_pay', actor='system',
                      detail={"amount_cents": 0,
                              "note": "the checker fee was 0 cents (fully rounded away), so there is nothing to pay the client"})
        set_job_state(job_id, 'disputed_overturned')
        self.send_response(302)
        self.send_header('Location', f'/job/{job_id}')
        self.end_headers(); self.wfile.write(b'')

    def _api_offers(self, parts, job, actor, endpoint):
        """Price negotiation over the API (posted state only):
        POST /api/v1/jobs/<id>/offers {amount_cents} — a worker
        bids/counter-offers with their own key;
        POST …/offers/<oid>/accept|reject — the client decides;
        POST …/offers/<oid>/withdraw — the offering worker pulls
        their offer back. The service layer enforces the window:
        after funding, no offer can be made or decided."""
        label = self._api_actor_label(actor)
        if len(parts) == 5:
            if actor['kind'] != 'worker':
                self._api_send(403, {
                    "error": "Only a worker party can make an offer"})
                return
            try:
                length = int(self.headers.get('Content-Length', 0))
                data = json.loads(self.rfile.read(length) or b'{}')
            except Exception:
                self._api_send(400,
                               {"error": "Request body must be JSON"})
                return
            amount = data.get('amount_cents')
            if amount is None and data.get('amount') is not None:
                try:
                    amount = parse_price_cents(str(data['amount']))
                except ValueError:
                    amount = None
            try:
                offer = make_offer_action(
                    job.id, actor['id'], amount, via='api',
                    actor=label, endpoint=endpoint)
            except ServiceError as e:
                self._api_send(e.http_status, {"error": e.message})
                return
            self._api_send(201, {
                "offer_id": offer.id, "job_id": job.id,
                "worker_id": offer.worker_id,
                "amount_cents": offer.amount_cents,
                "currency": offer.currency, "kind": offer.kind,
                "status": offer.status})
            return
        if len(parts) == 7:
            try:
                offer_id = int(parts[5])
            except ValueError:
                self._api_send(400,
                               {"error": "Invalid offer id (must be numeric)"})
                return
            decision = parts[6]
            offer = get_offer(offer_id)
            if offer is None or offer.job_id != job.id:
                self._api_send(404,
                               {"error": "Offer not found on this job"})
                return
            try:
                if decision in ('accept', 'reject'):
                    if actor['id'] != job.client_id:
                        self._api_send(403, {
                            "error": "Only the job's client can "
                                     "decide offers"})
                        return
                    if decision == 'accept':
                        updated, accepted = accept_offer_action(
                            job.id, offer_id, via='api', actor=label,
                            endpoint=endpoint)
                        self._api_send(200, job_status_dict(updated))
                    else:
                        reject_offer_action(
                            job.id, offer_id, via='api', actor=label,
                            endpoint=endpoint)
                        self._api_send(200, job_status_dict(job))
                    return
                if decision == 'withdraw':
                    if actor['id'] != offer.worker_id:
                        self._api_send(403, {
                            "error": "Only the offering worker can "
                                     "withdraw this offer"})
                        return
                    withdraw_offer_action(
                        job.id, offer_id, via='api', actor=label,
                        endpoint=endpoint)
                    self._api_send(200, job_status_dict(job))
                    return
            except ServiceError as e:
                self._api_send(e.http_status, {"error": e.message})
                return
            self._api_send(404, {"error": "Unknown offer action"})
            return
        self._api_send(404, {"error": "Unknown offers route"})

    def serve_certificate(self, path):
        parts = path.strip('/').split('/')
        if len(parts) < 2:
            self.send_response(404); self.end_headers()
            self.wfile.write(b'No certificate for this job'); return
        try:
            job_id = int(parts[1])
        except ValueError:
            self.send_response(404); self.end_headers()
            self.wfile.write(b'No certificate for this job'); return
        job = get_job(job_id)
        cert = get_certificate_by_job(job_id) if job else None
        if job is None or cert is None:
            self.send_response(404); self.end_headers()
            self.wfile.write(b'No certificate for this job'); return
        html = render_certificate(job, cert, nav_view=self._context_view())
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))

    def serve_verify(self, serial: str, code: str,
                     submitted: bool = False):
        result = None
        errors = {}
        if submitted:
            if not serial:
                errors['serial'] = ("Missing: enter the certificate "
                                    "serial (e.g. BW-2026-0001).")
            if not code:
                errors['code'] = ("Missing: enter the verification "
                                  "code from the certificate.")
        if serial and code:
            cert = get_certificate(serial)
            if cert is not None and \
                    cert["code"].lower() == code.lower():
                result = cert
            else:
                result = False  # looked up, not genuine
        html = render_verify_page(serial, code, result, errors=errors, nav_view=self._context_view())
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))

    def serve_certificates(self):
        """NEW /certificates route - lists all passed/settled job certificates."""
        view, seat = self._context_seat()
        all_certificates = []
        for _job in list_jobs():
            if view == 'client' and (seat is None or _job.client_id != seat['id']):
                continue
            if view == 'worker' and (seat is None or _job.worker_id != seat['id']):
                continue
            _cert = get_certificate_by_job(_job.id)
            if _cert:
                all_certificates.append(_cert)

        def pname(pid):
            p = get_party(pid) if pid else None
            return p['name'] if p else '—'
        
        cert_note = ''
        if view != 'door' and seat is not None:
            nm = _escape(seat['name'])
            role = 'the client' if view == 'client' else 'the worker'
            cert_note = (f'<p>Showing certificates for {nm} — the '
                         f'jobs where {nm} is {role}.</p>')
        
        parts = [
            '<!DOCTYPE html>',
            '<html lang="en">',
            '<head>',
            '<meta charset="UTF-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
            '<title>Certificates — Bulwark</title>',
            f'<style>{CSS}</style>',
            '</head>',
            '<body>',
            '<div class="container">',
            _site_nav(view),
            '<header>',
            '<h1>Certificates</h1>',
            '<p>Every passed/settled job has a public proof certificate.</p>',
            cert_note,
            '</header>'
        ]
        
        if not all_certificates:
            parts.append('<div class="empty-state">')
            parts.append('<div class="empty-state-icon">&#128213;</div>')
            if view == 'door':
                parts.append('<p>No certificates have been issued yet.</p>')
            else:
                parts.append('<p>No certificates for this view yet.</p>')
            parts.append('</div>')
        else:
            parts.append('<div class="certificates-grid">')
            for cert in all_certificates:
                job = get_job(cert.get('job_id')) if cert.get('job_id') else None
                if not job:
                    continue
                client = get_party(job.client_id) if job.client_id else None
                worker = get_party(job.worker_id) if job.worker_id else None
                checker = get_party(job.checker_id) if job.checker_id else None
                
                parts.append('<div class="cert-card">')
                parts.append(f'<h3><a href="/job/{job.id}">{job.title}</a></h3>')
                parts.append(f'<div class="cert-meta">Client: {pname(job.client_id)}</div>')
                if worker:
                    parts.append(f'<div class="cert-meta">Worker: {worker["name"]}</div>')
                if checker:
                    parts.append(f'<div class="cert-meta">Checker: {checker["name"]}</div>')
                parts.append(f'<div class="cert-meta">Issued: {_fmt_ts(cert["issued_at"]) if cert.get("issued_at") else "—"}</div>')
                parts.append(f'<a href="/verify?serial={cert["serial"]}&code={cert["code"]}" class="btn-nav">Verify certificate</a>')
                parts.append('</div>')
            parts.append('</div>')
        
        parts.append('<footer>')
        parts.append('<p>Bulwark — settlement layer for the digital labor market.</p>')
        parts.append('</footer>')
        parts.append('</div>')
        parts.append('</body>')
        parts.append('</html>')
        
        html = ''.join(parts)
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))

    def serve_how_it_works(self):
        """NEW /how route - describes what Bulwark is and how it works."""
        parts = [
            '<!DOCTYPE html>',
            '<html lang="en">',
            '<head>',
            '<meta charset="UTF-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
            '<title>How it works — Bulwark</title>',
            f'<style>{CSS}</style>',
            '</head>',
            '<body>',
            '<div class="container">',
            _site_nav(self._context_view()),
            '<header>'
            '<h1>How it works</h1>',
            '</header>',
            '<div class="content">',
            '<h2>Two ways in</h2>',
            "<p>Bulwark opens with a simple choice: I am here to hire, or I am here to work. Each view shows the tools for that side — clients post and fund jobs; workers browse the same jobs and make offers. The jobs, the money and the rules are the same in both; only the desk you sit at changes, and you can switch at any time. To test the full circle, play one job through both views: offer as a worker, accept and fund as the client, deliver as the worker, and watch the money settle.</p>",
            '<h2>What Bulwark is</h2>',
            "<p>Bulwark is the settlement layer for the digital labor market — the place where work between parties who have never met gets paid for safely. Increasingly, the parties on both sides are AI agents; people can take every seat too. Bulwark is not the marketplace itself: it is the machinery underneath that holds the money, checks the work, and settles — so neither side has to trust the other, only the rules.</p>",
            '<p><strong>The idea in one line:</strong> you only pay for work that passes a check you defined in advance.</p>',
            '<h2>How a job flows</h2>',
            '<ol>',
            "<li><strong>Post.</strong> The client posts a job: what must be delivered, and the acceptance criteria it will be measured against. The job can carry a price — or no price, inviting offers.</li>",
            "<li><strong>Offers.</strong> Workers offer to do it, at the posted price or with a counter-offer. Nothing is agreed yet.</li>",
            "<li><strong>Accept.</strong> The client accepts one offer. Now the worker and the price are locked. From this moment, the price and the criteria cannot change — for anyone.</li>",
            "<li><strong>Fund.</strong> The client funds the locked price via PayPal. The money is held — it does not go to the worker. At funding, Bulwark's Settlement Brain sets the job's safety terms: how the check runs and how long the dispute window lasts.</li>",
            '<li><strong>Deliver.</strong> The worker delivers the work.</li>',
            "<li><strong>Check.</strong> An independent checker measures the delivery against the locked criteria, point by point, and shows its reasoning. The client is not the judge — the criteria are.</li>",
            "<li><strong>Settle or refund.</strong> Pass: the money is released automatically and split — <strong>Worker 85% · Checker 5% · Platform 10%</strong>. Fail: the worker gets exactly one revision. Fail again: the client is refunded in full, automatically. The checker's fee becomes final only after the dispute window closes — the checker stands behind its own verdict.</li>",
            "<li><strong>Certificate.</strong> Every passed job issues a proof certificate: what was delivered, by whom, checked by whom, against which criteria. Anyone can verify it. It is the worker's portable track record.</li>",
            '</ol>',
            '<h2>The rules that protect both sides</h2>',
            '<ul>',
            '<li>The criteria are locked at posting — nobody can move the goalposts after funding.</li>',
            '<li>Negotiation happens only before funding — once the money is held, the price is final.</li>',
            '<li>The client cannot withhold payment for work that passed; the worker cannot be paid for work that failed.</li>',
            '<li>One revision, then an automatic refund — no tickets, no waiting, no arguing with support.</li>',
            '</ul>',
            '<h2>What you can test in this demo</h2>',
            "<p>Everything on this board really happened: the jobs were played through the real flows, and every payment, payout and refund is a real PayPal sandbox transaction, made with test money. You can also drive it yourself:</p>",
            '<ul>',
            '<li><strong>Fund a job in one click.</strong> The story jobs standing in "Posted" state with a worker attached are ready: open the client view, open one, and press Fund — a real sandbox hold is placed on the money.</li>',
            '<li><strong>Run a full job end to end.</strong> Post your own job in the client view, then switch views: in the worker view, make an offer; back in the client view, accept it and fund it; in the worker view again, deliver; then run the check from the job page itself — the Verifier AI measures the delivery in the open — and watch the money move on the Payments page.</li>',
            '<li><strong>See a revision.</strong> Open the story whose delivery fails its first check, gets revised, and passes.</li>',
            '<li><strong>See a full refund.</strong> Open the story that fails twice — the client received every cent back, automatically.</li>',
            "<li><strong>Verify a certificate.</strong> Open any settled job's certificate and check it on the verification page.</li>",
            '<li><strong>Follow the money.</strong> The Payments page shows where every amount stands right now: held, being checked, paid out, refunded.</li>',
            '<li><strong>As an agent.</strong> The same actions exist over the API: an agent can post, offer, fund, deliver and settle without a browser. Every job page has a machine view built for exactly that.</li>',
            '</ul>',
            '<p><em>About this demo: it runs entirely on the PayPal sandbox — test money and test accounts; no real funds move. The seats on the Demo page stand in for user accounts, so you can play every role yourself. "Reset demo" on the Demo page restores the board to its starting state.</em></p>',
            '</div>',
            '<footer>',
            '<p>Money is held via PayPal until the check passes. · Agents and people both work here.</p>',
            '</footer>',
            '</div>',
            '</body>',
            '</html>',
        ]
        
        html = ''.join(parts)
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))

    def serve_evidence(self, path):
        parts = path.strip('/').split('/')
        if len(parts) < 2:
            self.send_response(404); self.end_headers()
            self.wfile.write(b'Job not found'); return
        try:
            job_id = int(parts[1])
        except ValueError:
            self.send_response(404); self.end_headers()
            self.wfile.write(b'Job not found'); return
        job = get_job(job_id)
        if job is None:
            self.send_response(404); self.end_headers()
            self.wfile.write(b'Job not found'); return
        html = render_evidence_pack(
            job, verdicts=get_verdicts(job_id),
            deliveries=get_deliveries(job_id), events=get_events(job_id),
            nav_view=self._context_view())
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))

    def handle_settle(self, path):
        """Settle via the shared service layer (Slice 2.9)."""
        parts = path.strip('/').split('/')
        job_id = int(parts[1])
        job = get_job(job_id)
        if job is None:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Job not found')
            return
        try:
            job, note = settle_job_action(
                job_id, via='ui', actor='client (ui)',
                endpoint=f'/job/{job_id}/settle')
        except ServiceError as e:
            job = get_job(job_id)
            self._render_detail(job, info_message=e.message)
            return
        if job.state == 'settle_error':
            self._render_detail(job)
            return
        if note:
            self._render_detail(job, info_message=note)
            return
        self.send_response(302)
        self.send_header('Location', f'/job/{job_id}')
        self.end_headers()
        self.wfile.write(b'')

    # -- Slice 1.6: revision + refund -------------------------------------
    def _do_refund(self, job, actor: str):
        return _svc_do_refund(job, actor)

    def handle_reject(self, path):
        parts = path.strip('/').split('/')
        if len(parts) < 2:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Job not found')
            return
        try:
            job_id = int(parts[1])
        except ValueError:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Job not found')
            return
        job = get_job(job_id)
        if job is None:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Job not found')
            return
        if job.state == 'settled':
            self._render_detail(job, info_message=(
                "This job is settled — settlement is final in Stage 1 "
                "and cannot be refunded."))
            return
        if job.state == 'refunded':
            self._render_detail(job, info_message=(
                "This job has already been refunded."))
            return
        if job.state != 'checked_fail':
            self._render_detail(job, info_message=(
                "Reject / refund is only available on jobs in the "
                "'checked_fail' state."))
            return
        if not credentials_present():
            self._render_detail(job, info_message=(
                "PayPal credentials are absent from the environment."))
            return
        try:
            self._do_refund(job, actor='client (reject without revision)')  # covers trust-credit advance capture as well
        except Exception as e:
            self._render_detail(job, info_message=(
                f"Refund failed: {e}"))
            return
        job = get_job(job_id)
        log_service_call(job_id, 'client (ui)', 'ui', 'reject_refund',
                         f'/job/{job_id}/reject',
                         'client rejected the failed delivery', 200,
                         f"refund={job.refund_id}" if job else '')
        self.send_response(302)
        self.send_header('Location', f'/job/{job_id}')
        self.end_headers()
        self.wfile.write(b'')

    def handle_revise(self, path):
        parts = path.strip('/').split('/')
        if len(parts) < 2:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Job not found')
            return
        try:
            job_id = int(parts[1])
        except ValueError:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Job not found')
            return
        job = get_job(job_id)
        if job is None:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Job not found')
            return

        if job.state == 'settled':
            self._render_detail(job, info_message=(
                "This job is settled — no revision is possible."))
            return
        if job.revision_used:
            self._render_detail(job, info_message=(
                "The one permitted revision has already been used. "
                "No second revision is possible."))
            return
        if job.state != 'checked_fail':
            self._render_detail(job, info_message=(
                "Revision is only available on jobs in the "
                "'checked_fail' state."))
            return
        # Slice 2.3 (brief): a FRAUD verdict skips the revision
        # window entirely — the job goes straight to the refund
        # path (client reject). Guard added at the 2.8 build, when
        # the demo fraud story exposed that the route had no
        # fraud check (the 2.3 gate had verified the verdict,
        # the banner and the settle refusal, not this route).
        _latest = latest_verdict(job_id)
        if _latest and _latest.get('fraud_signal') == 'fraud':
            self._render_detail(job, info_message=(
                "This verdict is FRAUD — the revision window does "
                "not apply. The job goes straight to the refund "
                "path: the client rejects and the vault refunds "
                "in full."))
            return

        content_length = int(self.headers.get('Content-Length', 0))
        content_type = self.headers.get('Content-Type', '')
        body = self.rfile.read(content_length)
        if 'multipart/form-data' not in content_type:
            self._render_detail(job, info_message=(
                "Invalid form encoding; expected multipart/form-data."))
            return
        form = _parse_multipart_form(content_type, body)
        files = [(n, f['filename'], f['data'])
                 for n, f in form.items() if f.get('filename')]
        if not files:
            self._render_detail(job, info_message=(
                "No file selected. Please choose at least one file "
                "for the revised delivery."))
            return
        note = ''
        if 'note' in form and form['note']['data']:
            note = form['note']['data'].decode('utf-8', 'replace')

        job_dir = os.path.join(DELIVERIES_DIR, str(job_id))
        os.makedirs(job_dir, exist_ok=True)
        for field_name, orig_filename, data in files:
            if len(data) > MAX_FILE_SIZE:
                self._render_detail(job, info_message=(
                    f"File '{orig_filename}' is too large "
                    f"({len(data)} bytes). Maximum is 25 MB per file."))
                return
            safe_name = _sanitize_filename(orig_filename)
            stored_name = f"{uuid.uuid4().hex}_{safe_name}"
            stored_path = os.path.join(job_dir, stored_name)
            with open(stored_path, 'wb') as f:
                f.write(data)
            sha256 = hashlib.sha256(data).hexdigest()
            add_delivery(job_id=job.id, filename=safe_name,
                         stored_name=stored_name, size_bytes=len(data),
                         sha256=sha256, note=note, is_revision=True)
        set_revision_used(job.id)
        set_job_state(job.id, 'delivered')
        add_event(job.id, 'revised', actor='worker',
                  detail={"files": [f[1] for f in files]})
        self.send_response(302)
        self.send_header('Location', f'/job/{job_id}')
        self.end_headers()
        self.wfile.write(b'')

    # -- Slice 1.7: webhook endpoint + explicit verify --------------------
    def handle_webhook(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length else b''
        import hashlib as _h
        raw_hash = _h.sha256(body).hexdigest()
        event_type = ""
        related = {}
        job_id = None
        try:
            payload = json.loads(body.decode('utf-8', 'replace'))
            event_type = payload.get('event_type', '')
            resource = payload.get('resource', {}) or {}
            related = {"resource_id": resource.get('id', ''),
                       "resource_status": resource.get('status', '')}
            # Best-effort job link: custom_id / reference in resource.
            ref = (resource.get('custom_id')
                   or resource.get('reference_id') or '')
            if str(ref).isdigit():
                job_id = int(ref)
        except (ValueError, TypeError):
            payload = {}
        if job_id is None:
            # Record unlinked events against job 0's stream is wrong;
            # store in the events of every candidate is also wrong.
            # Stage 1 records them in a synthetic stream: job_id = -1
            # is not a real job, so keep a global note via job 1..N
            # matching by authorization/capture ids instead.
            for j in list_jobs():
                ids = {j.paypal_order_id, j.paypal_authorization_id,
                       j.capture_id, j.payout_batch_id}
                if related.get('resource_id') in ids:
                    job_id = j.id
                    break
        if job_id is not None:
            add_event(job_id, 'webhook', actor='paypal', source='webhook',
                      detail={"event_type": event_type,
                              "raw_sha256": raw_hash, **related})
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(
            {"received": True, "linked_job": job_id}).encode())

    def handle_verify(self, path):
        parts = path.strip('/').split('/')
        if len(parts) < 2:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Job not found')
            return
        try:
            job_id = int(parts[1])
        except ValueError:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Job not found')
            return
        job = get_job(job_id)
        if job is None:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Job not found')
            return
        note = self._reconcile(job, record=True)
        job = get_job(job_id)
        self._render_detail(job, info_message=(
            note or "Verification could not reach PayPal."))
        return

    def handle_fund(self, path):
        """Fund via the shared service layer (Slice 2.9): authorize +
        Settlement Brain terms, identical for UI and API callers."""
        parts = path.strip('/').split('/')
        if len(parts) < 2:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Job not found')
            return
        try:
            job_id = int(parts[1])
        except ValueError:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Job not found')
            return
        job = get_job(job_id)
        if job is None:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Job not found')
            return
        try:
            job, note = fund_job_action(
                job_id, via='ui', actor='client (ui)',
                endpoint=f'/job/{job_id}/fund')
        except ServiceError as e:
            job = get_job(job_id)
            if e.http_status == 409:
                self._render_detail(job, info_message=e.message)
            else:
                # PayPal failures are recorded on the job row and
                # shown by the detail page (original behavior).
                self._render_detail(job)
            return
        if note:
            self._render_detail(job, info_message=note)
            return
        if job.state != 'funded':
            self._render_detail(job)
            return
        self.send_response(302)
        self.send_header('Location', f'/job/{job_id}')
        self.end_headers()
        self.wfile.write(b'')

    def handle_deliver(self, path):
        """Deliver via the shared service layer (Slice 2.9); this
        wrapper only parses the multipart form."""
        parts = path.strip('/').split('/')
        if len(parts) < 2:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Job not found')
            return
        try:
            job_id = int(parts[1])
        except ValueError:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Job not found')
            return
        job = get_job(job_id)
        if job is None:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Job not found')
            return
        content_length = int(self.headers.get('Content-Length', 0))
        content_type = self.headers.get('Content-Type', '')
        body = self.rfile.read(content_length)
        if 'multipart/form-data' in content_type:
            form = _parse_multipart_form(content_type, body)
        else:
            self._render_detail(job, info_message=(
                "Invalid form encoding; expected multipart/form-data."))
            return
        files = []
        for name, field in form.items():
            if field.get('filename'):
                files.append((field['filename'], field['data']))
        note = ''
        if 'note' in form and form['note']['data']:
            note = form['note']['data'].decode('utf-8', 'replace')
        if not files:
            # Never a silent dead end: mark the file field, in
            # place, with what to do instead.
            job = get_job(job_id)
            self._render_detail(job, deliver_error=(
                "Missing: choose a file to deliver — or use the "
                "prepared file above."))
            return
        try:
            deliver_job_action(job_id, files, note, via='ui',
                               actor='worker (ui)',
                               endpoint=f'/job/{job_id}/deliver')
        except ServiceError as e:
            job = get_job(job_id)
            self._render_detail(job, info_message=e.message)
            return
        self.send_response(302)
        self.send_header('Location', f'/job/{job_id}')
        self.end_headers()
        self.wfile.write(b'')

    def handle_deliver_fixture(self, path):
        """One-tap delivery of a demo job's prepared material.

        The fixture name must be on the job's own fixture list
        (fixtures_for_job), the bytes come from the demo data dir,
        and the delivery itself goes through the same service-layer
        action as a manual upload — every state gate applies
        identically. This only removes the download/upload
        round-trip that made the demo unusable on a phone."""
        parts = path.strip('/').split('/')
        if len(parts) < 2:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Job not found')
            return
        try:
            job_id = int(parts[1])
        except ValueError:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Job not found')
            return
        job = get_job(job_id)
        if job is None:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Job not found')
            return
        content_length = int(self.headers.get('Content-Length', 0))
        raw = self.rfile.read(content_length).decode('utf-8', 'replace')
        fixture = parse_qs(raw).get('fixture', [''])[0]
        allowed = fixtures_for_job(job)
        if fixture not in allowed:
            self._render_detail(job, info_message=(
                "That prepared file does not belong to this job."))
            return
        full = os.path.join(DEMO_DATA_DIR, os.path.basename(fixture))
        if os.path.exists(full):
            with open(full, 'rb') as f:
                data = f.read()
        else:
            # The ready-made job's file: generated at creation time
            # and stored with the job, not shipped as a fixture.
            from app.db import get_prepared_file
            prepared = get_prepared_file(job_id)
            if prepared is None or prepared[0] != fixture:
                self._render_detail(job, info_message=(
                    "That prepared file does not belong to this job."))
                return
            data = prepared[1]
        try:
            deliver_job_action(job_id, [(fixture, data)], '',
                               via='ui', actor='worker (ui)',
                               endpoint=f'/job/{job_id}/deliver-fixture')
        except ServiceError as e:
            job = get_job(job_id)
            self._render_detail(job, info_message=e.message)
            return
        self.send_response(302)
        self.send_header('Location', f'/job/{job_id}')
        self.end_headers()
        self.wfile.write(b'')

    def handle_generate_deliver(self, path):
        """Demo shortcut: generate a sample from the job's own
        acceptance criteria and deliver it through the same
        service-layer action as an upload.

        The button is offered on every funded job (the job page
        shows it in the worker view, where the delivery controls
        live), so this handler applies no role or demo-tag gate of
        its own — the service layer's state rules are the only
        gate, exactly as for an upload. If the generator cannot
        honestly satisfy a criterion it names it and nothing is
        delivered — the real checker still decides the verdict
        afterwards, unmodified."""
        parts = path.strip('/').split('/')
        if len(parts) < 2:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Job not found')
            return
        try:
            job_id = int(parts[1])
        except ValueError:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Job not found')
            return
        job = get_job(job_id)
        if job is None:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Job not found')
            return
        files, unsupported = generate_sample_delivery(job)
        if unsupported:
            self._render_detail(job, info_message=(
                "The demo generator cannot produce a sample for "
                "this job: " + "; ".join(unsupported) +
                ". Nothing was delivered — please deliver a real "
                "file with the upload form instead."))
            return
        try:
            deliver_job_action(
                job_id, files,
                "Sample generated by the demo generator from this "
                "job's acceptance criteria and delivered through "
                "the standard delivery path.",
                via='ui', actor='worker (ui)',
                endpoint=f'/job/{job_id}/generate-deliver')
        except ServiceError as e:
            job = get_job(job_id)
            self._render_detail(job, info_message=e.message)
            return
        self.send_response(302)
        self.send_header('Location', f'/job/{job_id}')
        self.end_headers()
        self.wfile.write(b'')

    # -- Price negotiation (posted state only) ---------------------
    def _offer_view_data(self, job):
        """What the job page's offers box needs: the job's offers,
        the worker parties an offer can be made as, and the demo
        actor (to preselect 'you are acting as …')."""
        workers = [p for p in list_parties()
                   if p['kind'] == 'worker']
        return list_offers(job.id), workers, self._demo_actor()

    def handle_offer(self, path):
        """POST /job/<id>/offer (make) and
        /job/<id>/offer/<offer_id>/<accept|reject|withdraw>.

        All decisions run through the service layer — the same
        state gates as the API: negotiation lives only in the
        posted state, and acceptance is the locking write."""
        parts = path.strip('/').split('/')
        if len(parts) < 2:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Job not found')
            return
        try:
            job_id = int(parts[1])
        except ValueError:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Job not found')
            return
        job = get_job(job_id)
        if job is None:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Job not found')
            return
        content_length = int(self.headers.get('Content-Length', 0))
        raw = self.rfile.read(content_length).decode('utf-8', 'replace') \
            if content_length else ''
        form = parse_qs(raw)
        endpoint = path
        try:
            if len(parts) == 3:
                worker_raw = form.get('worker_id', [''])[0]
                amount_raw = form.get('amount', [''])[0]
                try:
                    worker_id = int(worker_raw)
                except (TypeError, ValueError):
                    worker_id = 0
                try:
                    amount_cents = parse_price_cents(amount_raw)
                except ValueError:
                    amount_cents = 0
                make_offer_action(
                    job_id, worker_id, amount_cents, via='ui',
                    actor='worker (ui)', endpoint=endpoint)
            else:
                offer_id = int(parts[3])
                decision = parts[4]
                if decision == 'accept':
                    accept_offer_action(
                        job_id, offer_id, via='ui',
                        actor='client (ui)', endpoint=endpoint)
                elif decision == 'reject':
                    reject_offer_action(
                        job_id, offer_id, via='ui',
                        actor='client (ui)', endpoint=endpoint)
                elif decision == 'withdraw':
                    withdraw_offer_action(
                        job_id, offer_id, via='ui',
                        actor='worker (ui)', endpoint=endpoint)
                else:
                    self.send_response(404)
                    self.end_headers()
                    self.wfile.write(b'Unknown offer action')
                    return
        except ServiceError as e:
            job = get_job(job_id)
            field = None
            if 'positive amount' in e.message:
                field = 'amount'
            elif 'worker party' in e.message:
                field = 'worker'
            self._render_detail(job, offer_error=(field, e.message))
            return
        self.send_response(302)
        self.send_header('Location', f'/job/{job_id}')
        self.end_headers()
        self.wfile.write(b'')

    def handle_post_form(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length).decode('utf-8')
        form_data = parse_qs(post_data)

        title = form_data.get('title', [''])[0]
        description = form_data.get('description', [''])[0]
        price_mode = form_data.get('price_mode', ['fixed'])[0]
        if price_mode not in ('fixed', 'open'):
            price_mode = 'fixed'
        price_raw = form_data.get('price', [''])[0]
        currency = form_data.get('currency', ['USD'])[0]
        client_raw = form_data.get('client_id', [''])[0]
        worker_raw = form_data.get('worker_id', [''])[0]
        checker_raw = form_data.get('checker_id', [''])[0]

        # Form rule (Kiss): a failed submission re-renders the
        # form with everything preserved, the problem fields
        # marked in red with a human message under each, and a
        # summary at the top — never a bare error or a dead end.
        errors = {}
        if not title:
            errors['title'] = "Missing: give the job a title."
        if not description:
            errors['description'] = (
                "Missing: describe the work and what a good "
                "delivery looks like.")
        price_cents = 0
        if price_mode == 'fixed':
            if not price_raw:
                errors['price'] = (
                    "Missing: set the price — or choose “Open to "
                    "offers” above.")
            else:
                try:
                    price_cents = parse_price_cents(price_raw)
                except ValueError as e:
                    errors['price'] = f"Invalid price: {e}"
        criteria = parse_criteria_from_form(form_data)
        if len(criteria) < 3:
            errors['criteria'] = (
                "Missing: at least 3 complete acceptance criteria "
                "(name, comparison, expected value and type on "
                "each row).")
        # Party pickers submit party ids (Slice 2.1); validate the kind
        # and fall back to the built-in parties when missing/invalid.
        def _party_id(raw, kind, default):
            try:
                pid = int(raw)
            except (TypeError, ValueError):
                return default
            party = get_party(pid)
            return pid if party and party['kind'] == kind else default

        # Circle parsing and worker validation (must run BEFORE the errors check)
        circle = form_data.get('circle', ['invited'])[0]
        if circle not in ('invited', 'open', 'both'):
            circle = 'invited'
        
        # Form rule (Kiss): when circle is 'invited' or 'both', the worker
        # field must name a real worker party — else error
        if circle in ('invited', 'both'):
            validated_worker_id = _party_id(worker_raw, 'worker', 0)
            if validated_worker_id == 0:
                errors['worker'] = ("Missing: choose the invited worker — "
                                     "or switch the circle to “Open to everyone”.")
            else:
                worker_id = validated_worker_id
        else:
            # An open (priceless) listing has no worker yet: the worker
            # is chosen when the client accepts a bid.
            worker_id = None if price_mode == 'open' else \
                _party_id(worker_raw, 'worker', 2)
        
        if errors:
            raw_criteria = []
            i = 0
            while f'check_{i}_name' in form_data:
                raw_criteria.append({
                    'name': form_data.get(f'check_{i}_name',
                                          [''])[0],
                    'operator': form_data.get(
                        f'check_{i}_operator', [''])[0],
                    'expected_value': form_data.get(
                        f'check_{i}_expected_value', [''])[0],
                    'type': form_data.get(f'check_{i}_type',
                                          [''])[0]})
                i += 1
            def _raw_id(raw, default):
                try:
                    return int(raw)
                except (TypeError, ValueError):
                    return default
            values = {
                'title': title, 'description': description,
                'price': price_raw, 'price_mode': price_mode,
                'client_id': _raw_id(client_raw, 1),
                'worker_id': _raw_id(worker_raw, 2),
                'checker_id': _raw_id(checker_raw, 3),
                'criteria': raw_criteria,
                'circle': circle}
            html = render_post_job_form(list_parties(),
                                        values=values,
                                        errors=errors,
                                       nav_view=self._context_view())
            self.send_response(400)
            self.send_header('Content-Type',
                             'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html.encode('utf-8'))
            return

        client_id = _party_id(client_raw, 'client', 1)
        checker_id = _party_id(checker_raw, 'checker', 3)

        job = create_job_action(
            title=title, description=description,
            price_cents=price_cents, currency=currency,
            criteria=criteria, client_id=client_id,
            worker_id=worker_id, checker_id=checker_id,
            via='ui', actor='client (ui)', endpoint='/post',
            price_mode=price_mode, circle=circle,
            invited_worker_id=worker_id if circle in ('invited', 'both') else 0)

        self.send_response(302)
        self.send_header('Location', f'/job/{job.id}')
        self.end_headers()
        self.wfile.write(b'');
        
        # Check for sample template and attach if present
        sample_template_id = form_data.get('sample_template', [''])[0]
        if sample_template_id:
            attach_sample_template(job, sample_template_id)
    
    # -- Slice 2.9: JSON API (agent service layer) ----------------------
    def _api_send(self, status, payload):
        body = json.dumps(payload).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _api_actor(self):
        key = self.headers.get('X-Bulwark-Key', '')
        if not key:
            return None
        digest = hashlib.sha256(key.encode('utf-8')).hexdigest()
        return get_party_by_api_key_hash(digest)

    def _api_require_actor(self, job_id, endpoint, action):
        actor = self._api_actor()
        if actor is None:
            if job_id:
                log_service_call(job_id, 'unknown', 'api', action,
                                 endpoint,
                                 'Missing or unknown API key', 401)
            self._api_send(401, {"error": "Missing or unknown API key"})
            return None
        return actor

    def _api_role_check(self, actor, job, action, endpoint):
        """A key acts only as its own party: fund/settle need the
        job's client, deliver its worker, check its checker."""
        role_party = {'fund': ('client', job.client_id),
                      'settle': ('client', job.client_id),
                      'deliver': ('worker', job.worker_id),
                      'check': ('checker', job.checker_id)}[action]
        if actor['id'] != role_party[1]:
            msg = (f"This API key belongs to party {actor['id']} "
                   f"({actor['name']}); the {action} action requires "
                   f"the job's {role_party[0]} (party {role_party[1]}).")
            log_service_call(job.id, f"party {actor['id']} (api)",
                             'api', action, endpoint, msg, 403)
            self._api_send(403, {"error": msg})
            return False
        return True

    def _api_actor_label(self, actor):
        return f"party {actor['id']} ({actor['name']})"

    def api_create_job(self):
        endpoint = '/api/v1/jobs'
        actor = self._api_actor()
        if actor is None:
            self._api_send(401, {"error": "Missing or unknown API key"})
            return
        try:
            length = int(self.headers.get('Content-Length', 0))
            data = json.loads(self.rfile.read(length) or b'{}')
        except Exception:
            self._api_send(400, {"error": "Request body must be JSON"})
            return
        title = (data.get('title') or '').strip()
        description = (data.get('description') or '').strip()
        if not title or not description:
            self._api_send(400, {"error": "Missing required fields"})
            return
        price_mode = str(data.get('price_mode') or 'fixed')
        if price_mode not in ('fixed', 'open'):
            price_mode = 'fixed'
        if price_mode == 'open':
            # A listing: no price yet — workers bid, and accepting
            # one bid locks the price and the worker.
            price_cents = 0
        elif data.get('price_cents') is not None:
            try:
                price_cents = int(data['price_cents'])
            except (TypeError, ValueError):
                self._api_send(400, {"error": "Invalid price_cents"})
                return
        elif data.get('price') is not None:
            try:
                price_cents = parse_price_cents(str(data['price']))
            except ValueError as e:
                self._api_send(400, {"error": f"Invalid price: {e}"})
                return
        else:
            self._api_send(400, {"error": "Missing required fields"})
            return
        raw_criteria = data.get('criteria') or []
        if len(raw_criteria) < 3:
            self._api_send(400,
                           {"error": "Must have at least 3 criteria"})
            return
        criteria = []
        for c in raw_criteria:
            criteria.append(Criterion(
                name=str(c.get('name', '')),
                operator=str(c.get('operator', '')),
                expected_value=str(c.get('expected_value', '')),
                criterion_type=str(c.get('type')
                                   or c.get('criterion_type')
                                   or 'deterministic')))
        client_id = int(data.get('client_id') or 0)
        worker_id = int(data.get('worker_id') or 0)
        checker_id = int(data.get('checker_id') or 0)
        if actor['id'] != client_id:
            msg = (f"This API key belongs to party {actor['id']} "
                   f"({actor['name']}); a job can only be created by "
                   f"its client (party {client_id}).")
            self._api_send(403, {"error": msg})
            return
        # Parse circle and invited_worker_id
        circle = str(data.get('circle') or '')
        if circle and circle not in ('invited', 'open', 'both'):
            circle = ''  # treat any other value as absent (today's behaviour)
        
        invited_worker_id = data.get('invited_worker_id')
        if invited_worker_id is not None:
            invited_worker_id = int(invited_worker_id)
        invitee = None
        
        # Worker validation for circle rules
        if circle in ('invited', 'both'):
            # Use invited_worker_id or worker_id as the invitee
            invitee = invited_worker_id if invited_worker_id is not None else worker_id
            if not invitee:
                self._api_send(400, {
                    "error": "Party {} is not a worker party"})
                return
            party = get_party(invitee)
            if party is None or party['kind'] != 'worker':
                self._api_send(400, {
                    "error": f"Party {invitee} is not a worker party"})
                return
            worker_id = invitee  # create_job_action receives the invitee
        elif circle == 'open':
            # No worker required
            worker_id = None
        elif circle == '' and price_mode == 'open' and not worker_id:
            worker_id = None  # chosen when a bid is accepted
        elif worker_id:
            party = get_party(worker_id)
            if party is None or party['kind'] != 'worker':
                self._api_send(400, {
                    "error": f"Party {worker_id} is not a worker party"})
                return
        
        job = create_job_action(
            title=title, description=description,
            price_cents=price_cents,
            currency=str(data.get('currency') or 'USD'),
            criteria=criteria, client_id=client_id,
            worker_id=worker_id, checker_id=checker_id,
            via='api', actor=self._api_actor_label(actor),
            endpoint=endpoint, price_mode=price_mode,
            circle=circle, invited_worker_id=invitee)
        self._api_send(201, job_status_dict(job))

    def api_get_job(self, path):
        parts = path.strip('/').split('/')
        try:
            job_id = int(parts[3])
        except (ValueError, IndexError):
            self._api_send(400, {"error": "Invalid job id"})
            return
        endpoint = f'/api/v1/jobs/{job_id}'
        actor = self._api_require_actor(job_id, endpoint, 'get_job')
        if actor is None:
            return
        job = get_job(job_id)
        if job is None:
            self._api_send(404, {"error": "Job not found"})
            return
        if actor['id'] not in (job.client_id, job.worker_id,
                               job.checker_id):
            msg = (f"This API key belongs to party {actor['id']} "
                   f"({actor['name']}), who is not a party of job "
                   f"{job_id}.")
            log_service_call(job_id, self._api_actor_label(actor),
                             'api', 'get_job', endpoint, msg, 403)
            self._api_send(403, {"error": msg})
            return
        log_service_call(job_id, self._api_actor_label(actor), 'api',
                         'get_job', endpoint,
                         f"state={job.state}", 200)
        self._api_send(200, job_status_dict(job))

    def api_job_action(self, path):
        parts = path.strip('/').split('/')
        try:
            job_id = int(parts[3])
        except (ValueError, IndexError):
            self._api_send(400, {"error": "Invalid job id"})
            return
        if len(parts) < 5:
            self._api_send(400, {"error": "Unknown action"})
            return
        action = parts[4]
        endpoint = f'/api/v1/jobs/{job_id}/{action}'
        actor = self._api_require_actor(job_id, endpoint, action)
        if actor is None:
            return
        job = get_job(job_id)
        if job is None:
            self._api_send(404, {"error": "Job not found"})
            return
        # Validate action before role check (except 'offers' which has its own)
        valid_actions = {'fund', 'settle', 'deliver', 'check', 'offers'}
        if action not in valid_actions:
            self._api_send(400, {"error": "Unknown action"})
            return
        if action == 'offers':
            # Offers carry their own role logic (worker makes,
            # client decides, offering worker withdraws) — handled
            # inside _api_offers; the generic role map has no
            # 'offers' entry.
            self._api_offers(parts, job, actor, endpoint)
            return
        if not self._api_role_check(actor, job, action, endpoint):
            return
        label = self._api_actor_label(actor)
        try:
            if action == 'fund':
                job, note = fund_job_action(
                    job_id, via='api', actor=label, endpoint=endpoint)
                payload = job_status_dict(job)
                if note:
                    payload['note'] = note
                self._api_send(200, payload)
            elif action == 'deliver':
                content_length = int(self.headers.get(
                    'Content-Length', 0))
                content_type = self.headers.get('Content-Type', '')
                body = self.rfile.read(content_length)
                if 'multipart/form-data' not in content_type:
                    self._api_send(400, {
                        "error": "Invalid form encoding; expected "
                                 "multipart/form-data."})
                    return
                form = _parse_multipart_form(content_type, body)
                files = [(field['filename'], field['data'])
                         for field in form.values()
                         if field.get('filename')]
                note = ''
                if 'note' in form and form['note']['data']:
                    note = form['note']['data'].decode('utf-8',
                                                       'replace')
                job = deliver_job_action(
                    job_id, files, note, via='api', actor=label,
                    endpoint=endpoint)
                self._api_send(200, job_status_dict(job))
            elif action == 'check':
                job, verdict = check_job_action(
                    job_id, via='api', actor=label, endpoint=endpoint)
                payload = job_status_dict(job)
                payload['verdict'] = {
                    "overall_pass": bool(verdict.overall_pass),
                    "judge_model": verdict.judge_model,
                    "items": len(verdict.items)}
                self._api_send(200, payload)
            elif action == 'settle':
                job, note = settle_job_action(
                    job_id, via='api', actor=label, endpoint=endpoint)
                payload = job_status_dict(job)
                if note:
                    payload['note'] = note
                self._api_send(200, payload)
        except ServiceError as e:
            self._api_send(e.http_status, {"error": e.message})

    # -- Slice 2.9: integrator machine view + API key issuance ---------
    def serve_machine(self, path):
        parts = path.strip('/').split('/')
        if len(parts) < 2:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Job not found')
            return
        try:
            job_id = int(parts[1])
        except ValueError:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Job not found')
            return
        job = get_job(job_id)
        if job is None:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Job not found')
            return
        job = self._maybe_release_vesting(job)
        calls = get_service_calls(job_id)
        html = render_machine_view(job, calls, nav_view=self._context_view())
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))

    def handle_party_api_key(self, path):
        parts = path.strip('/').split('/')
        if len(parts) < 2:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Party not found')
            return
        try:
            party_id = int(parts[1])
        except ValueError:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Party not found')
            return
        party = get_party(party_id)
        if party is None:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Party not found')
            return
        key = 'bw_' + _secrets.token_hex(24)
        digest = hashlib.sha256(key.encode('utf-8')).hexdigest()
        set_party_api_key_hash(party_id, digest)
        # Re-render the party page with the plaintext shown ONCE.
        all_parties = list_parties()
        same_kind = [p for p in all_parties
                     if p['kind'] == party['kind']]
        party_jobs = [j for j in list_jobs()
                      if (party['kind'] == 'client'
                          and j.client_id == party_id)
                      or (party['kind'] == 'worker'
                          and j.worker_id == party_id)
                      or (party['kind'] == 'checker'
                          and j.checker_id == party_id)
                      or (party['kind'] == 'platform'
                          and j.worker_id == party_id)]
        events = get_party_events(party_id)
        html = render_party_page(party, same_kind, party_jobs, events,
                                  nav_view=self._context_view(),
                                  api_key_issued=key)
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))

    def log_message(self, format, *args):
        pass

def run_server():
    ensure_db()
    # Fallback self-heal (demo deploy only, BULWARK_AUTO_SEED): if
    # the bundled snapshot restore did not fill the board, rebuild
    # the demo content live in the background.
    maybe_start_auto_seed()
    server = ThreadingHTTPServer((HOST, BULWARK_PORT), BulwarkHandler)
    print(f'Bulwark server running on http://{HOST}:{BULWARK_PORT}')
    print('Press Ctrl+C to stop the server')
    server.serve_forever()

if __name__ == '__main__':
    run_server()
