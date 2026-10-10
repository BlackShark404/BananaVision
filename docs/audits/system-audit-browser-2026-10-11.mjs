// Audit characterization of actual components with mocked HTTP/WebSocket only.
// Explicit envFile:false prevents Vite loading the station's frontend .env files.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createRequire } from 'node:module'
import { fileURLToPath, pathToFileURL } from 'node:url'
import path from 'node:path'
import os from 'node:os'
import { mkdtemp } from 'node:fs/promises'
import { installEnvironment } from '../../frontend/tests/dashboard.browser.mjs'

const frontend = fileURLToPath(new URL('../../frontend/', import.meta.url))
const require = createRequire(path.join(frontend, 'package.json'))
const { createServer } = await import(pathToFileURL(require.resolve('vite')).href)
const { default: react } = await import(pathToFileURL(require.resolve('@vitejs/plugin-react')).href)
const { default: tailwindcss } = await import(pathToFileURL(require.resolve('@tailwindcss/vite')).href)
const { chromium } = await import(pathToFileURL(process.env.PLAYWRIGHT_MODULE).href)
const config = { camera_ids:'CAM-001', camera_device_ids:[0], confidence_threshold:85,
  data_retention_enabled:true, revision:1, applied_revision:1, application_status:'applied',
  application_error:null, retention_days:14, retention_policy:'unreferenced_captures_only',
  restart_required:false, applied_camera_ids:'CAM-001', applied_camera_device_ids:[0], legacy_conflict:false }
const scan = { id:'scan-audit', revision:1, date_time:'2026-10-10T12:00:00+08:00',
  cultivar:'Lakatan', ripeness:'Ripe', confidence:90, spoilage_days:'5-7', finger_count:5,
  operator_name:'Audit Admin', inventory_status:'In Stock', intake_id:'intake-audit' }

async function until(predicate) {
  for(let i=0;i<200;i++) { if(await predicate()) return; await new Promise(r=>setTimeout(r,25)) }
  assert.fail('Expected characterization state was not reached')
}
async function setup(t, fixture, options={}) {
  const cacheDir=await mkdtemp(path.join(os.tmpdir(),'bv-audit-browser-'))
  console.log('AUDIT_TEMP='+cacheDir)
  const server=await createServer({root:frontend,configFile:false,envFile:false,logLevel:'error',cacheDir,
    define:{'import.meta.env.VITE_API_URL':JSON.stringify('http://127.0.0.1:8000')},
    plugins:[react(),tailwindcss(),{name:'audit-fixture',configureServer(vite) {
      vite.middlewares.use(async(req,res,next)=>{
        if(!/^\/(dashboard|logs)(\?|$)/.test(req.url??'')) return next()
        const html=await vite.transformIndexHtml(req.url,`<html><body><div id="root"></div><script type="module" src="/tests/${fixture}"></script></body></html>`)
        res.setHeader('Content-Type','text/html');res.end(html)
      })
    }}],
    resolve:{alias:[{find:'@/context/AuthContext',replacement:path.join(frontend,'tests/persistence.auth.tsx')},{find:'@',replacement:path.join(frontend,'src')}]},
    optimizeDeps:{entries:[`tests/${fixture}`]},server:{host:'127.0.0.1',port:5213,strictPort:true}})
  await server.listen()
  t.after(()=>server.close())
  const browser=await chromium.launch({headless:true,channel:'chrome'})
  t.after(()=>browser.close())
  const ctx=await browser.newContext({viewport:{width:1440,height:1000}})
  const page=await ctx.newPage();page.setDefaultTimeout(10000);page.setDefaultNavigationTimeout(45000)
  const errors=[];page.on('pageerror',e=>errors.push(e.message));t.after(()=>assert.deepEqual(errors,[]))
  await installEnvironment(page)
  const state={failIntakes:false,requests:[],intakes:[{id:'intake-audit',supplier_id:'supplier-audit',source:'Farm',status:'Active',intake_date:'2026-10-10',scan_count:1}],...options}
  await page.route('**/api/v1/**',async route=>{
    const request=route.request(),url=new URL(request.url())
    const headers={'access-control-allow-origin':'*','access-control-allow-headers':'*','access-control-allow-methods':'*'}
    const reply=(json,status=200)=>route.fulfill({json,status,headers}).catch(()=>{})
    if(request.method()==='OPTIONS')return reply({},204)
    state.requests.push(url.pathname)
    if(url.pathname==='/api/v1/config/maintenance' && state.maintenance) return state.maintenance(reply)
    if(url.pathname==='/api/v1/config')return reply(config)
    if(url.pathname==='/api/v1/config/maintenance')return reply({state:'ready',active_operations:0})
    if(url.pathname==='/api/v1/scans')return reply({items:[scan],total:1,page:1,page_size:100})
    if(url.pathname==='/api/v1/intakes')return state.failIntakes?reply({detail:'Audit intake failure'},503):reply(state.intakes)
    if(url.pathname==='/api/v1/suppliers')return reply([{id:'supplier-audit',name:'Farm',status:'Active'}])
    if(url.pathname==='/api/v1/users'||url.pathname==='/api/v1/activity')return reply({items:[],total:0,page:1,page_size:100})
    if(url.pathname==='/api/v1/devices'||url.pathname==='/api/v1/cameras')return reply([])
    return reply({detail:'Unexpected audit request'},404)
  })
  const url=`http://127.0.0.1:${server.httpServer.address().port}`
  await page.goto(url+'/dashboard'+(fixture.startsWith('persistence')?'?screen=inventory':''),{waitUntil:'domcontentloaded'})
  return {page,state}
}
const snapshot=async page=>JSON.parse(await page.getByTestId('state').textContent())
const hands=page=>page.locator('[data-slot="card"]').filter({has:page.getByText('Total Hands',{exact:true})}).getByRole('heading')

test('characterizes failed initial intake request showing successful zero inventory',async t=>{
  const {page,state}=await setup(t,'persistence.fixture.tsx',{failIntakes:true})
  await until(async()=>await page.getByTestId('state').count() && !(await snapshot(page)).loading && state.requests.includes('/api/v1/intakes'))
  await until(async()=>(await snapshot(page)).scans.length===1)
  assert.deepEqual((await snapshot(page)).intakes,[])
  assert.equal((await snapshot(page)).error,null)
  assert.equal(await hands(page).textContent(),'0')
  assert.equal(await page.getByRole('alert').count(),0)
})

test('characterizes failed intake refresh retaining silently stale stock eligibility',async t=>{
  const {page,state}=await setup(t,'persistence.fixture.tsx')
  await until(async()=>await page.getByTestId('state').count() && (await snapshot(page)).intakes.length===1 && !(await snapshot(page)).loading)
  assert.equal(await hands(page).textContent(),'1')
  state.failIntakes=true;state.intakes[0]={...state.intakes[0],status:'Depleted'}
  const before=state.requests.filter(p=>p==='/api/v1/intakes').length
  await page.evaluate(()=>{history.pushState({},'', '/logs?screen=inventory');window.dispatchEvent(new PopStateEvent('popstate'))})
  await until(()=>state.requests.filter(p=>p==='/api/v1/intakes').length>before)
  await until(async()=>!(await snapshot(page)).loading)
  assert.equal((await snapshot(page)).intakes[0].status,'Active')
  assert.equal(await hands(page).textContent(),'1')
  assert.equal(await page.getByRole('alert').count(),0)
})

test('characterizes delayed old maintenance ready response replacing recovery-required',async t=>{
  let calls=0,release
  const {page}=await setup(t,'maintenance.fixture.tsx',{maintenance:async reply=>{
    calls++
    if(calls===1) { await new Promise(r=>release=r);return reply({state:'ready',active_operations:0}) }
    return reply({state:'recovery-required',active_operations:0})
  }})
  await until(()=>Boolean(release))
  await page.clock.runFor(5100)
  await until(()=>calls===2)
  const reset=page.getByRole('button',{name:'Reset Defaults'})
  await until(()=>reset.isDisabled())
  release()
  await until(async()=>!(await reset.isDisabled()))
  assert.equal(calls,2,'No newer ready request caused this transition')
})
