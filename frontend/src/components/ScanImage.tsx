import { useEffect, useState, type ImgHTMLAttributes } from "react"
import { Skeleton } from "@/components/ui/skeleton"
import { Banana } from "lucide-react"
import { BASE_URL } from "@/lib/api"
import { getToken } from "@/lib/auth"
import { useAuth } from "@/context/AuthContext"

type Props = ImgHTMLAttributes<HTMLImageElement> & { onUnavailable?: () => void }

export function ScanImage(props: Props) {
  const { user } = useAuth()
  return <ImageEvidence key={`${user?.id}:${user?.role}:${props.src}`} {...props} />
}

function ImageEvidence({ src, alt, className, onUnavailable, ...props }: Props) {
  const url = src ? new URL(src, BASE_URL) : null
  const protectedImage = url?.origin === new URL(BASE_URL).origin && url.pathname.startsWith('/captures/')
  const [resolved, setResolved] = useState<string | undefined>(protectedImage ? undefined : src)
  const [failed, setFailed] = useState(!src)
  useEffect(() => {
    if (!protectedImage || !src) return
    const controller = new AbortController()
    let objectUrl: string | undefined
    const token = getToken()
    fetch(src, { headers: token ? { Authorization: `Bearer ${token}` } : {},
      signal: controller.signal, cache: 'no-store' }).then(async response => {
      if (!response.ok) throw new Error('Image unavailable')
      const blob = await response.blob()
      if (controller.signal.aborted) return
      objectUrl = URL.createObjectURL(blob)
      setResolved(objectUrl)
    }).catch(() => { if (!controller.signal.aborted) setFailed(true) })
    return () => { controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [src, protectedImage])
  useEffect(() => { if (failed) onUnavailable?.() }, [failed, onUnavailable])
  if (!failed && !resolved) return <Skeleton role="status" aria-label="Loading image" className={className} />
  if (failed) return <span role="img" aria-label={failed ? "Image unavailable" : "Loading image"}
    className={`flex items-center justify-center flex-col gap-1 text-muted-foreground bg-muted/50 ${className ?? ''}`}>
    <Banana className="w-6 h-6 opacity-40" />
    {failed && <span className="text-xs">Image unavailable</span>}
  </span>
  return <img {...props} src={resolved} alt={alt} className={className} onError={event => {
    setFailed(true); props.onError?.(event)
  }} />
}
