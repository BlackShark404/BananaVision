import { createRoot } from 'react-dom/client'
import { useState } from 'react'
import { BrowserRouter } from 'react-router-dom'
import { Toaster } from 'sonner'
import { AdminProvider, useAdmin } from '../src/context/AdminContext'
import SystemConfig from '../src/pages/admin/SystemConfig'
import '../src/index.css'
function Fixture() {
  const admin = useAdmin()
  const [open, setOpen] = useState(true)
  return <><output hidden data-testid="config">{JSON.stringify(admin.config)}</output><button onClick={() => void admin.reloadConfig()}>Fixture refresh</button><button onClick={() => setOpen(false)}>Fixture close</button><main className="p-6">{open && <SystemConfig />}</main><Toaster /></>
}
createRoot(document.getElementById('root')!).render(<BrowserRouter><AdminProvider><Fixture /></AdminProvider></BrowserRouter>)
