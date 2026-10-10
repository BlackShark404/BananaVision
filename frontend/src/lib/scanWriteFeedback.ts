import { toast } from 'sonner'
import { UncertainScanWrite } from './scanWrites'

/** Replays the exact retained request, even after navigating away or changing a draft. */
export function scanRetryAction(error: unknown, confirmed: (request: Readonly<Record<string, unknown>>) => void) {
  if (!(error instanceof UncertainScanWrite)) return undefined
  return { label: 'Retry previous', onClick: () => {
    void error.retry().then(() => {
      confirmed(error.request)
      toast.success('Previous change confirmed. Review the latest record before making another change.')
    }).catch(next => {
      toast.error(next instanceof Error ? next.message : 'Unable to confirm the previous change.', {
        action: scanRetryAction(next, confirmed),
      })
    })
  } }
}
