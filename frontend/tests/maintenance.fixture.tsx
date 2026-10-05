import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { Toaster } from 'sonner'
import { AdminProvider, useAdmin } from '../src/context/AdminContext'
import SystemConfig from '../src/pages/admin/SystemConfig'
import '../src/index.css'
function Fixture() {
  const admin = useAdmin()
  return <><output hidden data-testid="config">{JSON.stringify(admin.config)}</output><button onClick={() => void admin.reloadConfig()}>Fixture refresh</button><main className="p-6"><SystemConfig /></main><Toaster /></>
}
createRoot(document.getElementById('root')!).render(<BrowserRouter><AdminProvider><Fixture /></AdminProvider></BrowserRouter>)
