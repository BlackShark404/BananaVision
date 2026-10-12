import React, { StrictMode, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { useWebSocket } from '@/hooks/useWebSocket'
import { setToken, clearAuth } from '@/lib/auth'
import { api } from '@/lib/api'
import { ScanImage } from '@/components/ScanImage'

function Subscriber({ rooms }: { rooms: string[] }) {
  const [count, setCount] = useState(0)
  const { status } = useWebSocket({ rooms, onEvent: () => setCount(n => n + 1) })
  return <p>{rooms.join(',')}:{status}:{count}</p>
}
function Fixture() {
  const [mounted, setMounted] = useState(true)
  const [message, setMessage] = useState('')
  return <>
    <button onClick={() => setMounted(false)}>Unmount</button>
    <button onClick={() => setToken('replacement-fixture-token')}>Swap</button>
    <button onClick={clearAuth}>Logout</button>
    <button onClick={() => api.scans.detail('fixture').catch(e => setMessage(e.message))}>Request</button>
    <p>{message}</p>
    {mounted && <><Subscriber rooms={['dashboard']} /><Subscriber rooms={['dashboard', 'devices']} /></>}
    <ScanImage src="/captures/fixture/image.jpg" alt="Evidence" />
  </>
}
createRoot(document.getElementById('root')!).render(<StrictMode><Fixture /></StrictMode>)
