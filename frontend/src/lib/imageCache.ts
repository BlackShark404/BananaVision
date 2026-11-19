/** In-memory object URLs for protected evidence; the cache dies with the session token. */
const MAX_ENTRIES = 128
const MAX_BYTES = 8 * 1024 * 1024

type Entry = { url: string; bytes: number }
const entries = new Map<string, Entry>()
let totalBytes = 0

export function getCachedImage(key: string): string | undefined {
  const entry = entries.get(key)
  if (!entry) return undefined
  entries.delete(key)
  entries.set(key, entry)
  return entry.url
}

export function cacheImage(key: string, blob: Blob): string {
  const existing = entries.get(key)
  if (existing) return existing.url
  const url = URL.createObjectURL(blob)
  entries.set(key, { url, bytes: blob.size })
  totalBytes += blob.size
  for (const [oldKey, entry] of entries) {
    if (entries.size <= MAX_ENTRIES && totalBytes <= MAX_BYTES) break
    if (oldKey === key) continue
    entries.delete(oldKey)
    totalBytes -= entry.bytes
    URL.revokeObjectURL(entry.url)
  }
  return url
}

export function clearImageCache(): void {
  for (const entry of entries.values()) URL.revokeObjectURL(entry.url)
  entries.clear()
  totalBytes = 0
}
