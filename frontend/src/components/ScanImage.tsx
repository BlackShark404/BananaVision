import { useEffect, useRef, useState, type ImgHTMLAttributes } from "react"
import { Skeleton } from "@/components/ui/skeleton"
import { Banana } from "lucide-react"
import { BASE_URL } from "@/lib/api"
import { getToken } from "@/lib/auth"
import { cacheImage, getCachedImage } from "@/lib/imageCache"
import { useAuth } from "@/context/AuthContext"

type Props = ImgHTMLAttributes<HTMLImageElement> & {
  onUnavailable?: () => void
  /** Wait until the placeholder approaches the viewport before requesting protected evidence. */
  defer?: boolean
}

export function ScanImage(props: Props) {
  const { user } = useAuth()
  const cacheKey = `${user?.id ?? ""}:${user?.role ?? ""}:${props.src ?? ""}`
  return <ImageEvidence key={`${user?.id}:${user?.role}:${props.src}`} {...props} cacheKey={cacheKey} />
}

function ImageEvidence({ src, alt, className, onUnavailable, defer = false, cacheKey, ...props }: Props & { cacheKey: string }) {
  // An empty BASE_URL means same-origin behind the HTTPS reverse proxy.
  const base = BASE_URL || window.location.origin
  const url = src ? new URL(src, base) : null
  const protectedImage = url?.origin === new URL(base).origin && url.pathname.startsWith('/captures/')
  const cacheable = protectedImage && url?.searchParams.get("variant") === "thumb"
  const [resolved, setResolved] = useState<string | undefined>(() => (
    protectedImage ? (cacheable ? getCachedImage(cacheKey) : undefined) : src
  ))
  const [failed, setFailed] = useState(!src)
  const [visible, setVisible] = useState(() => (
    !defer || !protectedImage || typeof IntersectionObserver === "undefined"
  ))
  const placeholder = useRef<HTMLDivElement>(null)
  const ownedUrl = useRef<string | undefined>(undefined)

  useEffect(() => () => {
    if (ownedUrl.current) URL.revokeObjectURL(ownedUrl.current)
  }, [])

  useEffect(() => {
    if (!defer || visible || !protectedImage || failed) return
    const element = placeholder.current
    if (!element) return
    const observer = new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting)) {
        observer.disconnect()
        setVisible(true)
      }
    }, { rootMargin: "200px 0px" })
    observer.observe(element)
    return () => observer.disconnect()
  }, [defer, visible, protectedImage, failed])

  useEffect(() => {
    if (!protectedImage || !src || !visible || resolved) return
    const controller = new AbortController()
    const token = getToken()
    fetch(src, { headers: token ? { Authorization: `Bearer ${token}` } : {},
      signal: controller.signal, cache: 'no-store' }).then(async response => {
      if (!response.ok) throw new Error('Image unavailable')
      const blob = await response.blob()
      if (controller.signal.aborted) return
      if (cacheable) {
        setResolved(cacheImage(cacheKey, blob))
      } else {
        ownedUrl.current = URL.createObjectURL(blob)
        setResolved(ownedUrl.current)
      }
    }).catch(() => { if (!controller.signal.aborted) setFailed(true) })
    return () => controller.abort()
  }, [src, protectedImage, visible, cacheKey, cacheable, resolved])

  useEffect(() => { if (failed) onUnavailable?.() }, [failed, onUnavailable])
  if (!failed && !resolved) return <Skeleton ref={placeholder} role="status" aria-label="Loading image" className={className} />
  if (failed) return <span role="img" aria-label={failed ? "Image unavailable" : "Loading image"}
    className={`flex items-center justify-center flex-col gap-1 text-muted-foreground bg-muted/50 ${className ?? ''}`}>
    <Banana className="w-6 h-6 opacity-40" />
    {failed && <span className="text-xs">Image unavailable</span>}
  </span>
  return <img {...props} src={resolved} alt={alt} className={className} onError={event => {
    setFailed(true); props.onError?.(event)
  }} />
}
