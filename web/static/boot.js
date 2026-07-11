/**
 * Bootstrap: capture the auth token from the URL before app.js runs.
 *
 * Lives in a static file (not an inline <script>) so the CSP can drop
 * 'unsafe-inline' from script-src (DAR2-34 hardening). The token stays in
 * the query string for this release; header/cookie transport is Phase 5.
 */

'use strict';

window.APP_TOKEN = new URLSearchParams(location.search).get('token');
