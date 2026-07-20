/**
 * Bootstrap: capture the auth token from the URL before app.js runs.
 *
 * Lives in a static file (not an inline <script>) so the CSP can drop
 * 'unsafe-inline' from script-src (DAR2-34 hardening). The token stays in
 * the query string for this release; header/cookie transport is Phase 5.
 */

'use strict';

window.APP_TOKEN = new URLSearchParams(location.search).get('token');

// Material init must run pre-paint (this file loads in <head>) so the page
// never flashes the wrong theme. 'desk' = light paper, 'night' = After Hours.
(function initTheme() {
  var stored = null;
  try { stored = localStorage.getItem('darin-theme'); } catch (e) { /* private mode */ }
  var theme = stored === 'desk' || stored === 'night'
    ? stored
    : (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches
        ? 'night' : 'desk');
  document.documentElement.dataset.theme = theme;
})();
