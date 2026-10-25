import assert from 'node:assert/strict'
import { after, before, test } from 'node:test'
import { startBrowser } from './dashboard.browser.mjs'

let runtime
before(async () => { runtime = await startBrowser({ fixture: 'crosssession.fixture.tsx', auth: 'dashboard.auth.tsx', port: 5199 }) })
after(async () => { await runtime?.close() })

const NOW = '2026-10-02T04:00:00Z'
const NOW_MS = Date.parse(NOW)
const ADMIN = { id: 'admin-1', username: 'admin', fullName: 'Test Admin', role: 'Admin' }
const OPERATOR_A = { id: 'operator-a', username: 'operator-a', fullName: 'Operator A', role: 'Operator' }
const OPERATOR_B = { id: 'operator-b', username: 'operator-b', fullName: 'Operator B', role: 'Operator' }
const CORS = {
  'access-control-allow-origin': '*',
  'access-control-allow-headers': '*',
  'access-control-allow-methods': '*',
}
const METRICS = {
  cpu_name: 'Fixture CPU', cpu_percent: 12, memory_used_gb: 4, memory_total_gb: 16,
  memory_percent: 25, disk_used_gb: 100, disk_total_gb: 500, disk_percent: 20,
  uptime: '1 day', cpu_temp: null,
}

const iso = offsetMs => new Date(NOW_MS + offsetMs).toISOString()

function scanRow(index, operatorId, overrides = {}) {
  return {
    id: `scan-${index}`,
    revision: 1,
    created_seq: 0,
    date_time: iso(-index * 60_000),
    cultivar: index === 1 ? 'Lakatan' : index === 2 ? 'Saba' : `Cultivar ${index}`,
    ripeness: 'Ripe',
    confidence: 92,
    temperature: null,
    humidity: null,
    vpd: null,
    spoilage_days: '3',
    finger_count: 7,
    operator_name: operatorId === OPERATOR_A.id ? 'Operator A' : 'Operator B',
    operator_id: operatorId,
    source_key: 'supplier:supplier-1',
    source_name: 'Original supplier',
    source_text: 'Original supplier',
    intake_id: index === 1 || index === 11 ? 'intake-1' : null,
    intake_provenance: 'linked',
    inventory_eligible: true,
    remaining_days: 3,
    risk_as_of: NOW,
    inventory_status: 'In Stock',
    status_updated_at: null,
    flagged: false,
    is_overridden: false,
    has_notes: false,
    thumbnail_url: null,
    ...overrides,
  }
}

function createStation() {
  return {
    scans: Array.from({ length: 12 }, (_, index) =>
      scanRow(index + 1, index % 2 === 0 ? OPERATOR_A.id : OPERATOR_B.id)),
    intakes: [{
      id: 'intake-1', supplier_id: 'supplier-1', supplier_name: 'Original supplier',
      batch_number: 'B-1', intake_date: NOW, status: 'Active', scan_count: 2,
      updated_at: iso(-60_000),
    }],
    suppliers: [{
      id: 'supplier-1', name: 'Original supplier', status: 'Active',
      date_added: NOW, updated_at: iso(-60_000),
    }],
    notifications: { items: [], total: 0 },
    sensor: {
      temperature: 26.5, humidity: 70, recorded_at: iso(-90_000),
      server_time: NOW, stale_after_seconds: 15,
    },
    snapshots: new Map(),
    expired: new Set(),
    superseded: new Set(),
    logResponses: [],
    requests: [],
    commitSeq: 0,
    snapshotSeq: 0,
    eventSeq: 0,
    clock: NOW_MS,
    lastSnapshotId: null,
  }
}

const visibleScans = (station, account) => account === ADMIN.id
  ? station.scans
  : station.scans.filter(scan => scan.operator_id === account)

function captureSnapshot(station, account) {
  const id = `snap-${++station.snapshotSeq}`
  station.snapshots.set(id, {
    id, account, seq: station.commitSeq,
    rows: visibleScans(station, account).map(row => ({ ...row })),
  })
  station.lastSnapshotId = id
  return station.snapshots.get(id)
}

function matchesFilters(row, query) {
  if (query.search && !`${row.id} ${row.cultivar} ${row.operator_name} ${row.source_name}`.toLowerCase().includes(query.search.toLowerCase())) return false
  if (query.cultivar && row.cultivar !== query.cultivar) return false
  if (query.ripeness && row.ripeness !== query.ripeness) return false
  if (query.inventory_status && row.inventory_status !== query.inventory_status) return false
  if (query.flagged_only === 'true' && row.flagged !== true) return false
  if (query.intake_id && row.intake_id !== query.intake_id) return false
  if (query.operator_id && row.operator_id !== query.operator_id) return false
  if (query.stock_eligible === 'true' && row.inventory_eligible !== true) return false
  if (query.attention === 'at-risk' && !(row.inventory_eligible === true && typeof row.remaining_days === 'number' && row.remaining_days <= 2)) return false
  if (query.attention === 'success' && row.flagged === true) return false
  return true
}

function sortRows(rows, query) {
  const key = ['cultivar', 'confidence', 'spoilage_days', 'finger_count'].includes(query.sort) ? query.sort : 'date_time'
  const direction = query.direction === 'asc' ? 1 : -1
  return [...rows].sort((left, right) => {
    const a = left[key] ?? ''
    const b = right[key] ?? ''
    if (a < b) return -1 * direction
    if (a > b) return 1 * direction
    return left.id < right.id ? -1 : left.id > right.id ? 1 : 0
  })
}

function scanLogPage(station, account, query) {
  let snapshot
  if (query.snapshot_id) {
    snapshot = station.snapshots.get(query.snapshot_id)
    if (!snapshot || snapshot.account !== account || station.expired.has(query.snapshot_id)) {
      return { status: 410, body: { detail: 'Browse snapshot expired. Refresh.' } }
    }
    if (station.superseded.has(query.snapshot_id)) {
      return { status: 409, body: { detail: 'Browse snapshot superseded. Refresh.' } }
    }
  } else {
    snapshot = captureSnapshot(station, account)
  }
  const rows = sortRows(snapshot.rows.filter(row => matchesFilters(row, query)), query)
  const page = Number(query.page || 1)
  const pageSize = Number(query.page_size || 10)
  return {
    status: 200,
    body: {
      items: rows.slice((page - 1) * pageSize, page * pageSize).map(row => ({ ...row })),
      total: rows.length, page, page_size: pageSize, snapshot_id: snapshot.id,
      avg_confidence: 92, at_risk_count: 0, review_count: 0, flagged_count: 0,
      generated_at: NOW, confidence_threshold: 85,
      options: {
        sources: [{ key: 'supplier:supplier-1', name: 'Original supplier' }],
        operators: [
          { operator_id: OPERATOR_A.id, name: 'Operator A', username: 'operator-a' },
          { operator_id: OPERATOR_B.id, name: 'Operator B', username: 'operator-b' },
        ],
      },
    },
  }
}

async function installRoutes(page, world, account) {
  const station = world.station
  await page.route('**/health', route => route.fulfill({
    status: 200, headers: CORS, json: {
      status: 'ok', cameras_online: 0, cameras_total: 0, yolo_loaded: true, rfr_loaded: true,
      sensor_connected: true, sensor_recorded_at: station.sensor.recorded_at,
      sensor_stale_after_seconds: station.sensor.stale_after_seconds, server_time: station.sensor.server_time,
    },
  }).catch(() => {}))
  await page.route('**/api/v1/**', async route => {
    const request = route.request()
    const url = new URL(request.url())
    const method = request.method()
    const query = Object.fromEntries(url.searchParams)
    if (method === 'OPTIONS') return route.fulfill({ status: 204, headers: CORS })
    station.requests.push({ path: url.pathname, method, query, account })
    const reply = (json, status = 200) => route.fulfill({ status, headers: CORS, json }).catch(() => {})
    const body = method === 'GET' ? null : request.postDataJSON()
    const path = url.pathname

    if (path === '/api/v1/scan-logs') {
      const result = scanLogPage(station, account, query)
      station.logResponses.push({ status: result.status, query, account })
      return reply(result.body, result.status)
    }
    if (path === '/api/v1/scan-logs/reconcile') {
      if (station.failReconcile) return reply({ detail: 'Temporary read failure' }, 503)
      const frozen = scanLogPage(station, account, query)
      if (frozen.status !== 200) return reply(frozen.body, frozen.status)
      const live = visibleScans(station, account).filter(scan => matchesFilters(scan, query))
      const byId = new Map(live.map(scan => [scan.id, scan]))
      const items = frozen.body.items.flatMap(scan => byId.has(scan.id) ? [{ ...byId.get(scan.id) }] : [])
      const risk = scan => scan.exactRisk ?? (scan.inventory_eligible && scan.remaining_days != null && scan.remaining_days <= 2)
      return reply({
        snapshot_id: query.snapshot_id, items, total: live.length,
        at_risk_ids: items.filter(risk).map(scan => scan.id),
        avg_confidence: live.length ? live.reduce((sum, scan) => sum + scan.confidence, 0) / live.length : null,
        at_risk_count: live.filter(risk).length,
        review_count: live.filter(scan => scan.flagged || scan.confidence < 85).length,
        flagged_count: live.filter(scan => scan.flagged).length,
        confidence_threshold: 85, generated_at: NOW,
      })
    }
    if (path === '/api/v1/scan-logs/pending') {
      const snapshot = station.snapshots.get(query.snapshot_id)
      if (!snapshot) return reply({ detail: 'Browse snapshot expired. Refresh.' }, 410)
      const fresh = visibleScans(station, account)
        .filter(scan => (scan.created_seq ?? 0) > snapshot.seq)
        .filter(scan => matchesFilters(scan, query))
      return reply({ snapshot_id: snapshot.id, new_count: fresh.length, generated_at: NOW })
    }
    if (path === '/api/v1/scans' && method === 'GET') {
      const pageNumber = Number(query.page || 1)
      const pageSize = Number(query.page_size || 20)
      const rows = visibleScans(station, account)
      return reply({
        items: rows.slice((pageNumber - 1) * pageSize, pageNumber * pageSize),
        page: pageNumber, page_size: pageSize, total: rows.length,
      })
    }
    if (path === '/api/v1/intakes' && method === 'GET') return reply(station.intakes.map(intake => ({ ...intake })))
    if (path === '/api/v1/suppliers' && method === 'GET') return reply(station.suppliers.map(supplier => ({ ...supplier })))
    if (path === '/api/v1/users') return reply({ items: [], total: 0 })
    if (path === '/api/v1/config') return reply({ camera_ids: 'CAM-001', confidence_threshold: 85, data_retention_enabled: true, revision: 1 })
    if (path === '/api/v1/activity') return reply({ items: [], page: 1, page_size: 100, total: 0 })
    if (path === '/api/v1/devices') return reply([])
    if (path === '/api/v1/notifications') return reply({ items: station.notifications.items, total: station.notifications.items.length })
    if (path === '/api/v1/sensors/latest') return reply(station.sensor)
    if (path === '/api/v1/system/metrics') return reply(METRICS)
    if (path.startsWith('/api/v1/scans/') && method === 'GET') {
      const scan = station.scans.find(row => row.id === path.split('/')[4])
      return scan ? reply({ ...scan, notes: [] }) : reply({ detail: 'Scan not found' }, 404)
    }

    if (method === 'PATCH' && /^\/api\/v1\/scans\/[^/]+\/flag$/.test(path)) {
      const scan = station.scans.find(row => row.id === path.split('/')[4])
      if (!scan) return reply({ detail: 'Scan not found' }, 404)
      if (body.expected_revision !== scan.revision) return reply({ detail: 'This scan changed. Reload it before saving your changes.' }, 409)
      scan.flagged = body.flagged === true
      scan.revision += 1
      await reply({ ...scan })
      await world.emitScan(scan, { kind: 'flag', changed: ['flagged'], actorId: account })
      return
    }
    if (method === 'PATCH' && /^\/api\/v1\/scans\/[^/]+\/status$/.test(path)) {
      const scan = station.scans.find(row => row.id === path.split('/')[4])
      if (body.expected_revision !== scan.revision) return reply({ detail: 'This scan changed. Reload it before saving your changes.' }, 409)
      scan.inventory_status = body.inventory_status
      scan.inventory_eligible = body.inventory_status === 'In Stock'
      scan.status_updated_at = iso(station.clock += 1000)
      scan.revision += 1
      await reply({ ...scan })
      await world.emitScan(scan, { kind: 'status', changed: ['inventory_status'], actorId: account })
      return
    }
    if (method === 'PATCH' && /^\/api\/v1\/scans\/[^/]+$/.test(path)) {
      const scan = station.scans.find(row => row.id === path.split('/')[4])
      if (body.expected_revision !== scan.revision) return reply({ detail: 'This scan changed. Reload it before saving your changes.' }, 409)
      for (const field of ['cultivar', 'ripeness', 'finger_count', 'spoilage_days', 'source_text']) {
        if (body[field] !== undefined) scan[field] = body[field]
      }
      if (scan.source_text) scan.source_name = scan.source_text
      scan.is_overridden = true
      scan.revision += 1
      await reply({ ...scan })
      await world.emitScan(scan, { kind: 'correction', changed: Object.keys(body).filter(key => key !== 'reason' && key !== 'expected_revision'), actorId: account })
      return
    }
    if (method === 'PATCH' && /^\/api\/v1\/suppliers\/[^/]+$/.test(path)) {
      const supplier = station.suppliers.find(row => row.id === path.split('/')[4])
      Object.assign(supplier, body, { updated_at: iso(station.clock += 1000) })
      await reply({ ...supplier })
      await world.emit('supplier:changed', {
        event_id: `event-${++station.eventSeq}`, supplier_id: supplier.id, kind: 'updated',
        actor_id: account, supplier: { ...supplier },
      }, { rooms: ['dashboard', 'kiosk'] })
      return
    }
    if (method === 'POST' && path === '/api/v1/intakes') {
      const supplier = station.suppliers.find(row => row.id === body.supplier_id)
      const intake = {
        id: `intake-${station.intakes.length + 8}`, supplier_id: body.supplier_id,
        supplier_name: supplier?.name ?? body.source, batch_number: body.batch_number,
        intake_date: NOW, status: 'Active', treatment: body.treatment, scan_count: 0,
        created_at: iso(station.clock += 1000), updated_at: iso(station.clock),
      }
      station.intakes.unshift(intake)
      await reply({ ...intake })
      await world.emit('intake:changed', {
        event_id: `event-${++station.eventSeq}`, intake_id: intake.id, kind: 'created',
        actor_id: account, status: intake.status, intake: { ...intake },
      }, { rooms: ['dashboard', 'kiosk'] })
      return
    }
    if (method === 'PATCH' && /^\/api\/v1\/intakes\/[^/]+\/bulk-inventory$/.test(path)) {
      const intake = station.intakes.find(row => row.id === path.split('/')[4])
      const changed = []
      for (const [id, expected] of Object.entries(body.expected_revisions ?? {})) {
        const scan = station.scans.find(row => row.id === id)
        if (!scan || scan.revision !== expected) return reply({ detail: 'This scan changed. Reload it before saving your changes.' }, 409)
        scan.inventory_status = body.inventory_status
        scan.inventory_eligible = body.inventory_status === 'In Stock'
        scan.status_updated_at = iso(station.clock += 1000)
        scan.revision += 1
        changed.push(scan)
      }
      intake.status = 'Depleted'
      intake.updated_at = iso(station.clock += 1000)
      const revisions = Object.fromEntries(changed.map(scan => [scan.id, scan.revision]))
      await reply({
        message: `Updated ${changed.length} scans`, updated_count: changed.length,
        updated_scan_ids: changed.map(scan => scan.id), status_updated_at: intake.updated_at,
        intake_status: intake.status, revisions,
      })
      for (const scan of changed) {
        await world.emitScan(scan, { kind: 'bulk-inventory', changed: ['inventory_status'], actorId: account, partial: true })
      }
      await world.emit('intake:changed', {
        event_id: `event-${++station.eventSeq}`, intake_id: intake.id, kind: 'bulk-inventory',
        actor_id: account, status: intake.status, intake: { ...intake },
      }, { rooms: ['dashboard', 'kiosk'] })
      return
    }

    return reply({ detail: `Unexpected test API: ${method} ${path}` }, 404)
  })
}

function createWorld() {
  const world = {
    station: createStation(),
    sessions: [],
    async emit(event, data, filter = {}) {
      for (const session of world.sessions) {
        await session.page.evaluate(({ event, data, filter }) => {
          window.stationSocket?.deliver(event, data, filter)
        }, { event, data, filter }).catch(() => {})
      }
    },
    async emitScan(scan, { kind, changed, actorId, partial = false }) {
      const payload = {
        event_id: `event-${++world.station.eventSeq}`,
        scan_id: scan.id, revision: scan.revision, kind, changed,
        actor_id: actorId, partial, deleted: false,
        scan: partial ? {
          id: scan.id, revision: scan.revision, inventory_status: scan.inventory_status,
          status_updated_at: scan.status_updated_at, inventory_eligible: scan.inventory_eligible,
          remaining_days: scan.remaining_days, risk_as_of: scan.risk_as_of,
        } : { ...scan },
      }
      await world.emit('scan:changed', payload, { rooms: ['dashboard', 'kiosk'], account: scan.operator_id })
      return payload
    },
  }
  return world
}

async function open(world, t, { account, path = '/logs' }) {
  const context = await runtime.browser.newContext({ timezoneId: 'Asia/Manila' })
  const page = await context.newPage()
  page.setDefaultTimeout(10_000)
  page.setDefaultNavigationTimeout(30_000)
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  t.after(async () => { await context.close(); assert.deepEqual(errors, [], 'No uncaught browser errors') })
  await page.clock.install({ time: new Date(NOW_MS - 60_000) })
  await page.clock.pauseAt(new Date(NOW_MS))
  await page.addInitScript(({ user }) => {
    localStorage.setItem('bananavision_token', user.id)
    window.dashboardUser = user
    const sockets = []
    class TestWebSocket {
      static CONNECTING = 0; static OPEN = 1; static CLOSING = 2; static CLOSED = 3
      readyState = 0
      constructor(url) {
        const parsed = new URL(url)
        this.rooms = (parsed.searchParams.get('rooms') || '').split(',').filter(Boolean)
        // Mirror backend role authorization: Operators never join dashboard/devices.
        if (user.role !== 'Admin') this.rooms = this.rooms.filter(room => room === 'kiosk')
        this.account = parsed.searchParams.get('token') || ''
        sockets.push(this)
        queueMicrotask(() => this.open())
      }
      open() { this.readyState = 1; this.onopen?.({}) }
      close(code = 1000) { this.readyState = 3; this.onclose?.({ code }) }
      send() {}
    }
    window.WebSocket = TestWebSocket
    window.stationSocket = {
      deliver(event, data, filter = {}) {
        sockets
          .filter(socket => socket.readyState === 1)
          .filter(socket => !filter.rooms
            ? true
            : filter.account
              ? socket.rooms.includes('dashboard') || (socket.rooms.includes('kiosk') && socket.account === filter.account)
              : socket.rooms.some(room => filter.rooms.includes(room)))
          .forEach(socket => socket.onmessage?.({ data: JSON.stringify({ event, data }) }))
      },
      disconnect() { sockets.filter(socket => socket.readyState === 1).forEach(socket => socket.close(1006)) },
      connected() { return sockets.filter(socket => socket.readyState === 1).length },
    }
  }, { user: account })
  await installRoutes(page, world, account.id)
  const session = { page, account }
  world.sessions.push(session)
  await page.goto(`${runtime.url}${path}`)
  await until(async () => {
    const current = await state(page)
    return current.scans.length > 0 && current.intakesReady && !current.intakesLoading && current.suppliers.length > 0
  }, `${account.id} providers did not finish loading`)
  if (path.startsWith('/logs')) await page.getByRole('table').waitFor()
  return session
}

async function state(page) {
  const locator = page.getByTestId('state')
  if (!(await locator.count())) return { scans: [], intakes: [], suppliers: [], intakesReady: false, intakesLoading: true }
  return JSON.parse(await locator.textContent())
}

async function until(predicate, message = 'Expected state did not arrive') {
  for (let attempt = 0; attempt < 250; attempt++) {
    if (await predicate()) return
    await new Promise(resolve => setTimeout(resolve, 20))
  }
  assert.fail(message)
}

const listRequests = (station, account) => station.requests
  .filter(request => request.account === account && request.path === '/api/v1/scan-logs')
const freshListRequests = (station, account) => listRequests(station, account)
  .filter(request => !request.query.snapshot_id)
const notice = (page, text) => page.getByRole('status').filter({ hasText: text })

async function waitForAction(session, name) {
  await until(async () => (await session.page.getByTestId('action-result').textContent()) === `${name}:ok`,
    `${name} mutation did not commit`)
}

test('a committed flag reaches Admin and the owning Operator, and the actor sees no remote-change notice', async t => {
  const world = createWorld()
  const admin = await open(world, t, { account: ADMIN })
  const operatorA = await open(world, t, { account: OPERATOR_A })
  const operatorB = await open(world, t, { account: OPERATOR_B })
  const listCount = freshListRequests(world.station, ADMIN.id).length

  await operatorA.page.getByTestId('actions').getByRole('button', { name: 'flag', exact: true }).click()
  await waitForAction(operatorA, 'flag')

  await until(async () => (await state(admin.page)).scans.find(scan => scan.id === 'scan-1')?.flagged === true,
    'Admin did not receive the committed flag')
  await until(async () => (await state(operatorA.page)).scans.find(scan => scan.id === 'scan-1')?.flagged === true,
    'Owning Operator did not receive the committed flag')

  await admin.page.getByTitle('Flagged for QC Review').waitFor()
  await notice(admin.page, 'changed outside this view').waitFor()
  assert.match(await notice(admin.page, 'changed outside this view').innerText(), /1 scan record has changed outside this view/)
  assert.equal(await notice(operatorA.page, 'changed outside this view').count(), 0, 'The acting tab must not warn about its own edit')
  assert.equal(await notice(operatorB.page, 'changed outside this view').count(), 0)

  const operatorBState = await state(operatorB.page)
  assert.deepEqual(operatorBState.scans.map(scan => scan.id).sort(), ['scan-10', 'scan-12', 'scan-2', 'scan-4', 'scan-6', 'scan-8'])
  assert(operatorBState.scans.every(scan => scan.revision === 1 && scan.flagged === false))

  assert.equal(freshListRequests(world.station, ADMIN.id).length, listCount,
    'An edit must patch the frozen row instead of rebuilding the browse snapshot')
})

test('a frozen Page 2 row is patched in place, deduplicated by event id, and refreshed only on request', async t => {
  const world = createWorld()
  const admin = await open(world, t, { account: ADMIN, path: '/logs?page=2' })
  const operatorA = await open(world, t, { account: OPERATOR_A })
  const table = admin.page.getByRole('table')
  await table.getByText('Cultivar 11', { exact: true }).waitFor()
  await table.getByText('Cultivar 12', { exact: true }).waitFor()
  const listCount = freshListRequests(world.station, ADMIN.id).length

  await operatorA.page.getByTestId('actions').getByRole('button', { name: 'override', exact: true }).click()
  await waitForAction(operatorA, 'override')
  await table.getByText('Cardaba', { exact: true }).waitFor()
  assert.equal(await table.getByText('Cultivar 11', { exact: true }).count(), 0)
  await notice(admin.page, 'changed outside this view').waitFor()
  assert.equal(freshListRequests(world.station, ADMIN.id).length, listCount)
  assert.equal(await admin.page.getByRole('row').count(), 3, 'Page 2 keeps exactly its frozen two rows plus the header')

  // The same event can arrive from the dashboard and kiosk rooms; it must count once.
  const event = {
    event_id: 'duplicate-event', scan_id: 'scan-11', revision: 2, kind: 'correction',
    changed: ['cultivar'], actor_id: OPERATOR_A.id, partial: false, deleted: false,
    scan: { ...world.station.scans.find(scan => scan.id === 'scan-11') },
  }
  await world.emit('scan:changed', event, { rooms: ['dashboard', 'kiosk'], account: OPERATOR_A.id })
  await world.emit('scan:changed', event, { rooms: ['dashboard', 'kiosk'], account: OPERATOR_A.id })
  await admin.page.waitForTimeout(150)
  assert.match(await notice(admin.page, 'changed outside this view').innerText(), /1 scan record has changed outside this view/)

  await notice(admin.page, 'changed outside this view').getByRole('button', { name: 'Refresh', exact: true }).click()
  await until(() => freshListRequests(world.station, ADMIN.id).length > listCount,
    'Refresh did not request a new browse snapshot')
  await table.getByText('Cardaba', { exact: true }).waitFor()
  assert.equal(await notice(admin.page, 'changed outside this view').count(), 0)
})

test('a remote edit waits for a focused control instead of replacing the row', async t => {
  const world = createWorld()
  const admin = await open(world, t, { account: ADMIN })
  const table = admin.page.getByRole('table')
  await table.getByText('Lakatan', { exact: true }).waitFor()
  const search = admin.page.getByPlaceholder('Search by cultivar, operator, or ID...')
  await search.focus()
  assert.equal(await search.evaluate(node => document.activeElement === node), true)

  const scan = world.station.scans.find(row => row.id === 'scan-1')
  scan.flagged = true
  scan.revision = 2
  const liveRead = admin.page.waitForResponse(response => response.url().includes('/scan-logs/reconcile'))
  await world.emitScan(scan, { kind: 'flag', changed: ['flagged'], actorId: OPERATOR_A.id })
  await admin.page.clock.runFor(300)
  const fresh = await (await liveRead).json()
  assert.equal(fresh.items.find(row => row.id === 'scan-1').flagged, true)
  await admin.page.waitForTimeout(150)
  assert.equal(await admin.page.getByTitle('Flagged for QC Review').count(), 0,
    'A remote edit must not replace a row while a control is focused')
  assert.match(await notice(admin.page, 'changed outside this view').innerText(),
    /1 scan record has changed outside this view/)

  await admin.page.getByRole('heading', { level: 1 }).click()
  await admin.page.clock.runFor(300)
  await admin.page.getByTitle('Flagged for QC Review').waitFor()
})

test('Page 1 adopts a newly committed Kiosk scan without a manual refresh', async t => {
  const world = createWorld()
  const admin = await open(world, t, { account: ADMIN })
  const table = admin.page.getByRole('table')
  await table.getByText('Lakatan', { exact: true }).waitFor()
  const before = freshListRequests(world.station, ADMIN.id).length

  const fresh = scanRow(13, OPERATOR_A.id, { date_time: iso(60_000), cultivar: 'Fresh Kiosk Scan', created_seq: ++world.station.commitSeq })
  world.station.scans.unshift(fresh)
  await world.emit('scan:completed', { result: fresh }, { rooms: ['dashboard', 'kiosk'], account: OPERATOR_A.id })

  await until(() => freshListRequests(world.station, ADMIN.id).length > before,
    'Page 1 did not request a fresh snapshot for the new scan')
  await table.getByText('Fresh Kiosk Scan', { exact: true }).waitFor()
  assert.equal(await notice(admin.page, 'new Kiosk scan available').count(), 0)
  const last = freshListRequests(world.station, ADMIN.id).at(-1)
  assert.equal(last.query.page, '1')
  assert.equal((await state(admin.page)).scans[0].id, 'scan-13')
})

test('Page 2 keeps its frozen rows and offers View Latest Scans / Later for a new scan', async t => {
  const world = createWorld()
  const admin = await open(world, t, { account: ADMIN, path: '/logs?page=2' })
  const table = admin.page.getByRole('table')
  await table.getByText('Cultivar 11', { exact: true }).waitFor()
  const before = freshListRequests(world.station, ADMIN.id).length

  const fresh = scanRow(13, OPERATOR_A.id, { date_time: iso(60_000), cultivar: 'Fresh Kiosk Scan', created_seq: ++world.station.commitSeq })
  world.station.scans.unshift(fresh)
  await world.emit('scan:completed', { result: fresh }, { rooms: ['dashboard', 'kiosk'], account: OPERATOR_A.id })

  await notice(admin.page, 'new Kiosk scan available').waitFor()
  assert.match(await notice(admin.page, 'new Kiosk scan available').innerText(), /1 new Kiosk scan available/)
  assert.equal(await notice(admin.page, 'new Kiosk scan available').getByRole('button', { name: 'View Latest Scans', exact: true }).count(), 1)
  assert.equal(await notice(admin.page, 'new Kiosk scan available').getByRole('button', { name: 'Later', exact: true }).count(), 1)
  assert.equal(freshListRequests(world.station, ADMIN.id).length, before, 'A new scan must not replace frozen Page 2 rows')
  await table.getByText('Cultivar 11', { exact: true }).waitFor()

  await notice(admin.page, 'new Kiosk scan available').getByRole('button', { name: 'Later', exact: true }).click()
  await admin.page.getByRole('button', { name: 'Show latest scans', exact: true }).waitFor()
  await admin.page.getByRole('button', { name: 'Show latest scans', exact: true }).click()

  await until(() => freshListRequests(world.station, ADMIN.id).length > before,
    'Show latest scans did not request the latest snapshot')
  await table.getByText('Fresh Kiosk Scan', { exact: true }).waitFor()
  assert.equal(new URL(admin.page.url()).searchParams.get('page'), null, 'Viewing the latest scans returns to Page 1')
})

test('an expired or superseded browse snapshot recovers without surfacing a failed poll', async t => {
  const world = createWorld()
  const admin = await open(world, t, { account: ADMIN })
  const table = admin.page.getByRole('table')
  await table.getByText('Lakatan', { exact: true }).waitFor()
  const snapshot = world.station.lastSnapshotId
  world.station.expired.add(snapshot)

  await admin.page.getByLabel('Go to next page').click()
  await table.getByText('Cultivar 11', { exact: true }).waitFor()
  const expired = world.station.logResponses.filter(response => response.status === 410)
  assert.equal(expired.length, 1)
  assert.equal(expired[0].query.snapshot_id, snapshot)
  const recovery = world.station.logResponses.filter(response => response.status === 200 && !response.query.snapshot_id)
  assert.equal(recovery.at(-1).query.page, '2')
  assert.equal(await admin.page.getByRole('alert').count(), 0)

  const replacement = world.station.lastSnapshotId
  world.station.superseded.add(replacement)
  await admin.page.getByLabel('Go to previous page').click()
  await table.getByText('Lakatan', { exact: true }).waitFor()
  const superseded = world.station.logResponses.filter(response => response.status === 409)
  assert.equal(superseded.length, 1)
  assert.equal(superseded[0].query.snapshot_id, replacement)
  assert.equal(await admin.page.getByRole('alert').count(), 0)
})

test('intake and supplier changes reconcile across roles with timestamp ordering', async t => {
  const world = createWorld()
  const admin = await open(world, t, { account: ADMIN })
  const operatorA = await open(world, t, { account: OPERATOR_A })
  const operatorB = await open(world, t, { account: OPERATOR_B })

  await admin.page.getByTestId('actions').getByRole('button', { name: 'supplier', exact: true }).click()
  await waitForAction(admin, 'supplier')
  await until(async () => (await state(operatorA.page)).suppliers[0]?.name === 'Renamed Supplier', 'Supplier change did not reach Operator A')
  await until(async () => (await state(operatorB.page)).suppliers[0]?.name === 'Renamed Supplier', 'Supplier change did not reach Operator B')

  await world.emit('supplier:changed', {
    event_id: 'stale-supplier', supplier_id: 'supplier-1', kind: 'updated', actor_id: ADMIN.id,
    supplier: { id: 'supplier-1', name: 'Stale Supplier', status: 'Active', date_added: NOW, updated_at: iso(-120_000) },
  }, { rooms: ['dashboard', 'kiosk'] })
  await operatorA.page.waitForTimeout(150)
  assert.equal((await state(operatorA.page)).suppliers[0].name, 'Renamed Supplier', 'An older supplier event must not overwrite newer data')

  await admin.page.getByTestId('actions').getByRole('button', { name: 'intake', exact: true }).click()
  await waitForAction(admin, 'intake')
  await until(async () => (await state(operatorA.page)).intakes.some(intake => intake.id === 'intake-9'), 'Intake creation did not reach Operator A')
  await until(async () => (await state(operatorB.page)).intakes.some(intake => intake.id === 'intake-9'), 'Intake creation did not reach Operator B')

  await admin.page.getByTestId('actions').getByRole('button', { name: 'bulk', exact: true }).click()
  await waitForAction(admin, 'bulk')
  await until(async () => (await state(operatorA.page)).scans.find(scan => scan.id === 'scan-1')?.inventoryStatus === 'Sold', 'Owning Operator did not receive the bulk status change')
  assert.equal((await state(operatorB.page)).scans.find(scan => scan.id === 'scan-2').inventoryStatus, 'In Stock', 'Another Operator must not receive scan changes for a different owner')
  await until(async () => (await state(operatorB.page)).intakes.find(intake => intake.id === 'intake-1')?.status === 'Depleted', 'Shared intake status did not reach Operator B')
  await admin.page.getByRole('table').getByText('Sold', { exact: true }).waitFor()

  await world.emit('intake:changed', {
    event_id: 'stale-intake', intake_id: 'intake-1', kind: 'status', actor_id: ADMIN.id, status: 'Active',
    intake: { id: 'intake-1', supplier_id: 'supplier-1', supplier_name: 'Renamed Supplier', intake_date: NOW, status: 'Active', updated_at: iso(-120_000) },
  }, { rooms: ['dashboard', 'kiosk'] })
  await operatorB.page.waitForTimeout(150)
  assert.equal((await state(operatorB.page)).intakes.find(intake => intake.id === 'intake-1').status, 'Depleted', 'An older intake event must not reopen a depleted batch')
})

test('reconnect reconciles scans, intakes, admin config and notifications while frozen rows stay stable', async t => {
  const world = createWorld()
  const admin = await open(world, t, { account: ADMIN })
  const table = admin.page.getByRole('table')
  await table.getByText('Lakatan', { exact: true }).waitFor()
  const snapshot = world.station.lastSnapshotId
  const before = world.station.requests.length

  await admin.page.evaluate(() => window.stationSocket.disconnect())
  const scan = world.station.scans.find(row => row.id === 'scan-1')
  scan.revision = 2
  scan.cultivar = 'Reconnected Lakatan'
  world.station.intakes.unshift({
    id: 'intake-9', supplier_id: 'supplier-1', supplier_name: 'Renamed Supplier', batch_number: 'B-9',
    intake_date: NOW, status: 'Active', scan_count: 1, updated_at: iso(1000),
  })
  world.station.notifications = {
    items: [{ id: 'notification-1', type: 'intake_update', title: 'Registry updated', message: 'A batch changed', timestamp: NOW, read: false }],
    total: 1,
  }

  await admin.page.clock.runFor(1500)
  await admin.page.clock.runFor(600)

  await until(async () => (await state(admin.page)).scans.find(row => row.id === 'scan-1')?.cultivar === 'Reconnected Lakatan',
    'Scan history was not reconciled after reconnect')
  await until(async () => (await state(admin.page)).intakes.some(intake => intake.id === 'intake-9'),
    'Intake registry was not reconciled after reconnect')

  const afterReconnect = world.station.requests.slice(before)
  for (const path of ['/api/v1/scans', '/api/v1/intakes', '/api/v1/config', '/api/v1/users', '/api/v1/notifications']) {
    assert(afterReconnect.some(request => request.account === ADMIN.id && request.path === path),
      `Reconnect did not reconcile ${path}`)
  }
  const refreshedLogs = afterReconnect.filter(request => request.account === ADMIN.id && request.path === '/api/v1/scan-logs')
  assert(refreshedLogs.some(request => request.query.snapshot_id === snapshot),
    'Resume must keep reading the frozen browse snapshot instead of silently replacing it')
  await table.getByText('Reconnected Lakatan', { exact: true }).waitFor()
  assert.equal(await table.getByText('Lakatan', { exact: true }).count(), 0,
    'Reconnect must reconcile missed edits while preserving frozen row order')
})

test('live totals include off-page edits while inaccessible and deleted rows disappear on reconnect', async t => {
  const world = createWorld()
  const admin = await open(world, t, { account: ADMIN, path: '/logs?page=2' })
  const operator = await open(world, t, { account: OPERATOR_A })
  const snapshot = world.station.lastSnapshotId
  const before = freshListRequests(world.station, ADMIN.id).length
  const row = world.station.scans.find(scan => scan.id === 'scan-1')
  row.remaining_days = 1
  row.confidence = 80
  row.revision++
  await world.emitScan(row, { kind: 'correction', changed: ['confidence'], actorId: OPERATOR_A.id })
  await admin.page.clock.runFor(300)
  await until(async () => await admin.page.getByRole('button', { name: /At-Risk Scans/ }).getByRole('heading', { level: 3 }).innerText() === '1', 'Off-page risk KPI did not update')
  await admin.page.getByText('91.0%', { exact: true }).waitFor()
  assert.equal(freshListRequests(world.station, ADMIN.id).length, before)
  await admin.page.getByRole('table').getByText('Cultivar 11', { exact: true }).waitFor()

  // Simulate externally removed/reassigned records, not nonexistent delete UI endpoints.
  world.station.scans = world.station.scans.filter(scan => scan.id !== 'scan-11')
  row.operator_id = OPERATOR_B.id
  await admin.page.evaluate(() => window.dispatchEvent(new Event('online')))
  await operator.page.evaluate(() => window.dispatchEvent(new Event('online')))
  await until(async () => await admin.page.getByRole('table').getByText('Cultivar 11', { exact: true }).count() === 0, 'Deleted row remains visible')
  await until(async () => await operator.page.getByRole('table').getByText('Lakatan', { exact: true }).count() === 0, 'Inaccessible row remains visible')
  await admin.page.getByRole('table').getByText('Cultivar 12', { exact: true }).waitFor()
  assert.equal(freshListRequests(world.station, ADMIN.id).length, before)
  assert(world.station.snapshots.has(snapshot))
})

test('failed reconciliation retains last verified rows and recovers automatically', async t => {
  const world = createWorld()
  const admin = await open(world, t, { account: ADMIN, path: '/logs?page=2' })
  world.station.failReconcile = true
  world.station.scans.find(scan => scan.id === 'scan-11').cultivar = 'Recovered row'
  await admin.page.evaluate(() => window.dispatchEvent(new Event('online')))
  await admin.page.getByRole('alert').waitFor()
  await admin.page.getByRole('table').getByText('Cultivar 11', { exact: true }).waitFor()
  world.station.failReconcile = false
  await admin.page.clock.runFor(30_100)
  await admin.page.getByRole('table').getByText('Recovered row', { exact: true }).waitFor()
  assert.equal(await admin.page.getByRole('alert').count(), 0)
})

test('event patches never infer risk from rounded days and filter exits reconcile automatically', async t => {
  const world = createWorld()
  const admin = await open(world, t, { account: ADMIN, path: '/logs?cultivar=Lakatan' })
  const scan = world.station.scans.find(row => row.id === 'scan-1')
  scan.remaining_days = 2 // Transport rounded from an exact prediction above two.
  scan.exactRisk = false
  scan.revision++
  await world.emitScan(scan, { kind: 'correction', changed: ['spoilage_days'], actorId: OPERATOR_A.id })
  assert.equal(await admin.page.getByRole('img', { name: 'At-risk scan', exact: true }).count(), 0)
  await admin.page.clock.runFor(300)
  await until(() => world.station.requests.some(row => row.path.endsWith('/reconcile')), 'No authorized risk read')
  assert.equal(await admin.page.getByRole('img', { name: 'At-risk scan', exact: true }).count(), 0)
  scan.cultivar = 'Cardaba'
  scan.revision++
  await world.emitScan(scan, { kind: 'correction', changed: ['cultivar'], actorId: OPERATOR_A.id })
  await admin.page.clock.runFor(300)
  await until(async () => await admin.page.getByRole('button', { name: /Total Scans/ }).getByRole('heading', { level: 3 }).innerText() === '0', 'Filtered total did not reconcile')
  assert.equal(await admin.page.getByRole('table').getByText('Lakatan', { exact: true }).count(), 0)
})

test('sensor readings are never shown as live when recorded_at is stale or out of order', async t => {
  const world = createWorld()
  const admin = await open(world, t, { account: ADMIN, path: '/devices' })

  await admin.page.getByText('Stale', { exact: true }).waitFor()
  await admin.page.getByText('Sensor Reading Stale', { exact: true }).waitFor()
  assert.equal(await admin.page.getByText('Live', { exact: true }).count(), 0)
  await admin.page.getByText('26.5°C', { exact: true }).waitFor()

  await world.emit('sensor:update', {
    temperature: 27.2, humidity: 68, recorded_at: NOW, server_time: NOW, stale_after_seconds: 15,
  }, { rooms: ['dashboard'] })
  await admin.page.getByText('Live', { exact: true }).waitFor()
  await admin.page.getByText('27.2°C', { exact: true }).waitFor()

  await world.emit('sensor:update', {
    temperature: 99.9, humidity: 10, recorded_at: iso(-30_000), server_time: NOW, stale_after_seconds: 15,
  }, { rooms: ['dashboard'] })
  await admin.page.waitForTimeout(150)
  assert.equal(await admin.page.getByText('99.9°C', { exact: true }).count(), 0, 'An out-of-order reading must be ignored')
  assert.equal(await admin.page.getByText('27.2°C', { exact: true }).count(), 1)

  await admin.page.clock.runFor(16_000)
  await admin.page.getByText('Stale', { exact: true }).waitFor()
  await admin.page.getByText('Sensor Reading Stale', { exact: true }).waitFor()
  assert.equal(await admin.page.getByText('Live', { exact: true }).count(), 0)
})
