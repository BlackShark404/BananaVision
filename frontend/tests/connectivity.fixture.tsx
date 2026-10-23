import React, { StrictMode, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { useWebSocket } from '@/hooks/useWebSocket'
import { setToken, clearAuth } from '@/lib/auth'
import { api } from '@/lib/api'
import { ScanImage } from '@/components/ScanImage'

function Subscriber({ rooms, enabled, onDelivered }: { rooms: string[]; enabled: boolean; onDelivered: () => void }) {
  const [count, setCount] = useState(0)
  const { status } = useWebSocket({ rooms, enabled, onEvent: () => { setCount(n => n + 1); onDelivered() } })
  return <p>{rooms.join(',')}:{status}:{count}</p>
}
function Fixture() {
  const [mounted, setMounted] = useState(true)
  const [message, setMessage] = useState('')
  const [session, setSession] = useState<string | null>('fixture-account')
  const [delivered, setDelivered] = useState(0)
  return <>
    <button onClick={() => setMounted(false)}>Unmount</button>
    <button onClick={() => { setToken('replacement-fixture-token'); setSession('replacement-account') }}>Swap</button>
    <button onClick={() => { clearAuth(); setSession(null) }}>Logout</button>
    <button onClick={() => { setToken('login-fixture-token'); setSession('login-account') }}>Login</button>
    <button onClick={() => api.scans.detail('fixture').catch(e => setMessage(e.message))}>Request</button>
    <p>{message}</p>
    <output data-testid="delivered">{delivered}</output>
    {/* Match ScanProvider's account/role-keyed store and disabled anonymous socket. */}
    {mounted && <React.Fragment key={session ?? 'anonymous'}>
      <Subscriber rooms={['dashboard']} enabled={!!session} onDelivered={() => setDelivered(n => n + 1)} />
      <Subscriber rooms={['dashboard', 'devices']} enabled={!!session} onDelivered={() => setDelivered(n => n + 1)} />
    </React.Fragment>}
    <ScanImage src="/captures/fixture/image.jpg" alt="Evidence" />
  </>
}
createRoot(document.getElementById('root')!).render(<StrictMode><Fixture /></StrictMode>)
