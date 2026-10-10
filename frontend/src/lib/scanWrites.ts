/** Keep uncertain writes in memory so retrying cannot create a second mutation. */
type Pending = { signature: string; body: Record<string, unknown>; send: (body: Record<string, unknown>) => Promise<unknown>; promise?: Promise<unknown> }
const pending = new Map<string, Pending>()

export function clearScanWrites() { pending.clear() }

export class UncertainScanWrite extends Error {
  readonly retry: () => Promise<unknown>
  readonly request: Readonly<Record<string, unknown>>
  constructor(message: string, retry: () => Promise<unknown>, request: Record<string, unknown>) {
    super(message); this.retry = retry; this.request = Object.freeze({ ...request })
  }
}

async function execute(scope: string, current: Pending): Promise<unknown> {
  if (pending.get(scope) !== current) throw new Error('This change is no longer pending. Reload the record.')
  if (current.promise) return current.promise
  const promise = Promise.resolve().then(() => current.send(current.body)).then(result => {
    if (pending.get(scope) === current) pending.delete(scope)
    return result
  }).catch((error: unknown) => {
    const status = typeof error === 'object' && error !== null && 'status' in error ? Number(error.status) : 0
    if (status >= 400 && status < 500 && status !== 408) {
      if (pending.get(scope) === current) pending.delete(scope)
      throw error
    }
    throw new UncertainScanWrite(`${error instanceof Error ? error.message : 'Request failed.'} The result is uncertain. Retry the previous change to confirm it.`, () => execute(scope, current), current.body)
  }).finally(() => { current.promise = undefined })
  current.promise = promise
  return promise
}

export async function scanWrite<T, P extends object>(
  scope: string, payload: P, send: (body: P & { request_id: string }) => Promise<T>,
): Promise<T> {
  // Round-trip removes undefined fields and snapshots the user's exact intent.
  const value = JSON.parse(JSON.stringify(payload)) as Record<string, unknown>
  const signature = JSON.stringify(Object.keys(value).filter(key => key !== 'expected_revision').sort().map(key => [key, value[key]]))
  let entry = pending.get(scope)
  if (entry && entry.signature !== signature) {
    const previous = entry
    throw new UncertainScanWrite('Retry the previous change before submitting a different edit; its result is still uncertain.', () => execute(scope, previous), previous.body)
  }
  if (!entry) {
    entry = { signature, body: { ...value, request_id: crypto.randomUUID() }, send: body => send(body as P & { request_id: string }) }
    pending.set(scope, entry)
  }
  entry.send = body => send(body as P & { request_id: string })
  return execute(scope, entry) as Promise<T>
}

export function scanRevision(revision: number | undefined): number {
  if (!Number.isInteger(revision) || !revision || revision < 1) throw new Error('Reload this scan before saving changes.')
  return revision
}

export function isScanConflict(error: unknown): boolean {
  return typeof error === 'object' && error !== null && 'status' in error && error.status === 409
}
