/** Keep the same identity and exact payload after an uncertain network outcome. */
const operations = new Map<string, { fingerprint: string; requestId: string; pending: boolean }>()

export function errorStatus(error: unknown): number | undefined {
  return typeof error === "object" && error !== null && "status" in error && typeof error.status === "number" ? error.status : undefined
}

export async function scanWrite<T>(scope: string, body: Record<string, unknown>, send: (payload: Record<string, unknown>) => Promise<T>): Promise<T> {
  const fingerprint = JSON.stringify(body)
  let operation = operations.get(scope)
  if (operation?.pending) throw new Error("A change to this record is still being saved.")
  if (operation && operation.fingerprint !== fingerprint) throw new Error("The previous save was not confirmed. Retry the same change before making another edit.")
  if (!operation) {
    operation = { fingerprint, requestId: crypto.randomUUID(), pending: false }
    operations.set(scope, operation)
  }
  operation.pending = true
  try {
    const result = await send({ ...body, request_id: operation.requestId })
    operations.delete(scope)
    return result
  } catch (error) {
    const status = errorStatus(error)
    // Validation/conflict/auth failures have a definite outcome; 5xx/network may have committed.
    if (status && status < 500) operations.delete(scope)
    throw error
  } finally {
    operation.pending = false
  }
}

export function requireScanRevision(revision: number | undefined): number {
  if (!Number.isInteger(revision) || !revision || revision < 1) throw new Error("Reload this scan before making changes.")
  return revision
}
