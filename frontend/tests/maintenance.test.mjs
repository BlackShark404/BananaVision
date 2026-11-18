import assert from 'node:assert/strict'
import { before, after, test } from 'node:test'
import { startBrowser, installEnvironment } from './dashboard.browser.mjs'
let runtime
before(async () => { runtime = await startBrowser({ fixture:'maintenance.fixture.tsx', auth:'persistence.auth.tsx', port:5197 }) })
after(async () => runtime?.close())
const config = {camera_ids:'CAM-001',camera_device_ids:[0],confidence_threshold:85,data_retention_enabled:true,revision:1,applied_revision:1,application_status:'applied',application_error:null,retention_days:14,retention_policy:'unreferenced_captures_only',restart_required:false,applied_camera_ids:'CAM-001',applied_camera_device_ids:[0],legacy_conflict:false}
const until = async f => { for(let i=0;i<100;i++){if(await f())return;await new Promise(r=>setTimeout(r,30))}assert.fail('Condition not reached') }
async function setup(t, options={}) {
 const ctx=await runtime.browser.newContext({viewport:{width:1440,height:1000}});t.after(()=>ctx.close());const page=await ctx.newPage();page.setDefaultTimeout(5000);page.setDefaultNavigationTimeout(45000);await installEnvironment(page)
 const state={config:{...config}, requests:[], ...options}
 await page.route('**/api/v1/**',async route=>{const req=route.request(),path=new URL(req.url()).pathname,method=req.method();const headers={'access-control-allow-origin':'*','access-control-allow-headers':'*','access-control-allow-methods':'*'};const reply=(json,status=200)=>route.fulfill({json,status,headers}).catch(()=>{});if(method==='OPTIONS')return reply({},204)
 const body=req.headers()['content-type']?.includes('application/json')?req.postDataJSON():null;state.requests.push({path,method,body})
 if(path==='/api/v1/config'&&method==='GET'){const saved={...state.config};if(state.holdRead)await state.holdRead();return state.failLoad?reply({detail:'Offline'},503):reply(saved)}
 if(path==='/api/v1/config'&&method==='PATCH'){if(state.conflict)return reply({detail:'Configuration changed; reload to review'},409);state.config={...state.config,...body,revision:state.config.revision+1};return reply(state.config)}
 if(path==='/api/v1/config/maintenance')return state.maintenance ? state.maintenance(reply) : reply({state:'ready',active_operations:0})
 if(path==='/api/v1/config/maintenance/recover')return reply({state:'ready',active_operations:0})
 if(path==='/api/v1/cameras/discovery')return state.discoveryFailure?reply({detail:'Device list unavailable'},503):reply(state.discovery??{backend:'dshow',devices:[],error:null})
 if(path==='/api/v1/cameras')return reply([{device_id:0,camera_id:'CAM-001',label:'CAM-001',online:false}])
 if(path==='/api/v1/cameras/mapping')return reply({...state.config,revision:2,application_status:'partial',application_error:'Camera 0 failed',results:{'0':false}})
 if(path==='/api/v1/config/backups')return reply({id:body.operation_id,status:'completed',filename:'station.zip',manifest:{tables:18}})
 if(path==='/api/v1/config/restores/validate'){if(state.holdValidation)await state.holdValidation();return state.invalid?reply({detail:'Invalid archive'},422):reply({validation_id:'v1',token:'secret-token',manifest:{tables:18},expires_at:'2099-01-01T00:00:00Z'})}
 if(path==='/api/v1/config/restores'){if(state.holdRestore)await state.holdRestore();return reply({detail:'Rollback verified; restore failed'},503)}
 if(path==='/api/v1/config/restart'){if(state.holdPower)await state.holdPower();return reply({id:body.operation_id,status:'accepted',message:'Restart accepted'})}
 if(path==='/api/v1/devices')return reply([])
 if(path==='/api/v1/users'||path==='/api/v1/activity')return reply({items:[],total:0})
 return reply({detail:'Unexpected request'},404) })
 await page.goto(runtime.url+'/dashboard',{waitUntil:'domcontentloaded'});await page.getByRole('heading',{name:'System Configuration'}).waitFor();return {page,state}
}
test('failed initial load prevents editing fallback and permits retry',async t=>{const {page,state}=await setup(t,{failLoad:true});await until(()=>page.getByRole('button',{name:'Retry configuration'}).count());await page.getByText('Configuration details',{exact:true}).click();assert(await page.getByRole('button',{name:'Reset All Settings'}).isDisabled());assert(await page.getByRole('button',{name:'Calibrate Camera Positions'}).isDisabled());state.failLoad=false;await page.getByRole('button',{name:'Retry configuration'}).click();await until(async()=>!(await page.getByRole('button',{name:'Reset All Settings'}).isDisabled()))})

test('AI settings distinguish the current detection cutoff from result review', async t => {
 const {page,state}=await setup(t,{config:{...config,detection_confidence_threshold:42.5}})
 await page.getByRole('tab',{name:'Detection',exact:true}).click()
 await page.getByText('Review Confidence Threshold',{exact:true}).waitFor()
 await page.getByText('Model information',{exact:true}).click()
 await page.getByText('Current YOLO detection cutoff: 42.5%',{exact:true}).waitFor()
 assert.equal(JSON.parse(await page.getByTestId('config').textContent()).detectionConfidenceThreshold,42.5)
 assert.equal(await page.getByRole('slider').getAttribute('aria-valuenow'),'85')
 await page.getByRole('slider').press('ArrowLeft')
 await page.getByText(/Results below 84% are flagged for review/).waitFor()
 await page.getByText('Current YOLO detection cutoff: 42.5%',{exact:true}).waitFor()
 await page.getByRole('button',{name:'Save Changes',exact:true}).click()
 await until(()=>state.requests.some(r=>r.method==='PATCH'))
 assert.deepEqual(state.requests.find(r=>r.method==='PATCH').body,{
   confidence_threshold:84,expected_revision:1,
 })
})

test('two camera slots expand to four and save physical indices with names', async t => {
 const {page,state}=await setup(t,{config:{...config,camera_ids:'TOP, LEFT',camera_device_ids:[0,1]}})
 await page.getByRole('button',{name:'Add Camera',exact:true}).click()
 await page.getByRole('button',{name:'Add Camera',exact:true}).click()
 assert(await page.getByRole('button',{name:'Add Camera',exact:true}).isDisabled())
 for (let index=0;index<4;index++) {
  await page.getByText(`Advanced device settings for camera ${index+1}`,{exact:true}).click()
  await page.getByLabel(`Device index for camera ${index+1}`,{exact:true}).fill(String(index+1))
 }
 await page.getByRole('button',{name:'Save Changes',exact:true}).click()
 await until(()=>state.requests.some(r=>r.method==='PATCH'))
 assert.deepEqual(state.requests.find(r=>r.method==='PATCH').body,{
  expected_revision:1,camera_ids:'TOP, LEFT, CAM-003, CAM-004',camera_device_ids:[1,2,3,4],
 })
})

test('device-only mapping edits survive refresh and send only the changed mapping', async t => {
 const {page,state}=await setup(t)
 await page.getByText('Advanced device settings for camera 1',{exact:true}).click()
 await page.getByLabel('Device index for camera 1',{exact:true}).fill('4')
 await page.getByRole('button',{name:'Fixture refresh'}).click()
 await until(()=>state.requests.filter(r=>r.path==='/api/v1/config'&&r.method==='GET').length>=2)
 assert.equal(await page.getByLabel('Device index for camera 1',{exact:true}).inputValue(),'4')
 await page.getByRole('button',{name:'Save Changes',exact:true}).click()
 await until(()=>state.requests.some(r=>r.method==='PATCH'))
 assert.deepEqual(state.requests.find(r=>r.method==='PATCH').body,{expected_revision:1,camera_device_ids:[4]})
})

test('named device inventory exposes unused index and replaces missing fourth camera', async t => {
 const {page,state}=await setup(t,{config:{...config,camera_ids:'TOP, LEFT, RIGHT, REAR',camera_device_ids:[0,1,3,4]},discovery:{
  backend:'dshow',error:null,devices:[
   {device_id:0,name:'ACER HD User Facing',device_uid:'builtin',configured_camera_id:'TOP',online:true},
   {device_id:1,name:'EMEET SmartCam C100 2K',device_uid:'emeet-one',configured_camera_id:'LEFT',online:true},
   {device_id:2,name:'EMEET SmartCam C100 2K',device_uid:'emeet-two',configured_camera_id:null,online:false},
   {device_id:3,name:'Rapoo Camera',device_uid:'rapoo',configured_camera_id:'RIGHT',online:true},
  ]}})
 await page.getByText('Device discovery details',{exact:true}).click()
 await page.getByText(/Index 2 — EMEET.*emeet-two.*Not assigned/).waitFor()
 assert.match(await page.getByRole('combobox',{name:'Detected device for camera 4'}).textContent(),/Index 4.*not detected/)
 await page.getByRole('combobox',{name:'Detected device for camera 4'}).click()
 await page.getByRole('option',{name:/Index 2 — EMEET/}).click()
 assert.equal(await page.getByLabel('Device index for camera 4',{exact:true}).inputValue(),'2')
 await page.getByRole('button',{name:'Save Changes',exact:true}).click()
 await until(()=>state.requests.some(r=>r.method==='PATCH'))
 assert.deepEqual(state.requests.find(r=>r.method==='PATCH').body,{expected_revision:1,camera_device_ids:[0,1,3,2]})
})

test('failed device discovery preserves saved mapping and manual editing', async t => {
 const {page,state}=await setup(t,{discoveryFailure:true})
 await page.getByRole('alert').filter({hasText:'Device list unavailable'}).waitFor()
 await page.getByText('Advanced device settings for camera 1',{exact:true}).click()
 await page.getByLabel('Device index for camera 1',{exact:true}).fill('2')
 state.discoveryFailure=false
 await page.getByRole('button',{name:'Refresh Device List'}).click()
 await until(()=>state.requests.filter(r=>r.path==='/api/v1/cameras/discovery').length===2)
 assert.equal(await page.getByLabel('Device index for camera 1',{exact:true}).inputValue(),'2')
 assert.equal(state.requests.filter(r=>r.method==='PATCH').length,0)
})

test('duplicate and empty device indices cannot be saved', async t => {
 const {page,state}=await setup(t,{config:{...config,camera_ids:'TOP, LEFT',camera_device_ids:[0,1]}})
 await page.getByText('Advanced device settings for camera 2',{exact:true}).click()
 const index=page.getByLabel('Device index for camera 2',{exact:true})
 await index.fill('0')
 await page.getByRole('button',{name:'Save Changes',exact:true}).click()
 await page.clock.runFor(100)
 assert.equal(state.requests.filter(r=>r.method==='PATCH').length,0)
 await index.fill('')
 await page.getByRole('button',{name:'Save Changes',exact:true}).click()
 await page.clock.runFor(100)
 assert.equal(state.requests.filter(r=>r.method==='PATCH').length,0)
 await index.fill('4')
 await page.getByRole('button',{name:'Save Changes',exact:true}).click()
 await until(()=>state.requests.some(r=>r.method==='PATCH'))
 assert.deepEqual(state.requests.find(r=>r.method==='PATCH').body,{expected_revision:1,camera_device_ids:[0,4]})
})
test('threshold sends only changed fields and loaded revision; conflict retains draft',async t=>{const {page,state}=await setup(t);await page.getByRole('tab',{name:'Detection',exact:true}).click();await page.getByRole('slider').press('ArrowLeft');await page.getByRole('button',{name:'Save Changes',exact:true}).click();await until(()=>state.requests.some(r=>r.method==='PATCH'));assert.deepEqual(state.requests.find(r=>r.method==='PATCH').body,{confidence_threshold:84,expected_revision:1});await until(async()=>JSON.parse(await page.getByTestId('config').textContent()).revision===2);state.conflict=true;await page.getByRole('slider').press('ArrowLeft');await page.getByRole('button',{name:'Save Changes',exact:true}).click();await page.getByText(/Configuration changed elsewhere/).first().waitFor();assert.equal(await page.getByRole('slider').getAttribute('aria-valuenow'),'83');assert(await page.getByRole('button',{name:'Reload saved settings'}).count())})
test('late read cannot replace a more recent saved revision',async t=>{const {page,state}=await setup(t);let release;state.holdRead=()=>new Promise(r=>release=r);await page.getByRole('button',{name:'Fixture refresh'}).click();await until(()=>Boolean(release));await page.getByRole('tab',{name:'Detection',exact:true}).click();await page.getByRole('slider').press('ArrowLeft');await page.getByRole('button',{name:'Save Changes',exact:true}).click();await until(async()=>JSON.parse(await page.getByTestId('config').textContent()).revision===2);release();await until(async()=>JSON.parse(await page.getByTestId('config').textContent()).confidenceThreshold===84)})
test('camera partial application is never reported as fully applied',async t=>{const {page,state}=await setup(t);await page.getByRole('button',{name:'Calibrate Camera Positions'}).click();await page.getByRole('button',{name:'Save Mapping'}).click();await page.getByRole('alert').filter({hasText:'Camera 0 failed'}).waitFor();assert.equal(state.requests.find(r=>r.path.endsWith('/mapping')).body.expected_revision,1);assert.equal(await page.getByText('Camera mapping saved and camera manager refreshed').count(),0)})
test('backup completes server-side; restore requires validation and explicit replacement',async t=>{const {page,state}=await setup(t,{invalid:true});await page.getByRole('tab',{name:'Data & Backups',exact:true}).click();await page.getByRole('button',{name:'Create Backup',exact:true}).click();await page.getByRole('button',{name:'Download Backup'}).waitFor();await page.getByRole('button',{name:'Restore from Backup'}).click();await page.getByLabel('Backup archive').setInputFiles({name:'bad.zip',mimeType:'application/zip',buffer:Buffer.from('bad')});await page.getByRole('button',{name:'Validate Backup'}).click();await page.getByText('Invalid archive',{exact:false}).first().waitFor();assert(!state.requests.some(r=>r.path==='/api/v1/config/restores'));state.invalid=false;await page.getByRole('button',{name:'Validate Backup'}).click();await page.getByLabel('Administrator password').fill('test-password');await page.getByLabel('Type REPLACE to confirm').fill('REPLACE');await page.getByRole('button',{name:'Replace Station Data'}).click();await page.getByText('Rollback verified; restore failed',{exact:false}).first().waitFor();assert.equal(state.requests.filter(r=>r.path==='/api/v1/config/restores').length,1)})
test('power submission is single-flight and reports acceptance rather than completion',async t=>{let release;const {page,state}=await setup(t,{holdPower:()=>new Promise(r=>release=r)});await page.getByRole('tab',{name:'Power',exact:true}).click();await page.getByRole('button',{name:'Restart',exact:true}).click();await page.getByRole('button',{name:'Restart Now'}).click();await until(()=>Boolean(release));assert(await page.getByRole('button',{name:'Restart Now'}).isDisabled());assert.equal(state.requests.filter(r=>r.path.endsWith('/restart')).length,1);release();await page.getByText(/Restart accepted/).first().waitFor();assert(await page.getByRole('button',{name:'Restart',exact:true}).isDisabled())})


test('new backup after completion gets a new operation ID',async t=>{const {page,state}=await setup(t);await page.getByRole('tab',{name:'Data & Backups',exact:true}).click();await page.getByRole('button',{name:'Create Backup',exact:true}).click();await page.getByRole('button',{name:'Download Backup'}).waitFor();await page.getByRole('button',{name:'Create Backup',exact:true}).click();await until(()=>state.requests.filter(r=>r.path.endsWith('/backups')).length===2);const requests=state.requests.filter(r=>r.path.endsWith('/backups'));assert.notEqual(requests[0].body.operation_id,requests[1].body.operation_id)})

test('maintenance polling does not issue a scheduled request after unmount', async t => {
 const {page,state}=await setup(t)
 const polls=()=>state.requests.filter(r=>r.path==='/api/v1/config/maintenance').length
 await until(()=>polls()===1)
 await page.getByRole('button',{name:'Fixture close'}).click()
 const before=polls()
 await page.clock.runFor(6000)
 await new Promise(r=>setTimeout(r,100))
 assert.equal(polls(),before)
})

test('old maintenance poll cannot overwrite a newer recovery result', async t => {
 let calls=0,release,replied=false
 const {page}=await setup(t,{maintenance:async reply=>{
  calls++
  if(calls===2) {await new Promise(r=>release=r);await reply({state:'recovery-required',active_operations:0});replied=true;return}
  return reply({state:'recovery-required',active_operations:0})
 }})
 await page.getByRole('tab',{name:'Power',exact:true}).click()
 await page.getByLabel('Recovery administrator password').waitFor()
 await page.clock.runFor(5100)
 await until(()=>Boolean(release))
 await page.getByLabel('Recovery administrator password').fill('mock-only')
 await page.getByRole('button',{name:'Retry Restore Recovery'}).click()
 await until(()=>page.getByLabel('Recovery administrator password').count().then(n=>n===0))
 release()
 await until(()=>replied)
 await page.clock.runFor(100)
 await new Promise(r=>setTimeout(r,100))
 assert.equal(await page.getByLabel('Recovery administrator password').count(),0)
})


test('one save bar spans tabs and immediate cleanup saves preserve camera and threshold drafts', async t => {
 const {page,state}=await setup(t)
 assert.equal(await page.getByRole('region',{name:'Unsaved configuration changes'}).count(),0)
 await page.getByRole('button',{name:'Rename camera 1: CAM-001'}).click()
 await page.getByRole('textbox',{name:'Camera 1 name'}).fill('TOP')
 await page.getByRole('textbox',{name:'Camera 1 name'}).press('Enter')
 await page.getByRole('tab',{name:'Detection',exact:true}).click()
 await page.getByRole('slider').press('ArrowLeft')
 await page.getByRole('tab',{name:'Data & Backups',exact:true}).click()
 assert.equal(await page.getByRole('button',{name:'Save Changes',exact:true}).count(),1)
 await page.getByRole('switch',{name:'Automatic capture cleanup'}).click()
 await until(async()=>JSON.parse(await page.getByTestId('config').textContent()).revision===2)
 assert.deepEqual(state.requests.find(r=>r.method==='PATCH').body,{data_retention_enabled:false,expected_revision:1})
 await page.getByRole('button',{name:'Save Changes',exact:true}).click()
 await until(async()=>JSON.parse(await page.getByTestId('config').textContent()).revision===3)
 assert.deepEqual(state.requests.filter(r=>r.method==='PATCH')[1].body,{camera_ids:'TOP',confidence_threshold:84,expected_revision:2})
 assert.equal(await page.getByRole('region',{name:'Unsaved configuration changes'}).count(),0)
})

test('global reset is explicit, reviewable and discardable across tabs', async t => {
 const {page,state}=await setup(t,{config:{...config,camera_ids:'TOP',camera_device_ids:[3],confidence_threshold:70,data_retention_enabled:false}})
 await page.getByText('Configuration details',{exact:true}).click()
 await page.getByRole('button',{name:'Reset All Settings'}).click()
 await page.getByRole('button',{name:'Rename camera 1: CAM-001'}).waitFor()
 await page.getByRole('tab',{name:'Detection',exact:true}).click()
 assert.equal(await page.getByRole('slider').getAttribute('aria-valuenow'),'80')
 assert.equal(state.requests.filter(r=>r.method==='PATCH').length,0)
 await page.getByRole('button',{name:'Discard',exact:true}).click()
 assert.equal(await page.getByRole('slider').getAttribute('aria-valuenow'),'70')
 await page.getByRole('tab',{name:'Cameras',exact:true}).click()
 await page.getByRole('button',{name:'Rename camera 1: TOP'}).waitFor()
 assert.equal(await page.getByLabel('Device index for camera 1',{exact:true}).inputValue(),'3')
})

test('restore dialog guards pending work and clears credentials when dismissed', async t => {
 let releaseValidation,releaseRestore
 const {page,state}=await setup(t,{holdValidation:()=>new Promise(r=>releaseValidation=r),holdRestore:()=>new Promise(r=>releaseRestore=r)})
 await page.getByRole('tab',{name:'Data & Backups',exact:true}).click()
 assert.equal(await page.getByLabel('Backup archive').count(),0)
 await page.getByRole('button',{name:'Restore from Backup'}).click()
 const dialog=page.getByRole('dialog',{name:'Restore Station Data'})
 assert(await page.getByRole('button',{name:'Validate Backup'}).isDisabled())
 await page.getByLabel('Backup archive').setInputFiles({name:'station.zip',mimeType:'application/zip',buffer:Buffer.from('fixture')})
 await page.getByRole('button',{name:'Validate Backup'}).click()
 await until(()=>Boolean(releaseValidation))
 await page.keyboard.press('Escape')
 assert(await dialog.isVisible())
 assert.equal(await dialog.getByRole('button',{name:'Close',exact:true}).count(),0)
 releaseValidation()
 await page.getByLabel('Administrator password').fill('fixture-password')
 assert(await page.getByRole('button',{name:'Replace Station Data'}).isDisabled())
 await page.getByLabel('Type REPLACE to confirm').fill('REPLACE')
 await dialog.getByRole('button',{name:'Close',exact:true}).click()
 await page.getByRole('button',{name:'Restore from Backup'}).click()
 assert.equal(await page.getByLabel('Administrator password').inputValue(),'')
 assert.equal(await page.getByLabel('Type REPLACE to confirm').inputValue(),'')
 await page.getByLabel('Administrator password').fill('fixture-password')
 await page.getByLabel('Type REPLACE to confirm').fill('REPLACE')
 await page.getByRole('button',{name:'Replace Station Data'}).click()
 await until(()=>Boolean(releaseRestore))
 await page.keyboard.press('Escape')
 assert(await dialog.isVisible())
 assert(await page.getByRole('button',{name:'Restoring Station Data…'}).isDisabled())
 assert.equal(state.requests.filter(r=>r.path==='/api/v1/config/restores').length,1)
 releaseRestore()
 await page.getByText('Rollback verified; restore failed',{exact:false}).first().waitFor()
 await page.getByLabel('Backup archive').setInputFiles({name:'other.zip',mimeType:'application/zip',buffer:Buffer.from('other')})
 assert.equal(await page.getByLabel('Administrator password').count(),0)
 assert.equal(await page.getByRole('button',{name:'Replace Station Data'}).count(),0)
})

test('backup result remains available after switching tabs', async t => {
 const {page,state}=await setup(t)
 await page.getByRole('tab',{name:'Data & Backups',exact:true}).click()
 await page.getByRole('button',{name:'Create Backup',exact:true}).click()
 await page.getByRole('button',{name:'Download Backup'}).waitFor()
 await page.getByRole('tab',{name:'Cameras',exact:true}).click()
 await page.getByRole('tab',{name:'Data & Backups',exact:true}).click()
 await page.getByRole('button',{name:'Download Backup'}).waitFor()
 assert.equal(state.requests.filter(r=>r.path.endsWith('/backups')).length,1)
})

test('station status stops reporting ready after maintenance polling fails', async t => {
 let failed=false
 const {page}=await setup(t,{maintenance:reply=>failed?reply({detail:'Unavailable'},503):reply({state:'ready',active_operations:0})})
 await page.getByRole('tab',{name:'Power',exact:true}).click()
 const status=page.getByRole('tabpanel',{name:'Power',exact:true}).getByRole('status')
 await until(async()=>(await status.textContent()).includes('ready'))
 assert.match(await status.getAttribute('class'),/emerald/)
 failed=true
 await page.clock.runFor(5100)
 await until(async()=>(await status.textContent()).includes('Status unavailable'))
 assert.doesNotMatch(await status.getAttribute('class'),/emerald/)
})
