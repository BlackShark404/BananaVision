import assert from "node:assert/strict"
import { before, after, test } from "node:test"
import { startBrowser, installEnvironment } from "./dashboard.browser.mjs"

let runtime
before(async () => { runtime = await startBrowser({ fixture: "scanrecords.fixture.tsx", auth: "persistence.auth.tsx", port: 5194 }) })
after(async () => { await runtime?.close() })
const record = () => ({ id: "old-scan", revision: 3, date_time: "2024-05-05T08:10:00+08:00", cultivar: "Lakatan", ripeness: "Ripe", confidence: 92,
  spoilage_days: "2", finger_count: 7, operator_name: "Historical Operator", source_text: "Retired supplier", inventory_status: "In Stock", flagged: false,
  images: [{camera_id: "RETIRED-CAM", file_path: "/missing.jpg"}], detections: [{camera_id:"RETIRED-CAM",camera_label:"Historic left",bounding_boxes:[]}],
  notes: [{id:"note-old",scan_id:"old-scan",text:"Stored review",author_name:"Former reviewer",timestamp:"2024-05-05T08:11:00+08:00"}],
  history: [{id:"event-1",kind:"status",timestamp:"2024-05-05T08:11:00+08:00",actor_name:"Former reviewer",reason:"Returned delivery",previous_values:{inventory_status:"Sold"},new_values:{inventory_status:"In Stock"},revision:3}],
})
async function setup(t, options = {}) {
 const context = await runtime.browser.newContext({timezoneId:"America/Los_Angeles",viewport:{width:1440,height:1200}})
 const page = await context.newPage(); page.setDefaultTimeout(7000); page.setDefaultNavigationTimeout(45000)
 t.after(() => context.close()); await installEnvironment(page)
 const state = {scan:record(),requests:[],detailStatus:200,writeStatus:200,...options}
 await page.route("**/missing.jpg", route => route.fulfill({status:404,body:"missing"}))
 await page.route("**/api/v1/**", async route => {
  const request=route.request(), url=new URL(request.url()), path=url.pathname, method=request.method()
  const headers={"access-control-allow-origin":"*","access-control-allow-headers":"*","access-control-allow-methods":"*"}
  if(method==="OPTIONS") return route.fulfill({status:204,headers})
  const body=request.postDataJSON(); state.requests.push({path,method,body,params:Object.fromEntries(url.searchParams)})
  const reply=(json,status=200)=>route.fulfill({json,status,headers}).catch(()=>{})
  if(method!=="GET") {
   if(state.writeStatus!==200)return reply({detail:"Scan changed; reload and review"},state.writeStatus)
   state.scan={...state.scan,...body,revision:state.scan.revision+1}
   return reply(state.scan)
  }
  if(path==="/api/v1/scans/old-scan")return reply(state.detailStatus===200?state.scan:{detail:"Record unavailable"},state.detailStatus)
  if(path==="/api/v1/scans")return reply({items:[],total:0,page:1,page_size:100})
  if(path==="/api/v1/scan-logs")return reply({items:[{...state.scan,source_name:"Retired supplier",remaining_days:1,temperature:null,humidity:null}],total:1,page:1,page_size:10,generated_at:state.scan.date_time,avg_confidence:92,at_risk_count:1,review_count:0,flagged_count:0,options:{sources:[],operators:[]}})
  if(path==="/api/v1/config")return reply({camera_ids:"NEW-CAM",confidence_threshold:85,data_retention_enabled:true})
  if(path==="/api/v1/users")return reply({items:[],total:0})
  if(path==="/api/v1/activity")return reply({items:[],total:0,page:1,page_size:100})
  if(path.endsWith("/notes"))return reply([])
  if(["/api/v1/devices","/api/v1/intakes","/api/v1/suppliers"].includes(path))return reply([])
  return reply({detail:`Unexpected ${path}`},404)
 })
 await page.goto(`${runtime.url}${options.path??"/scans/old-scan"}`,{waitUntil:"domcontentloaded"})
 return {page,state}
}
test("historical detail hydrates notes and audit evidence without separate notes load",async t=>{
 const {page,state}=await setup(t)
 await page.getByText("Stored review",{exact:true}).waitFor()
 await page.getByText("Returned delivery",{exact:true}).waitFor()
 assert.equal(state.requests.filter(r=>r.path.endsWith("/notes")).length,0)
 await page.getByText("No image available",{exact:true}).first().waitFor()
 assert.equal(await page.getByText("RETIRED-CAM",{exact:true}).count()>0,true)
})
test("known deleted and forbidden details have distinct outcomes",async t=>{
 for(const [detailStatus,title] of [[410,"Scan deleted"],[403,"Access denied"],[404,"Scan not found"]]){
  const {page}=await setup(t,{detailStatus}); await page.getByText(title,{exact:true}).waitFor()
  assert.equal(await page.getByRole("button",{name:"Retry",exact:true}).count(),0)
 }
})
test("correction requires reason and sends observed revision with request identity",async t=>{
 const {page,state}=await setup(t)
 await page.getByRole("button",{name:"Edit",exact:true}).click()
 await page.getByLabel("Est. Finger Count").fill("8")
 assert.equal(await page.getByRole("button",{name:"Save Changes",exact:true}).isDisabled(),true)
 await page.getByLabel("Reason for correction").fill("Recounted visible fingers")
 await page.getByRole("button",{name:"Save Changes",exact:true}).click()
 await page.getByRole("button",{name:"Edit",exact:true}).waitFor()
 const write=state.requests.find(r=>r.method==="PATCH")
 assert.equal(write.body.expected_revision,3); assert.equal(write.body.reason,"Recounted visible fingers")
 assert.match(write.body.request_id,/^[0-9a-f-]{36}$/)
})
