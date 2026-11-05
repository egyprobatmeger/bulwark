import re
from typing import Dict, Any, List, Optional
import json
from app.models import Criterion, Delivery, Job, Party
from app.demo import _crit

CSS = """
:root {
    --deep-blue: #0A2E5C;
    --bright-blue: #2B7CD3;
    --light-blue: #5FCDFD;
    --black: #14273C;
    --white: #FFFFFF;
    --gray: #5B6B7F;
    --light-gray: #F4F7FB;
    --border-color: #DFE8F1;
    --success-green: #1F9D66;
    --danger-red: #D64550;
    --warning-orange: #DD8A1B;
    --gold: #F5B921;
}
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
    background-color: var(--light-gray);
    color: var(--black);
    line-height: 1.6;
}
.container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 20px;
}
header {
    text-align: center;
    margin-bottom: 30px;
}
header p {
    max-width: 620px;
    margin: 0 auto;
}
header p:first-of-type {
    font-size: 1.3rem;
    font-weight: 700;
    color: var(--deep-blue);
    margin-bottom: 6px;
}
h1 {
    color: var(--deep-blue);
    font-size: 2.5rem;
    font-weight: 800;
    letter-spacing: -0.02em;
    margin-bottom: 10px;
}
h2 {
    color: var(--deep-blue);
    font-size: 1.5rem;
    margin-bottom: 15px;
}
p {
    color: var(--gray);
    line-height: 1.5;
}
a {
    color: var(--deep-blue);
    text-decoration: none;
}
a:hover {
    text-decoration: underline;
}
.process-rail {
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 10px;
    margin-bottom: 30px;
    flex-wrap: wrap;
}
.process-step {
    display: flex;
    flex-direction: column;
    align-items: center;
    font-size: 0.9rem;
}
.process-step div.circle {
    width: 26px;
    height: 26px;
    font-size: 0.78rem;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: bold;
    color: white;
    margin-bottom: 5px;
}
.process-step.completed div.circle {
    background-color: var(--deep-blue);
}
.process-step.active div.circle {
    background-color: var(--bright-blue);
}
.process-step.waiting div.circle {
    background-color: var(--white);
    border: 1.5px solid #C6D5E4;
    color: var(--gray);
}
.process-step-label {
    text-align: center;
    font-size: 0.8rem;
}
.job-board {
    display: grid;
    gap: 20px;
}
.counters-grid {
    display: grid;
    gap: 16px;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    margin: 20px 0;
}
.counter-card {
    background: var(--white);
    border: 1px solid var(--border-color);
    border-radius: 16px;
    padding: 16px;
    text-align: center;
    box-shadow: 0 1px 3px rgba(10,46,92,0.05);
}
.counter-value {
    font-size: 2rem;
    font-weight: 700;
    color: var(--deep-blue);
}
.counter-label {
    font-size: 0.9rem;
    color: var(--gray);
    margin-top: 4px;
}
.job-card {
    background: var(--white);
    border: 1px solid var(--border-color);
    border-top: 3px solid var(--gold);
    border-radius: 16px;
    box-shadow: 0 1px 3px rgba(10,46,92,0.06), 0 10px 28px rgba(10,46,92,0.06);
    overflow: hidden;
    display: flex;
    flex-direction: column;
}
.job-header {
    background-color: var(--white);
    color: var(--black);
    padding: 18px 22px 2px;
}
.job-title {
    font-size: 1.28rem;
    font-weight: 700;
    margin-bottom: 5px;
}
.job-header .job-title a {
    color: var(--black);
}
.seat-switcher a, .seat-switcher .current {
    margin-right: 14px;
    white-space: nowrap;
}
.seat-switcher .current {
    font-weight: 700;
}
.job-price {
    font-size: 1.15rem;
    font-weight: 700;
    color: var(--deep-blue);
}
.job-body {
    padding: 20px;
    flex-grow: 1;
}
.job-description {
    color: var(--gray);
    margin-bottom: 15px;
}
.job-footer {
    padding: 15px 20px;
    border-top: 1px solid var(--border-color);
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.state-chip {
    padding: 5px 10px;
    border-radius: 20px;
    font-size: 0.85rem;
    font-weight: 500;
}
.state-posted {
    background-color: #e3f2fd;
    color: var(--deep-blue);
}
.state-funded {
    background-color: #e8f5e8;
    color: var(--success-green);
}
.state-delivered {
    background-color: #fff8e1;
    color: #856404;
}
.state-checking {
    background-color: #e3f2fd;
    color: #0d6efd;
}
.state-settled {
    background-color: #e8f5e8;
    color: var(--success-green);
}
.state-refunded {
    background-color: #fff3cd;
    color: var(--warning-orange);
}
.state-refund {
    color: var(--warning-orange);
}
.state-revision {
    background-color: #fff3cd;
    color: var(--warning-orange);
}
/* One button system on every page. The pill shape stays, but all
   buttons share the same metrics (height, type size, padding
   rhythm), and hierarchy comes from fill alone: at most ONE solid
   primary per view; everything else is a quiet outline chip in the
   same family as the cards. */
.btn-primary, .btn-secondary, .btn-nav {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    min-height: 44px;
    padding: 10px 22px;
    border-radius: 12px;
    font-weight: 600;
    cursor: pointer;
    font-family: inherit;
    font-size: 1rem;
    box-sizing: border-box;
    text-decoration: none;
}
.btn-primary {
    background-color: var(--deep-blue);
    color: var(--white);
    border: 1px solid var(--deep-blue);
}
.btn-primary:hover {
    opacity: 0.9;
    text-decoration: none;
}
.btn-secondary, .btn-nav {
    background-color: var(--white);
    color: var(--deep-blue);
    border: 1px solid #B9C9DC;
}
.btn-secondary:hover, .btn-nav:hover {
    text-decoration: none;
    background-color: #eef4ff;
}
.btn-nav.primary {
    background-color: var(--deep-blue);
    color: var(--white);
}
.btn-nav.primary:hover {
    background-color: var(--deep-blue);
    opacity: 0.9;
}
.header-nav {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    justify-content: center;
    align-items: center;
    margin-top: 18px;
}
/* The site strip: identical on EVERY page — brand (home), Jobs,
   Payments, Certificates, How it works, Demo, and the one solid action,
   Post a job. From any page, home and every main view are one tap
   away. Hidden when printing (evidence packs stay clean). */
.site-nav {
    display: flex; justify-content: space-between; align-items: center;
    gap: 8px 16px; flex-wrap: wrap;
    padding: 4px 0 14px; margin-bottom: 10px;
    border-bottom: 1px solid var(--border-color);
}
.site-brand {
    font-size: 1.35rem; font-weight: 800; color: var(--deep-blue);
    text-decoration: none; letter-spacing: -0.01em;
    display: inline-flex; align-items: center; gap: 9px;
}
.brand-shield { height: 1.3em; width: auto; flex: none; }
.site-brand:hover { text-decoration: none; opacity: 0.85; }
.site-links { display: flex; gap: 4px; flex-wrap: wrap; }
.site-links a {
    display: inline-flex; align-items: center; min-height: 40px;
    padding: 8px 13px; border-radius: 12px;
    color: var(--deep-blue); font-weight: 600; font-size: 0.98rem;
    text-decoration: none;
}
.site-links a:hover { background: #eef4ff; text-decoration: none; }
.site-links a.site-post {
    background: var(--deep-blue); color: var(--white);
    border: 1px solid var(--deep-blue); padding: 8px 16px;
}
.site-links a.site-post:hover { opacity: 0.9; background: var(--deep-blue); }
.site-nav.site-switch-enabled .site-switch { opacity: 0.7; }
@media print { .site-nav { display: none; } }
.filter-chips {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    align-items: center;
    margin: 10px 0 16px;
}
.filter-chip {
    display: inline-flex;
    align-items: center;
    min-height: 38px;
    padding: 7px 15px;
    border: 1px solid #C6D5E4;
    border-radius: 20px;
    color: var(--deep-blue);
    background-color: var(--white);
    font-weight: 600;
    font-size: 0.95rem;
    text-decoration: none;
}
.filter-chip.active {
    background-color: var(--deep-blue);
    color: var(--white);
}
@media (max-width: 640px) {
    h1 {
        font-size: 1.9rem;
    }
    .btn-primary, .btn-secondary, .btn-nav {
        padding: 9px 16px;
        font-size: 0.95rem;
    }
}
.btn-add {
    display: flex;
    align-items: center;
    justify-content: center;
    text-align: center;
    background-color: var(--white);
    color: var(--deep-blue);
    border: 2px dashed var(--deep-blue);
    min-height: 44px;
    padding: 10px 20px;
    border-radius: 30px;
    font-weight: 600;
    cursor: pointer;
    font-family: inherit;
    font-size: 1rem;
    width: 100%;
    margin-top: 20px;
    box-sizing: border-box;
    text-decoration: none;
}
.btn-add:hover {
    background-color: #eef4ff;
    text-decoration: none;
}
.empty-state {
    text-align: center;
    padding: 60px 20px;
    color: var(--gray);
}
.empty-state-icon {
    font-size: 4rem;
    margin-bottom: 20px;
    color: var(--light-blue);
}
form-container {
    background: var(--white);
    border-radius: 12px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
    padding: 30px;
}
.form-group {
    margin-bottom: 25px;
}
.form-group label {
    display: block;
    margin-bottom: 8px;
    font-weight: 600;
    color: var(--deep-blue);
}
.form-group input,
    .form-group textarea,
    .form-group select {
        width: 100%;
        padding: 12px;
        border: 1px solid var(--border-color);
        border-radius: 12px;
        font-family: inherit;
        font-size: 1rem;
    }
.form-group input:focus,
.form-group textarea:focus,
.form-group select:focus {
    outline: none;
    border-color: var(--bright-blue);
    box-shadow: 0 0 0 3px rgba(0, 140, 255, 0.25);
}
.criteria-group {
    margin-top: 20px;
    padding-top: 20px;
    border-top: 1px solid var(--border-color);
}
.criteria-item {
    display: flex;
    gap: 15px;
    margin-bottom: 15px;
    align-items: center;
}
.criteria-item input[type="text"],
    .criteria-item input[type="number"] {
        flex: 1;
        min-width: 0;
        border-radius: 12px;
    }
    .criteria-item select {
        width: 120px;
        border-radius: 12px;
    }
    .criteria-item input[type="number"] {
        width: 100px;
        border-radius: 12px;
    }
.criteria-item button {
    background-color: var(--black);
    color: var(--white);
    border: 1px solid var(--black);
    padding: 8px 12px;
    border-radius: 12px;
    cursor: pointer;
    font-family: inherit;
    font-size: 1rem;
    box-sizing: border-box;
    text-decoration: none;
}
.criteria-item button:hover {
    opacity: 0.9;
}
@media (max-width: 560px) {
    /* One criterion row cannot fit a phone in a single line:
       the name field takes its own full line and the comparison
       controls wrap below it — nothing gets crushed. */
    .criteria-item {
        flex-wrap: wrap;
        gap: 8px;
    }
    .criteria-item input[type="text"] {
        flex: 1 1 100%;
    }
    .criteria-item select {
        flex: 1 1 30%;
        width: auto;
    }
    .criteria-item input[type="number"] {
        flex: 1 1 30%;
        width: auto;
    }
}
.help-text {
    font-size: 0.875rem;
    color: var(--gray);
    margin-top: 5px;
}
.required::after {
    content: " *";
    color: var(--danger-red);
}
.job-detail-container {
    background: var(--white);
    border-radius: 12px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
    display: flex;
    flex-direction: column;
    gap: 25px;
}
.detail-header {
    background-color: var(--white);
    color: var(--black);
    padding: 25px;
}
.detail-title {
    font-size: 1.75rem;
    font-weight: 600;
    color: var(--black);
    margin-bottom: 10px;
}
.detail-price {
    font-size: 1.5rem;
    font-weight: 500;
    color: var(--deep-blue);
    display: flex;
    align-items: baseline;
    gap: 5px;
}
.detail-price-currency {
    font-size: 1rem;
    opacity: 0.9;
}
.vault-figure {
    display: flex;
    align-items: flex-start;
    justify-content: center;
    flex-wrap: nowrap;
    padding: 20px 12px;
    gap: 16px;
}
.vault-side {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
    min-width: 0;
    flex: 1 1 0;
    text-align: center;
}
.vault-circle {
    width: 56px;
    height: 56px;
    flex-shrink: 0;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: bold;
    color: var(--white);
    font-size: 1.1rem;
    background-color: var(--deep-blue);
    box-shadow: 0 0 0 2px var(--gold);
}
.vault-circle.left {
    background-color: var(--deep-blue);
}
.vault-circle.right {
    background-color: var(--bright-blue);
}
.vault-circle.overlap {
    background-color: var(--light-blue);
    margin: 0;
}
.vault-label {
    text-align: center;
}
@media (max-width: 640px) {
    .vault-figure {
        gap: 8px;
        padding: 14px 6px;
    }
    .vault-circle {
        width: 56px;
        height: 56px;
        font-size: 0.95rem;
    }
    .vault-label.primary {
        font-size: 0.85rem;
    }
    .vault-label.secondary {
        font-size: 0.75rem;
    }
}
.vault-label.primary {
    font-weight: 600;
}
.vault-label.secondary {
    font-size: 0.9rem;
    color: var(--gray);
}
.vault-held {
    background: var(--white);
    border: 2px solid var(--success-green);
    border-radius: 12px;
    padding: 20px;
    margin: 20px 0;
}
.vault-held .held-amount {
    font-size: 2rem;
    font-weight: 700;
    color: var(--success-green);
}
.vault-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    margin-top: 12px;
    font-size: 0.9rem;
}
.vault-meta-item {
    display: flex;
    align-items: center;
    gap: 6px;
    color: var(--gray);
}
.vault-meta-item strong {
    color: var(--deep-blue);
    font-family: monospace;
    font-size: 0.85rem;
}
.error-banner {
    background: #fff5f5;
    border: 1px solid var(--danger-red);
    color: var(--danger-red);
    border-radius: 8px;
    padding: 15px 20px;
    margin: 20px 0;
    font-weight: 500;
}
.info-banner {
    background: #e3f2fd;
    border: 1px solid var(--deep-blue);
    color: var(--deep-blue);
    border-radius: 8px;
    padding: 12px 20px;
    margin: 20px 0;
    font-weight: 500;
}
.btn-fund {
    /* The one money action on a job page — the view's single
       primary, a touch larger than the shared metrics. */
    background-color: var(--deep-blue);
    color: var(--white);
    border: 2px solid var(--deep-blue);
    min-height: 48px;
    padding: 12px 30px;
    border-radius: 30px;
    font-weight: 600;
    cursor: pointer;
    font-family: inherit;
    font-size: 1rem;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    box-sizing: border-box;
}
.btn-fund:hover {
    opacity: 0.9;
}
.offers-panel {
    background: var(--white);
    border: 1px solid var(--border-color);
    border-radius: 12px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.06);
    padding: 20px 25px;
    margin: 20px 0;
}
.offers-panel h2 {
    margin-top: 0;
}
.offer-row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px 14px;
    align-items: center;
    justify-content: space-between;
    padding: 10px 0;
    border-top: 1px solid var(--border-color);
}
.offer-main { min-width: 200px; }
.offer-amount { font-weight: 700; color: var(--deep-blue); }
.offer-meta { color: var(--gray); font-size: 0.9rem; }
.offer-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.offer-actions form { display: inline; }
.offer-status {
    padding: 4px 10px;
    border-radius: 20px;
    font-size: 0.82rem;
    font-weight: 600;
}
.offer-pending { background-color: #e3f2fd; color: var(--deep-blue); }
.offer-accepted { background-color: #e8f5e8; color: var(--success-green); }
.offer-closed { background-color: var(--light-gray); color: var(--gray); }
.offer-form {
    display: flex; flex-wrap: wrap; gap: 10px; align-items: flex-end;
    margin-top: 14px;
}
.offer-form .form-group { margin-bottom: 0; }
.locked-note {
    background: #e8f5e8;
    border: 1px solid var(--success-green);
    color: #1e6b1e;
    border-radius: 8px;
    padding: 12px 16px;
    margin: 14px 0;
    font-weight: 500;
}
.cert-chips {
    display: flex; flex-wrap: wrap; gap: 8px; margin: 8px 0 4px;
}
.cert-chip {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 6px 12px; border-radius: 20px;
    background: #eef4ff; border: 1.5px solid var(--deep-blue);
    color: var(--deep-blue); font-size: 0.9rem; font-weight: 600;
}
.fixture-deliver button {
    /* A prepared file's name can be long and unbroken — the
       button must wrap it, never stretch past the panel. */
    white-space: normal;
    overflow-wrap: anywhere;
    max-width: 100%;
    text-align: center;
}
.cert-line {
    color: var(--deep-blue); font-size: 0.88rem; font-weight: 600;
    margin-top: 2px;
}
.price-mode-group label {
    display: flex; gap: 8px; align-items: flex-start;
    font-weight: 500; margin-bottom: 10px; cursor: pointer;
}
.price-mode-group input[type="radio"] {
    margin-top: 4px; width: auto;
}
/* Form errors — a failed submission NEVER dies silently: a
   summary at the top, a red border on each problem field, and a
   short human message under it; the page scrolls to the first
   one. The server renders all of it (values preserved). */
.form-summary {
    background: #fdecea; border: 1.5px solid #c0392b;
    color: #7b241c; border-radius: 8px;
    padding: 12px 16px; margin: 0 0 18px; font-weight: 600;
}
.field-error {
    border: 2px solid #c0392b !important;
    background: #fff7f6;
}
.field-msg {
    color: #c0392b; font-size: 0.88rem; font-weight: 600;
    margin-top: 5px;
}
.criteria-section {
    padding: 0 25px;
}
.criterion-list {
    display: flex;
    flex-direction: column;
    gap: 12px;
}
.criterion-item-detail {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    padding: 10px 12px;
    background-color: var(--light-gray);
    border-radius: 8px;
}
.criterion-info {
    display: flex;
    flex-direction: column;
    gap: 4px;
    min-width: 0;
}
.criterion-status {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-shrink: 0;
}
.status-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background-color: var(--light-blue);
    flex-shrink: 0;
}
.status-label {
    font-size: 0.8rem;
    color: var(--gray);
}
.criterion-name {
    font-weight: 600;
    color: var(--deep-blue);
    overflow-wrap: anywhere;
}
.criterion-detail {
    font-size: 0.9rem;
    color: var(--gray);
    overflow-wrap: anywhere;
}
.state-badge {
    padding: 8px 16px;
    border-radius: 30px;
    font-weight: 600;
    font-size: 0.9rem;
}
.job-meta {
    display: flex;
    gap: 16px;
    flex-wrap: wrap;
    margin-top: 8px;
}
.job-meta-item {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 0.85rem;
    color: var(--gray);
}
footer {
    text-align: center;
    margin-top: 40px;
    color: var(--gray);
    font-size: 0.85rem;
    padding: 20px;
}
.fixture-deliver {
    border: 1px dashed var(--bright-blue);
    border-radius: 8px;
    padding: 12px 14px;
    margin-bottom: 16px;
}
.fixture-deliver form {
    margin-top: 8px;
}
.delivery-section {
    background: var(--light-gray);
    border: 2px dashed var(--light-blue);
    border-radius: 12px;
    padding: 25px;
    margin: 20px 0;
}
.delivery-section h2 {
    color: var(--deep-blue);
    margin-bottom: 15px;
}
.deliveries-section {
    margin: 20px 0;
}
.deliveries-section h2 {
    color: var(--deep-blue);
    margin-bottom: 15px;
}
.delivery-list {
    display: flex;
    flex-direction: column;
    gap: 15px;
}
.delivery-item {
    background: var(--white);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 15px;
}
.delivery-filename {
    font-weight: 600;
    color: var(--deep-blue);
    margin-bottom: 5px;
    overflow-wrap: anywhere;
}
.delivery-meta {
    display: flex;
    gap: 15px;
    font-size: 0.85rem;
    color: var(--gray);
    flex-wrap: wrap;
}
.delivery-meta span {
    white-space: nowrap;
}
.delivery-hash {
    font-family: monospace;
}
.delivery-note {
    margin-top: 10px;
    color: var(--gray);
    line-height: 1.5;
    overflow-wrap: anywhere;
}
.job-title, .detail-title, .job-description {
    overflow-wrap: anywhere;
}
.state-checked_pass {
    background-color: #e8f5e8;
    color: var(--success-green);
}
.state-checked_fail {
    background-color: #fdecea;
    color: var(--danger-red);
}
.state-settle_error {
    background-color: #fdecea;
    color: var(--danger-red);
}
.verifier-card {
    background: var(--white);
    border: 2px solid var(--deep-blue);
    border-radius: 12px;
    padding: 25px;
    margin: 20px 0;
}
.verifier-card h2 {
    color: var(--deep-blue);
    margin-bottom: 8px;
}
.verifier-overall {
    display: inline-block;
    padding: 8px 20px;
    border-radius: 30px;
    font-weight: 700;
    font-size: 1rem;
    margin: 8px 0 12px 0;
}
.verifier-overall.pass {
    background-color: #e8f5e8;
    color: var(--success-green);
    border: 1px solid var(--success-green);
}
.verifier-overall.fail {
    background-color: #fdecea;
    color: var(--danger-red);
    border: 1px solid var(--danger-red);
}
.verifier-overall.incomplete {
    background-color: #fff3cd;
    color: #856404;
    border: 1px solid #856404;
}
.verifier-meta {
    font-size: 0.9rem;
    color: var(--gray);
    margin-bottom: 15px;
    overflow-wrap: anywhere;
}
.verdict-item {
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 12px 15px;
    margin-bottom: 10px;
    background: var(--light-gray);
}
.verdict-item-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
}
.verdict-item-name {
    font-weight: 600;
    color: var(--deep-blue);
    overflow-wrap: anywhere;
}
.verdict-chip {
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 0.85rem;
    font-weight: 700;
}
.verdict-chip.pass {
    background-color: #e8f5e8;
    color: var(--success-green);
}
.verdict-chip.fail {
    background-color: #fdecea;
    color: var(--danger-red);
}
.verdict-chip.unjudged {
    background-color: #fff3cd;
    color: #856404;
}
.verdict-item-detail {
    font-size: 0.9rem;
    color: var(--gray);
    margin-top: 6px;
    line-height: 1.5;
    overflow-wrap: anywhere;
}
.check-section {
    background: var(--light-gray);
    border: 1px solid var(--border-color);
    border-radius: 16px;
    padding: 25px;
    margin: 20px 0;
}
.brain-panel {
    background: #FFFDF6;
    border: 1px solid var(--border-color);
    border-left: 4px solid var(--gold);
    border-radius: 16px;
    padding: 25px;
    margin: 20px 0;
}
.trust-panel {
    background: var(--white);
    border: 1px solid var(--border-color);
    border-radius: 16px;
    padding: 25px;
    margin: 20px 0;
}
.settlement-panel {
    background: var(--white);
    border: 1px solid var(--border-color);
    border-left: 4px solid var(--success-green);
    border-radius: 16px;
    padding: 25px;
    margin: 20px 0;
}
.settlement-row {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
    padding: 10px 0;
    border-bottom: 1px solid var(--border-color);
    font-size: 0.95rem;
}
.settlement-row:last-child {
    border-bottom: none;
}
.timeline-section {
    margin: 20px 0;
}
.timeline-entry {
    display: flex;
    gap: 14px;
    padding: 10px 0;
    border-bottom: 1px solid var(--border-color);
    font-size: 0.92rem;
    flex-wrap: wrap;
}
.timeline-kind {
    font-weight: 600;
    color: var(--deep-blue);
    min-width: 130px;
}
.timeline-detail {
    color: var(--gray);
    font-size: 0.88rem;
}
.timeline-when {
    color: var(--gray);
    font-size: 0.85rem;
}
.process-steps {
    display: flex;
    flex-wrap: wrap;
    gap: 14px 8px;
    justify-content: space-between;
}
.process-step-detail {
    display: flex;
    flex-direction: column;
    align-items: center;
    flex: 1 1 88px;
    text-align: center;
}
.process-step-detail .circle {
    width: 38px;
    height: 38px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    color: var(--white);
    margin-bottom: 6px;
    flex-shrink: 0;
}
.process-step-detail.completed .circle {
    background-color: var(--deep-blue);
}
.process-step-detail.active .circle {
    background-color: var(--bright-blue);
}
.process-step-detail.waiting .circle {
    background-color: rgba(102, 102, 102, 0.15);
    color: var(--gray);
}
.process-step-detail .process-step-label {
    font-size: 0.82rem;
    text-align: center;
}
.process-step-detail a.step-link,
.process-step a.step-link {
    display: flex;
    flex-direction: column;
    align-items: center;
    text-decoration: none;
    color: inherit;
}
.process-step-detail a.step-link:hover .process-step-label,
.process-step a.step-link:hover .process-step-label {
    text-decoration: underline;
}
.error-tech {
    display: block;
    margin-top: 8px;
    font-size: 0.78rem;
    font-weight: 400;
    opacity: 0.75;
    word-break: break-all;
}
@media (max-width: 640px) {
    .timeline-entry {
        gap: 6px 10px;
    }
    .timeline-kind {
        min-width: 0;
    }
    .criteria-section {
        padding: 0 5px;
    }
}
@media (max-width: 390px) {
    .process-rail {
        flex-wrap: nowrap;
        gap: 4px;
    }
    .process-step {
        flex: 1 1 auto;
    }
    .process-step div.circle {
        width: 22px;
        height: 22px;
        font-size: 0.66rem;
        margin-bottom: 3px;
    }
    .process-step-label {
        font-size: 0.66rem;
    }
    .process-step-detail {
        flex: 1 1 0;
    }
    .process-step-detail .circle {
        width: 22px;
        height: 22px;
        font-size: 0.66rem;
        margin-bottom: 3px;
    }
}
"""


def _state_label(state: str) -> str:
    return state.replace('_', ' ').capitalize()


def _fmt_cents(cents: int, currency: str = "USD") -> str:
    try:
        cents = int(cents)
    except (TypeError, ValueError):
        cents = 0
    return f"${cents // 100:,}.{cents % 100:02d} {currency}"


# --- Human-readable rendering helpers (owner's standard, 2026-10-10:
# everything a person sees appears in human form — readable times and
# sentences, no raw machine formats or internal field names). ---

def _fmt_ts(value: str) -> str:
    """ISO timestamp -> '10 Oct 2026, 09:47 UTC'. Unparseable values
    are returned trimmed but unchanged."""
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    except (ValueError, TypeError):
        return text


_KIND_TITLES = {
    "posted": "Job posted",
    "offer_made": "Offer made",
    "offer_accepted": "Offer accepted — price locked",
    "offer_rejected": "Offer rejected",
    "offer_withdrawn": "Offer withdrawn",
    "offer_superseded": "Offer no longer standing",
    "terms_set": "Terms set",
    "funded": "Funded — money in the vault",
    "delivered": "Work delivered",
    "revised": "Revision delivered",
    "verdict": "Check completed",
    "captured": "Payment captured",
    "settled": "Settled — money split",
    "refunded": "Refunded",
    "discrepancy": "Discrepancy flagged",
    "appeal_decided": "Appeal decided",
    "dispute_opened": "Dispute opened",
    "dispute_upheld": "Dispute resolved — delivery upheld",
    "dispute_overturned": "Dispute resolved — verdict overturned",
    "checker_fee_paid_to_client": "Checker fee paid to the client",
    "checker_fee_released": "Checker fee released",
    "checker_fee_vesting": "Checker fee vesting",
    "capture_recovered": "Capture recovered",
    "refund_error": "Refund problem",
    "dispute_payout_error": "Dispute payout problem",
    "vesting_release_error": "Vesting release problem",
    "trust_credit_advanced": "Trust credit advanced",
    "trust_credit_error": "Trust credit problem",
    "settle_refused_capture_linkage": "Settlement refused",
    "settle_linkage_unverifiable": "Settlement verification incomplete",
    "settle_refused_voided_authorization": "Settlement refused",
    "webhook": "PayPal update",
}


def _kind_title(kind: str) -> str:
    if kind in _KIND_TITLES:
        return _KIND_TITLES[kind]
    return kind.replace("_", " ").capitalize()


_ACTOR_LABELS = {
    "client": "the client",
    "worker": "the worker",
    "checker": "the checker",
    "worker (appeal)": "the worker (appeal)",
    "settlement_brain": "the Settlement Brain",
    "system": "the system",
    "paypal": "PayPal",
}


def _human_words(key: str) -> str:
    return key.replace("_", " ").strip().capitalize()


def _event_summary(kind: str, detail) -> str:
    """One human sentence summarising a timeline event's detail dict.
    PayPal reference numbers are kept — they are the proof — but the
    raw JSON form is never shown."""
    if not isinstance(detail, dict) or not detail:
        return ""
    d = detail
    cur = d.get("currency", "USD")
    if kind == "posted" and "price_cents" in d:
        if d.get("price_mode") == "open":
            return ("Posted without a price — open to offers; "
                    "workers bid, the client picks one")
        circle_suffix = ""
        if d.get("circle") == "invited":
            circle_suffix = " — invited worker only"
        elif d.get("circle") == "open":
            circle_suffix = " — open to all workers"
        elif d.get("circle") == "both":
            circle_suffix = " — an invited worker plus open to all workers"
        return f"Price {_fmt_cents(d['price_cents'], cur)}{circle_suffix}"
    if kind in ("offer_made", "offer_accepted", "offer_rejected",
                "offer_withdrawn", "offer_superseded"):
        who = _escape(str(d.get("worker_name") or "A worker"))
        amount = _fmt_cents(d["amount_cents"], cur) \
            if "amount_cents" in d else ""
        verb = {"offer_made": "offered",
                "offer_rejected": "'s offer of",
                "offer_withdrawn": "withdrew their offer of",
                "offer_superseded": "'s earlier offer of"
                } .get(kind)
        if kind == "offer_accepted":
            return (f"The client accepted {who}'s offer of "
                    f"{amount} — the price is now locked, and the "
                    "vault will hold exactly this amount")
        if kind == "offer_made":
            what = "counter-offer" if d.get("kind") == "counter" \
                else "bid" if d.get("kind") == "bid" \
                else "took the job at the listed price"
            return f"{who} made a {what} of {amount}"
        if kind == "offer_rejected":
            return f"The client declined {who}{verb} {amount}"
        return f"{who} {verb} {amount} — it no longer stands"
    if kind == "terms_set":
        bits = []
        mode = d.get("verification_mode")
        if mode == "single":
            bits.append("single verification")
        elif mode == "dual":
            bits.append("two independent verifications")
        hours = d.get("vesting_hours")
        if hours:
            bits.append(f"checker fee vests after {hours} hours")
        if d.get("trust_credit_percent"):
            bits.append(f"trust credit {d['trust_credit_percent']}%")
        else:
            bits.append("no trust credit")
        if d.get("stake_percent"):
            bits.append(f"checker stake {d['stake_percent']}%")
        else:
            bits.append("no checker stake")
        if d.get("degraded"):
            bits.insert(0, "Set by the fallback rulebook "
                           "(the Brain was unavailable)")
        return " · ".join(bits)
    if kind == "funded":
        bits = []
        if d.get("order_id"):
            bits.append(f"PayPal order {d['order_id']}")
        if d.get("authorization_id"):
            bits.append(f"authorization {d['authorization_id']}")
        if "amount_cents" in d:
            bits.append(_fmt_cents(d["amount_cents"], cur))
        return " · ".join(bits)
    if kind in ("delivered", "revised"):
        files = d.get("files") or []
        if files:
            names = ", ".join(str(f) for f in files)
            return f"{len(files)} file{'s' if len(files) != 1 else ''}: {names}"
        return ""
    if kind == "verdict":
        if "overall_pass" in d:
            return "Result: passed" if d["overall_pass"] \
                else "Result: did not pass"
        return ""
    if kind == "captured":
        bits = []
        if "amount_cents" in d:
            bits.append(_fmt_cents(d["amount_cents"], cur))
        if d.get("capture_id"):
            bits.append(f"PayPal ref {d['capture_id']}")
        return " · ".join(bits)
    if kind == "settled":
        bits = []
        for item in d.get("items") or []:
            if isinstance(item, dict) and "amount_cents" in item:
                who = str(item.get("party", "")).replace("_", " ")
                bits.append(f"{who}: "
                            f"{_fmt_cents(item['amount_cents'], cur)}")
        vesting = d.get("checker_fee_vesting_cents")
        if vesting:
            bits.append(f"checker fee held for vesting: "
                        f"{_fmt_cents(vesting, cur)}")
        if d.get("payout_batch_id"):
            bits.append(f"payout batch {d['payout_batch_id']}")
        return " · ".join(bits)
    if kind == "refunded":
        bits = ["The full held amount went back to the client"]
        if d.get("refund_id"):
            bits.append(f"PayPal ref {d['refund_id']}")
        return " · ".join(bits)
    if kind == "webhook":
        evt = d.get("event_type") or d.get("event") or ""
        if evt:
            return f"PayPal reported: {str(evt).replace('_', ' ').lower()}"
        return ""
    # Generic fallback: readable key–value pairs, never raw JSON.
    bits = []
    for key, value in d.items():
        if value in (None, "", [], {}):
            continue
        if key.endswith("_cents") and isinstance(value, (int, float)):
            bits.append(f"{_human_words(key[:-6])}: "
                        f"{_fmt_cents(int(value), cur)}")
        elif isinstance(value, bool):
            bits.append(f"{_human_words(key)}: "
                        f"{'yes' if value else 'no'}")
        elif isinstance(value, (str, int, float)):
            if isinstance(value, str) and key.endswith("_at"):
                value = _fmt_ts(value)
            bits.append(f"{_human_words(key)}: {value}")
    return " · ".join(bits)


def _criterion_sentence(c) -> str:
    """An acceptance criterion as one human sentence."""
    name = str(getattr(c, "name", "") or "")
    op = str(getattr(c, "operator", "") or "=")
    val = str(getattr(c, "expected_value", "") or "")
    if name == "file_count":
        if op == ">=":
            return f"At least {val} file{'s' if val != '1' else ''} delivered"
        if op == "<=":
            return f"At most {val} file{'s' if val != '1' else ''} delivered"
        return f"Exactly {val} file{'s' if val != '1' else ''} delivered"
    if name == "format":
        return f"File format: {val.upper()}"
    if name == "row_count":
        if op == ">=":
            return f"At least {val} rows in the file"
        if op == "<=":
            return f"At most {val} rows in the file"
        return f"Exactly {val} rows in the file"
    if name == "unique_column":
        return f"No duplicate values in the '{val}' column"
    if name == "nonempty_column":
        return f"The '{val}' column must never be empty"
    op_words = {"=": "is", ">=": "at least", "<=": "at most",
                ">": "more than", "<": "fewer than",
                "contains": "contains"}
    return f"{_human_words(name)} {op_words.get(op, op)} {val}"


def _paypal_error_html(raw: str) -> str:
    """The PayPal error banner in human form first; the raw technical
    text stays available as a small reference line."""
    text = str(raw or "")
    if "TRANSACTION_REFUSED" in text:
        lead = ("PayPal's test system declined this funding attempt — "
                "no money moved. These declines come in waves, so "
                "please try again in a few minutes.")
    elif "credentials are absent" in text:
        lead = text
        text = ""
    else:
        lead = "PayPal could not complete this step."
    html = _escape(lead)
    if text:
        html += f'<span class="error-tech">{_escape(text)}</span>'
    return html


def _circle_marker(job):
    """Human-readable circle marker for the UI — '' for legacy jobs."""
    if not job.circle:
        return ""
    if job.circle == 'invited':
        # invitedee = job.invited_worker_id or, for fixed+invited, job.worker_id
        invitee = job.invited_worker_id if job.invited_worker_id else (job.worker_id if job.price_mode == 'fixed' else 0)
        if invitee:
            from app.db import get_party
            invited = get_party(invitee)
            if invited:
                return f"Invited: {invited['name']}"
        return "Invited"
    if job.circle == 'open':
        return "Open to all workers"
    if job.circle == 'both':
        invitee = job.invited_worker_id if job.invited_worker_id else (job.worker_id if job.price_mode == 'fixed' else 0)
        from app.db import get_party
        invited = get_party(invitee) if invitee else None
        base = f"Invited: {invited['name']}" if invited else "Invited"
        return f"{base} · open to all workers"
    return ""


_NEGOTIATION_STAGE_LABEL = {
    'agreed': "Price agreed — ready to fund",
    'counter': "Counter-offer — waiting for the client",
    'invited': "Waiting for the worker to accept",
    'waiting': "Waiting for offers",
}

_PHASE_NEXT_STEP = {
    'waiting': "Next step: a worker places a bid. Sit as the worker "
               "(LinguaCert Agency) with the picker on the Demo page "
               "and make an offer.",
    'offers': "Next step: the client chooses one offer — accepting it "
              "locks the price and the worker. Sit as the client "
              "(Mira's Shop) and accept one.",
    'invited': "Next step: the invited worker answers. Sit as the worker "
               "(LinguaCert Agency) — accept the listed price, or "
               "counter-offer.",
    'counter': "Next step: the client decides on the counter-offer. Sit "
               "as the client (Mira's Shop) and accept or decline it.",
    'agreed': "Next step: the client funds the job — one click on the "
              "Fund button. Sit as the client (Mira's Shop).",
}


def _offer_field(offer, field):
    """Offers reach the template layer as Offer objects
    (attribute access); accept dicts too, so probes and API
    shaped data behave the same."""
    if isinstance(offer, dict):
        return offer.get(field)
    return getattr(offer, field, None)


def _negotiation_stage(job, offers=None):
    """Derive the negotiation stage key for a posted negotiation job.
    Returns 'agreed' | 'counter' | 'offers' | 'invited' | 'waiting'
    for posted negotiation shapes, or '' when the job is not a posted
    negotiation shape (legacy circle, unposted, etc.)."""
    if not job.circle or job.state != 'posted':
        return ''
    pending = offers or []
    if any(_offer_field(o, 'status') == 'accepted' for o in pending):
        return 'agreed'
    if job.price_mode == 'fixed' and job.circle == 'invited':
        if any(_offer_field(o, 'kind') == 'counter'
               and _offer_field(o, 'status') == 'pending'
               for o in pending):
            return 'counter'
        return 'invited'
    if job.price_mode == 'open' and any(
            _offer_field(o, 'status') == 'pending' for o in pending):
        return 'offers'
    return 'waiting'


def _label_offers(job):
    """Offers for label purposes: only a posted circle job
    can carry a negotiation stage, so only there is the
    per-card fetch worth it. Everywhere else the label is
    '' anyway, exactly as before."""
    if job.circle and job.state == 'posted':
        from app.db import list_offers as _lo
        return _lo(job.id)
    return None


def _negotiation_label(job, offers=None):
    """Label for the negotiation state in the UI — '' unless state == 'posted' and circle set."""
    stage = _negotiation_stage(job, offers)
    if stage == 'offers':
        n = sum(1 for o in (offers or [])
                if _offer_field(o, 'status') == 'pending')
        return f"{n} offer received" if n == 1 \
            else f"{n} offers received"
    return _NEGOTIATION_STAGE_LABEL.get(stage, "")


def _circle_note(job, offers=None):
    """Circle marker + negotiation label as one human-readable note.

    The two parts are joined with ' · ' whenever BOTH are present —
    never concatenated bare (fix: for circle == 'open' the card
    rendered 'Open to all workersPrice agreed — ready to fund')."""
    marker = _circle_marker(job)
    label = _negotiation_label(job, offers)
    if marker and label:
        return f"{marker} · {label}"
    return marker or label


def _phase_next_step(job, offers=None) -> str:
    """Guidance sentence for a phase job's negotiation stage.
    Falls back to the lifecycle text when the stage is ''."""
    stage = _negotiation_stage(job, offers)
    if stage in _PHASE_NEXT_STEP:
        return _PHASE_NEXT_STEP[stage]
    return _DEMO_NEXT_STEP.get(
        job.state, "Next step: follow the process rail at the top.")


def _state_class(state: str) -> str:
    return f"state-{state}"


def _process_rail_steps() -> List[tuple]:
    return [
        (1, "test fixed", "Requirements"),
        (2, "funded", "Funded"),
        (3, "delivered", "Delivered"),
        (4, "checking", "Checked"),
        (5, "split", "Paid out"),
        (6, "certificate", "Certificate"),
    ]


#: Where each finished rail step's record lives on the job page.
_STEP_ANCHORS = {
    "test fixed": "criteria", "funded": "vault",
    "delivered": "deliveries", "checking": "check",
    "split": "settlement", "certificate": "certificate",
}


def _render_process_rail(current_step: int, state: str,
                         link: bool = False) -> str:
    steps = _process_rail_steps()
    html_parts = ['<div class="process-rail">']
    step_map = {
        'posted': 1, 'funded': 2, 'delivered': 3,
        'checking': 4, 'checked_pass': 4, 'checked_fail': 4,
        'revision': 4, 'settle_error': 5,
        'settled': 6, 'refunded': 6,
    }
    active = step_map.get(state, 1)
    for idx, (_, key, label) in enumerate(steps):
        step_num = idx + 1
        if step_num < active:
            cls = "completed"
        elif step_num == active:
            cls = "active"
        else:
            cls = "waiting"
        inner = (f'<div class="circle">{step_num}</div>'
                 f'<div class="process-step-label">{label}</div>')
        anchor = _STEP_ANCHORS.get(key)
        if link and anchor and step_num <= active:
            inner = f'<a class="step-link" href="#{anchor}">{inner}</a>'
        html_parts.append(
            f'<div class="process-step {cls}">{inner}</div>'
        )
    html_parts.append('</div>')
    return ''.join(html_parts)


def _form_summary(errors) -> str:
    """The top-of-form summary line for a failed submission."""
    if not errors:
        return ""
    n = len(errors)
    return (f'<div class="form-summary" role="alert">'
            f'{n} thing{"s" if n != 1 else ""} to fix before you '
            'can continue — the fields are marked below.</div>')


_SCROLL_TO_ERROR_JS = (
    "<script>window.addEventListener('DOMContentLoaded',function(){"
    "var el=document.querySelector('.field-error');"
    "if(el){el.scrollIntoView({block:'center'});"
    "if(el.focus){el.focus({preventScroll:true});}}});</script>")


def _field_msg(errors, key) -> str:
    if errors and key in errors:
        return f'<div class="field-msg">{_escape(errors[key])}</div>'
    return ""


def _field_cls(errors, key) -> str:
    return ' class="field-error"' if errors and key in errors else ""


def _site_nav(view: str = 'client') -> str:
    """The one header strip, identical on every rendered page:
    the Bulwark brand (→ home), Jobs, Payments, Certificates, How it works,
    Post a job as the strip's single solid action, and Demo.
    
    View variants:
    - 'door': brand, Payments, Certificates, How it works, Demo (no Jobs, no Post)
    - 'client': brand, Jobs (→ /c), Payments, Certificates, How it works, Post a job (→ /post), Demo, switch link "Worker view →" (→ /w)
    - 'worker': brand, Browse jobs (→ /w), Payments, Certificates, How it works, Demo, switch link "Client view →" (→ /c), no Post a job
    """
    # Add site-switcher CSS class
    css_class = 'site-nav'
    if view != 'door':
        css_class += ' site-switch-enabled'
    
    if view == 'door':
        return (
            f'<nav class="{css_class}">'
            '<a class="site-brand" href="/"><svg class="brand-shield" viewBox="0 0 284 329" aria-hidden="true"><path d="M142 6 L280 50 L280 155 C280 228 229 283 142 324 C55 283 4 228 4 155 L4 50 Z" fill="#FCF6E3" stroke="#F5B921" stroke-width="13"/><path d="M76 148 L128 200 L205 93" fill="none" stroke="#F5B921" stroke-width="30" stroke-linecap="round" stroke-linejoin="round"/></svg> Bulwark</a>'
            '<div class="site-links">'
            '<a href="/dashboard">Payments</a>'
            '<a href="/certificates">Certificates</a>'
            '<a href="/how">How it works</a>'
            '<a href="/demo" class="site-demo">Demo</a>'
            '</div></nav>')
    elif view == 'client':
        return (
            f'<nav class="{css_class}">'
            '<a class="site-brand" href="/"><svg class="brand-shield" viewBox="0 0 284 329" aria-hidden="true"><path d="M142 6 L280 50 L280 155 C280 228 229 283 142 324 C55 283 4 228 4 155 L4 50 Z" fill="#FCF6E3" stroke="#F5B921" stroke-width="13"/><path d="M76 148 L128 200 L205 93" fill="none" stroke="#F5B921" stroke-width="30" stroke-linecap="round" stroke-linejoin="round"/></svg> Bulwark</a>'
            '<div class="site-links">'
            '<a href="/c">Jobs</a>'
            '<a href="/dashboard">Payments</a>'
            '<a href="/certificates">Certificates</a>'
            '<a href="/how">How it works</a>'
            '<a href="/post" class="site-post">Post a job</a>'
            '<a href="/demo" class="site-demo">Demo</a>'
            '<a href="/w" class="site-switch">Worker view →</a>'
            '</div></nav>')
    elif view == 'worker':
        return (
            f'<nav class="{css_class}">'
            '<a class="site-brand" href="/"><svg class="brand-shield" viewBox="0 0 284 329" aria-hidden="true"><path d="M142 6 L280 50 L280 155 C280 228 229 283 142 324 C55 283 4 228 4 155 L4 50 Z" fill="#FCF6E3" stroke="#F5B921" stroke-width="13"/><path d="M76 148 L128 200 L205 93" fill="none" stroke="#F5B921" stroke-width="30" stroke-linecap="round" stroke-linejoin="round"/></svg> Bulwark</a>'
            '<div class="site-links">'
            '<a href="/w">Browse jobs</a>'
            '<a href="/dashboard">Payments</a>'
            '<a href="/certificates">Certificates</a>'
            '<a href="/how">How it works</a>'
            '<a href="/demo" class="site-demo">Demo</a>'
            '<a href="/c" class="site-switch">Client view →</a>'
            '</div></nav>')
    else:
        raise ValueError(f"Invalid nav_view: {view}. Must be 'door', 'client', or 'worker'")


def render_job_board(jobs: List[Job], state_filter: str = "",
                     notice: str = None, counters=None, latest_certificate=None, nav_view: str = 'client',
                     actor_line: str = None) -> str:
    parts = [
        '<!DOCTYPE html>',
        '<html lang="en">',
        '<head>',
        '<meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
        f'<title>{ "Jobs — Bulwark" if nav_view == "client" else "Browse jobs — Bulwark" if nav_view == "worker" else "Bulwark" }</title>',
        f'<style>{CSS}</style>',
        '</head>',
        '<body>',
        '<div class="container">',
        _site_nav(nav_view),
        '<header>',
        f'<h1>{ "Jobs" if nav_view == "client" else "Browse jobs" if nav_view == "worker" else "Bulwark" }</h1>',
        f'<p>{ "Find work. Pass the check. Get paid." if nav_view == "worker" else "Hire any agent. Pay only for work that passes." }</p>',
        f'<p>{ "Every job is listed here, at the stage it has reached. Open one to make an offer, deliver work, or follow its progress — each job page shows the step that is yours from this desk." if nav_view == "worker" else "Your money is held, the delivery is checked against your criteria, then released or refunded automatically." }</p>',
        '</header>',
    ]
    # Board role strip: ONE line under the heading
    # when the seated actor is known.
    if actor_line:
        parts.append(
            '<p style="margin:12px 0 0;font-style:italic;'
            f'color:#555;">{_escape(actor_line)}</p>')
    parts.append(_render_process_rail(1, 'posted'))

    # State filter (audit visibility at a glance).
    # BOTH boards carry the same chips over the same job
    # set — each board's chips point at its own board.
    _board_base = '/w' if nav_view == "worker" else '/c'
    filters = [("funded", "Funded"), ("delivered", "Delivered"),
               ("checked", "Checked"), ("settled", "Settled"),
               ("refunded", "Refunded")]
    if filters:
        parts.append('<div class="filter-chips">')
        for value, label in filters:
            active = (state_filter == value)
            href = _board_base if not value else \
                f'{_board_base}?state={value}'
            parts.append(
                f'<a href="{href}" class="filter-chip'
                f'{" active" if active else ""}">{label}</a>')
        # Add reset chip
        if state_filter:
            parts.append(
                f'<a href="{_board_base}" class="filter-chip">Reset</a>')
        parts.append('</div>')

    if notice:
        parts.append('<div class="brain-panel">'
                     f'<p>{_escape(notice)}</p></div>')

    if not jobs:
        # The empty text must be honest about WHICH view is empty:
        # under a state filter the board is not empty in general,
        # only that state has no jobs yet.
        empty_texts = {
            "funded": "No funded jobs yet.",
            "delivered": "No delivered jobs yet.",
            "checked": "No checked jobs yet.",
            "settled": "No settled jobs yet.",
            "refunded": "No refunded jobs yet.",
        }
        if state_filter in empty_texts:
            empty_text = empty_texts[state_filter]
        elif notice:
            empty_text = ("The demo board is being prepared — the "
                          "sample projects will appear here in a "
                          "moment.")
        elif nav_view == 'client':
            empty_text = ("No jobs posted yet. Be the first to "
                          "create a job!")
        else:
            empty_text = ("No jobs posted yet. Be the first to "
                          "create a job!")
        parts.append('<div class="job-board">')
        parts.append('<div class="empty-state">')
        parts.append('<div class="empty-state-icon">&#128209;</div>')
        parts.append(f'<p>{_escape(empty_text)}</p>')
        parts.append('</div>')
        parts.append('</div>')
    else:
        parts.append('<div class="job-board">')
        for job in jobs:
            parts.append('<div class="job-card">')
            parts.append(
                f'<div class="job-header">'
                f'<div class="job-title">{_escape(job.title)}</div>'
                f'<div class="job-price">{job.formatted_price()}</div>'
                f'</div>'
            )
            parts.append(
                f'<div class="job-body">'
                f'<p class="job-description">{_escape(job.description)}</p>'
                f'</div>'
            )
            parts.append('<div class="job-footer">')
            parts.append(
                f'<span class="state-chip {_state_class(job.state)}">'
                f'{_state_label(job.state)}</span>'
            )
            # Add circle marker and label
            note = _circle_note(job, _label_offers(job))
            if note:
                parts.append(
                    f'<span class="circle-note">{note}</span>'
                )
            if nav_view == "worker":
                # An offer can only be made while a job is posted;
                # at every later stage the worker opens the job to
                # work on it or follow it, so the card says so.
                button_text = ('View & offer' if job.state == 'posted'
                               else 'View job')
            else:
                button_text = 'View Details'
            parts.append(
                f'<a href="/job/{job.id}" class="btn-nav">{button_text}</a>'
            )
            parts.append('</div>')
            parts.append('</div>')
        parts.append('</div>')

    parts.append('<div class="counters-grid">')
    # Use computed counters if provided, otherwise keep empty (graceful fallback)
    if counters:
        parts.append('<a href="/dashboard" class="counter-card">')
        parts.append(f'<div class="counter-value">{counters.get("held", {}).get("formatted", "$0.00")}</div>')
        parts.append('<div class="counter-label">Held</div>')
        parts.append('</a>')
        parts.append('<a href="/dashboard" class="counter-card">')
        parts.append(f'<div class="counter-value">{counters.get("checking", {}).get("formatted", "$0.00")}</div>')
        parts.append('<div class="counter-label">Being checked</div>')
        parts.append('</a>')
        parts.append('<a href="/dashboard" class="counter-card">')
        parts.append(f'<div class="counter-value">{counters.get("paid_out", {}).get("formatted", "$0.00")}</div>')
        parts.append('<div class="counter-label">Paid out</div>')
        parts.append('</a>')
        parts.append('<a href="/dashboard" class="counter-card">')
        parts.append(f'<div class="counter-value">{counters.get("refunded", {}).get("formatted", "$0.00")}</div>')
        parts.append('<div class="counter-label">Refunded</div>')
        parts.append('</a>')
    else:
        # Fallback for backwards compatibility - show empty cards
        parts.append('<a href="/dashboard" class="counter-card">')
        parts.append('<div class="counter-value">0</div>')
        parts.append('<div class="counter-label">Held</div>')
        parts.append('</a>')
        parts.append('<a href="/dashboard" class="counter-card">')
        parts.append('<div class="counter-value">0</div>')
        parts.append('<div class="counter-label">Being checked</div>')
        parts.append('</a>')
        parts.append('<a href="/dashboard" class="counter-card">')
        parts.append('<div class="counter-value">0</div>')
        parts.append('<div class="counter-label">Paid out</div>')
        parts.append('</a>')
        parts.append('<a href="/dashboard" class="counter-card">')
        parts.append('<div class="counter-value">0</div>')
        parts.append('<div class="counter-label">Refunded</div>')
        parts.append('</a>')
    parts.append('</div>')

    parts.append('<div class="empty-state">')
    parts.append('<div class="empty-state-icon">&#128210;</div>')
    if latest_certificate:
        job_title = latest_certificate.get('job_title') or 'Latest certificate'
        worker_name = latest_certificate.get('worker_name') or ''
        parts.append('<p>Latest certificate</p>')
        parts.append(f'<h3><a href="/certificates">{_escape(job_title)}</a></h3>')
        if worker_name:
            parts.append(f'<p>Worker: {_escape(worker_name)}</p>')
        parts.append(f'<p>Issued: {_fmt_ts(latest_certificate.get("issued_at"))}</p>')
    else:
        parts.append('<p>No certificates yet.</p>')
    parts.append('</div>')

    parts.append('</div>')
    parts.append(
        '<footer><p>Money is held via PayPal until the check passes.</p><p>Agents and people both work here.</p></footer>'
    )
    parts.append('</body>')
    parts.append('</html>')
    return ''.join(parts)


def render_post_job_form(parties=None, values=None,
                         errors=None, templates=None, template_id=None,
                         form_open=False, nav_view='door') -> str:
    values = values or {}
    errors = errors or {}
    _mode = values.get('price_mode', 'fixed')
    parts = [
        '<!DOCTYPE html>',
        '<html lang="en">',
        '<head>',
        '<meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
        f'<title>Post a Job - Bulwark</title>',
        f'<style>{CSS}</style>'
    ]
    
    # Add sample card styles if templates are provided
    if templates:
        parts.append('''
        <style>
        .sample-card {
            background: var(--white);
            border-radius: 12px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            overflow: hidden;
            margin-bottom: 20px;
            border: 2px solid var(--bright-blue);
        }
        .sample-card .card-header {
            background-color: var(--deep-blue);
            color: var(--white);
            padding: 15px 20px;
        }
        .sample-card .card-title {
            font-size: 1.25rem;
            font-weight: 600;
            margin-bottom: 5px;
        }
        .sample-card .card-description {
            color: var(--gray);
            margin-bottom: 15px;
            padding: 15px 20px;
        }
        .sample-card .meta {
            padding: 0 20px;
            margin-bottom: 12px;
            color: var(--deep-blue);
            font-size: 0.95rem;
        }
        .sample-card ul {
            list-style: none;
            padding: 0 20px;
            margin-bottom: 20px;
        }
        .sample-card li {
            padding: 8px 0;
            border-bottom: 1px solid var(--border-color);
        }
        .sample-card li:last-child {
            border-bottom: none;
        }
        </style>
        ''')
    
    parts.extend([
        '</head>',
        '<body>',
        '<div class="container">',
        _site_nav(nav_view),
        '<header>',
        '<h1>Post a Job</h1>',
        '<p>Create a new job with clear acceptance criteria</p>',
        '</header>',
        _render_process_rail(1, 'posted'),
    ])

    # Samples section when templates are available
    if templates:
        parts.append('<h2>Start from a sample job</h2>')
        parts.append('<p>One click fills in the form below. The sample\'s prepared delivery is attached to the job, so the whole flow — fund, deliver, check, payout, certificate — runs with no file to download or upload.</p>')
        for t in templates:
            parts.append(f'''<div class="sample-card">
                <div class="card-header">
                    <div class="card-title">{_escape(t["card_title"])}</div>
                </div>
                <div class="card-description">{_escape(t["blurb"])}</div>
                <div class="meta">Price {_fmt_cents(t["price_cents"])} · {_escape(t["client"])} → {_escape(t["worker"])}</div>
                <ul>''')
            for c in t["criteria"]:
                parts.append(f'<li>{_escape(_criterion_sentence(c))}</li>')
            parts.append(f'''</ul>
                <a href="/post?template={t["id"]}" class="btn-primary">Use this sample</a>
            </div>''')
    
    # Wrap form in details when templates are available
    if templates:
        parts.append(f'<details class="blank-job" {"open" if form_open or errors or template_id else ""}>')
        parts.append('<summary>Start a blank job</summary>')
        parts.append('<div class="form-container">')
    else:
        parts.append('<div class="form-container">')
    
    parts.append('<form id="jobForm" method="POST" action="/post">')
    if template_id:
        parts.append(f'<input type="hidden" name="sample_template" value="{_escape(template_id)}">')
    if errors:
        parts.append(_form_summary(errors))
    if errors:
        parts.append(_form_summary(errors))

    parts.append('<div class="form-group">')
    parts.append('<label for="title" class="required">Job Title</label>')
    parts.append('<input type="text" id="title" name="title" '
                 'placeholder="e.g., Website Redesign" '
                 f'value="{_escape(str(values.get("title", "")))}"'
                 f'{_field_cls(errors, "title")} required>')
    parts.append(_field_msg(errors, 'title'))
    parts.append('</div>')

    parts.append('<div class="form-group">')
    parts.append('<label for="description" class="required">Job Description</label>')
    parts.append('<textarea id="description" name="description" rows="6" '
                 f'{_field_cls(errors, "description")} required>'
                 f'{_escape(str(values.get("description", "")))}'
                 '</textarea>')
    parts.append(_field_msg(errors, 'description'))
    parts.append('</div>')

    parts.append('<div class="form-group price-mode-group">')
    parts.append('<label>Pricing</label>')
    parts.append(
        '<label><input type="radio" name="price_mode" value="fixed"'
        f'{" checked" if _mode != "open" else ""}> '
        '<span><strong>Fixed price</strong> — I set the '
        'price now. The assigned worker can counter-offer before '
        'funding; if I accept, that amount becomes the locked '
        'price.</span></label>')
    parts.append(
        '<label><input type="radio" name="price_mode" value="open"'
        f'{" checked" if _mode == "open" else ""}> '
        '<span><strong>Open to offers</strong> — I post without a '
        'price, like a listing. Workers bid; when I accept one bid, '
        'that worker and that price are locked in.</span></label>')
    parts.append(
        '<span class="help-text">Either way, nothing about the '
        'price or the criteria can change once the job is funded — '
        'the vault holds exactly the agreed amount.</span>')
    parts.append('</div>')

    _circle_mode = values.get('circle', 'invited')
    _mode = values.get('price_mode', 'fixed')

    parts.append('<div class="form-group circle-group">')
    parts.append('<label>Who can take this job</label>')
    parts.append(
        '<label><input type="radio" name="circle" value="invited"'
        f'{" checked" if _circle_mode == "invited" else ""}> '
        '<span><strong>Invited worker only</strong> — I name the worker. '
        'Only they can take this job: they accept my price, or '
        'counter-offer and I decide.</span></label>')
    parts.append(
        '<label><input type="radio" name="circle" value="open"'
        f'{" checked" if _circle_mode == "open" else ""}> '
        '<span><strong>Open to everyone</strong> — any worker can offer. On a '
        'fixed price they can take the job at that price or '
        'counter-offer; I choose who gets it.</span></label>')
    parts.append(
        '<label><input type="radio" name="circle" value="both"'
        f'{" checked" if _circle_mode == "both" else ""}> '
        '<span><strong>Both</strong> — I invite one worker (they are shown '
        'first, highlighted) and the job stays open to everyone '
        'else as well.</span></label>')
    parts.append(
        '<span class="help-text">With "Invited worker only" and "Both", '
        'I name the worker. With "Open to everyone", no worker is named '
        'yet — the worker is chosen when you accept an offer.</span>')
    parts.append('</div>')

    _circle_invitees = ' disabled' if _circle_mode == 'open' else ''
    _circle_req = ' required' if _circle_mode in ('invited', 'both') else ''
    _open_req = '' if _mode == 'open' else ' required'
    _open_dis = ' disabled' if _mode == 'open' else ''
    parts.append('<div class="form-group" id="price-group">')
    parts.append('<label for="price" class="required">Fixed Price (USD)</label>')
    parts.append('<input type="number" id="price" name="price" min="0" step="0.01" '
                  'placeholder="0.00" '
                  f'value="{_escape(str(values.get("price", "")))}"'
                  f'{_field_cls(errors, "price")}{_open_req}{_open_dis}>')
    parts.append(_field_msg(errors, 'price'))
    parts.append('<span class="help-text">Amount in USD (e.g., 1500.00)</span>')
    parts.append('</div>')

    parts.append('<div class="form-group">')
    parts.append('<label for="currency" class="required">Currency</label>')
    parts.append('<select id="currency" name="currency" required>')
    parts.append('<option value="USD" selected>USD</option>')
    parts.append('</select>')
    parts.append('</div>')

    parts.append('<div class="form-group">')
    parts.append('<label for="client_id" class="required">Client</label>')
    parts.append('<select id="client_id" name="client_id" required>')

    for _p in (parties or []):
        if _p['kind'] == 'client':
            _sel = ' selected' if _p['id'] == int(values.get('client_id', 1)) else ''
            parts.append(f'<option value="{_p["id"]}"{_sel}>{_escape(_p["name"])}</option>')
    parts.append('</select>')
    parts.append('</div>')

    parts.append('<div class="form-group" id="worker-group" '
                 f'{_circle_invitees}>')
    parts.append('<label for="worker_id" class="required">Worker</label>')
    parts.append(f'<select id="worker_id" name="worker_id"{_circle_req}{_circle_invitees}{_field_cls(errors, "worker")}>')

    for _p in (parties or []):
        if _p['kind'] == 'worker':
            # For 'both' mode, highlight the invitee worker
            _invite_worker_id = int(values.get('invited_worker_id', 0))
            _is_invitee = (_p['id'] == _invite_worker_id)
            _sel = ' selected' if _p['id'] == int(values.get('worker_id', 2)) else ''
            _highlighted = ' style="background:#e8f4ff;"' if _is_invitee and _circle_mode == 'both' else ''
            parts.append(f'<option value="{_p["id"]}"{_sel}{_highlighted}>{_escape(_p["name"])}{" (invited)" if _is_invitee and _circle_mode == 'both' else ""}</option>')
    parts.append('</select>')
    parts.append(_field_msg(errors, 'worker'))
    parts.append('<span class="help-text" id="worker-open-note" '
                 'style="display:none">With “Open to everyone” no worker is named '
                 'yet — the worker is chosen when you accept an offer.</span>')
    parts.append('<span class="help-text" id="worker-invited-note" '
                 'style="display:none">With “Invited worker only” and “Both”, I have '
                 'named the invited worker above.</span>')
    parts.append('</div>')

    parts.append('<div class="form-group">')
    parts.append('<label for="checker_id" class="required">Checker</label>')
    parts.append('<select id="checker_id" name="checker_id" required>')

    for _p in (parties or []):
        if _p['kind'] == 'checker':
            _sel = ' selected' if _p['id'] == int(values.get('checker_id', 3)) else ''
            parts.append(f'<option value="{_p["id"]}"{_sel}>{_escape(_p["name"])}</option>')
    parts.append('</select>')
    parts.append('</div>')

    parts.append('<div class="criteria-group">')
    parts.append('<h2>Acceptance Criteria</h2>')
    parts.append('<p>Define clear, measurable criteria for job completion.</p>')
    parts.append(_field_msg(errors, 'criteria'))
    _crit_cls = ' class="field-error"' if 'criteria' in errors else ''
    parts.append(f'<div id="criteriaContainer"{_crit_cls}>')

    _crit_values = values.get('criteria') or []
    for i in range(max(4, len(_crit_values))):
        _cv = _crit_values[i] if i < len(_crit_values) else None
        parts.append(_render_criterion_input(i, True, _cv))

    parts.append('</div>')
    parts.append('<button type="button" id="addCriteriaBtn" class="btn-add">'
                 '+ Add Criteria</button>')
    parts.append('</div>')

    parts.append('<button type="submit" class="btn-primary">Post Job</button>')
    parts.append('</form>')
    parts.append('</div>')

    parts.append('<script>')
    parts.append(_add_criteria_js())
    parts.append('</script>')
    parts.append('<script>')
    parts.append("""
document.querySelectorAll('input[name="price_mode"]').forEach(
  function(radio) {
    radio.addEventListener('change', function() {
      var open = document.querySelector(
        'input[name="price_mode"]:checked').value === 'open';
      var price = document.getElementById('price');
      var worker = document.getElementById('worker_id');
      price.disabled = open;
      price.required = !open;
      worker.disabled = open;
      worker.required = !open;
      document.getElementById('price-group').style.opacity =
        open ? '0.45' : '1';
      document.getElementById('worker-group').style.opacity =
        open ? '0.45' : '1';
      document.getElementById('worker-open-note').style.display =
        open ? 'block' : 'none';
    });
  });
document.querySelectorAll('input[name="circle"]').forEach(
  function(radio) {
    radio.addEventListener('change', function() {
      var circle = document.querySelector(
        'input[name="circle"]:checked').value;
      var worker = document.getElementById('worker_id');
      if (circle === 'open') {
        worker.disabled = true;
        worker.required = false;
      } else {
        worker.disabled = false;
        worker.required = true;
      }
      document.getElementById('worker-group').style.opacity =
        (circle === 'open') ? '0.45' : '1';
      document.getElementById('worker-invited-note').style.display =
        (circle === 'open') ? 'none' : 'block';
    });
  });
""")
    parts.append('</script>')
    if errors:
        parts.append(_SCROLL_TO_ERROR_JS)

    parts.append('</div>')
    parts.append(
        '<footer><p>Bulwark — settlement layer for the digital labor market.</p></footer>'
    )
    parts.append('</body>')
    parts.append('</html>')
    return ''.join(parts)


def _render_criterion_input(index: int, is_static: bool = False,
                            value=None) -> str:
    if is_static:
        # Static initial row: use indexed field names expected by
        # main.py. `value` (a dict from a failed submission) re-fills
        # the row so nothing the user typed is lost.
        v = value or {}
        def _sel(options, current, placeholder):
            out = [f'<option value="" disabled'
                   f'{" selected" if not current else ""}>'
                   f'{placeholder}</option>']
            for ov, label in options:
                s = ' selected' if current == ov else ''
                out.append(f'<option value="{ov}"{s}>{label}</option>')
            return ''.join(out)
        operator_attr = (
            f'<select name="check_{index}_operator" required>'
            + _sel([("=", "="), (">", "&gt;"), ("<", "<"),
                    (">=", "&gt;="), ("<=", "&lt;="),
                    ("contains", "contains")],
                   v.get('operator', ''), '=') + '</select>')
        type_attr = (
            f'<select name="check_{index}_type" required>'
            + _sel([("deterministic", "Deterministic"),
                    ("judgment", "Judgment")],
                   v.get('type', ''), 'Type') + '</select>')
        return (
            f'<div class="criteria-item" id="criterion-{index}">'
            f'<input type="text" name="check_{index}_name" '
            f'placeholder="Criterion name" '
            f'value="{_escape(str(v.get("name", "")))}" required>'
            f'{operator_attr}'
            f'<input type="text" name="check_{index}_expected_value" '
            f'placeholder="Expected value" '
            f'value="{_escape(str(v.get("expected_value", "")))}" '
            'required>'
            f'{type_attr}'
            f'<button type="button" class="remove-criteria-btn">Remove</button>'
            f'</div>'
        )
    else:
        # Dynamic row: use indexed field names for the JS-added rows
        return (
            f'<div class="criteria-item" id="criterion-{index}">'
            f'<input type="text" name="name" placeholder="Criterion name" required>'
            f'<select name="operator" required>'
            f'<option value="" disabled selected>=</option>'
            f'<option value="=">=</option>'
            f'<option value=">">' + '&gt;' + '</option>'
            f'<option value="<"><</option>'
            f'<option value=">=">>=' + '&gt;=' + '</option>'
            f'<option value="<="><=' + '&lt;=' + '</option>'
            f'<option value="contains">contains</option>'
            f'</select>'
            f'<input type="text" name="expected_value" placeholder="Expected value" required>'
            f'<select name="type" required>'
            f'<option value="" disabled selected>Type</option>'
            f'<option value="deterministic">Deterministic</option>'
            f'<option value="judgment">Judgment</option>'
            f'</select>'
            f'<button type="button" class="remove-criteria-btn">Remove</button>'
            f'</div>'
        )


def _add_criteria_js() -> str:
    return """
document.addEventListener('DOMContentLoaded', function() {
    var addBtn = document.getElementById('addCriteriaBtn');
    var container = document.getElementById('criteriaContainer');
    var index = 4;
    addBtn.addEventListener('click', function() {
        var div = document.createElement('div');
        div.className = 'criteria-item';
        div.id = 'criterion-' + index;
div.innerHTML =
                '<input type="text" name="check_' + index + '_name" placeholder="Criterion name" required>' +
                '<select name="check_' + index + '_operator" required>' +
                '<option value="" disabled selected>=</option>' +
                '<option value="=">=</option>' +
                '<option value=">">' + '&gt;' + '</option>' +
                '<option value="<"><</option>' +
                '<option value=">=">>=' + '&gt;=' + '</option>' +
                '<option value="<="><=' + '&lt;=' + '</option>' +
                '<option value="contains">contains</option>' +
                '</select>' +
                '<input type="text" name="check_' + index + '_expected_value" placeholder="Expected value" required>' +
                '<select name="check_' + index + '_type" required>' +
                '<option value="" disabled selected>Type</option>' +
                '<option value="deterministic">Deterministic</option>' +
                '<option value="judgment">Judgment</option>' +
                '</select>' +
                '<button type="button" class="remove-criteria-btn">Remove</button>';
        var removeBtn = div.querySelector('.remove-criteria-btn');
        removeBtn.addEventListener('click', function() {
            div.remove();
        });
        container.appendChild(div);
        index++;
    });
    var removeBtns = container.querySelectorAll('.remove-criteria-btn');
    removeBtns.forEach(function(btn) {
        btn.addEventListener('click', function() {
            btn.parentElement.remove();
        });
    });
});
"""


def _verdict_item_title(it: Dict[str, Any]) -> str:
    """Return human-readable title for a verdict item.
    
    Follows the specification:
    - name == "originality" -> "Originality check"
    - Else parse operator prefix off expected: candidates "<=", ">=",
      "contains", "=", ">", "<" followed by a space -> (op, value);
      default ("=", expected unchanged).
    - If checker_kind == "llm": strip a leading "judgment: " from the value;
      title = _human_words(name) (already capitalized by that helper);
      empty name -> "Judgment".
    - Else build the real Criterion (from app.models import Criterion;
      criterion_type = it.get("checker_kind") mapped: "code" ->
      "deterministic") and return _criterion_sentence(criterion).
    Use the title in the existing .verdict-item-name span.
    """
    name = str(it.get("name", "") or "")
    if name == "originality":
        return "Originality check"

    expected = str(it.get("expected", "") or "")
    checker_kind = it.get("checker_kind") or ""

    # Parse operator and value from expected
    op = "="
    val = expected
    for prefix in ["<=", ">=", "contains", "=", ">", "<"]:
        if expected.startswith(f"{prefix} "):
            op = prefix
            val = expected[len(prefix):].strip()
            break

    if checker_kind == "llm":
        # Strip leading "judgment: " from value
        if val.startswith("judgment: "):
            val = val[len("judgment: "):].strip()

        if not name:
            name = "Judgment"
        else:
            name = _human_words(name)

        return name

    # Build Criterion for deterministic checks
    criterion = Criterion(
        name=name,
        operator=op,
        expected_value=val,
        criterion_type="deterministic"
    )
    return _criterion_sentence(criterion)


def _strip_stored_prefix(text) -> str:
    """Strip stored-file token <32 lowercase hex>_<name> from text."""
    return re.sub(r"[0-9a-f]{32}_", "", str(text))


def _render_verifier_card(verdict_row, attempt_label: str = "") -> str:
    """Render one stored verdict as the D3 Verifier AI card: every
    criterion itemized with result, measured evidence, reason, and how
    it was checked. Never a bare tick."""
    if not verdict_row:
        return ""
    verdict = verdict_row.get("verdict") or {}
    items = verdict.get("items") or []
    overall = bool(verdict_row.get("overall_pass"))
    checked_at = verdict_row.get("checked_at") or verdict.get("checked_at") or ""
    judge_model = verdict_row.get("judged_model") or verdict.get("judge_model") or ""
    parts = ['<div class="verifier-card">']
    title = "Verifier AI — Acceptance Check"
    if attempt_label:
        title += f" ({_escape(attempt_label)})"
    if verdict_row.get("is_appeal"):
        title += " — Appeal verdict (final)"
    if verdict_row.get("is_dispute"):
        title += " — Dispute re-check (senior)"
    parts.append(f'<h2>{title}</h2>')
    if verdict_row.get("incomplete"):
        overall_cls = "incomplete"
        overall_label = ("NOT COMPLETED — the AI judge was "
                         "unavailable; no verdict was reached")
    else:
        overall_cls = "pass" if overall else "fail"
        overall_label = "PASS" if overall else "FAIL"
    parts.append(f'<div class="verifier-overall {overall_cls}">'
                 f'Overall verdict: {overall_label}</div>')
    meta = f'Checked at: {_escape(_fmt_ts(checked_at))}'
    if judge_model:
        meta += f' &middot; Judgment model: {_escape(str(judge_model))}'
    parts.append(f'<div class="verifier-meta">{meta}</div>')
    # --- Originality surface ---
    _sim = verdict_row.get("similarity_max", -1)
    _sim_job = verdict_row.get("similarity_job_id", -1)
    _dup = verdict_row.get("csv_dup_ratio", -1)
    if (verdict_row.get("fraud_signal") or "") == "fraud":
        parts.append(
            '<div style="background-color: #f8d7da; color: #721c24; '
            'border: 1px solid #f5c6cb; border-radius: 8px; '
            'padding: 10px 14px; margin: 10px 0; font-weight: 600;">'
            'Fraud signal — this delivery matches an earlier delivery '
            '(see the originality item below). The verdict is FAIL '
            'and the worker has been flagged.</div>')
    elif _sim is not None and _sim >= 0:
        parts.append(
            f'<div class="verifier-meta">Originality: no copy detected; '
            f'the closest earlier delivery is {float(_sim) * 100:.0f}% '
            f'similar (job #{_sim_job}).</div>')
    if _dup is not None and _dup >= 0:
        parts.append(
            f'<div class="verifier-meta">CSV duplicate data rows: '
            f'{float(_dup) * 100:.1f}% (over 5% fails the delivery).</div>')

    # Collect distinct "How it was checked" modes across items, in first-seen order
    modes = []
    seen = set()
    for it in items:
        kind = it.get("checker_kind") or ""
        model_id = it.get("model_id") or ""
        if kind == "llm":
            mode = f'Verifier AI judgment call ({model_id})' if model_id else 'Verifier AI judgment call'
        else:
            mode = 'Deterministic code check against the delivered files'
        if mode not in seen:
            seen.add(mode)
            modes.append(mode)

    for it in items:
        passed = bool(it.get("passed"))
        if it.get("judged") is False:
            chip_cls = "unjudged"
            chip_label = "NOT JUDGED"
        else:
            chip_cls = "pass" if passed else "fail"
            chip_label = "PASS" if passed else "FAIL"
        parts.append('<div class="verdict-item">')
        parts.append('<div class="verdict-item-head">')
        parts.append(f'<span class="verdict-item-name">'
                     f'{_escape(_verdict_item_title(it))}</span>')
        parts.append(f'<span class="verdict-chip {chip_cls}">{chip_label}</span>')
        parts.append('</div>')

        # Strip stored-file tokens from expected, measured and reason
        expected_clean = _strip_stored_prefix(it.get("expected", ""))
        measured_clean = _strip_stored_prefix(it.get("measured", ""))
        reason_clean = _strip_stored_prefix(it.get("reason", ""))

        parts.append(
            f'<div class="verdict-item-detail">'
            f'Expected: {_escape(str(expected_clean))} &middot; '
            f'Measured: {_escape(str(measured_clean))}<br>'
            f'Reason: {_escape(str(reason_clean))}</div>')
        parts.append('</div>')
    parts.append(f'<div class="verifier-meta">How it was checked: {" &middot; ".join(modes)}</div>')
    parts.append('</div>')
    return ''.join(parts)


def _render_offers_box(job, offers, offer_workers, offer_actor,
                       offer_error=None, nav_view='client') -> str:
    """The price-negotiation panel, shown while a job is posted.

    Two shapes: a priced job (its worker may counter-offer; the
    client may accept — that amount becomes the locked price) and
    an open listing (any worker bids; accepting one bid locks the
    worker AND the price, and every other bid lapses). The moment
    the job is funded the window closes for good — the copy says
    so, and the service layer enforces it.

    nav_view selects the controls-view: 'worker' iff the cookie is
    exactly 'worker', else 'client' (this covers 'client', 'door',
    and no-cookie the same way _context_view does)."""
    if job.state != 'posted':
        return ""
    offers = offers or []
    accepted = next((o for o in offers if o.status == 'accepted'),
                    None)
    # filter the action controls by the visitor's view.
    # 'worker' -> worker controls (bid forms, Withdraw on own offers);
    # everything else ('client', 'door', no cookie) -> client controls
    # (Accept/Decline only).
    controls_view = 'worker' if nav_view == 'worker' else 'client'
    from app.db import get_party as _gp

    def party_name(pid):
        p = _gp(pid) if pid else None
        return p['name'] if p else '—'

    status_label = {
        'pending': 'Awaiting the client\'s decision',
        'accepted': 'Accepted — price locked',
        'rejected': 'Declined by the client',
        'withdrawn': 'Withdrawn by the worker',
        'superseded': 'No longer standing',
    }
    rows = []
    for o in offers:
        cls = ('offer-pending' if o.status == 'pending' else
               'offer-accepted' if o.status == 'accepted'
               else 'offer-closed')
        kind_label = ('Counter-offer' if o.kind == 'counter' else
                     'Takes it at the listed price' if o.kind == 'accept' else
                     'Bid')
        actions = ''
        if o.status == 'pending':
            if controls_view == 'client':
                actions = (
                    '<div class="offer-actions">'
                    f'<form method="POST" action="/job/{job.id}/offer/'
                    f'{o.id}/accept"><button type="submit" '
                    'class="btn-nav primary">Accept</button></form>'
                    f'<form method="POST" action="/job/{job.id}/offer/'
                    f'{o.id}/reject"><button type="submit" '
                    'class="btn-nav">Decline</button></form>'
                    '</div>')
            elif controls_view == 'worker' and offer_actor and \
                    offer_actor.get('id') == o.worker_id:
                # in worker view, Withdraw appears ONLY on the
                # actor's own offers (offer_actor is a party dict or
                # None); no actor -> no Withdraw anywhere.
                actions = (
                    '<div class="offer-actions">'
                    f'<form method="POST" action="/job/{job.id}/offer/'
                    f'{o.id}/withdraw"><button type="submit" '
                    'class="btn-nav">Withdraw</button></form>'
                    '</div>')
            # Non-pending and non-matching offers: no buttons (as today).
        rows.append(
            '<div class="offer-row"><div class="offer-main">'
            f'<span class="offer-amount">'
            f'{_escape(o.formatted_amount())}</span> '
            f'<span class="offer-meta">{kind_label} by '
            f'<a href="/party/{o.worker_id}">'
            f'{_escape(party_name(o.worker_id))}</a> · '
            f'{_escape(_fmt_ts(o.created_at))}</span></div>'
            f'<span class="offer-status {cls}">'
            f'{status_label.get(o.status, o.status)}</span>'
            f'{actions}</div>')

    parts = ['<div class="offers-panel" id="offers">']
    _offer_errors = {}
    if offer_error:
        _ofield, _omsg = offer_error
        _offer_errors[_ofield or 'offer'] = _omsg
        parts.append(_form_summary(_offer_errors))
    if job.is_open:
        parts.append('<h2>Offers — posted without a price</h2>')
        parts.append(
            '<p class="help-text">This job went out as a listing, '
            'with no price attached. Workers bid below; when the '
            'client accepts one bid, that worker and that amount '
            'are locked in — and every other bid lapses. Funding '
            'opens only once a price is agreed, and from the '
            'moment of funding neither the price nor the criteria '
            'can ever change.</p>')
    if job.price_mode == 'open':
        parts.append('<h2>Offers — posted without a price</h2>')
        parts.append(
            '<p class="help-text">This job went out as a listing, '
            'with no price attached. Workers bid below; when the '
            'client accepts one bid, that worker and that amount '
            'are locked in — and every other bid lapses. Funding '
            'opens only once a price is agreed, and from the '
            'moment of funding neither the price nor the criteria '
            'can ever change.</p>')
        # Circle-specific note for open jobs
        if job.circle == 'invited':
            parts.append('<p class="help-text">Only the invited worker can bid on this job.</p>')
        elif job.circle == 'both':
            parts.append('<p class="help-text">The invited worker is shown first; anyone can bid.</p>')
        elif job.circle:
            pass  # '' or 'open' have no extra note
    elif job.circle == 'invited':
        parts.append('<h2>Price negotiation — before funding only</h2>')
        parts.append(
            f'<p class="help-text">Listed price: '
            f'<strong>{job.formatted_price()}</strong>. The invited worker, '
            f'{_escape(party_name(job.invited_worker_id))}, can accept this price — '
            'that yes is the whole agreement — or counter-offer below; '
            'a counter-offer is the client\'s to accept or decline. '
            'Funding opens once the price is agreed.</p>')
    elif job.circle in ('open', 'both'):
        parts.append('<h2>Price negotiation — before funding only</h2>')
        parts.append(
            f'<p class="help-text">Listed price: '
            f'<strong>{job.formatted_price()}</strong>. Any worker can take '
            'this job at the listed price, or counter-offer below. The '
            'client chooses — the chosen worker and the agreed amount '
            'are then locked in. Funding opens once the price is agreed.</p>')
    else:  # legacy '' (legacy)
        parts.append('<h2>Price negotiation — before funding only</h2>')
        parts.append(
            f'<p class="help-text">Listed price: '
            f'<strong>{job.formatted_price()}</strong>. The client '
            'can fund at this price right away — or the assigned '
            'worker can counter-offer below, and the client can '
            'accept (the accepted amount becomes the locked price) '
            'or decline. Negotiation ends for good the moment the '
            'job is funded.</p>')
    if accepted is not None:
        parts.append(
            f'<div class="locked-note">&#128274; Price agreed and '
            f'locked: <strong>{_escape(accepted.formatted_amount())}'
            f'</strong> with {_escape(party_name(accepted.worker_id))}'
            '. The vault will hold exactly this amount — funding '
            'is open below.</div>')
    elif job.is_open:
        parts.append(
            '<p class="help-text"><strong>Funding is locked</strong>'
            ' until the client accepts an offer.</p>')
    parts.extend(rows)
    if accepted is None and controls_view == 'client':
        # bidding lives at the worker's desk. In the client
        # view the offers stay readable, and one line where the
        # bid form belongs switches THIS job to the worker view.
        parts.append(
            f'<p class="help-text">Making an offer is the '
            f'worker\'s step. <a href="/job/{job.id}/as/worker">'
            f'Switch to the worker view of this job</a> to bid '
            f'on it.</p>')
    if accepted is None and controls_view == 'worker':
        # The make-an-offer form. only the worker controls-view
        # may make an offer; the client view sees none of these forms.
        if job.is_open:
            options = []
            for w in (offer_workers or []):
                # For 'both' mode, highlight the invitee worker
                if job.circle == 'both' and job.invited_worker_id and w['id'] == job.invited_worker_id:
                    label = f'{_escape(w["name"])} (invited)'
                else:
                    label = _escape(w["name"])
                sel = ' selected' if offer_actor and \
                    offer_actor.get('id') == w['id'] else ''
                options.append(f'<option value="{w["id"]}"{sel}>{label}</option>')
            
            parts.append(
                f'<form method="POST" action="/job/{job.id}/offer" '
                'class="offer-form">'
                '<div class="form-group"><label for="offer-worker">'
                'Bid as worker</label>'
                f'<select id="offer-worker" name="worker_id"'
                f'{_field_cls(_offer_errors, "worker")}>'
                f'{"".join(options)}</select>'
                f'{_field_msg(_offer_errors, "worker")}</div>'
                '<div class="form-group"><label for="offer-amount">'
                'Your price (USD)</label>'
                '<input id="offer-amount" type="text" '
                'inputmode="decimal" name="amount" '
                f'value="{job.price_cents / 100:.2f}" '
                'placeholder="e.g. 420.00" required'
                f'{_field_cls(_offer_errors, "amount")}>'
                f'{_field_msg(_offer_errors, "amount")}</div>'
                '<p class="help-text">Leave the amount at the listed price '
                'to take the job at that price, or change it to counter-offer.</p>'
                '<div class="funding-locked-note">'
                'Funding is locked until the price is agreed.</div>'
                '<button type="submit" class="btn-primary">'
                'Make an offer</button></form>')
        elif job.circle == 'invited':
            # Fixed + invited: accept form + counter form
            parts.append(
                f'<form method="POST" action="/job/{job.id}/offer" '
                'class="offer-form">'
                f'<input type="hidden" name="worker_id" '
                f'value="{job.invited_worker_id}">'
                '<div class="form-group"><label for="offer-amount">'
                f'Accept the listed price — {job.formatted_price()}</label>'
                f'<input id="offer-amount" type="hidden" '
                f'name="amount" value="{job.price_cents / 100:.2f}">'
                '<div class="accept-info">'
                'That yes is the whole agreement — funding opens once '
                'the price is agreed.</div>'
                '<button type="submit" class="btn-primary">'
                f'Accept the listed price — {job.formatted_price()}</button>'
                '</form>')
            
            parts.append(
                f'<form method="POST" action="/job/{job.id}/offer" '
                'class="offer-form counter-form">'
                f'<input type="hidden" name="worker_id" '
                f'value="{job.invited_worker_id}">'
                '<div class="form-group"><label for="offer-amount">'
                'Or counter-offer (USD)</label>'
                '<input id="offer-amount" type="text" '
                'inputmode="decimal" name="amount" '
                'placeholder="e.g. 380.00" required'
                f'{_field_cls(_offer_errors, "amount")}>'
                f'{_field_msg(_offer_errors, "amount")}</div>'
                '<p class="help-text">A counter-offer is the client\'s '
                'to accept or decline.</p>'
                '<div class="funding-locked-note">'
                'Funding is locked until the price is agreed.</div>'
                '<button type="submit" class="btn-secondary">'
                'Make a counter-offer</button></form>')
        elif job.circle in ('open', 'both'):
            # Fixed + open / both: worker select + pre-filled amount + help text
            options = []
            for w in (offer_workers or []):
                if job.circle == 'both' and job.invited_worker_id and w['id'] == job.invited_worker_id:
                    label = f'{_escape(w["name"])} (invited)'
                else:
                    label = _escape(w["name"])
                sel = ' selected' if offer_actor and \
                    offer_actor.get('id') == w['id'] else ''
                options.append(f'<option value="{w["id"]}"{sel}>{label}</option>')
            
            parts.append(
                f'<form method="POST" action="/job/{job.id}/offer" '
                'class="offer-form">'
                '<div class="form-group"><label for="offer-worker">'
                'Choose worker</label>'
                f'<select id="offer-worker" name="worker_id"'
                f'{_field_cls(_offer_errors, "worker")}>'
                f'{"".join(options)}</select>'
                f'{_field_msg(_offer_errors, "worker")}</div>'
                '<div class="form-group"><label for="offer-amount">'
                'Your price (USD)</label>'
                '<input id="offer-amount" type="text" '
                'inputmode="decimal" name="amount" '
                f'value="{job.price_cents / 100:.2f}" '
                'placeholder="e.g. 420.00" required'
                f'{_field_cls(_offer_errors, "amount")}>'
                f'{_field_msg(_offer_errors, "amount")}</div>'
                '<p class="help-text">Leave the amount at the listed price '
                'to take the job at that price, or change it to counter-offer.</p>'
                '<div class="funding-locked-note">'
                'Funding is locked until the price is agreed.</div>'
                '<button type="submit" class="btn-primary">'
                'Choose worker and agree</button></form>')
        elif job.worker_id:
            # Legacy '' (legacy): exactly as today (byte-identical)
            parts.append(
                f'<form method="POST" action="/job/{job.id}/offer" '
                'class="offer-form">'
                f'<input type="hidden" name="worker_id" '
                f'value="{job.worker_id}">'
                '<div class="form-group"><label for="offer-amount">'
                f'Counter-offer by '
                f'{_escape(party_name(job.worker_id))} (USD)</label>'
                '<input id="offer-amount" type="text" '
                'inputmode="decimal" name="amount" '
                'placeholder="e.g. 380.00" required'
                f'{_field_cls(_offer_errors, "amount")}>'
                f'{_field_msg(_offer_errors, "amount")}</div>'
                '<button type="submit" class="btn-secondary">'
                'Make a counter-offer</button></form>')
    if accepted is None and controls_view == 'worker':
        # deciding on an offer lives at the client's desk.
        parts.append(
            f'<p class="help-text">Accepting or declining an '
            f'offer is the client\'s step. '
            f'<a href="/job/{job.id}/as/client">Switch to the '
            f'client view of this job</a> to decide.</p>')
    if offer_error:
        parts.append(_SCROLL_TO_ERROR_JS)
    parts.append('</div>')
    return "".join(parts)


def render_job_detail(job: Job, info_message: str = "",
                     deliveries: Optional[List[Delivery]] = None,
                     verdict=None, verdicts=None,
                     events=None, sync_note: str = "",
                     demo_fixtures=None,
                     sample_generator: bool = False,
                     offers=None, offer_workers=None,
                     offer_actor=None, offer_error=None,
                     price_agreed=None, deliver_error: str = "",
                     guide_html: str = "", nav_view='client') -> str:
    parts = [
        '<!DOCTYPE html>',
        '<html lang="en">',
        '<head>',
        '<meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
        '<title>Job Detail - Bulwark</title>',
        f'<style>{CSS}</style>',
        '</head>',
        '<body>',
        '<div class="container">',
        _site_nav(nav_view),
        '<header>'
        '<h1>Job Detail</h1>',
        f'<p>{_escape(job.title)}</p>',
        '</header>',
        _render_process_rail(1, job.state, link=True),
        '<div class="job-detail-container">',
        '<div class="detail-header">',
        f'<div class="detail-title">{_escape(job.title)}</div>',
        f'<div class="detail-price">{job.formatted_price()}</div>',
        (f'<div class="detail-subtitle">'
         f'<span class="circle-note">{_circle_note(job, offers)}</span>'
         f'</div>'
         if _circle_note(job, offers) else ''),
        '</div>'
        '<div class="job-body">',
        f'<p class="job-description">{_escape(job.description)}</p>',
        f'<p><a href="/job/{job.id}/evidence">Evidence pack</a> — the '
        'printable record of this job (test, verdicts, money ids, '
        'timeline).</p>',
        f'<p><a href="/job/{job.id}/machine">Machine view</a> — the '
        'service-call stream for this job, as an integrating partner '
        'sees it (API + UI actions, in order).</p>',
    ]

    # role separation: the view selects whose controls this
    # page renders — each side works from its own desk, while all
    # status information stays visible from both. 'worker' only
    # when the visitor is at the worker's desk; everything else
    # ('client', 'door', no cookie) renders the client's desk —
    # the same convention _render_offers_box uses, so the whole
    # page agrees with itself. Rendering only: the service layer
    # still enforces every action.
    controls_view = 'worker' if nav_view == 'worker' else 'client'

    def _other_side_note(step_text, view):
        """One line where the other side's step belongs: name the
        step, and switch THIS job to that side's view in place —
        the link reloads the same job page at the other desk."""
        label = 'worker' if view == 'worker' else 'client'
        return (f'<p class="help-text">{step_text} '
                f'<a href="/job/{job.id}/as/{view}">Switch to the '
                f'{label} view of this job</a> to continue.</p>')

    # Demo guide: directly under the header/rail, so a
    # demo visitor always sees their current role + the next step
    # before anything else.
    if guide_html:
        parts.append(guide_html)

    # Parties section: show the three parties with links to /party/<id>
    from app.db import get_party as _get_party
    client_party = _get_party(job.client_id) if hasattr(job, 'client_id') and job.client_id else None
    worker_party = _get_party(job.worker_id) if hasattr(job, 'worker_id') and job.worker_id else None
    checker_party = _get_party(job.checker_id) if hasattr(job, 'checker_id') and job.checker_id else None

    parts.append('<div class="party-section" style="margin: 20px 0; padding: 15px; background: #f8f9fa; border-radius: 8px;">')
    parts.append('<h2 style="color: var(--deep-blue); margin-bottom: 10px;">Parties</h2>')
    parts.append('<div style="display: flex; gap: 15px; flex-wrap: wrap;">')
    def _party_link(party, label):
        if not party:
            return ""
        certs = party.get("certifications") or []
        cert_html = ""
        if certs:
            cert_html = ('<div class="cert-line">&#127891; '
                         + _escape(" · ".join(certs)) + '</div>')
        return (f'<div><a href="/party/{party["id"]}" '
                'style="color: var(--deep-blue); '
                f'text-decoration: none;"><strong>{label}:</strong> '
                f'{_escape(party["name"])}</a>{cert_html}</div>')

    parts.append(_party_link(client_party, "Client"))
    if worker_party:
        parts.append(_party_link(worker_party, "Worker"))
    elif job.is_open:
        parts.append('<div><strong>Worker:</strong> not chosen yet '
                     '— set when the client accepts a bid</div>')
    parts.append(_party_link(checker_party, "Checker"))
    parts.append('</div>')
    parts.append('</div>')

    # Banners: PayPal error first (if any), then informational.
    if job.paypal_error:
        parts.append(
            f'<div class="error-banner">'
            f'{_paypal_error_html(job.paypal_error)}'
            f'</div>'
        )
    if info_message:
        parts.append(f'<div class="info-banner">{_escape(info_message)}</div>')

    # Price negotiation panel (posted state only; empty otherwise).
    parts.append(_render_offers_box(job, offers, offer_workers,
                                    offer_actor, offer_error,
                                    nav_view=nav_view))

    # Vault figure — three columns in ONE structure: client, the
    # vault itself, worker. Every column carries its own label and
    # a human status line in every state (the middle column used to
    # stand bare). Funded jobs also get the held-amount panel.
    is_funded = bool(job.paypal_order_id)
    _amt = job.formatted_funded_amount()
    if job.state == 'posted':
        _left_status = 'Not funded yet'
        effective_agreed = price_agreed if price_agreed is not None else job.has_agreed_price
        if job.is_open and not effective_agreed:
            _mid_status = 'Open to offers — no price agreed yet'
            _right_status = 'No worker chosen yet'
        else:
            _mid_status = 'Waiting for funding'
            _right_status = 'Waiting for funding'
    elif job.state == 'funded':
        _left_status = _amt
        _mid_status = f'Holding {_amt} in escrow'
        _right_status = 'Waiting for delivery'
    elif job.state == 'delivered':
        _left_status = _amt
        _mid_status = f'Holding {_amt} in escrow'
        _right_status = 'Delivered — being checked'
    elif job.state == 'checked_pass':
        _left_status = _amt
        _mid_status = f'Holding {_amt} in escrow'
        _right_status = 'Passed — ready to settle'
    elif job.state == 'checked_fail':
        _left_status = _amt
        _mid_status = f'Holding {_amt} in escrow'
        _right_status = 'Did not pass — see the verdict below'
    elif job.state == 'settle_error':
        _left_status = _amt
        _mid_status = f'Holding {_amt} in escrow'
        _right_status = 'Settlement needs attention'
    elif job.state in ('settled', 'disputed_overturned'):
        _left_status = _amt
        _mid_status = 'Released — paid out'
        _right_status = 'Paid out'
    elif job.state == 'refunded':
        _left_status = _amt
        _mid_status = 'Refunded to the client'
        _right_status = 'Refunded in full'
    else:
        _left_status = _amt if is_funded else 'Not funded yet'
        _mid_status = (f'Holding {_amt} in escrow' if is_funded
                       else 'Waiting for funding')
        _right_status = 'Waiting for delivery'

    def _vault_column(circle_cls, letter, label, status):
        return (
            '<div class="vault-side">'
            f'<div class="vault-circle {circle_cls}">{letter}</div>'
            '<div class="vault-label">'
            f'<div class="vault-label primary">{label}</div>'
            f'<div class="vault-label secondary">'
            f'{_escape(status)}</div>'
            '</div></div>')

    parts.append('<div class="vault-figure" id="vault">')
    parts.append(_vault_column('left', 'C', 'Client Funding',
                               _left_status))
    parts.append(_vault_column('overlap', 'O', 'Bulwark Vault',
                               _mid_status))
    parts.append(_vault_column('right', 'W', 'Worker Delivery',
                               _right_status))
    parts.append('</div>')

    if is_funded:
        parts.append('<div class="vault-held">')
        parts.append(f'<div class="held-amount">{_escape(job.formatted_funded_amount())}</div>')
        parts.append('<div class="vault-meta">')
        parts.append(f'<span class="vault-meta-item">Authorization status: '
                     f'<strong>{_escape(job.authorization_status)}</strong></span>')
        parts.append(f'<span class="vault-meta-item">Order ID: '
                     f'<strong>{_escape(job.paypal_order_id)}</strong></span>')
        parts.append(f'<span class="vault-meta-item">Authorization ID: '
                     f'<strong>{_escape(job.paypal_authorization_id)}</strong></span>')
        parts.append(f'<span class="vault-meta-item">Funded: '
                     f'<strong>{_escape(_fmt_ts(job.funded_at))}</strong></span>')
        parts.append('</div>')
        parts.append('</div>')
    elif job.state == 'posted' and (price_agreed if price_agreed is not None else job.has_agreed_price):
        # The Fund button exists only against an agreed price:
        # on an open listing it appears the moment an offer is
        # accepted — before that there is nothing to fund.
        # Funding is the client's step: the worker's desk
        # gets the pointer line instead of the button.
        price_label = job.formatted_price()
        if controls_view == 'client':
            parts.append(
                f'<form method="POST" action="/job/{job.id}/fund" '
                f'style="margin: 20px 0;">'
                f'<button type="submit" class="btn-fund">&#128274; Fund Vault '
                f'({price_label})</button>'
                f'</form>'
            )
        else:
            parts.append(_other_side_note(
                'Funding this job is the client\'s step.', 'client'))

    # --- Delivery section ---
    # Delivery form: visible only when job is funded (state can accept a
    # delivery). Deliveries list: visible when state is delivered or when
    # prior deliveries exist.
    # delivering is the worker's step — the whole section
    # (prepared-file button, sample generator, upload form) renders
    # only at the worker's desk; the client's desk gets one pointer
    # line where the section belongs.
    if job.state == 'funded' and controls_view != 'worker':
        parts.append(_other_side_note(
            'Delivering the finished work is the worker\'s step.',
            'worker'))
    elif job.state == 'funded':
        parts.append('<div class="delivery-section">')
        parts.append('<h2>Deliver Work</h2>')
        if deliver_error:
            parts.append(_form_summary({'files': deliver_error}))
        if demo_fixtures:
            parts.append('<div class="fixture-deliver">')
            parts.append(
                '<p><strong>Demo shortcut:</strong> this job\'s '
                'prepared file is ready — deliver it with one tap, '
                'no file to find or upload. It goes through the '
                'same delivery path as an upload, so the check, '
                'payout and certificate that follow are the real '
                'ones.</p>')
            for fx in demo_fixtures:
                parts.append(
                    f'<form method="POST" '
                    f'action="/job/{job.id}/deliver-fixture">'
                    f'<input type="hidden" name="fixture" '
                    f'value="{_escape(fx)}">'
                    f'<button type="submit" class="btn-primary">'
                    f'Deliver the prepared file: {_escape(fx)}'
                    '</button></form>')
            parts.append('</div>')
        if sample_generator:
            parts.append('<div class="fixture-deliver">')
            parts.append(
                '<p><strong>Demo shortcut:</strong> generate a '
                'sample file from this job\'s own acceptance '
                'criteria and deliver it with one tap — through '
                'the same delivery path as an upload, so the '
                'check, payout and certificate that follow are '
                'the real ones. This is a convenience of the '
                'demo for trying the flow, not part of the '
                'product: a real worker prepares and uploads '
                'their own work — the upload form below is that '
                'path, unchanged.</p>')
            parts.append(
                f'<form method="POST" '
                f'action="/job/{job.id}/generate-deliver">'
                f'<button type="submit" class="btn-secondary">'
                f'Generate &amp; deliver a sample</button>'
                f'</form>')
            if offer_actor is None or \
                    offer_actor.get('id') != job.worker_id:
                _wname = (worker_party or {}).get('name') \
                    or 'the worker'
                parts.append(
                    f'<p class="muted">You are at the worker\'s '
                    f'desk, but you are not playing '
                    f'{_escape(_wname)}: in the demo this button '
                    f'still delivers the sample for them — the '
                    f'delivery is recorded as theirs, through the '
                    f'same path as an upload.</p>')
            parts.append('</div>')
        if demo_fixtures or sample_generator:
            parts.append('<p style="margin-top:18px;"><strong>'
                         'Or upload your own file instead</strong> '
                         '— the real path, unchanged:</p>')
        parts.append(
            f'<form method="POST" action="/job/{job.id}/deliver" '
            f'enctype="multipart/form-data">'
        )
        parts.append('<div class="form-group">')
        parts.append(
            '<label for="files" class="required">Delivery Files</label>')
        _files_err = deliver_error or ""
        parts.append(
            '<input type="file" id="files" name="files" multiple '
            f'required{_field_cls({"files": _files_err} if _files_err else {}, "files")}>')
        if _files_err:
            parts.append(_field_msg({'files': _files_err}, 'files'))
        parts.append(
            '<span class="help-text">Maximum 25 MB per file. '
            'Accepted: any file type matching the acceptance criteria.</span>')
        parts.append('</div>')
        parts.append('<div class="form-group">')
        parts.append('<label for="note">Delivery Note</label>')
        parts.append(
            '<textarea id="note" name="note" rows="4" '
            'placeholder="Describe what you delivered and how it meets '
            'the criteria..."></textarea>')
        parts.append('</div>')
        # The submit lives INSIDE the form — an earlier layout had
        # it outside, where a click silently did nothing at all.
        parts.append(
            '<button type="submit" class="btn-primary">'
            'Submit Delivery</button>')
        parts.append('</form>')
        if deliver_error:
            parts.append(_SCROLL_TO_ERROR_JS)
        parts.append('</div>')

    if deliveries:
        parts.append('<div class="deliveries-section" id="deliveries">')
        parts.append('<h2>Deliveries</h2>')
        parts.append('<div class="delivery-list">')
        for d in deliveries:
            parts.append('<div class="delivery-item">')
            rev_marker = ' (revision)' if getattr(d, 'is_revision', False) else ''
            parts.append(
                f'<div class="delivery-filename">'
                f'{_escape(d.filename)}{rev_marker}</div>')
            parts.append(
                f'<div class="delivery-meta">'
                f'<span class="delivery-size">'
                f'{_escape(d.formatted_size())}</span>'
                f'<span class="delivery-hash">'
                f'sha256: {_escape(d.short_hash())}</span>'
                f'<span class="delivery-time">'
                f'{_escape(_fmt_ts(d.uploaded_at))}</span>'
                f'</div>')
            if d.note:
                parts.append(
                    f'<div class="delivery-note">'
                    f'{_escape(d.note)}</div>')
            parts.append('</div>')
        parts.append('</div>')
        parts.append('</div>')

    # --- Check section: Run check on a delivered job ---
    if job.state == 'delivered':
        parts.append('<div class="check-section" id="check">')
        parts.append('<h2>Run Acceptance Check</h2>')
        parts.append(
            '<p>The independent Verifier AI measures this delivery '
            'against the recorded acceptance test: deterministic criteria '
            'are checked by code, judgment criteria by the Verifier AI '
            'model. The itemized verdict is stored and shown below.</p>')
        parts.append(
            f'<form method="POST" action="/job/{job.id}/check" '
            f'style="margin-top: 15px;">'
            f'<button type="submit" class="btn-primary">'
            f'Run Check</button></form>')
        parts.append('</div>')

    # --- Verifier AI card(s) (both attempts shown) ---
    all_verdicts = verdicts if verdicts is not None else (
        [verdict] if verdict else [])
    if all_verdicts:
        ordered = list(reversed(all_verdicts))  # oldest attempt first
        total = len(ordered)
        if job.state != 'delivered':
            # Anchor target for the rail's Checking step when the
            # run-check section above is not rendered.
            parts.append('<div id="check">')
        for idx, vrow in enumerate(ordered):
            label = ""
            if total > 1:
                label = f"attempt {idx + 1} of {total}"
            parts.append(_render_verifier_card(vrow, label))
        if job.state != 'delivered':
            parts.append('</div>')

    # --- Appeal: ONE senior re-check after a final FAIL,
    # decided by the OTHER AI judge model. Its verdict is final.
    if job.state == 'checked_fail' and all_verdicts:
        _has_appeal = any(v.get('is_appeal') for v in all_verdicts)
        parts.append('<div class="check-section">')
        parts.append('<h2>Appeal — one senior re-check</h2>')
        if _has_appeal:
            parts.append(
                '<p>The appeal has been decided by the other AI judge '
                'model; the appeal verdict above is <strong>final</strong>.'
                '</p>')
        elif not all_verdicts[0].get('overall_pass'):
            parts.append(
                '<p>The worker may appeal this FAIL verdict <strong>'
                'exactly once</strong>. A senior re-check by the other '
                'AI judge model re-evaluates the whole delivery '
                '(criteria and originality); its verdict replaces this '
                'one and is final.</p>')
            if controls_view == 'worker':
                # Appealing is the worker's step.
                parts.append(
                    f'<form method="POST" action="/job/{job.id}/appeal" '
                    f'style="margin-top: 12px;">'
                    f'<button type="submit" class="btn-primary">'
                    f'Appeal this verdict</button></form>')
        parts.append('</div>')

    # --- Revision window: a failed check opens exactly one
    # revision; the client may instead reject and refund immediately.
    if job.state == 'checked_fail':
        _fraud = bool(verdict) and verdict.get('fraud_signal') == 'fraud'
        parts.append('<div class="check-section">')
        if _fraud:
            parts.append('<h2>No revision — fraud verdict</h2>')
            parts.append(
                '<p>This delivery was judged <strong>FRAUD</strong> '
                'by the originality screen. The revision window does '
                'not apply: the job goes straight to the refund path '
                '— the client rejects below and the vault refunds in '
                'full.</p>')
        else:
            parts.append('<h2>Revision — one chance to fix the delivery</h2>')
            parts.append(
                '<p>The Verifier AI verdict above lists the defects. The '
                'worker may upload <strong>exactly one</strong> revised '
                'delivery, which is re-checked against the same acceptance '
                'test. If the re-check also fails, the client is refunded '
                'in full automatically.</p>')
        if _fraud:
            pass  # no revision form on a fraud verdict
        elif not job.revision_used:
            if controls_view == 'worker':
                # The revised delivery is the worker's step.
                parts.append(
                    f'<form method="POST" action="/job/{job.id}/revise" '
                    f'enctype="multipart/form-data" style="margin-top: 12px;">'
                    f'<div class="form-group">'
                    f'<label for="rev_files" class="required">Revised '
                    f'Delivery Files</label>'
                    f'<input type="file" id="rev_files" name="files" '
                    f'multiple required>'
                    f'<span class="help-text">Maximum 25 MB per file.</span>'
                    f'</div>'
                    f'<div class="form-group">'
                    f'<label for="rev_note">Revision Note</label>'
                    f'<textarea id="rev_note" name="note" rows="3" '
                    f'placeholder="What was fixed?"></textarea></div>'
                    f'<button type="submit" class="btn-primary">'
                    f'Submit Revised Delivery</button></form>')
            else:
                parts.append(_other_side_note(
                    'Uploading the revised delivery is the '
                    'worker\'s step.', 'worker'))
        else:
            parts.append(
                '<p><strong>The one permitted revision has been '
                'used.</strong></p>')
        if controls_view == 'client':
            # Rejecting and refunding is the client's step.
            parts.append(
                f'<form method="POST" action="/job/{job.id}/reject" '
                f'style="margin-top: 15px;">'
                f'<button type="submit" class="btn-secondary">'
                f'Reject without revision — refund the client</button>'
                f'</form>')
        else:
            parts.append(_other_side_note(
                'Rejecting the delivery and refunding the client '
                'is the client\'s step.', 'client'))
        parts.append('</div>')


    # --- Trust credit: the advance, visible from the
    # moment it is paid at acceptance.
    if job.trust_credit_state == 'advanced':
        parts.append('<div class="trust-panel">')
        parts.append('<h2>Trust credit — advanced at acceptance</h2>')
        parts.append(
            f'<div class="settlement-row"><span>Advanced to the '
            f'worker</span><span><strong>'
            f'{_escape(_fmt_cents(job.advanced_cents, job.funded_currency or job.currency))}'
            f'</strong> of the worker&rsquo;s fee, paid as soon as the '
            f'check passed (capture '
            f'{_escape(job.advance_capture_id)} &middot; payout batch '
            f'{_escape(job.advance_batch_id)})</span></div>')
        for it in job.advance_payout_items or []:
            parts.append(
                f'<div class="settlement-row">'
                f'<span>{_escape(str(it.get("party", "")).capitalize())} '
                f'&middot; {_escape(str(it.get("receiver", "")))}</span>'
                f'<span><strong>'
                f'{_escape(_fmt_cents(it.get("amount_cents", 0), job.funded_currency or job.currency))}'
                f'</strong> &middot; {_escape(str(it.get("status", "")))}'
                f' &middot; item {_escape(str(it.get("payout_item_id", "")))}'
                f'</span></div>')
        parts.append(
            '<p>The rest of the held amount stays in the vault and is '
            'captured and split at settlement below.</p>')
        parts.append('</div>')

    # --- Settlement ---
    if job.state == 'checked_pass':
        parts.append('<div class="check-section">')
        parts.append('<h2>Settle this job</h2>')
        parts.append(
            '<p>The check passed. Settling captures the held amount '
            'and splits it three ways by the configured percentages.</p>')
        if controls_view == 'client':
            # Settling releases the money — the client's step.
            parts.append(
                f'<form method="POST" action="/job/{job.id}/settle" '
                f'style="margin-top: 12px;">'
                f'<button type="submit" class="btn-primary">'
                f'Settle — capture &amp; split</button></form>')
        else:
            parts.append(_other_side_note(
                'Settling and releasing the money is the '
                'client\'s step.', 'client'))
        parts.append('</div>')

    if job.state == 'settle_error':
        parts.append('<div class="error-banner">')
        parts.append(
            f'Settlement incomplete: {_escape(job.settle_error)}</div>')
        if job.capture_id and controls_view == 'client':
            parts.append(
                f'<form method="POST" action="/job/{job.id}/settle">'
                f'<button type="submit" class="btn-primary">'
                f'Resume payouts (capture already completed)</button>'
                f'</form>')
    
    # FD.2: Dedicated settle-refusal for voided authorization
    # Check for the dedicated settle_refused_voided_authorization event in the job's timeline
    # Note: job.state is preserved as 'checked_pass' with the dedicated event recorded
    if events:
        void_events = [e for e in events if e.get('kind') == 'settle_refused_voided_authorization']
        if void_events:
            parts.append('<div class="info-banner">')
            parts.append(
                f'<strong>Settlement refused — authorization voided/denied at PayPal.</strong><br>')
            parts.append(
                f'The authorization was voided or denied by PayPal outside the app. ')
            parts.append(
                f'The client can refund / close the job manually. ')
            parts.append(
                f'<br><a href="/job/{job.id}">View details</a> including the ')
            parts.append('recorded refusal event.')
            parts.append('</div>')

    if job.capture_id or job.payout_items:
        parts.append('<div class="settlement-panel" id="settlement">')
        parts.append('<h2>Settlement</h2>')
        if job.capture_id:
            parts.append(
                f'<div class="settlement-row"><span>Captured</span>'
                f'<span><strong>'
                f'{_escape(_fmt_cents(job.captured_amount_cents, job.captured_currency or job.currency))}'
                f'</strong> &middot; status '
                f'{_escape(job.capture_status)} &middot; capture ID '
                f'{_escape(job.capture_id)}</span></div>')
        if job.trust_credit_state == 'advanced':
            parts.append(
                f'<div class="settlement-row"><span>Advance capture '
                f'(trust credit)</span><span><strong>'
                f'{_escape(_fmt_cents(job.advanced_cents, job.funded_currency or job.currency))}'
                f'</strong> &middot; capture ID '
                f'{_escape(job.advance_capture_id)}</span></div>')
        if job.payout_batch_id:
            parts.append(
                f'<div class="settlement-row"><span>Payout batch</span>'
                f'<span>{_escape(job.payout_batch_id)}</span></div>')
        for it in job.payout_items or []:
            parts.append(
                f'<div class="settlement-row">'
                f'<span>{_escape(str(it.get("party", "")).capitalize())} '
                f'&middot; {_escape(str(it.get("receiver", "")))}</span>'
                f'<span><strong>'
                f'{_escape(_fmt_cents(it.get("amount_cents", 0), job.captured_currency or job.currency))}'
                f'</strong> &middot; {_escape(str(it.get("status", "")))}'
                f' &middot; item {_escape(str(it.get("payout_item_id", "")))}'
                f'</span></div>')
        # --- Checker fee vesting row ---
        if job.checker_vesting_state:
            cur = job.captured_currency or job.currency
            amt = _fmt_cents(job.checker_vesting_amount_cents, cur)
            if job.checker_vesting_state == 'vesting':
                vtxt = (f'<strong>{_escape(amt)}</strong> &middot; vesting '
                        f'until {_escape(_fmt_ts(job.checker_release_at))} '
                        f'&middot; paid after the dispute window closes')
            elif job.checker_vesting_state == 'released':
                vtxt = (f'<strong>{_escape(amt)}</strong> &middot; released '
                        f'&middot; batch '
                        f'{_escape(job.checker_released_batch_id)} '
                        f'&middot; item '
                        f'{_escape(job.checker_released_item_id)}')
            else:  # paid_to_client
                vtxt = (f'<strong>{_escape(amt)}</strong> &middot; paid to '
                        f'the client after an overturned dispute '
                        f'&middot; batch '
                        f'{_escape(job.checker_released_batch_id)} '
                        f'&middot; item '
                        f'{_escape(job.checker_released_item_id)}')
            parts.append(
                f'<div class="settlement-row"><span>Checker fee</span>'
                f'<span>{vtxt}</span></div>')
        parts.append('</div>')

    # --- Certificate panel ---
    from app.db import get_certificate_by_job as _gcert
    _cert = _gcert(job.id) if job.state in ('settled', 'disputed_overturned') else None
    if _cert:
        parts.append('<div class="settlement-panel" id="certificate">')
        parts.append('<h2>Birth certificate</h2>')
        parts.append(
            f'<div class="settlement-row"><span>Serial</span><span>'
            f'<strong>{_escape(_cert.get("serial", ""))}</strong> '
            f'&middot; verification code '
            f'{_escape(_cert.get("code", ""))} &middot; '
            f'<a href="/job/{job.id}/certificate">view certificate</a>'
            f'</span></div>')
        parts.append('</div>')

    # --- Dispute card ---
    if job.checker_vesting_state == 'vesting' and not job.dispute_state:
        parts.append('<div class="brain-panel">')
        parts.append('<h2>Dispute window — checker fee still vesting</h2>')
        parts.append(
            '<p>While the checker fee vests, the client may dispute '
            'this settlement. Opening a dispute freezes the fee until a '
            'senior re-check of the stored delivery decides it.</p>')
        if controls_view == 'client':
            # Opening a dispute is the client's step.
            parts.append(f'<form method="POST" action="/job/{job.id}/dispute">')
            parts.append(
                '<label>Reason <input type="text" name="reason" '
                'style="width: 60%;"></label> ')
            parts.append(
                '<button type="submit" class="btn-secondary">Open '
                'dispute</button></form>')
        else:
            parts.append(_other_side_note(
                'Opening a dispute is the client\'s step.', 'client'))
        parts.append('</div>')
    if job.dispute_state == 'open':
        parts.append('<div class="brain-panel">')
        parts.append('<h2>Dispute open — checker fee frozen</h2>')
        parts.append(
            f'<p>Opened {_escape(_fmt_ts(job.dispute_opened_at))} &middot; '
            f'reason: {_escape(job.dispute_reason) or "—"}</p>')
        parts.append(
            '<p>A senior re-check of the stored delivery decides the '
            'dispute: if the delivery still passes, the dispute closes '
            'and vesting resumes; if it fails, the vesting checker fee '
            'is paid to the client instead.</p>')
        if controls_view == 'client':
            # Running the dispute's resolution is driven from the
            # client's desk, like opening it.
            parts.append(
                f'<form method="POST" action="/job/{job.id}/dispute/resolve">'
                '<button type="submit" class="btn-primary">Run senior '
                're-check to resolve</button></form>')
        parts.append('</div>')
    if job.dispute_state == 'upheld_closed':
        parts.append('<div class="brain-panel">')
        parts.append('<h2>Dispute resolved — delivery upheld</h2>')
        parts.append(
            f'<p>The senior re-check passed the delivery '
            f'({_escape(_fmt_ts(job.dispute_resolved_at))}); the dispute is '
            f'closed and the checker fee resumed vesting.</p>')
        parts.append('</div>')
    if job.dispute_state == 'overturned':
        parts.append('<div class="brain-panel">')
        parts.append('<h2>Dispute resolved — verdict overturned</h2>')
        parts.append(
            f'<p>The senior re-check failed the delivery '
            f'({_escape(_fmt_ts(job.dispute_resolved_at))}). The unvested '
            f'checker fee was paid to the client (recovery ladder, '
            f'step 1). The worker\'s paid share is not clawed back.</p>')
        parts.append('</div>')
    if job.checker_vesting_state == 'vesting' and job.dispute_state != 'open':
        if controls_view == 'client':
            # Releasing the vested fee is a release control — the
            # client's desk.
            parts.append(
                f'<form method="POST" action="/job/{job.id}/release-vesting" '
                'style="margin: 10px 0;"><button type="submit" '
                'class="btn-secondary">Release vested fee</button></form>')
        else:
            parts.append(_other_side_note(
                'Releasing the vested checker fee is the '
                'client\'s step.', 'client'))

    # --- Refund panel ---
    if job.state == 'refunded':
        parts.append('<div class="settlement-panel" id="settlement">')
        parts.append('<h2>Money returned</h2>')
        parts.append(
            f'<div class="settlement-row"><span>Refund / void</span>'
            f'<span class="state-refund"><strong>'
            f'{_escape(job.refund_status)}</strong></span>'
            f'<span>'
            f' &middot; ID {_escape(job.refund_id)}'
            f' &middot; {_escape(_fmt_ts(job.refunded_at))}</span></div>')
        parts.append(
            '<p>The full held amount was returned to the client. No '
            'party received a payout for this job.</p>')
        parts.append('</div>')

    # Settlement Brain section
    if job.has_terms:
        parts.append(_render_brain_box(job))

    # Acceptance criteria
    parts.append('<div class="criteria-section" id="criteria">')
    parts.append('<h2>Acceptance Criteria</h2>')
    parts.append('<p class="verifier-meta">What the delivered work '
                 'will be checked against — agreed before the money '
                 'moved.</p>')
    parts.append('<div class="criterion-list">')
    # Per-criterion status follows the LATEST verdict when one exists:
    # a checked job must not keep telling the visitor every criterion
    # is still "waiting" (state-display rule, 2026-10-19).
    _latest_items = {}
    if all_verdicts:
        _lv = all_verdicts[0].get('verdict') or {}
        for _it in _lv.get('items') or []:
            _latest_items[str(_it.get('name', ''))] = bool(_it.get('passed'))
    for c in job.criteria:
        parts.append('<div class="criterion-item-detail">')
        parts.append('<div class="criterion-info">')
        parts.append(f'<div class="criterion-name">'
                     f'{_escape(_criterion_sentence(c))}</div>')
        parts.append('</div>')
        _cstatus = 'waiting'
        if str(getattr(c, 'name', '')) in _latest_items:
            _cstatus = 'passed' if _latest_items[str(c.name)] else 'did not pass'
        parts.append('<div class="criterion-status">')
        parts.append('<span class="status-dot"></span>')
        parts.append(f'<span class="status-label">{_cstatus}</span>')
        parts.append('</div>')
        parts.append('</div>')
    parts.append('</div>')
    parts.append('</div>')

    # Process section (6-step rail)
    parts.append('<div class="process-section">')
    parts.append('<h2>Process</h2>')
    parts.append(_render_process_rail_detail(job.state))
    parts.append(
        '<p class="muted">Tap a finished step to jump to its record '
        'on this page. Steps you have passed are read-only: the job '
        'only ever offers the action for the step it is on now, so '
        'nothing can be submitted twice.</p>')
    parts.append('</div>')

    # --- Timeline / audit trail ---
    if events:
        parts.append('<div class="timeline-section">')
        parts.append('<h2>Timeline</h2>')
        if sync_note:
            parts.append(
                f'<div class="verifier-meta">{_escape(sync_note)}</div>')
        for e in events:
            kind = str(e.get("kind", ""))
            actor = _ACTOR_LABELS.get(str(e.get("actor", "")),
                                      str(e.get("actor", "")))
            when = _fmt_ts(str(e.get("created_at", "")))
            meta = when
            if actor:
                meta += f' &middot; by {_escape(actor)}'
            if str(e.get("source", "")) == 'webhook':
                meta += ' &middot; reported by PayPal'
            summary = _event_summary(kind, e.get('detail') or {})
            parts.append('<div class="timeline-entry">')
            parts.append(
                f'<span class="timeline-kind">'
                f'{_escape(_kind_title(kind))}</span>')
            parts.append(
                f'<span class="timeline-when">{meta}</span>')
            if summary:
                parts.append(
                    f'<span class="timeline-detail">'
                    f'{_escape(summary)}</span>')
            parts.append('</div>')
        if job.paypal_authorization_id:
            parts.append(
                f'<form method="POST" action="/job/{job.id}/verify" '
                f'style="margin-top: 12px;">'
                f'<button type="submit" class="btn-secondary">'
                f'Verify with PayPal</button></form>')
            parts.append(
                '<p class="verifier-meta">PayPal also sends event '
                'notifications back to Bulwark; they appear on this '
                'timeline as they arrive. The state shown here is '
                'reconciled against PayPal directly — any contradiction '
                'is flagged on this timeline, never silently '
                'overwritten.</p>')
        else:
            parts.append(
                '<p class="verifier-meta">No PayPal payment has been '
                'made for this job yet. Payment verification becomes '
                'available once the job is funded.</p>')
        parts.append('</div>')

    parts.append('</div>')
    parts.append('<div class="job-footer">')
    parts.append(f'<span class="state-badge {_state_class(job.state)}">'
                 f'{_state_label(job.state)}</span>')
    parts.append('<div>')
    parts.append('<a href="/" class="btn-secondary">Back to Board</a>')
    parts.append('</div>')
    parts.append('</div>')
    parts.append('</div>')
    parts.append('</div>')
    parts.append(
        '<footer><p>Bulwark — settlement layer for the digital labor market.</p></footer>'
    )
    parts.append('</body>')
    parts.append('</html>')
    return ''.join(parts)


def _render_process_rail_detail(state: str) -> str:
    steps = _process_rail_steps()
    step_map = {
        'posted': 1, 'funded': 2, 'delivered': 3,
        'checking': 4, 'checked_pass': 4, 'checked_fail': 4,
        'revision': 4, 'settle_error': 5,
        'settled': 6, 'refunded': 6,
    }
    # Completed and current steps link DOWN to their record on this
    # page (view only). They never re-open an action: every action on
    # this page is gated by the job's current state in the service
    # layer, so a past step can be looked at but never re-done.
    anchors = _STEP_ANCHORS
    active = step_map.get(state, 1)
    html_parts = ['<div class="process-steps">']
    for idx, (_, key, label) in enumerate(steps):
        step_num = idx + 1
        if step_num < active:
            cls = "completed"
        elif step_num == active:
            cls = "active"
        else:
            cls = "waiting"
        inner = (f'<div class="circle">{step_num}</div>'
                 f'<div class="process-step-label">{label}</div>')
        anchor = anchors.get(key)
        if anchor and step_num <= active:
            inner = f'<a class="step-link" href="#{anchor}">{inner}</a>'
        html_parts.append(
            f'<div class="process-step-detail {cls}">{inner}</div>'
        )
    html_parts.append('</div>')
    return ''.join(html_parts)


def _escape(text: str) -> str:
    return (text.replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;')
                .replace('"', '&quot;')
                .replace("'", '&#39;'))


def _get_client_stage_title(state: str) -> str:
    """Get human-readable stage title for client view."""
    titles = {
        'posted': 'Posted — waiting to be funded',
        'funded': 'Funded — money waiting in the vault',
        'delivered': 'Delivered — ready to check',
        'checked_pass': 'Checked — passed',
        'checked_fail': 'Checked — did not pass',
        'revision': 'Checked — did not pass',
        'settled': 'Settled — paid out',
        'refunded': 'Refunded',
    }
    return titles.get(state, _human_words(state))


def _get_worker_stage_title(state: str) -> str:
    """Get human-readable stage title for worker view."""
    titles = {
        'posted': 'Posted — work waiting for you',
        'funded': 'Funded — the money is already in the vault',
        'delivered': 'Delivered — with the checker',
        'checked_pass': 'Checked — passed',
        'checked_fail': 'Checked — did not pass',
        'revision': 'Checked — did not pass',
        'settled': 'Paid',
        'refunded': 'Refunded — no payment',
    }
    return titles.get(state, _human_words(state))


def _render_client_job_card(job, party, certificate) -> str:
    """Render a single job card for the client view."""
    # Get the other party (worker) name
    other_party_name = party["name"] if party["kind"] == "worker" else None
    if not other_party_name:
        from app.db import get_party
        worker_party = get_party(job.worker_id) if job.worker_id else None
        if worker_party:
            other_party_name = worker_party["name"]
    
    if not other_party_name:
        other_party_name = "the worker"
    
    # Get stage-specific info
    if job.state == 'posted':
        subtitle = "The acceptance test is fixed and cannot change. The next step is yours: fund the vault, and the worker can start."
    elif job.state == 'funded':
        subtitle = f"{job.formatted_funded_amount()} is held safely in the PayPal vault. Waiting for the worker to deliver."
    elif job.state == 'delivered':
        subtitle = "The delivery is in. The next step is the check: an independent checker measures it against the test you fixed."
    elif job.state == 'checked_pass':
        subtitle = "It passed the test. The next step is yours: settle, and the vault pays out."
    elif job.state == 'checked_fail':
        subtitle = "The worker gets exactly one revision. If the revision also fails, you are refunded in full, automatically. Fraud skips the revision and refunds at once."
    elif job.state == 'revision':
        subtitle = "The worker gets exactly one revision. If the revision also fails, you are refunded in full, automatically. Fraud skips the revision and refunds at once."
    elif job.state == 'settled':
        subtitle = _get_settlement_info(job)
        cert_link = f' <a href="/job/{job.id}/certificate">View the proof certificate</a>' if certificate else ''
    elif job.state == 'refunded':
        subtitle = f"It did not pass. The full {job.formatted_price()} came back to you automatically — no forms, no chasing."
    else:
        subtitle = "Open the job to see what is needed."
    
    # Build the card
    card_html = f'''
    <div class="job-card">
        <div class="job-header">
            <div class="job-title"><a href="/job/{job.id}">{_escape(job.title)}</a></div>
            <div class="job-price">{job.formatted_price()}</div>
        </div>
        <div class="job-body">
            <p class="job-description">Worker: {other_party_name}</p>
            <p>{subtitle}</p>
    '''
    
    if job.state == 'settled':
        card_html += cert_link
    
    note = _circle_note(job, _label_offers(job))

    card_html += f'''
        </div>
        </div>
        <div class="job-footer">
            <a href="/job/{job.id}" class="btn-nav">View Details</a>
            <div class="job-footer-extra">
                <span class="circle-note">{note}</span>
            </div>
        </div>
        </div>
    </div>
    '''
    
    return card_html

def _render_worker_job_card(job, party, certificate) -> str:
    """Render a single job card for the worker view."""
    # Get the other party (client) name
    other_party_name = party["name"] if party["kind"] == "client" else None
    if not other_party_name:
        from app.db import get_party
        client_party = get_party(job.client_id) if job.client_id else None
        if client_party:
            other_party_name = client_party["name"]
    
    if not other_party_name:
        other_party_name = "the client"
    
    # Get stage-specific info
    if job.state == 'posted':
        subtitle = f"Posted by {other_party_name}. The vault is not funded yet — you will see the money here the moment the client funds it."
    elif job.state == 'funded':
        subtitle = f"{job.formatted_funded_amount()} is held in the PayPal vault for this job, before you lift a finger. The next step is yours: deliver the work."
    elif job.state == 'delivered':
        subtitle = "Your delivery is with the independent checker, measured against the test that was fixed before you started."
    elif job.state == 'checked_pass':
        subtitle = "It passed. When the client settles, the vault pays you."
    elif job.state == 'checked_fail':
        subtitle = "You get exactly one revision. If the revision also fails, the client is refunded in full and this job pays nothing."
    elif job.state == 'revision':
        subtitle = "You get exactly one revision. If the revision also fails, the client is refunded in full and this job pays nothing."
    elif job.state == 'settled':
        leg_amount = _get_worker_leg_amount(job)
        if leg_amount:
            subtitle = f"You received {leg_amount}."
        else:
            subtitle = "Paid at settlement. Open the job for the full record."
        
        # Add vesting line if applicable
        if hasattr(job, 'checker_vesting_state') and job.checker_vesting_state == 'vesting':
            cur = job.captured_currency or job.currency
            amt = _fmt_cents(job.checker_vesting_amount_cents, cur)
            subtitle += f" The checker's fee ({amt}) is still vesting until {_escape(_fmt_ts(job.checker_release_at))} — it becomes final when the dispute window closes."
        
        cert_link = f' <a href="/job/{job.id}/certificate">View the proof certificate</a>' if certificate else ''
    elif job.state == 'refunded':
        subtitle = "The job ended in a full refund to the client, so it paid nothing."
    else:
        subtitle = "Open the job to see what is needed."
    
    # Build the card
    card_html = f'''
    <div class="job-card">
        <div class="job-header">
            <div class="job-title"><a href="/job/{job.id}">{_escape(job.title)}</a></div>
            <div class="job-price">{job.formatted_price()}</div>
        </div>
        <div class="job-body">
            <p class="job-description">Client: {other_party_name}</p>
            <p>{subtitle}</p>
    '''
    
    if job.state == 'settled':
        card_html += cert_link
    
    note = _circle_note(job, _label_offers(job))

    card_html += f'''
        </div>
        <div class="job-footer">
            <a href="/job/{job.id}" class="btn-nav">View Details</a>
            <div class="job-footer-extra">
                <span class="circle-note">{note}</span>
            </div>
        </div>
    </div>
    '''
    
    return card_html


def _get_settlement_info(job) -> str:
    """Get human-readable settlement info for client view."""
    parts = []
    
    # Find legs by party field
    for item in (job.payout_items or []):
        party = item.get('party')
        amount_cents = item.get('amount_cents')
        if not amount_cents or not party:
            continue
        if party == 'worker':
            parts.append(f"Worker — {_fmt_cents(amount_cents)}")
        elif party == 'checker':
            parts.append(f"Checker — {_fmt_cents(amount_cents)}")
        elif party == 'platform':
            parts.append(f"Platform — {_fmt_cents(amount_cents)}")
    
    # Vesting line (applies with or without payout legs)
    vesting_line = None
    if hasattr(job, 'checker_vesting_state') and job.checker_vesting_state == 'vesting':
        cur = job.captured_currency or job.currency
        amt = _fmt_cents(job.checker_vesting_amount_cents, cur)
        vesting_line = f"The checker's fee ({amt}) is still vesting until {_escape(_fmt_ts(job.checker_release_at))} — it becomes final when the dispute window closes."

    # If no payout items with party info, fallback to formatted price
    if not parts:
        base = "Paid out at settlement. Open the job for the full record."
        return base + ("<br>" + vesting_line if vesting_line else "")

    # Build the payment lines
    result = [f"Paid out of the vault:"]
    result.extend(parts)
    if vesting_line:
        result.append(vesting_line)

    return "<br>".join(result)


def _get_worker_leg_amount(job) -> str:
    """Get worker leg amount for worker view."""
    if job.payout_items:
        for item in job.payout_items:
            if item.get('party') == 'worker':
                return _fmt_cents(item.get('amount_cents'))
    
    # No worker leg found
    return None


def _render_brain_box(job) -> str:
    """Render the Settlement Brain box showing the job's terms."""
    parts = ['<div class="brain-panel">']
    parts.append('<h2>Settlement Brain</h2>')
    
    has_terms = bool(job.terms_verification_mode or job.brain_narrative)
    
    if not has_terms:
        parts.append('<p><em>Terms for this job are set by the Settlement Brain at funding.</em></p>')
    else:
        # Show the stored terms
        verification_display = {
            "single": "single verification",
            "dual": "two independent AI verdicts"
        }.get(job.terms_verification_mode, job.terms_verification_mode)
        
        vesting_display = f"{job.terms_vesting_hours} hour{'s' if job.terms_vesting_hours != 1 else ''} checker-fee vesting"
        
        trust_credit_display = {
            0: "none",
            25: "25% of the worker fee may be advanced at delivery",
            50: "50% of the worker fee may be advanced at delivery"
        }.get(job.terms_trust_credit_percent, f"{job.terms_trust_credit_percent}% of the worker fee may be advanced at delivery")
        
        stake_display = {
            0: "none",
            10: "10% worker stake on first jobs"
        }.get(job.terms_stake_percent, f"{job.terms_stake_percent}% worker stake")
        
        parts.append(f'<div class="settlement-row"><span>Verification</span><span>{verification_display}</span></div>')
        parts.append(f'<div class="settlement-row"><span>Checker fee vesting</span><span>{vesting_display}</span></div>')
        parts.append(f'<div class="settlement-row"><span>Trust credit</span><span>{trust_credit_display}</span></div>')
        parts.append(f'<div class="settlement-row"><span>Worker stake</span><span>{stake_display}</span></div>')
        
        if job.brain_narrative:
            parts.append(f'<div class="verifier-card" style="border-color: var(--deep-blue); margin-top: 15px;">')
            parts.append(f'<h3 style="color: var(--deep-blue); margin-bottom: 8px;">Brain Narrative</h3>')
            parts.append(f'<div style="font-style: italic; color: var(--gray);">"{job.brain_narrative}"</div>')
            parts.append('</div>')
        
        parts.append(f'<div style="margin-top: 15px; font-size: 0.9rem; color: var(--gray);">')
        parts.append(f'Set by the Settlement Brain ({job.brain_model or "fallback"}) at funding.')
        if job.brain_degraded:
            parts.append(' ')
            parts.append('<span style="background-color: #fff3cd; color: #856404; padding: 3px 8px; border-radius: 12px; font-weight: 600; font-size: 0.8rem;">Fallback terms — Brain unavailable when this job was funded</span>')
        parts.append('</div>')
    
    parts.append('</div>')
    return ''.join(parts)


def render_party_page(party, same_kind_parties, party_jobs, events,
                      api_key_issued: str = "", nav_view='client') -> str:
    parts = [
        '<!DOCTYPE html>',
        '<html lang="en">',
        '<head>',
        '<meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
        f'<title>{ "Jobs — Bulwark" if nav_view == "client" else "Browse jobs — Bulwark" if nav_view == "worker" else "Bulwark" }</title>',
        f'<style>{CSS}</style>',
        '</head>',
        '<body>',
        '<div class="container">',
        _site_nav(nav_view),
        '<header>',
        f'<h1>{ "Jobs" if nav_view == "client" else "Browse jobs" if nav_view == "worker" else "Bulwark" }</h1>',
        f'<p>{ "Hire any agent. Pay only for work that passes." if nav_view == "worker" else "Hire any agent. Pay only for work that passes." }</p>',
        f'<p>{ "Find work. Pass the check. Get paid." if nav_view == "worker" else "Your money is held, the delivery is checked against your criteria, then released or refunded automatically." if nav_view != "worker" else "Every job below is open. Make an offer — when the client accepts it and funds the job, the money waits in the vault while you work." }</p>',
        '</header>'
    ]

    parts.append('<div class="job-detail-container">')
    parts.append('<div class="detail-header">')
    parts.append(f'<div class="detail-title">{_escape(party["name"])}</div>')
    parts.append(f'<div class="detail-price">')
    if party['kind'] == 'client':
        parts.append('<span>Client</span>')
    elif party['kind'] == 'worker':
        parts.append('<span>Worker</span>')
    elif party['kind'] == 'checker':
        parts.append('<span>Checker</span>')
    elif party['kind'] == 'platform':
        parts.append('<span>Platform</span>')
    parts.append('</div>')
    parts.append('</div>')

    parts.append('<div class="job-body">')
    parts.append('<div class="party-section">')
    parts.append('<h2>Party Information</h2>')
    parts.append('<div class="party-info">')
    parts.append(f'<div class="form-group"><label>Kind</label><div>{_escape(party["kind"].capitalize())}</div></div>')
    parts.append(f'<div class="form-group"><label>Form</label><div>{_escape(party["form"].capitalize())}</div></div>')
    parts.append(f'<div class="form-group"><label>Payout Email</label><div>{_escape(party["payout_email"] if party["payout_email"] else "(Not configured)")}</div></div>')
    parts.append('<div class="form-group"><label>Created</label><div>' + party['created_at'][:10] + '</div></div>')
    parts.append('</div>')

    # Certifications & credentials: the party's public, verifiable
    # qualifications — the reason a client can trust this party with
    # specialist work. Shown on the profile next to reputation.
    _certifications = party.get("certifications") or []
    if _certifications:
        parts.append('<div class="party-info">')
        parts.append('<h2>Certifications &amp; credentials</h2>')
        parts.append('<div class="cert-chips">')
        for _cert in _certifications:
            parts.append(
                f'<span class="cert-chip">&#127891; '
                f'{_escape(str(_cert))}</span>')
        parts.append('</div>')
        parts.append('<p class="help-text">Recorded on this '
                     'party\'s public profile — the qualifications '
                     'behind the specialist work it takes on.</p>')
        parts.append('</div>')

    # API access: per-party key for the JSON API. The
    # plaintext is shown exactly once, right after issuance; only its
    # sha256 hash is stored.
    parts.append('<div class="counters-section">')
    parts.append('<h2>API access</h2>')
    if api_key_issued:
        parts.append(
            '<div class="info-banner"><strong>Your new API key — '
            'shown once, copy it now:</strong><br>'
            f'<code>{_escape(api_key_issued)}</code><br>'
            'Send it as the <code>X-Bulwark-Key</code> header on '
            '/api/v1/ calls. Only a hash of this key is stored; '
            'issuing a new key replaces the old one.</div>')
    elif party.get("api_key_hash"):
        parts.append('<p>An API key is active for this party '
                     '(only its hash is stored).</p>')
    else:
        parts.append('<p>No API key issued yet.</p>')
    parts.append(
        f'<form method="post" action="/party/{party["id"]}/api-key">'
        '<button type="submit" class="btn-primary">'
        + ('Regenerate API key' if party.get("api_key_hash")
           else 'Issue API key') + '</button></form>')
    parts.append('</div>')

    # Certificates earned as a worker.
    if party["kind"] == "worker":
        from app.db import list_certificates_for_worker as _lcerts
        _certs = _lcerts(party["id"])
        if _certs:
            parts.append('<div class="counters-section">')
            parts.append('<h2>Certificates earned</h2>')
            parts.append('<ul>')
            for _c in _certs:
                _f = _c.get("facts") or {}
                parts.append(
                    f'<li><a href="/job/{_c["job_id"]}/certificate">'
                    f'{_escape(_c["serial"])}</a> — job #{_c["job_id"]} '
                    f'({_escape(str(_f.get("title", "")))}) &middot; '
                    f'{_escape(str(_c["issued_at"])[:10])}</li>')
            parts.append('</ul></div>')

    parts.append('<div class="counters-section">')
    parts.append('<h2>Reputation Counters</h2>')
    
    # Get derived counters from the reputation_events ledger via get_party_counters
    from app.db import get_party_counters
    counters = get_party_counters(party['id'])
    
    parts.append('<div class="counters-grid">')
    parts.append(f'<div class="counter-card"><div class="counter-value">{counters["jobs_posted"] + counters["jobs_delivered"] + counters["verdict_issued"] + counters["job_settled"]}</div><div class="counter-label">Jobs Completed</div></div>')
    parts.append(f'<div class="counter-card"><div class="counter-value">{counters["verdict_pass_first"]}</div><div class="counter-label">First Verdicts Passed</div></div>')
    parts.append(f'<div class="counter-card"><div class="counter-value">{counters["verdict_fail_first"]}</div><div class="counter-label">First Verdicts Failed</div></div>')
    parts.append(f'<div class="counter-card"><div class="counter-value">{counters["verdict_issued"]}</div><div class="counter-label">Verdicts Issued</div></div>')
    parts.append(f'<div class="counter-card"><div class="counter-value">{"Yes" if counters["fraud_flags"] else "No"}</div><div class="counter-label">Fraud Flags</div></div>')
    parts.append(f'<div class="counter-card"><div class="counter-value">{counters["verdicts_overturned"]}</div><div class="counter-label">Verdicts Overturned</div></div>')
    parts.append(f'<div class="counter-card"><div class="counter-value">{counters["verdicts_upheld"]}</div><div class="counter-label">Verdicts Upheld</div></div>')
    parts.append('</div>')
    parts.append('</div>')
    parts.append('</div>')

    parts.append('<div class="jobs-section">')
    parts.append('<h2>Jobs</h2>')
    if party_jobs:
        parts.append('<div class="job-board">')
        for job in party_jobs:
            parts.append('<div class="job-card">')
            parts.append(f'<div class="job-header"><div class="job-title">{_escape(job.title)}</div><div class="job-price">{job.formatted_price()}</div></div>')
            parts.append(f'<div class="job-body"><p class="job-description">{_escape(job.description[:100])}</p></div>')
            parts.append(f'<div class="job-footer"><span class="state-chip {_state_class(job.state)}">{_state_label(job.state)}</span><a href="/job/{job.id}" class="btn-nav">View Details</a></div>')
            parts.append('</div>')
        parts.append('</div>')
    else:
        parts.append('<div class="empty-state"><div class="empty-state-icon">&#128209;</div><p>No jobs for this party yet.</p></div>')
    parts.append('</div>')

    parts.append('<div class="events-section">')
    parts.append('<h2>Recent Reputation Events</h2>')
    if events:
        parts.append('<div class="timeline-section">')
        for event in events[:20]:  # Show last 20 events
            kind = str(event.get("kind", ""))
            actor = _ACTOR_LABELS.get(str(event.get("actor", "")),
                                      str(event.get("actor", "")))
            when = _fmt_ts(str(event.get("created_at", "")))
            meta = when
            if actor:
                meta += f' &middot; by {_escape(actor)}'
            summary = _event_summary(kind, event.get("detail") or {})
            parts.append('<div class="timeline-entry">')
            parts.append(f'<span class="timeline-kind">{_escape(_kind_title(kind))}</span>')
            parts.append(f'<span class="timeline-when">{meta}</span>')
            if summary:
                parts.append(f'<span class="timeline-detail">{_escape(summary)}</span>')
            parts.append('</div>')
        parts.append('</div>')
    else:
        parts.append('<div class="empty-state"><p>No reputation events yet.</p></div>')
    parts.append('</div>')

    parts.append('</div>')
    parts.append('<div class="job-footer">')
    parts.append(f'<a href="/" class="btn-secondary">Back to Board</a>')
    parts.append('</div>')
    parts.append('</div>')
    parts.append('<footer><p>Bulwark — settlement layer for the digital labor market.</p></footer>')
    parts.append('</body>')
    parts.append('</html>')
    return ''.join(parts)


def render_party_form(values=None, errors=None, nav_view='door') -> str:
    """Add-a-party form: name, kind, form, payout email.
    A failed submission re-renders with values preserved and the
    problem fields marked (the form rule)."""
    values = values or {}
    errors = errors or {}
    parts = [
        '<!DOCTYPE html>',
        '<html lang="en">',
        '<head>',
        '<meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
        '<title>Add a Party - Bulwark</title>',
        f'<style>{CSS}</style>',
        '</head>',
        '<body>',
        '<div class="container">',
        _site_nav(nav_view),
        '<header>',
        '<h1>Add a Party</h1>',
        '<p>Parties are the named clients, workers and checkers of Bulwark. '
        'Every job names one of each, and each carries a public, '
        'ledger-derived reputation.</p>',
        '</header>',
        '<div class="form-container">',
        '<form id="partyForm" method="POST" action="/parties">',
    ]
    if errors:
        parts.append(_form_summary(errors))
    parts.append('<div class="form-group">')
    parts.append('<label for="name" class="required">Display Name</label>')
    parts.append('<input type="text" id="name" name="name" '
                 'placeholder="e.g., Acme Research (agent)" '
                 f'value="{_escape(str(values.get("name", "")))}"'
                 f'{_field_cls(errors, "name")} required>')
    parts.append(_field_msg(errors, 'name'))
    parts.append('</div>')
    parts.append('<div class="form-group">')
    parts.append('<label for="kind" class="required">Kind</label>')
    parts.append(f'<select id="kind" name="kind"'
                 f'{_field_cls(errors, "kind")} required>')
    for _v, _l in (('client', 'Client'), ('worker', 'Worker'),
                   ('checker', 'Checker')):
        _s = ' selected' if values.get('kind') == _v else ''
        parts.append(f'<option value="{_v}"{_s}>{_l}</option>')
    parts.append('</select>')
    parts.append(_field_msg(errors, 'kind'))
    parts.append('</div>')
    parts.append('<div class="form-group">')
    parts.append('<label for="form" class="required">Form</label>')
    parts.append(f'<select id="form" name="form"'
                 f'{_field_cls(errors, "form")} required>')
    for _v, _l in (('human', 'Human'), ('agent', 'Agent'),
                   ('company', 'Company')):
        _s = ' selected' if values.get('form') == _v else ''
        parts.append(f'<option value="{_v}"{_s}>{_l}</option>')
    parts.append('</select>')
    parts.append(_field_msg(errors, 'form'))
    parts.append('</div>')
    parts.append('<div class="form-group">')
    parts.append('<label for="payout_email">Payout Email (PayPal)</label>')
    parts.append('<input type="email" id="payout_email" name="payout_email" '
                 'placeholder="Optional - falls back to the platform default" '
                 f'value="{_escape(str(values.get("payout_email", "")))}">')
    parts.append('<span class="help-text">Where this party receives its '
                 'settlement payouts. Leave empty to use the default.</span>')
    parts.append('</div>')
    parts.append('<button type="submit" class="btn-primary">Add Party</button>')
    parts.append('</form>')
    if errors:
        parts.append(_SCROLL_TO_ERROR_JS)
    parts.append('</div>')
    parts.append('</div>')
    parts.append('</body>')
    parts.append('</html>')
    return ''.join(parts)


def render_evidence_pack(job: Job, verdicts=None, deliveries=None,
                         events=None, nav_view: str = 'door') -> str:
    """the printable evidence pack for a job — every fact a
    dispute (here or at PayPal) would need, on one page."""
    from app.db import get_party as _gp
    verdicts = verdicts or []
    deliveries = deliveries or []
    events = events or []
    cur = job.captured_currency or job.funded_currency or job.currency

    def party_line(label, pid):
        p = _gp(pid) if pid else None
        if not p:
            return f"<tr><td>{label}</td><td>—</td></tr>"
        return (f"<tr><td>{label}</td><td>{_escape(p.get('name', ''))} "
                f"(party #{p.get('id', '')}) &middot; payout: "
                f"{_escape(p.get('payout_email', '') or '—')}</td></tr>")

    rows = [
        f"<tr><td>Job</td><td>#{job.id} — {_escape(job.title)}</td></tr>",
        f"<tr><td>State</td><td>{_escape(job.state)}</td></tr>",
        f"<tr><td>Price</td><td>{_escape(_fmt_cents(job.price_cents, job.currency))}</td></tr>",
        party_line("Client", job.client_id),
        party_line("Worker", job.worker_id),
        party_line("Checker", job.checker_id),
    ]
    crit = "".join(
        f"<li>{_escape(c.name)} {_escape(c.operator)} "
        f"{_escape(c.expected_value)} ({_escape(c.criterion_type)})</li>"
        for c in (job.criteria or []))
    terms = ""
    if job.terms_verification_mode:
        terms = (
            f"<p>Verification: {_escape(job.terms_verification_mode)} "
            f"&middot; checker fee vesting: {job.terms_vesting_hours}h "
            f"&middot; trust credit: {job.terms_trust_credit_percent}% "
            f"&middot; worker stake: {job.terms_stake_percent}%<br>"
            f"Brain narrative: {_escape(job.brain_narrative)}<br>"
            f"Brain model: {_escape(job.brain_model)}"
            f"{' (degraded fallback)' if job.brain_degraded else ''}</p>")
    dels = "".join(
        f"<li>{_escape(d.filename)} — sha256 {_escape(d.sha256)} "
        f"({d.size_bytes} bytes, {_escape(_fmt_ts(d.uploaded_at))})</li>"
        for d in deliveries) or "<li>none</li>"
    vparts = []
    for v in verdicts:
        tag = (" — appeal" if v.get("is_appeal")
               else " — dispute re-check" if v.get("is_dispute") else "")
        items = (v.get("verdict") or {}).get("items") or []
        ilines = "".join(
            f"<li>{_escape(str(it.get('name', '')))}: "
            f"{'PASS' if it.get('passed') else 'FAIL'} — "
            f"{_escape(str(it.get('reason', '')))}</li>" for it in items)
        vparts.append(
            f"<h3>Verdict{tag} — "
            f"{'PASS' if v.get('overall_pass') else 'FAIL'} "
            f"({_escape(_fmt_ts(str(v.get('checked_at', ''))))}, model "
            f"{_escape(str(v.get('judged_model', '') or '—'))})</h3>"
            f"<ul>{ilines}</ul>")
    money = [
        ("Order", job.paypal_order_id), ("Authorization", job.paypal_authorization_id),
        ("Capture", job.capture_id), ("Advance capture", job.advance_capture_id),
        ("Settle payout batch", job.payout_batch_id),
        ("Advance payout batch", job.advance_batch_id),
        ("Checker vesting release batch", job.checker_released_batch_id),
        ("Refund / void", job.refund_id),
    ]
    mrows = "".join(f"<tr><td>{k}</td><td>{_escape(v or '—')}</td></tr>"
                    for k, v in money)
    items_rows = ""
    for it in (job.payout_items or []) + (job.advance_payout_items or []):
        items_rows += (
            f"<tr><td>{_escape(str(it.get('party', '')))}</td>"
            f"<td>{_escape(str(it.get('receiver', '')))}</td>"
            f"<td>{_escape(_fmt_cents(it.get('amount_cents', 0), cur))}</td>"
            f"<td>{_escape(str(it.get('status', '')))}</td>"
            f"<td>{_escape(str(it.get('payout_item_id', '')))}</td></tr>")
    vest = ""
    if job.checker_vesting_state:
        vest = (f"<p>Checker fee: "
                f"{_escape(_fmt_cents(job.checker_vesting_amount_cents, cur))} "
                f"— state {_escape(job.checker_vesting_state)}, release at "
                f"{_escape(job.checker_release_at or '—')}.</p>")
    disp = ""
    if job.dispute_state:
        disp = (f"<p>Dispute: {_escape(job.dispute_state)} &middot; opened "
                f"{_escape(_fmt_ts(job.dispute_opened_at) or '—')} &middot; resolved "
                f"{_escape(_fmt_ts(job.dispute_resolved_at) or '—')} &middot; reason: "
                f"{_escape(job.dispute_reason or '—')}</p>"
                "<p>Recovery ladder: step 1 (the unvested checker fee to "
                "the client) is executed in-app when a dispute overturns "
                "the verdict. Steps 2–3 are record-level: the worker's "
                "stake obligation under the job terms and the hand-off "
                "of this evidence pack to PayPal's dispute process are "
                "recorded here; the worker's paid share is not clawed "
                "back in-app.</p>")
    ev = "".join(
        f"<li>{_escape(_fmt_ts(str(e.get('created_at', ''))))} — "
        f"<strong>{_escape(str(e.get('kind', '')))}</strong> "
        f"({_escape(str(e.get('actor', '')))})</li>" for e in events)
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<title>Evidence pack — Job #{job.id} — Bulwark</title>
<style>{CSS}
table {{ border-collapse: collapse; margin: 12px 0; }}
td {{ border: 1px solid var(--border-color); padding: 6px 10px; }}
@media print {{ .container {{ max-width: none; }} }}
</style></head><body><div class="container">
{_site_nav(nav_view)}
<header><h1>Evidence pack</h1><p>Job #{job.id} — {_escape(job.title)}</p></header>
<p><a href="/job/{job.id}">&larr; back to the job</a></p>
<h2>Job and parties</h2><table>{''.join(rows)}</table>
<h2>Acceptance test</h2><ul>{crit}</ul>
<h2>Settlement Brain terms</h2>{terms or '<p>no terms recorded</p>'}
<h2>Deliveries</h2><ul>{dels}</ul>
<h2>Verdicts</h2>{''.join(vparts) or '<p>none</p>'}
<h2>Money identifiers (PayPal)</h2><table>{mrows}</table>
<h2>Payout items</h2><table>{items_rows or '<tr><td>none</td></tr>'}</table>
{vest}{disp}
<h2>Timeline</h2><ul>{ev}</ul>
</div></body></html>"""


def render_certificate(job: Job, cert, nav_view: str = 'door') -> str:
    """the birth certificate page — a premium D3 document."""
    f = cert.get("facts") or {}
    from app.db import get_party as _gp

    def pname(pid):
        p = _gp(pid) if pid else None
        return _escape(p.get("name", "")) if p else "—"

    verdict_txt = ("PASS" if f.get("verdict_pass") else "FAIL")
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<title>Certificate { _escape(cert.get('serial', '')) } — Bulwark</title>
<style>{CSS}
.cert-doc {{ border: 3px solid var(--deep-blue); border-radius: 16px;
  padding: 40px; margin: 24px 0; background: var(--white); }}
.cert-serial {{ font-size: 2rem; color: var(--deep-blue);
  letter-spacing: 2px; font-weight: 700; }}
.cert-code {{ font-family: monospace; font-size: 1.1rem; }}
</style></head><body><div class="container">
{_site_nav(nav_view)}
<header><h1>Bulwark — Birth Certificate</h1>
<p><a href="/job/{job.id}">&larr; back to the job</a></p></header>
<div class="cert-doc">
<div style="text-align:center;">
<div class="vault-figure"><div class="vault-circle left">C</div><div class="vault-circle overlap">O</div><div class="vault-circle right">W</div></div>
<div class="cert-serial">{_escape(cert.get('serial', ''))}</div>
<p>Proof of verified work and settled payment</p>
</div>
<table>
<tr><td>Job</td><td>#{job.id} — {_escape(job.title)}</td></tr>
<tr><td>Client</td><td>{pname(f.get('client_id'))}</td></tr>
<tr><td>Worker</td><td>{pname(f.get('worker_id'))}</td></tr>
<tr><td>Checker</td><td>{pname(f.get('checker_id'))}</td></tr>
<tr><td>Price</td><td>{_escape(_fmt_cents(f.get('price_cents', 0), f.get('currency', 'USD')))}</td></tr>
<tr><td>Acceptance verdict</td><td>{verdict_txt} &middot; model {_escape(str(f.get('judge_model', '') or '—'))}</td></tr>
<tr><td>PayPal order</td><td>{_escape(str(f.get('order_id', '') or '—'))}</td></tr>
<tr><td>PayPal capture</td><td>{_escape(str(f.get('capture_id', '') or '—'))}</td></tr>
<tr><td>Payout batch</td><td>{_escape(str(f.get('payout_batch_id', '') or '—'))}</td></tr>
<tr><td>Issued</td><td>{_escape(str(f.get('issued_at', '') or ''))}</td></tr>
</table>
<p style="text-align:center;">Verification code<br>
<span class="cert-code">{_escape(cert.get('code', ''))}</span></p>
<p style="text-align:center;">Verify this certificate at
<a href="/verify">/verify</a> with the serial and the code above.</p>
</div>
</div></body></html>"""


def render_verify_page(serial: str, code: str, result,
                        errors=None, nav_view='door') -> str:
    errors = errors or {}
    """public verification — genuine pair shows the recorded
    facts; anything else is a clear invalid with no facts leaked."""
    if result:
        f = result.get("facts") or {}
        body = f"""<div class="settlement-panel">
<h2>Genuine certificate</h2>
<p>Serial <strong>{_escape(result.get('serial', ''))}</strong> is
recorded in Bulwark's registry.</p>
<table>
<tr><td>Job</td><td>#{f.get('job_id', '')} — {_escape(str(f.get('title', '')))}</td></tr>
<tr><td>Price</td><td>{_escape(_fmt_cents(f.get('price_cents', 0), f.get('currency', 'USD')))}</td></tr>
<tr><td>Acceptance verdict</td><td>{'PASS' if f.get('verdict_pass') else 'FAIL'}</td></tr>
<tr><td>PayPal capture</td><td>{_escape(str(f.get('capture_id', '') or '—'))}</td></tr>
<tr><td>Issued</td><td>{_escape(str(f.get('issued_at', '') or ''))}</td></tr>
</table></div>"""
    elif result is False:
        body = """<div class="settlement-panel">
<h2>Not verified</h2>
<p>No genuine certificate matches that serial and code. Either the
serial is unknown or the code does not match the recorded facts —
nothing further can be shown.</p></div>"""
    else:
        body = ""
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<title>Verify a certificate — Bulwark</title>
<style>{CSS}</style></head><body><div class="container">
{_site_nav(nav_view)}
<header><h1>Verify a Bulwark certificate</h1></header>
{_form_summary(errors)}
<form method="GET" action="/verify">
<label>Serial <input type="text" name="serial" value="{_escape(serial)}"
 placeholder="BW-2026-0001"{_field_cls(errors, 'serial')}></label>
{_field_msg(errors, 'serial')}
<label>Verification code <input type="text" name="code"
 value="{_escape(code)}" placeholder="16 hex characters"{_field_cls(errors, 'code')}></label>
{_field_msg(errors, 'code')}
<button type="submit" class="btn-primary">Verify</button>
</form>
{body}
{_SCROLL_TO_ERROR_JS if errors else ''}
</div></body></html>"""


# ---------------------------------------------------------------------------
# money-state dashboard (AG Grid + server-rendered fallback)

_MONEY_STATES = [
    ("posted", "Posted"),
    ("funded-held", "Funded — held"),
    ("delivered", "Delivered"),
    ("checking", "Checking"),
    ("released", "Released"),
    ("refunded", "Refunded"),
]


def money_state_of(state: str):
    """Map a job's raw state to the dashboard money state (key, label).

    checked_pass / checked_fail / revision / settle_error group under
    "checking": the verdict is in, a revision is awaited, or settlement
    failed — and the money has not been released or refunded yet. disputed_overturned groups under
    "released": its settlement completed and the checker fee was
    redirected to the client by the dispute outcome.
    """
    if state == "posted":
        return ("posted", "Posted")
    if state == "funded":
        return ("funded-held", "Funded — held")
    if state == "delivered":
        return ("delivered", "Delivered")
    if state in ("checked_pass", "checked_fail", "revision", "settle_error"):
        return ("checking", "Checking")
    if state in ("settled", "disputed_overturned"):
        return ("released", "Released")
    if state == "refunded":
        return ("refunded", "Refunded")
    return ("posted", "Posted")


def render_dashboard(rows, totals, history=None, nav_view='client', view_note=None) -> str:
    """/dashboard — redesigned according to Design 4.0.

    rows: list of dicts prepared by the handler.
    totals: list of (key, label, count, total_cents) in _MONEY_STATES order.
    history: optional list of {ts, job_title, text, amount_cents} events.
    view_note: optional context note about whose eyes the list is shown.
    """
    # Compute the four totals per Design 4.0
    # Mapping: Held = 'funded-held' + 'delivered'; Being checked = 'checking';
    # Paid out = 'released'; Refunded = 'refunded'; 'posted' excluded.
    from collections import defaultdict
    held_total = 0
    checking_total = 0
    paid_out_total = 0
    refunded_total = 0
    
    held_count = 0
    checking_count = 0
    paid_out_count = 0
    refunded_count = 0
    
    for r in rows:
        key = r.get('money_state_key')
        amount = r.get('amount_in_state_cents', 0)
        if key in ('funded-held', 'delivered'):
            held_total += amount
            held_count += 1
        elif key == 'checking':
            checking_total += amount
            checking_count += 1
        elif key == 'released':
            paid_out_total += amount
            paid_out_count += 1
        elif key == 'refunded':
            refunded_total += amount
            refunded_count += 1
    
    held_formatted = _fmt_cents(held_total)
    checking_formatted = _fmt_cents(checking_total)
    paid_out_formatted = _fmt_cents(paid_out_total)
    refunded_formatted = _fmt_cents(refunded_total)
    
    parts = [
        '<!DOCTYPE html>',
        '<html lang="en">',
        '<head>',
        '<meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
        f'<title>Payments — Bulwark</title>',
        f'<style>{CSS}</style>',
        '</head>',
        '<body>',
        '<div class="container">',
        _site_nav(nav_view),
        '<header>',
        f'<h1>Payments</h1>',
        f'<p>{ "Hire any agent. Pay only for work that passes." if nav_view != "worker" else "Find work. Pass the check. Get paid." }</p>',
        f'<p>{ "Your money is held, the delivery is checked against your criteria, then released or refunded automatically." if nav_view != "worker" else "Every job below is open. Make an offer — when the client accepts it and funds the job, the money waits in the vault while you work." }</p>',
        f'<p>{view_note}</p>' if view_note else '',
        '</header>'
        '<div class="counters-grid">',
        f'<a href="/dashboard" class="counter-card"><div class="counter-value">{held_formatted}</div><div class="counter-label">Held</div><div class="counter-label">{held_count} job(s)</div></a>',
        f'<a href="/?state=checked" class="counter-card"><div class="counter-value">{checking_formatted}</div><div class="counter-label">Being checked</div><div class="counter-label">{checking_count} job(s)</div></a>',
        f'<a href="/?state=settled" class="counter-card"><div class="counter-value">{paid_out_formatted}</div><div class="counter-label">Paid out</div><div class="counter-label">{paid_out_count} job(s)</div></a>',
        f'<a href="/?state=refunded" class="counter-card"><div class="counter-value">{refunded_formatted}</div><div class="counter-label">Refunded</div><div class="counter-label">{refunded_count} job(s)</div></a>',
        '</div>',
    ]
    
    if view_note is not None and not rows:
        parts.append('<p>No payments for this view yet.</p>')
    
    # Group jobs by state
    grouped = defaultdict(list)
    for r in rows:
        grouped[r['money_state_key']].append(r)
    
    # Render each group
    def render_group(key, label, jobs_list):
        if not jobs_list:
            return ''
        parts.append(f'<h2>{label}</h2>')
        parts.append('<div class="job-group">')
        for r in jobs_list:
            parts.append(f'<div class="job-row"><a href="/job/{r["id"]}">{r["title"]}</a> — {r["client"]} / {r["worker"]} · {_fmt_cents(r["amount_in_state_cents"])}</div>')
        parts.append('</div>')
    
    render_group('funded-held', 'Held', grouped.get('funded-held', []) + grouped.get('delivered', []))
    render_group('checking', 'Being checked', grouped.get('checking', []))
    render_group('released', 'Paid out', grouped.get('released', []))
    render_group('refunded', 'Refunded', grouped.get('refunded', []))
    
    # Transaction history
    parts.append('<div class="timeline-section"><h2>Transaction history</h2>')
    if history:
        parts.append('<div class="timeline">')
        for entry in history:
            if entry.get('ts') and entry.get('text'):
                parts.append(f'<div class="timeline-entry"><span class="timeline-when">{_fmt_ts(entry["ts"])}</span><span class="timeline-kind">{entry["job_title"]}</span><span class="timeline-detail">{entry["text"]}</span>{f"<span class=\"timeline-amount\">{_fmt_cents(entry.get('amount_cents', 0))}</span>" if entry.get('amount_cents') else ""}</div>')
        parts.append('</div>')
    else:
        parts.append('<p>No transaction history yet.</p>')
    parts.append('</div>')
    
    parts.append('</div>')
    parts.append('<footer><p>Bulwark — settlement layer for the digital labor market.</p></footer>')
    parts.append('</body>')
    parts.append('</html>')
    return ''.join(parts)


# ---------------------------------------------------------------------------
# demo cast — guided demo UX

#: The funded step as the worker lives it: every delivery
#: way really is further down the page at the worker’s desk.
_FUNDED_STEP_WORKER = (
    "Funded — now you deliver the work, and every way is "
    "on this page, further down: the prepared file’s "
    "“Deliver the prepared file” button (one tap), the "
    "“Generate & deliver a sample” shortcut beside it, or "
    "the upload form below them, if you want to deliver a "
    "real file yourself.")


_DEMO_NEXT_STEP = {
    "posted": "Next step: the client funds the job — the price moves "
              "into the PayPal vault and the Settlement Brain sets "
              "the terms.",
    "funded": "Funded — the money sits in the PayPal vault. "
              "The next step is the worker’s: deliver the "
              "work against the acceptance test.",
    "delivered": "Next step: run the check — the Verifier AI "
                 "measures the delivery against the acceptance test, "
                 "in the open, item by item.",
    "checked_pass": "Next step: the client settles — the capture "
                    "runs and the money splits worker / checker / "
                    "platform.",
    "checked_fail": "Next step: the worker may revise the delivery "
                    "once and be re-checked, or the client rejects "
                    "and the vault refunds. (A FRAUD verdict skips "
                    "the revision and refunds at once.)",
    "settled": "Done — the money is split and the birth certificate "
               "is issued (rail step 6). The evidence pack holds the "
               "full record.",
    "refunded": "Done — the authorization was voided and the money "
                "went back to the client.",
    "settle_error": "Settlement hit an error — the page shows it, "
                    "and settling again resumes only the missing leg.",
    "disputed_overturned": "Done — a dispute overturned the verdict "
                           "and the checker fee went to the client.",
}


def _demo_role_line(job, actor, client_name, worker_name):
    if actor is None:
        return ("You have not picked a side yet — you are just looking. Pick "
                "‘I am here to hire’ or ‘I am here to work’ on the home page to "
                f"play this job from one side. On this job the client is "
                f"{_escape(client_name)} and the worker is {_escape(worker_name)}.")
    if actor.get("id") == job.client_id:
        return (f"You are the client now ({_escape(actor['name'])}). "
                "Your money funds the vault; you settle or reject "
                "at the end.")
    if actor.get("id") == job.worker_id:
        return (f"You are the worker now ({_escape(actor['name'])}). "
                "You deliver the material; the checker measures it "
                "against the test.")
    return (f"You are acting as {_escape(actor['name'])} — a "
            "bystander on this job. The client is "
            f"{_escape(client_name)}, the worker is "
            f"{_escape(worker_name)}.")


def render_demo_guide(job, actor, client_name, worker_name,
                      view=None) -> str:
    """The guided-demo caption box for a job page. For an active
    demo job: the visitor's current role + the next step, always.
    For any other funded job: the plain waiting-for-a-worker note,
    so a funded job never looks broken."""
    if job.demo_tag not in ("active", "phase"):
        if job.state == "funded":
            return ('<div class="info-banner">This job is funded '
                    'and waiting for its worker to deliver the '
                    'material.</div>')
        return ""

    # Next step: phase jobs speak from their negotiation
    # stage; other demo jobs keep the lifecycle text.
    if job.demo_tag == "phase":
        from app.db import list_offers as _list_offers
        offers = _list_offers(job.id)
        nxt = _phase_next_step(job, offers)
    else:
        nxt = _DEMO_NEXT_STEP.get(
            job.state, "Next step: follow the process rail at the top.")

    role = _demo_role_line(job, actor, client_name, worker_name)

    is_client = actor and actor.get("id") == job.client_id
    is_worker = actor and actor.get("id") == job.worker_id

    # Funded jobs: the step text follows the DESK you are at,
    # the same convention the page’s controls use — the
    # delivery ways really are on the page at the worker’s
    # desk and nowhere else. At the client’s desk the guide
    # keeps the neutral text (money in the vault, the
    # worker’s step is next): that desk holds no delivery
    # controls, and the guide must not pretend otherwise
    # (role split).
    at_worker_desk = (view == "worker")
    if job.state == "funded" and at_worker_desk:
        nxt = _FUNDED_STEP_WORKER

    # Step owner. Phase jobs: from the negotiation stage —
    # 'waiting' belongs to any worker, 'invited' to the
    # invited worker, the rest to the client. Other demo
    # jobs keep the lifecycle owners, unchanged.
    step_owner = None
    if job.demo_tag == "phase":
        stage = _negotiation_stage(job, offers)
        if stage == "waiting":
            step_owner = "any-worker"
        elif stage == "invited":
            step_owner = "invited-worker"
        elif stage in ("offers", "counter", "agreed"):
            step_owner = "client"
    elif job.state == "posted":
        step_owner = "client"
    elif job.state == "funded":
        step_owner = "worker"
    elif job.state == "delivered":
        step_owner = "check"
    elif job.state == "checked_pass":
        step_owner = "client"
    elif job.state == "checked_fail":
        step_owner = "both"

    # A phase job past its negotiation stage (funded and
    # beyond) has no stage, so it takes the lifecycle owner
    # like any other job — without this, the guide could
    # not say whose step is next on exactly the jobs a
    # visitor plays forward (found live, 2026-11-05).
    if step_owner is None:
        step_owner = {
            "posted": "client", "funded": "worker",
            "delivered": "check", "checked_pass": "client",
            "checked_fail": "both",
        }.get(job.state)

    needs_your_move = False
    if actor is not None and job.demo_tag == "phase":
        if step_owner == "client" and is_client:
            needs_your_move = True
        elif step_owner == "any-worker" and \
                actor.get("kind") == "worker":
            needs_your_move = True
        elif step_owner == "invited-worker" and \
                actor.get("id") in (job.invited_worker_id,
                                    job.worker_id):
            needs_your_move = True
    elif actor is not None and is_client and step_owner in ("client", "both"):
        needs_your_move = True
    elif actor is not None and is_worker and step_owner in ("worker", "both"):
        needs_your_move = True
    
    if not needs_your_move and actor is not None:
        if is_worker and step_owner in ("worker", "both"):
            needs_your_move = True
        elif is_client and step_owner in ("client", "both"):
            needs_your_move = True

    if needs_your_move and nxt.startswith("Next step: "):
        lead_in = "<strong>Your move — </strong>"
        step_text = nxt[len("Next step: "):]
        formatted_nxt = f"{lead_in}{_escape(step_text)}"
    elif needs_your_move:
        lead_in = "<strong>Your move — </strong>"
        formatted_nxt = f"{lead_in}{_escape(nxt)}"
    else:
        formatted_nxt = nxt
    
    # Closing lines: the guide always
    # offers the other side’s view of THIS job — that is
    # where a visitor switches sides, in place — and when
    # the next step belongs to the other side it says who we
    # are waiting for first. The way back leads to the board
    # the visitor is actually working from (client or worker
    # board), not the demo page: most visitors arrive from a
    # board, not from /demo.
    if step_owner == "client" and at_worker_desk:
        switch_line = (
            '<p>This is the client’s step, so from this side '
            'you are waiting on them. To play it yourself, '
            f'<a href="/job/{job.id}/as/client">switch to the '
            'client view of this job</a> and continue there.</p>')
    elif step_owner in ("worker", "any-worker", "invited-worker") \
            and not at_worker_desk:
        switch_line = (
            '<p>This is the worker’s step, so from this side '
            'you are waiting on them. To play it yourself, '
            f'<a href="/job/{job.id}/as/worker">switch to the '
            'worker view of this job</a> and continue there.</p>')
    else:
        other_view = "client" if at_worker_desk else "worker"
        switch_line = (
            '<p>To see this job from the other side, '
            f'<a href="/job/{job.id}/as/{other_view}">switch to '
            f'the {other_view} view of this job</a>.</p>')
    if at_worker_desk:
        back_line = '<a href="/w">Back to the worker board</a>'
    else:
        back_line = '<a href="/c">Back to the client board</a>'

    return ('<div class="brain-panel"><h2>Demo guide</h2>'
            f'<p>{role}</p><p>{formatted_nxt}</p>'
            f'{switch_line}'
            f'<p>{back_line}.</p></div>')


def render_demo_page(demo_parties, stories, jobs_map, actor,
                     history=None, seed_note=None, ready=None,
                     phase_jobs=None) -> str:
    """/demo — the three stories, the one-click role
    switcher, and a Reset that recreates the cast fresh."""
    parts = [
        '<!DOCTYPE html>',
        '<html lang="en">',
        '<head>',
        '<meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width, '
        'initial-scale=1.0">',
        '<title>Demo — Bulwark</title>',
        f'<style>{CSS}</style>',
        '<style>.story-card{border:2px solid var(--deep-blue);'
        'border-radius:12px;padding:18px;margin:18px 0;background:#fff;}'
        '.actor-btn{display:inline-block;margin:4px 6px 4px 0;'
        'padding:8px 14px;border-radius:20px;border:1px solid '
        'var(--deep-blue);color:var(--deep-blue);text-decoration:none;}'
        '.actor-btn.current{background:var(--deep-blue);color:#fff;'
        'font-weight:700;}'
        '.demo-shortcut{border:2px dashed var(--deep-blue);'
        'border-radius:12px;padding:18px;margin:18px 0;'
        'background:#f4f8ff;}'
        '.seat-current{border:3px solid var(--deep-blue);'
        'background:#e6f3ff;}'
        '.seat-card{border:1px solid #c9d6e3;border-radius:12px;'
        'padding:14px;margin:10px 0;}</style>',
        '</head>',
        '<body>',
        '<div class="container">',
        _site_nav('door'),
        '<div class="brain-panel" style="margin-bottom:20px;"><p><strong>Demo mode — not part of the product.</strong></p></div>',
        '<header>',
        '<h1>Bulwark Demo — three stories</h1>',
        '<p>Every story runs on the real flows: the same fund, '
        'deliver, check and settle buttons a customer uses. You play '
        'both sides — the captions on each job page always say which '
        'role you are in and what the next step is.</p>',
        '<p>There is no sign-in. Pick one of the two seats below '
        'and Bulwark behaves as if you were that participant — '
        'their steps appear on the jobs themselves.</p>',
        '</header>',
    ]
    
    # Pick your seat: the seat picker lives on this
    # page. Choosing a seat sets the guide cookie; the
    # chosen card shows the state straight back, with the
    # way onward for that seat.
    _seat_blurbs = {
        "Mira's Shop": "Posts jobs, funds them, accepts "
                       "offers and settles at the end.",
        "LinguaCert Agency": "Delivers the work \u2014 bids on "
                             "open jobs, accepts a listed "
                             "price or counter-offers.",
    }
    _seat_continue = {
        'client': ('/c', 'Continue to the jobs as the '
                         'client \u2192'),
        'worker': ('/w', 'Continue to the jobs as the '
                         'worker \u2192'),
    }
    parts.append('<div class="demo-entrances">')
    parts.append('<h2>Pick your seat</h2>')
    if actor is None:
        parts.append(
            '<p>You have not picked a seat yet \u2014 you are just '
            'looking around. Everything here is visible; pick '
            'a seat to play a job from one side.</p>')
    _cast = {"Mira's Shop", "LinguaCert Agency"}
    for party in demo_parties:
        _name = party['name']
        if _name not in _cast:
            continue
        _kind = party['kind']
        _is_current = actor is not None and \
            actor.get('id') == party['id']
        _cls = 'seat-card seat-current' if _is_current \
            else 'seat-card'
        parts.append(f'<div class="{_cls}">')
        parts.append(
            f'<p><strong>{_escape(_name)}</strong> \u2014 '
            f'the {_escape(_kind)}</p>')
        if _name in _seat_blurbs:
            parts.append(f'<p>{_seat_blurbs[_name]}</p>')
        if _is_current:
            parts.append(
                f'<p><strong>You are now: {_escape(_name)} '
                f'\u2014 {_escape(_kind)}.</strong></p>')
            if _kind in _seat_continue:
                _href, _label = _seat_continue[_kind]
                parts.append(
                    f'<p><a href="{_href}" '
                    f'class="btn-primary">{_label}</a></p>')
        else:
            parts.append(
                '<form method="POST" action="/demo/actor">'
                f'<input type="hidden" name="party_id" '
                f'value="{party["id"]}">'
                '<button type="submit">Sit in this '
                'seat</button></form>')
        parts.append('</div>')
    parts.append(
        '<p>Visiting the client or worker board seats you '
        'as that board\'s participant \u2014 that is the '
        'boards\' own rule. The acceptance check is not a '
        'seat: when a delivery lands, the check runs from '
        'the job page itself \u2014 rules plus the Verifier AI, '
        'with Verifier Prime standing as the checker of '
        'record.</p>')
    parts.append('</div>')

    # Reset. (flex with wrap — at phone width the note
    # takes its own row instead of overlapping the button; on
    # wide screens it sits beside the button as before.)
    parts.append(
        '<form method="POST" action="/demo/reset" '
        'style="margin:18px 0; display:flex; align-items:center; '
        'gap:12px; flex-wrap:wrap;">'
        '<button type="submit" class="btn-primary">Reset demo</button>'
        '<span style="flex:1 1 240px;">Recreates the three story '
        'jobs fresh in posted state; the previous run\'s demo jobs '
        'are archived (tagged DEMO, hidden from the board).</span>'
        '</form>')

    # Ready-made job: the judge-friendly trial path. Framed as what
    # it is — a demo convenience — with the manual path (post your
    # own job, upload a real file) pointed to right beside it.
    parts.append('<div class="demo-shortcut">')
    parts.append('<h2>Demo shortcut — post a ready-made job</h2>')
    parts.append(
        '<p>This button is a <strong>demo convenience, not part of '
        'the product</strong>: it posts one fully filled-in sample '
        'job so you can try the whole flow — fund, deliver, check, '
        'payout, certificate — in a couple of minutes, without '
        'inventing a job and a document first. To post a job of your '
        'own, the <a href="/post">post page</a> starts from one-click '
        'sample jobs — the form comes filled in and the prepared '
        'delivery is already attached, so there is nothing to '
        'download or upload — or a blank job with your own criteria '
        'and a real file upload.</p>')
    if ready is not None:
        # State-aware guidance: the panel must always name the
        # action that actually exists next — never "press Fund"
        # on a job that is already funded.
        from app.db import get_party as _gp_ready
        _wp = _gp_ready(ready.worker_id) if ready.worker_id else None
        _worker_name = _wp["name"] if _wp else "the worker"
        _next_step = {
            'posted': "Next step: open it and press Fund — that "
                      "puts the money into the vault.",
            'funded': "It is funded and waiting for the work — "
                      "and its prepared file is already attached. "
                      "Next step: open the job in the worker view "
                      "and press “Deliver the prepared file”. "
                      "One tap, no upload needed.",
            'delivered': "The sample work is already in. Next "
                         "step: open the job and run the "
                         "acceptance check.",
            'checked_pass': "It passed its acceptance check. "
                            "Next step: open the job and press "
                            "Settle — the money splits and the "
                            "certificate is issued.",
            'checked_fail': "Its acceptance check did not pass. "
                            "Open the job to see the verdict and "
                            "what happens next.",
            'settle_error': "Settlement was interrupted. Open "
                            "the job to review it and complete "
                            "the payout.",
        }.get(ready.state,
              "Open it to continue from where it stands.")
        parts.append(
            f'<p>Your ready-made job is already waiting: '
            f'<a href="/job/{ready.id}">{_escape(ready.title)}</a> '
            f'— {ready.formatted_price()} · state: '
            f'{_escape(_state_label(ready.state))}. {_next_step}</p>')
        parts.append(
            f'<p><a href="/job/{ready.id}" class="btn-primary">'
            'Open the ready-made job</a></p>')
    else:
        parts.append(
            '<form method="POST" action="/demo/ready-job">'
            '<button type="submit" class="btn-primary">Post a '
            'ready-made job</button></form>')
    parts.append('</div>')

    # Try the flow: the five phase jobs, one per
    # negotiation stage, in stage order — each with its
    # stage badge and the next step for that stage.
    if phase_jobs:
        from app.db import list_offers as _list_offers_flow
        parts.append('<div class="demo-shortcut">')
        parts.append('<h2>Try the flow — agreeing a price, '
                     'step by step</h2>')
        parts.append(
            '<p>Five ready-made jobs, one for each stage of '
            'agreeing a price. Open one and play its next '
            'step — each line says whose seat you need '
            '(pick it above).</p>')
        _by_stage = {}
        for _job in phase_jobs:
            _offers = _list_offers_flow(_job.id)
            _by_stage.setdefault(
                _negotiation_stage(_job, _offers),
                []).append((_job, _offers))
        for _stage in ('waiting', 'offers', 'invited',
                       'counter', 'agreed'):
            for _job, _offers in _by_stage.get(_stage, []):
                _price = _job.formatted_price() \
                    if _job.price_cents else 'no price yet'
                parts.append(
                    f'<p><strong>'
                    f'{_negotiation_label(_job, _offers)}'
                    f'</strong> — <a href="/job/{_job.id}">'
                    f'{_escape(_job.title)}</a> · {_price}'
                    f'<br>{_phase_next_step(_job, _offers)}'
                    '</p>')
        parts.append('</div>')

    # Seeded history: finished projects, played through the real
    # flows, so the board / parties / dashboard are not empty.
    if seed_note:
        parts.append('<div class="brain-panel"><h2>Demo history</h2>'
                     f'<p>{_escape(seed_note)}</p></div>')
    if history:
        parts.append('<div class="brain-panel"><h2>Finished '
                     'projects — real history</h2>')
        parts.append('<p>Played end-to-end through the same flows '
                     'as the stories: real PayPal authorizations, '
                     'checks, payouts and refunds. Open any of '
                     'them — every timeline entry and certificate '
                     'is genuine.</p>')
        for job in history:
            parts.append(
                f'<p><a href="/job/{job.id}">'
                f'{_escape(job.title)}</a> — '
                f'{job.formatted_price()} · state: '
                f'{_escape(_state_label(job.state))}</p>')
        parts.append('</div>')
    else:
        parts.append(
            '<form method="POST" action="/demo/seed-history" '
            'style="margin:18px 0;">'
            '<button type="submit" class="btn-primary">Seed demo '
            'history</button>'
            ' <span>Plays three finished projects through the '
            'real flows — two settle with certificates, one fails '
            'twice and refunds in full — so the board, the '
            'parties and the dashboard show real history. Takes '
            'about a minute; runs once.</span></form>')

    for story in stories:
        parts.append('<div class="story-card">')
        parts.append(f'<h2>{_escape(story["headline"])}</h2>')
        parts.append(f'<p>{_escape(story["blurb"])}</p>')
        jobs = jobs_map.get(story["key"], {})
        if not jobs:
            parts.append('<p><em>Not created yet — press Reset demo '
                         'above.</em></p>')
        from app.db import get_party
        
        for spec in story["jobs"]:
            job = jobs.get(spec["slot"])
            if job is None:
                continue
            nxt = _DEMO_NEXT_STEP.get(job.state, "")
            parts.append(
                f'<p><a href="/job/{job.id}">'
                f'{_escape(job.title)}</a> — '
                f'{job.formatted_price()} · state: '
                f'{_escape(_state_label(job.state))}</p>')
            if nxt:
                parts.append(f'<p>{_escape(nxt)}</p>')
            
            if actor is not None:
                client_party = get_party(job.client_id) if job.client_id else None
                worker_party = get_party(job.worker_id) if job.worker_id else None
                client_name = _escape(client_party["name"]) if client_party else ""
                worker_name = _escape(worker_party["name"]) if worker_party else ""
                
                is_client = actor.get("id") == job.client_id
                is_worker = actor.get("id") == job.worker_id
                
                if is_client:
                    if job.state == "posted":
                        role_line = f"Your part: you are the client ({client_name}) on this job — the next step above is yours."
                    elif job.state == "funded":
                        role_line = f"Your part: you are the client ({client_name}) on this job — the next step is the worker's."
                    elif job.state == "delivered":
                        role_line = f"Your part: you are the client ({client_name}) on this job — next, the check runs."
                    elif job.state == "checked_pass":
                        role_line = f"Your part: you are the client ({client_name}) on this job — the next step above is yours."
                    elif job.state == "checked_fail":
                        role_line = f"Your part: you are the client ({client_name}) on this job — the worker may revise, or you may reject."
                    elif job.state in ("settled", "refunded"):
                        role_line = f"Your part: you are the client ({client_name}) on this job — this one is finished."
                    else:
                        role_line = f"Your part: you are the client ({client_name}) on this job."
                elif is_worker:
                    if job.state == "posted":
                        role_line = f"Your part: you are the worker ({worker_name}) on this job — the next step is the client’s."
                    elif job.state == "funded":
                        role_line = f"Your part: you are the worker ({worker_name}) on this job — next step is yours."
                    elif job.state == "delivered":
                        role_line = f"Your part: you are the worker ({worker_name}) on this job — next, the check runs."
                    elif job.state == "checked_pass":
                        role_line = f"Your part: you are the worker ({worker_name}) on this job — the next step is the client’s."
                    elif job.state == "checked_fail":
                        role_line = f"Your part: you are the worker ({worker_name}) on this job — you may revise, or the client may reject."
                    elif job.state in ("settled", "refunded"):
                        role_line = f"Your part: you are the worker ({worker_name}) on this job — this one is finished."
                    else:
                        role_line = f"Your part: you are the worker ({worker_name}) on this job."
                else:
                    role_line = f"Your part: you are not a party on this job — the client is {client_name} and the worker is {worker_name}."
                
                parts.append(f'<p>{role_line}</p>')
            
            if job.state in ('posted', 'funded'):
                for fx in spec["fixtures"]:
                    parts.append(
                        f'<p>Delivery material: <a href="/demo/fixture/'
                        f'{_escape(fx)}">{_escape(fx)}</a> — download it, '
                        'then upload it on the job page as the worker.</p>')
        parts.append('</div>')
    parts.append('</div>')
    parts.append(
        '<footer><p>Bulwark — settlement layer for the digital labor '
        'market.</p></footer>')
    parts.append('</body>')
    parts.append('</html>')
    return ''.join(parts)


def render_client_view(party, jobs, jobs_by_stage, certificates,
                      counters, certificates_for_worker, switcher_list, nav_view='client') -> str:
    """Render the client view page.
    
    Job stages (always in order):
    1. 'posted' -> "Posted — waiting to be funded"
    2. 'funded' -> "Funded — money waiting in the vault"  
    3. 'delivered' -> "Delivered — ready to check"
    4. 'checked_pass' -> "Checked — passed"
    5. 'checked_fail' and 'revision' -> "Checked — did not pass"
    6. 'settled' -> "Settled — paid out" + certificate + vesting line if applicable
    7. 'refunded' -> "Refunded"
    """
    parts = [
        '<!DOCTYPE html>',
        '<html lang="en">',
        '<head>',
        '<meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width, '
        'initial-scale=1.0">',
        f'<title>Client view — {party["name"]} — Bulwark</title>',
        f'<style>{CSS}</style>',
        '</head>',
        '<body>',
        '<div class="container">',
        _site_nav(nav_view),

    ]
    
    # Header block
    parts.append('<div class="view-header">')
    parts.append('<h1>Bulwark as the client</h1>')
    parts.append(f'<p>You are sitting in the seat of {party["name"]}.</p>')
    parts.append('<p>This is what the person paying sees: the job goes out with its acceptance test fixed, the money waits in the vault, and it only moves when the work is proven.</p>')
    
    # Seat switcher
    parts.append('<div class="seat-switcher">')
    parts.append('<p>Sit in another seat:</p>')
    for p in switcher_list:
        if p['id'] == party['id']:
            parts.append(f'<span class="current">{_escape(p["name"])}</span>')
    parts.append('</div>')
    
    # Cross-links
    parts.append('<div class="view-links">')
    parts.append('<a href="/">The shared board — every job, from no one\'s seat</a>')
    parts.append('<a href="/demo">Back to the demo guide</a>')
    parts.append('</div>')
    parts.append('</div>')
    
    # Workflow strip (static)
    parts.append('<div class="workflow-strip">')
    parts.append('<h2>Process</h2>')
    parts.append('<div class="process-steps">')
    for step in [
        ("Post the job — test fixed first", "Posted"),
        ("Fund the vault", "Funded"),
        ("The delivery arrives", "Delivered"),
        ("Read the check", "Checked"),
        ("Settle", "Settled"),
        ("Certificate", "Certificate")
    ]:
        parts.append(f'<div class="process-step">{step[0]} — {step[1]}</div>')
    parts.append('</div>')
    parts.append('</div>')
    
    # Stage sections ('revision' jobs belong to the did-not-pass stage)
    _KNOWN_STAGES = ['posted', 'funded', 'delivered', 'checked_pass',
                     'checked_fail', 'settled', 'refunded']
    for stage in _KNOWN_STAGES:
        parts.append(f'<div class="stage-section">')
        parts.append(f'<h2>{_get_client_stage_title(stage)}</h2>')
        stage_jobs = list(jobs_by_stage.get(stage, []))
        if stage == 'checked_fail':
            stage_jobs += jobs_by_stage.get('revision', [])
        if stage_jobs:
            for job in stage_jobs:
                parts.append(_render_client_job_card(job, party, certificates.get(job.id)))
        else:
            parts.append('<p>Nothing here right now.</p>')
        parts.append('</div>')

    # Any other state -> needs attention
    other_jobs = [j for j in jobs if j.state not in _KNOWN_STAGES + ['revision']]
    if other_jobs:
        parts.append('<div class="stage-section">')
        parts.append('<h2>Needs attention</h2>')
        parts.append('<p>Open the job to see what is needed.</p>')
        for j in other_jobs:
            parts.append(_render_client_job_card(j, party, certificates.get(j.id)))
        parts.append('</div>')
    
    parts.append('</div>')
    parts.append(
        '<footer><p>Bulwark — settlement layer for the digital labor market.</p></footer>'
    )
    parts.append('</body>')
    parts.append('</html>')
    return ''.join(parts)


def render_worker_view(party, jobs, jobs_by_stage, certificates,
                      counters, certificates_for_worker, switcher_list, nav_view='worker') -> str:
    """Render the worker view page.
    
    Job stages (always in order):
    1. 'posted' -> "Work waiting for you"
    2. 'funded' -> "Funded — the money is already in the vault"
    3. 'delivered' -> "Delivered — with the checker"
    4. 'checked_pass' -> "Checked — passed"
    5. 'checked_fail' and 'revision' -> "Checked — did not pass"
    6. 'settled' -> "Paid" + certificate
    7. 'refunded' -> "Refunded — no payment"
    """
    parts = [
        '<!DOCTYPE html>',
        '<html lang="en">',
        '<head>',
        '<meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width, '
        'initial-scale=1.0">',
        f'<title>Worker view — {party["name"]} — Bulwark</title>',
        f'<style>{CSS}</style>',
        '</head>',
        '<body>',
        '<div class="container">',
        _site_nav(nav_view),

    ]
    
    # Header block
    parts.append('<div class="view-header">')
    parts.append('<h1>Bulwark as the worker</h1>')
    parts.append(f'<p>You are sitting in the seat of {party["name"]}.</p>')
    parts.append('<p>This is what the person working sees: the money is already in the vault before the work starts, an independent checker measures the delivery, and a clean record wins the next job.</p>')
    
    # Seat switcher
    parts.append('<div class="seat-switcher">')
    parts.append('<p>Sit in another seat:</p>')
    for p in switcher_list:
        if p['id'] == party['id']:
            parts.append(f'<span class="current">{_escape(p["name"])}</span>')
    parts.append('</div>')
    
    # Cross-links
    parts.append('<div class="view-links">')
    parts.append('<a href="/">The shared board — every job, from no one\'s seat</a>')
    parts.append('<a href="/demo">Back to the demo guide</a>')
    parts.append('</div>')
    parts.append('</div>')
    
    # Workflow strip (static)
    parts.append('<div class="workflow-strip">')
    parts.append('<h2>Process</h2>')
    parts.append('<div class="process-steps">')
    for step in [
        ("Take the job", "Posted"),
        ("See the money held", "Funded"),
        ("Deliver", "Delivered"),
        ("The checker measures it", "Checked"),
        ("Get paid", "Settled"),
        ("Your record grows", "Certificate")
    ]:
        parts.append(f'<div class="process-step">{step[0]} — {step[1]}</div>')
    parts.append('</div>')
    parts.append('</div>')
    
    # Record block — the same counters, labels and figures as the
    # party's public profile (render_party_page), plus its
    # certifications and the proof certificates it has earned.
    parts.append('<div class="record-block">')
    parts.append('<h2>Your record</h2>')
    parts.append('<div class="counters-grid">')
    parts.append(f'<div class="counter-card"><div class="counter-value">{counters["jobs_posted"] + counters["jobs_delivered"] + counters["verdict_issued"] + counters["job_settled"]}</div><div class="counter-label">Jobs Completed</div></div>')
    parts.append(f'<div class="counter-card"><div class="counter-value">{counters["verdict_pass_first"]}</div><div class="counter-label">First Verdicts Passed</div></div>')
    parts.append(f'<div class="counter-card"><div class="counter-value">{counters["verdict_fail_first"]}</div><div class="counter-label">First Verdicts Failed</div></div>')
    parts.append(f'<div class="counter-card"><div class="counter-value">{counters["verdict_issued"]}</div><div class="counter-label">Verdicts Issued</div></div>')
    parts.append(f'<div class="counter-card"><div class="counter-value">{"Yes" if counters["fraud_flags"] else "No"}</div><div class="counter-label">Fraud Flags</div></div>')
    parts.append(f'<div class="counter-card"><div class="counter-value">{counters["verdicts_overturned"]}</div><div class="counter-label">Verdicts Overturned</div></div>')
    parts.append(f'<div class="counter-card"><div class="counter-value">{counters["verdicts_upheld"]}</div><div class="counter-label">Verdicts Upheld</div></div>')
    parts.append('</div>')
    _certifications = party.get("certifications") or []
    if _certifications:
        parts.append('<div class="cert-chips">')
        for _cert in _certifications:
            parts.append(
                f'<span class="cert-chip">&#127891; '
                f'{_escape(str(_cert))}</span>')
        parts.append('</div>')
    if certificates_for_worker:
        parts.append('<h3>Certificates earned</h3>')
        parts.append('<ul>')
        for _c in certificates_for_worker:
            _f = _c.get("facts") or {}
            parts.append(
                f'<li><a href="/job/{_c["job_id"]}/certificate">'
                f'{_escape(_c["serial"])}</a> — job #{_c["job_id"]} '
                f'({_escape(str(_f.get("title", "")))}) &middot; '
                f'{_escape(str(_c["issued_at"])[:10])}</li>')
        parts.append('</ul>')
    parts.append(f'<p>A clean record is what wins the next job — and it is what the Settlement Brain reads when it sets the terms of your next engagement.</p>')
    parts.append('</div>')
    
    # Stage sections ('revision' jobs belong to the did-not-pass stage)
    _KNOWN_STAGES = ['posted', 'funded', 'delivered', 'checked_pass',
                     'checked_fail', 'settled', 'refunded']
    for stage in _KNOWN_STAGES:
        parts.append(f'<div class="stage-section">')
        parts.append(f'<h2>{_get_worker_stage_title(stage)}</h2>')
        stage_jobs = list(jobs_by_stage.get(stage, []))
        if stage == 'checked_fail':
            stage_jobs += jobs_by_stage.get('revision', [])
        if stage_jobs:
            for job in stage_jobs:
                parts.append(_render_worker_job_card(job, party, certificates.get(job.id)))
        else:
            parts.append('<p>Nothing here right now.</p>')
        parts.append('</div>')

    # Any other state -> needs attention
    other_jobs = [j for j in jobs if j.state not in _KNOWN_STAGES + ['revision']]
    if other_jobs:
        parts.append('<div class="stage-section">')
        parts.append('<h2>Needs attention</h2>')
        parts.append('<p>Open the job to see what is needed.</p>')
        for j in other_jobs:
            parts.append(_render_worker_job_card(j, party, certificates.get(j.id)))
        parts.append('</div>')
    
    parts.append('</div>')
    parts.append(
        '<footer><p>Bulwark — settlement layer for the digital labor market.</p></footer>'
    )
    parts.append('</body>')
    parts.append('</html>')
    return ''.join(parts)


def render_machine_view(job, calls, nav_view='client') -> str:
    """the integrator machine view — one job's service-call
    stream (API + UI actions) in call order."""
    parts = [
        '<!DOCTYPE html>',
        '<html lang="en">',
        '<head>',
        '<meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width, '
        'initial-scale=1.0">',
        f'<title>Machine view — Job #{job.id} — Bulwark</title>',
        f'<style>{CSS}</style>',
        '</head>',
        '<body>',
        '<div class="container">',
        _site_nav(nav_view),
        _render_process_rail(1, job.state),
        '<div class="job-detail-container">',
        '<div class="detail-header">',
        f'<div class="detail-title">Machine view — '
        f'{_escape(job.title)}</div>',
        f'<div class="detail-price">{job.formatted_price()}</div>',
        '</div>',
        '<div class="job-body">',
        '<p>Every service call recorded for this job, in order — '
        'API calls and UI actions in one stream: who called, through '
        'which channel, what happened, and which PayPal ids were '
        'touched. This is what an integrating partner sees.</p>',
        f'<p>Current state: <strong>{_escape(job.state)}</strong> '
        f'&middot; <a href="/job/{job.id}">Human view</a></p>',
    ]
    if not calls:
        parts.append('<p>No service calls recorded for this job '
                     'yet.</p>')
    else:
        parts.append('<table class="machine-table">')
        parts.append(
            '<thead><tr><th>#</th><th>Time (UTC)</th><th>Actor</th>'
            '<th>Via</th><th>Action</th><th>Endpoint</th>'
            '<th>Status</th><th>Request summary</th>'
            '<th>PayPal ids</th></tr></thead><tbody>')
        for i, c in enumerate(calls, 1):
            parts.append(
                '<tr>'
                f'<td>{i}</td>'
                f'<td>{_escape(str(c["created_at"])[:19])}</td>'
                f'<td>{_escape(c["actor"])}</td>'
                f'<td>{_escape(c["via"])}</td>'
                f'<td>{_escape(c["action"])}</td>'
                f'<td><code>{_escape(c["endpoint"])}</code></td>'
                f'<td>{c["response_status"]}</td>'
                f'<td>{_escape(c["request_summary"])}</td>'
                f'<td><code>{_escape(c["paypal_ids"])}</code></td>'
                '</tr>')
        parts.append('</tbody></table>')
    parts.append('</div></div>')
    parts.append(
        '<footer><p>Bulwark — settlement layer for the digital labor '\
        'market.</p></footer>')
    parts.append('</body>')
    parts.append('</html>')
    return ''.join(parts)


def render_entry(held: int = 0, checking: int = 0, paid_out: int = 0, refunded: int = 0,
                 latest_certificate=None, nav_view='door') -> str:
    """the entry page (door) — door nav, header, chooser, counters grid,
    latest certificate card, footer lines. NO job list, NO rails, NO chips, NO job pages.
    """
    # Door nav
    nav = _site_nav(nav_view)
    
    # Choose text for door header
    if nav_view == 'door':
        header_title = "Bulwark"
        header_sub1 = "Hire any agent. Pay only for work that passes."
        header_sub2 = "Your money is held, the delivery is checked against your criteria, then released or refunded automatically."
    elif nav_view == 'client':
        header_title = "Jobs"
        header_sub1 = "Find your next project. Fund it, get it done."
        header_sub2 = "All jobs are vetted — just pick yours and fund it."
    elif nav_view == 'worker':
        header_title = "Browse jobs"
        header_sub1 = "Find work. Pass the check. Get paid."
        header_sub2 = "Every job below is open. Make an offer — when the client accepts it and funds the job, the money waits in the vault while you work."
    else:
        header_title = "Bulwark"
        header_sub1 = "Hire any agent. Pay only for work that passes."
        header_sub2 = "Your money is held, the delivery is checked against your criteria, then released or refunded automatically."
    
    # Entry chooser
    chooser = (
        '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px;margin:6px 0 26px">'
        '<a href="/c" style="text-decoration:none"><div class="counter-card" style="text-align:left;padding:22px">'
        '<div style="font-size:1.15rem;font-weight:700;color:var(--deep-blue)">I am here to hire</div>'
        '<p style="margin-top:6px">Post a job, fund it, and pay only for work that passes the check.</p>'
        '<div style="margin-top:10px;font-weight:600;color:var(--deep-blue)">Client view &rarr;</div></div></a>'
        '<a href="/w" style="text-decoration:none"><div class="counter-card" style="text-align:left;padding:22px">'
        '<div style="font-size:1.15rem;font-weight:700;color:var(--deep-blue)">I am here to work</div>'
        '<p style="margin-top:6px">Browse open jobs, make an offer, and get paid when your work passes.</p>'
        '<div style="margin-top:10px;font-weight:600;color:var(--deep-blue)">Worker view &rarr;</div></div></a></div>'
    )
    
    parts = [
        '<!DOCTYPE html>',
        '<html lang="en">',
        '<head>',
        '<meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
        f'<title>Entry — Bulwark</title>',
        f'<style>{CSS}</style>',
        '</head>',
        '<body>',
        '<div class="container">',
        nav,
        '<header>',
        f'<h1>{header_title}</h1>',
        f'<p>{header_sub1}</p>',
        f'<p>{header_sub2}</p>',
        '</header>',
        chooser,
        '<div class="counters-grid">',
        f'<a href="/dashboard" class="counter-card"><div class="counter-value">{_fmt_cents(held)}</div><div class="counter-label">Held</div></a>',
        f'<a href="/dashboard" class="counter-card"><div class="counter-value">{_fmt_cents(checking)}</div><div class="counter-label">Being checked</div></a>',
        f'<a href="/dashboard" class="counter-card"><div class="counter-value">{_fmt_cents(paid_out)}</div><div class="counter-label">Paid out</div></a>',
        f'<a href="/dashboard" class="counter-card"><div class="counter-value">{_fmt_cents(refunded)}</div><div class="counter-label">Refunded</div></a>',
        '</div>',
    ]
    if latest_certificate:
        job_title = latest_certificate.get('job_title') or 'Latest certificate'
        worker_name = latest_certificate.get('worker_name') or ''
        parts.append(
            '<a href="/certificates" class="counter-card" style="display:block;text-align:left;margin-top:16px">'
            '<div style="font-weight:700;color:var(--deep-blue)">Latest certificate</div>'
            f'<p style="margin-top:4px">{_escape(job_title)} — work by {_escape(worker_name)}, checked and settled.</p></a>')
    parts += [
        '<footer>',
        '<p>Money is held via PayPal until the check passes. · Agents and people both work here.</p>',
        '</footer>',
        '</div>',
        '</body>',
        '</html>'
    ]
    return ''.join(parts)
