/** Keep uncertain writes in memory so retrying cannot create a second mutation. */
type Pending = { signature: string; body: Record<string, unknown>; promise?: Promise<unknown> }
const pending = new Map<string, Pending>()

export function clearScanWrites() { pending.clear() }

export async function scanWrite<T, P extends object>(
  scope: string, payload: P, send: (body: P & { request_id: string }) => Promise<T>,
): Promise<T> {
  // Round-trip removes undefined fields and snapshots the user's exact intent.
  const value = JSON.parse(JSON.stringify(payload)) as Record<string, unknown>
  const signature = JSON.stringify(Object.keys(value).filter(key => key !== 'expected_revision').sort().map(key => [key, value[key]]))
  let entry = pending.get(scope)
  if (entry && entry.signature !== signature) throw new Error("Retry the previous change before submitting a different edit; its result is still uncertain.")
  if (!entry) {
    entry = { signature, body: { ...value, request_id: crypto.randomUUID() } }
    pending.set(scope, entry)
  }
  if (entry.promise) return entry.promise as Promise<T>
  const current = entry
  const promise = Promise.resolve().then(() => send(current.body as P & { request_id: string })).then(result => {
    if (pending.get(scope) === current) pending.delete(scope)
    return result
  }).catch((error: unknown) => {
    const status = typeof error === 'object' && error !== null && 'status' in error ? Number(error.status) : 0
    // A server rejection is definite; network/timeout/5xx may have lost an acknowledgement.
    if (status >= 400 && status < 500 && status !== 408 && pending.get(scope) === current) pending.delete(scope)
    throw error
  }).finally(() => { current.promise = undefined })
  entry.promise = promise
  return promise
}

export function scanRevision(revision: number | undefined): number {
  if (!Number.isInteger(revision) || !revision || revision < 1) throw new Error('Reload this scan before saving changes.')
  return revision
}

export function isScanConflict(error: unknown): boolean {
  return typeof error === 'object' && error !== null && 'status' in error && error.status === 409
}
