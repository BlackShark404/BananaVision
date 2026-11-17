import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFile } from 'node:fs/promises'
import { transform } from 'esbuild'

const source = await readFile(new URL('../src/lib/activityActions.ts', import.meta.url), 'utf8')
const { code } = await transform(source, { loader: 'ts', format: 'esm' })
const {
  ACTIVITY_ACTIONS, activityLabel, activityBadgeClass, activityCategory, isCriticalActivity,
  activityProfileLabel, actorlessName,
} = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)

// The backend vocabulary is the single source of truth: parse it instead of copying it.
const audit = await readFile(new URL('../../backend/app/services/audit.py', import.meta.url), 'utf8')
const block = audit.slice(audit.indexOf('class AuditAction(StrEnum):'))
const body = block.slice(0, block.search(/\n(?=\S)/))
const backendActions = [...body.matchAll(/^\s+[A-Z][A-Z_]*\s*=\s*"([a-z_]+)"/gm)].map(match => match[1])

const CATEGORIES = new Set(['auth', 'security', 'credential', 'data', 'export', 'system'])
const CRITICAL = new Set([
  'login_failed', 'pin_failed', 'login_blocked', 'account_locked', 'login_denied',
  'setup_token_rejected', 'access_denied', 'reauth_failed', 'password_change_failed',
  'pin_change_failed', 'password_reset', 'pin_reset', 'user_role_changed', 'user_status_changed',
  'data_exported', 'backup_downloaded', 'restore_completed', 'restore_failed',
  'maintenance_recovered', 'config_changed', 'config_applied', 'system_restart',
  'system_shutdown', 'power_failed', 'power_cancelled', 'bootstrap_admin_created',
])

test('every backend audit action has exactly one friendly entry', () => {
  assert.ok(backendActions.length > 40, `parsed ${backendActions.length} actions`)
  assert.equal(new Set(backendActions).size, backendActions.length)
  assert.deepEqual(new Set(Object.keys(ACTIVITY_ACTIONS)), new Set(backendActions))
})

test('entries carry a label, a known category, a badge class, a critical flag and a profile phrase', () => {
  for (const [action, entry] of Object.entries(ACTIVITY_ACTIONS)) {
    assert.ok(entry.label && !entry.label.includes('_'), action)
    assert.equal(activityLabel(action), entry.label)
    assert.ok(CATEGORIES.has(entry.category), action)
    assert.equal(activityCategory(action), entry.category)
    assert.match(entry.badge, /^bg-\w+-50 text-\w+-700 border-\w+-200$/, action)
    assert.equal(activityBadgeClass(action), entry.badge)
    assert.equal(typeof entry.critical, 'boolean', action)
    assert.ok(entry.profile && entry.profile.length > 3, action)
  }
  const labels = Object.values(ACTIVITY_ACTIONS).map(entry => entry.label)
  assert.equal(new Set(labels).size, labels.length, 'labels are distinct')
})

test('badges reuse the page palette by category', () => {
  const tone = action => activityBadgeClass(action).match(/^bg-(\w+)-50/)[1]
  for (const [action, entry] of Object.entries(ACTIVITY_ACTIONS)) {
    if (entry.category === 'security') assert.equal(tone(action), 'red', action)
    if (entry.category === 'credential') assert.equal(tone(action), 'indigo', action)
    if (entry.category === 'export') assert.equal(tone(action), 'cyan', action)
  }
  assert.equal(activityBadgeClass('login'), 'bg-blue-50 text-blue-700 border-blue-200')
  assert.equal(activityBadgeClass('scan_created'), 'bg-emerald-50 text-emerald-700 border-emerald-200')
  assert.equal(activityBadgeClass('user_created'), 'bg-purple-50 text-purple-700 border-purple-200')
  assert.equal(activityBadgeClass('scan_rejected'), 'bg-amber-50 text-amber-700 border-amber-200')
  assert.equal(activityBadgeClass('config_changed'), 'bg-orange-50 text-orange-700 border-orange-200')
})

test('unknown and legacy actions fall back to title case and a muted badge', () => {
  assert.equal(activityLabel('scan_edited'), 'Scan Edited')
  assert.equal(activityLabel('made_up_action'), 'Made Up Action')
  assert.equal(activityLabel(''), '')
  for (const action of ['made_up_action', 'toString', 'constructor', '__proto__', 'hasOwnProperty', '']) {
    assert.equal(activityBadgeClass(action), 'bg-muted', action)
    assert.equal(isCriticalActivity(action), false, action)
    assert.equal(activityCategory(action), null, action)
    assert.equal(actorlessName(action), 'System', action)
    assert.equal(activityProfileLabel(action, 'Raw details'), 'Raw details', action)
  }
  assert.equal(activityLabel('toString'), 'ToString')
})

test('critical actions are security failures, resets, role/status changes, egress and system power', () => {
  const critical = Object.keys(ACTIVITY_ACTIONS).filter(isCriticalActivity)
  assert.deepEqual(new Set(critical), CRITICAL)
  for (const [action, entry] of Object.entries(ACTIVITY_ACTIONS)) {
    if (entry.category === 'security') assert.equal(entry.critical, true, action)
  }
  for (const quiet of ['login', 'logout', 'scan_created', 'user_updated', 'supplier_updated', 'system_started']) {
    assert.equal(isCriticalActivity(quiet), false, quiet)
  }
})

test('rows without an account read as unauthenticated for security events, else system', () => {
  for (const [action, entry] of Object.entries(ACTIVITY_ACTIONS)) {
    assert.equal(actorlessName(action), entry.category === 'security' ? 'Unauthenticated' : 'System', action)
  }
  assert.equal(actorlessName('login_failed'), 'Unauthenticated')
  assert.equal(actorlessName('access_denied'), 'Unauthenticated')
  assert.equal(actorlessName('system_started'), 'System')
  assert.equal(actorlessName('retention_cleanup'), 'System')
})

test('profile phrases keep the existing wording and fall back to the stored details', () => {
  const kept = {
    login: 'Signed in to the web dashboard',
    logout: 'Signed out from the session',
    scan_created: 'Captured a new banana scan in Kiosk',
    scan_rejected: 'Scan rejected: no supported banana detected',
    intake_created: 'Recorded a new delivery intake',
    intake_status_changed: 'Updated intake status in Intake Management',
    config_changed: 'Adjusted system configuration settings',
    scan_correction: 'Updated scan data in Quality Control',
  }
  for (const [action, phrase] of Object.entries(kept)) {
    assert.equal(activityProfileLabel(action, 'ignored'), phrase, action)
  }
  assert.equal(activityProfileLabel('scan_flag', 'Scan 1: flagged False → True'), 'Flagged a scan for manual review')
  assert.equal(activityProfileLabel('scan_flag', 'Scan 1: flagged True → False'), "Cleared a scan's review flag")
  assert.equal(activityProfileLabel('scan_flag', 'Scan 1, revision 2'), "Changed a scan's review flag")
  assert.equal(activityProfileLabel('password_changed', 'x'), 'Changed account password')
  assert.equal(activityProfileLabel('legacy_event', 'Stored text'), 'Stored text')
  assert.equal(activityProfileLabel('legacy_event', ''), 'Legacy Event')
})
