'use strict';

/* Lathar Labs - customer meeting workspace.
 *
 * Contract (owned by the backend; this file invents no new endpoints):
 *   GET  /auth/session  -> { authenticated: true, csrf: string }
 *   GET  /api/review    -> { meetings: [...], operations: boolean,
 *                            live_effects: boolean, csrf: string }
 *   POST /api/operate   JSON + X-Labs-CSRF, actions: create, sync, leave,
 *                        approve, execute, reconcile (queued chat only)
 *   POST /auth/logout   {} + X-Labs-CSRF, then location.assign('/')
 *
 * Safety rules enforced here:
 * - All server/user data is rendered as text nodes only. There is no
 *   markup-string injection, no dynamic code evaluation, and no external
 *   script or font.
 * - No browser storage and no auth-token storage. The CSRF value lives
 *   only in a module variable for the life of this page.
 * - All cookies are HttpOnly and every fetch uses credentials: 'same-origin'.
 * - No polling and no automatic retry. Refresh is a manual button.
 * - A 401 redirects to '/' once. Errors shown to the user are fixed generic
 *   strings, never raw exception text from a response.
 * - Statuses are labelled honestly: submitted is a join request, not
 *   admitted; queued is not posted; sent is not delivered; unknown is
 *   never retried automatically.
 * - AI notes and delivery are not enabled for customers yet, so this file
 *   renders no AI-notes or delivery buttons. AI notes are shown read-only
 *   only if the server returns them.
 */

var MEET_LINK = /^https:\/\/meet\.google\.com\/[a-z]{3}-[a-z]{4}-[a-z]{3}$/;
var GENERIC_LOAD_ERROR = 'Could not load your workspace. Check your connection and try again.';
var GENERIC_OPERATION_ERROR = 'Operation did not complete. Check the current review state before trying again. Uncertain sends must be reconciled, never retried automatically.';

var csrf = null;
var meetings = [];
var selectedId = null;
var tab = 'notes';
var operations = false;
var liveEffects = false;
var redirecting = false;
var mutationBusy = false;

function $(id) { return document.getElementById(id); }

function el(tag, cls, text) {
  var n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined && text !== null) n.textContent = text;
  return n;
}

function isObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function asArray(value) {
  return Array.isArray(value) ? value : [];
}

function asText(value) {
  if (typeof value === 'string') return value;
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  return '';
}

function stamp(seconds) {
  if (typeof seconds !== 'number' || !Number.isFinite(seconds) || seconds < 0) return '-';
  var total = Math.floor(seconds);
  var minutes = Math.floor(total / 60);
  var secs = total % 60;
  return (minutes < 10 ? '0' + minutes : '' + minutes) + ':' + (secs < 10 ? '0' + secs : '' + secs);
}

function formatCreated(value) {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return new Date(value * 1000).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
  }
  if (typeof value === 'string' && value) {
    var parsed = new Date(value);
    if (!Number.isNaN(parsed.getTime())) return parsed.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
    return value;
  }
  return 'Date not recorded';
}

function kindLabel(kind) {
  var labels = {
    join: 'Join this meeting as the visible notes bot',
    leave: 'Leave this meeting',
    chat: 'Post this answer in meeting chat',
    email: 'Send these meeting notes by email',
    whatsapp: 'Send these meeting notes on WhatsApp'
  };
  return labels[kind] || 'Review action';
}

/* Honest status wording. Never present a request as a completed effect. */
function statusMeaning(status) {
  var map = {
    local: { label: 'Staged - not joined', tone: '' },
    draft: { label: 'Draft - not sent', tone: '' },
    approved: { label: 'Approved - not sent', tone: 'mint' },
    stale: { label: 'Stale - review again', tone: 'alert' },
    superseded: { label: 'Superseded', tone: '' },
    submitted: { label: 'Join requested - not admitted', tone: '' },
    sending: { label: 'Sending - check status', tone: '' },
    queued: { label: 'Queued - not posted', tone: '' },
    sent: { label: 'Sent - not confirmed delivered', tone: 'mint' },
    accepted: { label: 'Accepted by provider - not delivered', tone: 'mint' },
    posted: { label: 'Posted', tone: 'mint' },
    failed: { label: 'Failed', tone: 'alert' },
    unknown: { label: 'Unknown - do not retry', tone: 'alert' }
  };
  return map[status] || { label: asText(status) || 'Status not recorded', tone: '' };
}

function redirectToLanding() {
  if (redirecting) return;
  redirecting = true;
  window.location.assign('/');
}

function setStatus(text) {
  $('status').textContent = text || '';
}

function showError() {
  $('error').hidden = false;
}

function hideError() {
  $('error').hidden = true;
}

function unauthenticatedError() {
  var error = new Error('Unauthenticated');
  error.name = 'Unauthenticated';
  return error;
}

async function apiJson(path, options) {
  var response = await fetch(path, options || {});
  if (response.status === 401) throw unauthenticatedError();
  var data = null;
  try { data = await response.json(); } catch (e) { data = null; }
  if (!response.ok) throw new Error('Request failed');
  return data;
}

async function loadSession() {
  var data = await apiJson('/auth/session', { credentials: 'same-origin', headers: { Accept: 'application/json' } });
  if (!isObject(data) || data.authenticated !== true) throw unauthenticatedError();
  if (typeof data.csrf === 'string' && data.csrf) csrf = data.csrf;
}

async function loadReview() {
  var data = await apiJson('/api/review', { credentials: 'same-origin', headers: { Accept: 'application/json' } });
  if (!isObject(data) || !Array.isArray(data.meetings)) throw new Error('Invalid review data');
  if (typeof data.csrf === 'string' && data.csrf) csrf = data.csrf;
  operations = data.operations === true;
  liveEffects = data.live_effects === true;
  meetings = data.meetings;
  var previous = selectedId;
  var selected = meetings.find(function (m) { return isObject(m) && m.id === previous; }) || meetings[0] || null;
  selectedId = selected ? selected.id : null;
  render();
}

function selectedMeeting() {
  if (!selectedId) return null;
  return meetings.find(function (m) { return isObject(m) && m.id === selectedId; }) || null;
}

function renderNotices() {
  var liveNotice = $('live-notice');
  if (!liveEffects) {
    liveNotice.hidden = false;
    liveNotice.replaceChildren();
    liveNotice.appendChild(el('strong', null, 'Live operations are disabled.'));
    liveNotice.appendChild(document.createTextNode(' Approvals do not join, post, or send anything.'));
  } else {
    liveNotice.hidden = true;
    liveNotice.replaceChildren();
  }
  var opsNotice = $('ops-notice');
  if (!operations) {
    opsNotice.hidden = false;
    opsNotice.replaceChildren();
    opsNotice.appendChild(el('strong', null, 'Operations are disabled for this account.'));
    opsNotice.appendChild(document.createTextNode(' You can read your meetings, but you cannot create, approve, or execute anything.'));
  } else {
    opsNotice.hidden = true;
    opsNotice.replaceChildren();
  }
}

function renderList() {
  var list = $('meeting-list');
  list.replaceChildren();
  var count = $('meeting-count');
  count.textContent = meetings.length === 1 ? '1 meeting' : meetings.length + ' meetings';
  var empty = $('meetings-empty');
  empty.hidden = meetings.length !== 0;
  meetings.forEach(function (meeting) {
    var item = el('li');
    var button = el('button', 'meeting-item' + (meeting.id === selectedId ? ' selected' : ''));
    button.type = 'button';
    if (meeting.id === selectedId) button.setAttribute('aria-current', 'true');
    var title = el('span', 'meeting-item-title', asText(meeting.title) || 'Untitled meeting');
    var meta = el('span', 'meeting-item-meta');
    meta.appendChild(el('span', null, 'meet.google.com/' + asText(meeting.code)));
    var meaning = statusMeaning(meeting.status);
    var tag = el('span', 'tag' + (meaning.tone ? ' ' + meaning.tone : ''), meaning.label);
    meta.appendChild(tag);
    meta.appendChild(el('span', null, formatCreated(meeting.created)));
    button.appendChild(title);
    button.appendChild(meta);
    button.addEventListener('click', function () {
      selectedId = meeting.id;
      renderList();
      renderDetail();
    });
    item.appendChild(button);
    list.appendChild(item);
  });
}

function quoteNode(item) {
  var node = el('div', 'quote', asText(item.quote));
  var detail = asText(item.speaker) + ' · ' + stamp(item.start);
  node.appendChild(el('small', null, detail));
  if (item.evidence) node.appendChild(el('span', 'evidence', 'Source ' + asText(item.evidence)));
  return node;
}

function notesCard(label, title, rows, hint) {
  var card = el('article', 'card');
  if (label) card.appendChild(el('div', 'label', label));
  card.appendChild(el('h3', null, title));
  if (rows.length === 0) {
    card.appendChild(el('p', 'hint', 'None identified in confirmed notes.'));
  } else {
    rows.forEach(function (row) { card.appendChild(quoteNode(row)); });
  }
  if (hint) card.appendChild(el('p', 'hint', hint));
  return card;
}

function renderNotes(meeting) {
  var panel = $('panel-notes');
  panel.replaceChildren();
  var notes = isObject(meeting.notes) ? meeting.notes : null;
  if (!notes) {
    panel.appendChild(el('p', 'hint', 'No notes yet. Notes appear after the transcript is confirmed.'));
  } else {
    var layout = el('div', 'notes-layout');
    layout.appendChild(notesCard('', 'Conversation highlights', asArray(notes.summary), 'Extractive notes, not a full AI summary.'));
    layout.appendChild(notesCard('', 'Possible decisions', asArray(notes.decision_candidates), 'These quotes are candidates. Confirm what was actually decided.'));
    layout.appendChild(notesCard('', 'Possible tasks', asArray(notes.action_candidates), 'Owner and deadline: not set. No assignments have been created.'));
    panel.appendChild(layout);
  }
  var ai = isObject(meeting.ai_notes) ? meeting.ai_notes : null;
  if (ai) {
    var section = el('section', 'notes-section');
    section.appendChild(el('h3', null, 'AI notes'));
    var groups = [['summary', 'AI summary'], ['decisions', 'Possible decisions'], ['actions', 'Possible tasks']];
    groups.forEach(function (group) {
      var key = group[0];
      var heading = group[1];
      var items = asArray(ai[key]);
      if (items.length === 0) return;
      section.appendChild(el('h3', null, heading));
      items.forEach(function (item) {
        var node = el('div', 'quote', asText(item.text));
        asArray(item.citations).forEach(function (citation) {
          var details = el('details', 'citation');
          details.appendChild(el('summary', null, 'Source ' + asText(citation.id)));
          details.appendChild(el('p', null, asText(citation.quote)));
          node.appendChild(details);
        });
        section.appendChild(node);
      });
    });
    section.appendChild(el('p', 'hint', 'AI draft. Check the cited words before sharing.'));
    panel.appendChild(section);
  } else {
    panel.appendChild(el('p', 'hint', 'AI notes are not enabled for customers yet.'));
  }
}

function renderTranscript(meeting) {
  var panel = $('panel-transcript');
  panel.replaceChildren();
  var segments = asArray(meeting.segments);
  if (segments.length === 0) {
    panel.appendChild(el('div', 'empty', 'No confirmed transcript yet.'));
    return;
  }
  var card = el('article', 'card');
  card.appendChild(el('h3', null, 'Confirmed transcript'));
  segments.forEach(function (segment) {
    var row = el('div', 'transcript-row');
    row.appendChild(el('span', 'time', stamp(segment.start)));
    var body = el('div');
    var speaker = asText(segment.speaker) || 'Unknown speaker';
    if (segment.source === 'chat') speaker += ' · chat';
    body.appendChild(el('div', 'speaker', speaker));
    body.appendChild(el('p', null, asText(segment.text)));
    if (segment.id) body.appendChild(el('span', 'evidence', asText(segment.id)));
    row.appendChild(body);
    card.appendChild(row);
  });
  panel.appendChild(card);
}

function reviewPayload(outboxItem) {
  var node = el('div', 'review-payload');
  var payload = isObject(outboxItem.payload) ? outboxItem.payload : {};
  node.appendChild(el('h3', null, kindLabel(outboxItem.kind)));
  var fields = [
    ['code', 'Google Meet', 'meet'],
    ['from', 'From', 'text'],
    ['to', 'To', 'text'],
    ['subject', 'Subject', 'text'],
    ['consent', 'Consent record', 'text'],
    ['notice', 'Participant notice', 'text']
  ];
  fields.forEach(function (field) {
    var key = field[0];
    var label = field[1];
    var mode = field[2];
    var value = asText(payload[key]);
    if (!value) return;
    var row = el('p', 'review-detail');
    row.appendChild(el('strong', null, label + ': '));
    row.appendChild(el('span', null, mode === 'meet' ? 'meet.google.com/' + value : value));
    node.appendChild(row);
  });
  if (asText(payload.text)) node.appendChild(el('pre', null, asText(payload.text)));
  var details = el('details', 'citation');
  details.appendChild(el('summary', null, 'Technical record'));
  details.appendChild(el('pre', null, JSON.stringify(payload, null, 2)));
  node.appendChild(details);
  return node;
}

function mutationButton(text, onClick) {
  var button = el('button', 'button', text);
  button.type = 'button';
  button.setAttribute('data-operate', 'true');
  button.disabled = !operations;
  button.addEventListener('click', onClick);
  return button;
}

function renderReview(meeting) {
  var panel = $('panel-review');
  panel.replaceChildren();
  var outbox = asArray(meeting.outbox);
  $('review-count').textContent = String(outbox.length);
  if (outbox.length === 0) {
    panel.appendChild(el('div', 'empty', 'Nothing waiting for review.'));
    return;
  }
  outbox.forEach(function (item) {
    var card = el('article', 'card outbox');
    var row = el('div', 'row');
    var destination = asText(item.payload && item.payload.to) || (item.payload && item.payload.code ? 'GOOGLE MEET ' + asText(item.payload.code) : '');
    row.appendChild(el('div', 'label', String(item.kind || '').toUpperCase() + (destination ? ' / ' + destination : '')));
    var meaning = statusMeaning(item.status);
    row.appendChild(el('span', 'tag' + (meaning.tone ? ' ' + meaning.tone : ''), meaning.label));
    card.appendChild(row);
    card.appendChild(reviewPayload(item));
    if (item.digest) card.appendChild(el('p', 'digest', 'Digest: ' + asText(item.digest)));
    card.appendChild(el('p', 'hint', 'Read the complete destination and words. Approval alone does not send.'));
    var actions = el('div', 'actions');
    if (item.status === 'draft') {
      actions.appendChild(mutationButton('Approve this exact item', function () {
        if (window.confirm('Approve this exact destination and complete payload? This does not send yet.')) {
          operate({ action: 'approve', outbox: item.id, digest: item.digest });
        }
      }));
    }
    if (item.status === 'approved' && liveEffects) {
      actions.appendChild(mutationButton('Execute approved item', function () {
        if (window.confirm('Perform the approved ' + asText(item.kind) + ' action now? This can join a call, post text, or send a message.')) {
          operate({ action: 'execute', outbox: item.id });
        }
      }));
    }
    if (item.status === 'approved' && !liveEffects) {
      actions.appendChild(el('p', 'warning', 'Live operations are disabled in this installation. This approval has not joined or sent anything.'));
    }
    if (item.status === 'queued' && item.kind === 'chat') {
      actions.appendChild(mutationButton('Check posting status', function () {
        operate({ action: 'reconcile', outbox: item.id });
      }));
    }
    if (item.status === 'unknown') {
      actions.appendChild(el('p', 'warning', 'Do not retry. The provider may already have accepted this action. Reconcile with the provider before any recovery.'));
    }
    if (actions.childNodes.length > 0) card.appendChild(actions);
    panel.appendChild(card);
  });
}

function renderDetail() {
  var meeting = selectedMeeting();
  var detail = $('meeting-detail');
  if (!meeting) {
    detail.hidden = true;
    $('review-count').textContent = '0';
    return;
  }
  detail.hidden = false;
  $('detail-kicker').textContent = 'Google Meet · meet.google.com/' + asText(meeting.code);
  $('detail-title').textContent = asText(meeting.title) || 'Untitled meeting';
  var segments = asArray(meeting.segments);
  $('detail-meta').textContent = formatCreated(meeting.created) + ' · ' + segments.length + (segments.length === 1 ? ' confirmed segment' : ' confirmed segments');
  $('detail-consent').textContent = 'Consent: ' + (asText(meeting.consent) || 'Not recorded');
  var meaning = statusMeaning(meeting.status);
  var statusTag = $('detail-status');
  statusTag.className = 'tag' + (meaning.tone ? ' ' + meaning.tone : '');
  statusTag.textContent = meaning.label;
  $('sync-button').disabled = !operations;
  $('leave-button').disabled = !operations;
  if (tab === 'notes') renderNotes(meeting);
  else if (tab === 'transcript') renderTranscript(meeting);
  else renderReview(meeting);
}

function render() {
  renderNotices();
  renderList();
  renderDetail();
  setBusy(mutationBusy);
}

function setTab(name) {
  tab = name;
  var tabs = document.querySelectorAll('[data-tab]');
  tabs.forEach(function (button) {
    var active = button.getAttribute('data-tab') === name;
    button.classList.toggle('active', active);
    button.setAttribute('aria-selected', active ? 'true' : 'false');
    button.tabIndex = active ? 0 : -1;
    var panel = $(button.getAttribute('aria-controls'));
    if (panel) panel.hidden = !active;
  });
  renderDetail();
}

function setBusy(busy) {
  mutationBusy = busy;
  document.querySelectorAll('button[data-operate]').forEach(function (button) {
    button.disabled = busy || !operations;
  });
}

async function operate(data) {
  if (mutationBusy) return;
  if (!operations) {
    setStatus('Operations are disabled for this account.');
    return;
  }
  if (!csrf) {
    setStatus(GENERIC_OPERATION_ERROR);
    return;
  }
  setStatus('Working...');
  setBusy(true);
  try {
    await apiJson('/api/operate', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json', 'X-Labs-CSRF': csrf },
      body: JSON.stringify(data)
    });
    setStatus('Saved. Check the updated state below. Staging and approval do not send.');
    await loadReview();
  } catch (error) {
    if (error && error.name === 'Unauthenticated') {
      redirectToLanding();
      return;
    }
    setStatus(GENERIC_OPERATION_ERROR);
    try { await loadReview(); } catch (e) { /* keep the generic message; do not retry */ }
  } finally {
    setBusy(false);
  }
}

async function refresh() {
  hideError();
  setStatus('Loading...');
  try {
    await loadReview();
    setStatus('');
  } catch (error) {
    if (error && error.name === 'Unauthenticated') {
      redirectToLanding();
      return;
    }
    showError();
  }
}

async function logout() {
  $('logout-button').disabled = true;
  try {
    await apiJson('/auth/logout', {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json', 'X-Labs-CSRF': csrf || '' },
      body: JSON.stringify({})
    });
    redirectToLanding();
  } catch (e) {
    if (e && e.name === 'Unauthenticated') redirectToLanding();
    else setStatus('Log out was not confirmed. Your session may still be active. Try again when connected.');
  } finally { $('logout-button').disabled = false; }
}

function openAddDialog() {
  if (!operations || mutationBusy) return;
  var dialog = $('add-dialog');
  $('add-form').reset();
  $('add-error').hidden = true;
  $('add-error').textContent = '';
  if (typeof dialog.showModal === 'function') dialog.showModal();
  else dialog.setAttribute('open', '');
  $('field-title').focus();
}

function closeAddDialog() {
  var dialog = $('add-dialog');
  if (typeof dialog.close === 'function') dialog.close();
  else dialog.removeAttribute('open');
  $('add-meeting-button').focus();
}

function showFormError(text) {
  var error = $('add-error');
  error.textContent = text;
  error.hidden = false;
}

async function submitAddForm(event) {
  event.preventDefault();
  var title = $('field-title').value.trim();
  var link = $('field-link').value.trim();
  var consent = $('field-consent').checked;
  if (title.length < 1 || title.length > 200) {
    showFormError('Enter a meeting title of 1 to 200 characters.');
    $('field-title').focus();
    return;
  }
  if (!MEET_LINK.test(link)) {
    showFormError('Use an https://meet.google.com/abc-defg-hij link.');
    $('field-link').focus();
    return;
  }
  if (!consent) {
    showFormError('Confirm organizer authority and participant notice first.');
    $('field-consent').focus();
    return;
  }
  if (!window.confirm('Create this meeting and stage a join request for review? This does not join the call yet.')) return;
  closeAddDialog();
  await operate({ action: 'create', title: title, link: link, consent_confirmed: true });
}

async function init() {
  hideError();
  $('loading').hidden = false;
  $('app').hidden = true;
  try {
    await loadSession();
    await loadReview();
    $('loading').hidden = true;
    $('app').hidden = false;
  } catch (error) {
    if (error && error.name === 'Unauthenticated') {
      redirectToLanding();
      return;
    }
    $('loading').hidden = true;
    showError();
  }
}

function wireEvents() {
  document.querySelectorAll('[data-tab]').forEach(function (button) {
    button.addEventListener('click', function () { setTab(button.getAttribute('data-tab')); });
  });
  var tablist = document.querySelector('[role="tablist"]');
  if (tablist) {
    tablist.addEventListener('keydown', function (event) {
      if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return;
      var tabs = Array.prototype.slice.call(document.querySelectorAll('[data-tab]'));
      var index = tabs.indexOf(document.activeElement);
      if (index === -1) return;
      event.preventDefault();
      var next = event.key === 'ArrowRight' ? (index + 1) % tabs.length : (index - 1 + tabs.length) % tabs.length;
      tabs[next].focus();
      setTab(tabs[next].getAttribute('data-tab'));
    });
  }
  $('refresh-button').addEventListener('click', refresh);
  $('error-retry').addEventListener('click', init);
  $('logout-button').addEventListener('click', logout);
  $('add-meeting-button').addEventListener('click', openAddDialog);
  $('empty-add-button').addEventListener('click', openAddDialog);
  $('add-cancel').addEventListener('click', closeAddDialog);
  $('add-form').addEventListener('submit', submitAddForm);
  $('add-dialog').addEventListener('click', function (event) {
    if (event.target === $('add-dialog')) closeAddDialog();
  });
  $('sync-button').addEventListener('click', function () {
    var meeting = selectedMeeting();
    if (meeting) operate({ action: 'sync', meeting: meeting.id });
  });
  $('leave-button').addEventListener('click', function () {
    var meeting = selectedMeeting();
    if (!meeting) return;
    if (window.confirm('Stage a leave request for this meeting? This does not leave yet.')) {
      operate({ action: 'leave', meeting: meeting.id });
    }
  });
  var addButton = $('add-meeting-button');
  addButton.setAttribute('data-operate', 'true');
  $('empty-add-button').setAttribute('data-operate', 'true');
  $('add-submit').setAttribute('data-operate', 'true');
  $('sync-button').setAttribute('data-operate', 'true');
  $('leave-button').setAttribute('data-operate', 'true');
}

wireEvents();
init();
