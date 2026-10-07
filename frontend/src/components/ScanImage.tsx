import { useState, type ImgHTMLAttributes } from "react"
import { Banana } from "lucide-react"

export function ScanImage({ src, alt, ...props }: ImgHTMLAttributes<HTMLImageElement>) {
  const [failedSource, setFailedSource] = useState<string>()
  return src && failedSource !== src ? <img {...props} src={src} alt={alt} onError={() => setFailedSource(src)} /> :
    <div className="w-full h-full flex flex-col items-center justify-center gap-2 text-muted-foreground"><Banana className="w-6 h-6 opacity-40" /><span className="text-xs">No image available</span></div>
}
