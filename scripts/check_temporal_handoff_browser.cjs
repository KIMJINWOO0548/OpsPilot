/* Actual Chromium source UI; synthetic API interception, no backend/competitor claim. */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_CORE);
const root=path.resolve(__dirname,'..'),dist=path.join(root,'.local/browser-dist'),out=path.resolve(process.argv[2]||path.join(root,'.local/browser-evidence'));fs.mkdirSync(out,{recursive:true});
const saved={claim_key:'inspection_priority',effective_at:'2026-09-20T01:00:31.123Z',known_as_of:'2026-09-21T01:00:32.456Z'};
const citation={evidence_id:'synthetic-source',source_id:'source',source_version:'1',locator:'section1',checksum:'a'.repeat(64)};
const proposal={proposal_id:'synthetic-proposal',state:'PENDING_APPROVAL',action:'manual_inspection',owner_user:'engineer-1',asset_id:'A-104',fingerprint:'b'.repeat(64),citations:[citation],evidence_reviewable:true,review_context:saved};
const analysis={state:'SUPPORTED',recommended_action:'manual_inspection',reason:'Visible synthetic SOP',citations:[citation],effective_at:saved.effective_at,known_as_of:saved.known_as_of};
(async()=>{const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});const page=await browser.newPage({viewport:{width:1440,height:900},reducedMotion:'reduce'});const posts=[],errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',async route=>{const u=new URL(route.request().url());if(u.origin!=='http://opspilot.test')return route.abort();let data;
 if(u.pathname==='/health')data={ok:true};
 else if(u.pathname==='/api/v1/auth/me')data={user_id:'engineer-1',role:'engineer',tenant:'demo',team:'team_a',csrf_token:'synthetic-only'};
 else if(u.pathname==='/api/v1/proposals')data={items:[proposal]};
 else if(u.pathname==='/api/v1/demo/scenarios')data={assets:['A-104']};
 else if(u.pathname.endsWith('/audit'))data={items:[]};
 else if(u.pathname==='/api/v1/proposals/synthetic-proposal')data=proposal;
 else if(u.pathname==='/api/v1/analysis/compare'){const body=route.request().postDataJSON();posts.push({path:u.pathname,body});data={before:analysis,after:{...analysis,known_as_of:body.after_known_as_of},changed:false,changes:{state_changed:false,action_changed:false,added_citations:[],removed_citations:[]}};}
 else if(u.pathname==='/api/v1/analysis'){const body=route.request().postDataJSON();posts.push({path:u.pathname,body});data={...analysis,effective_at:body.effective_at,known_as_of:body.known_as_of};}
 else if(u.pathname.startsWith('/api/'))throw new Error('Unexpected request '+u.pathname);
 if(data)return route.fulfill({contentType:'application/json',body:JSON.stringify(data)});
 const file=path.resolve(dist,u.pathname==='/'?'index.html':'.'+u.pathname);if(!file.startsWith(dist+path.sep)||!fs.existsSync(file))return route.fulfill({status:404,body:''});return route.fulfill({path:file,contentType:{'.js':'text/javascript','.css':'text/css','.html':'text/html'}[path.extname(file)]});});
 try{await page.goto('http://opspilot.test/');await page.getByRole('button',{name:/Approval Inbox/}).click();await page.locator('.proposal-link').click();
 await page.getByRole('button',{name:'초안 이후 근거 변화 비교 →'}).click();await page.locator('.comparison-next-step').waitFor();assert.equal(posts[0].body.effective_at,saved.effective_at);assert.equal(posts[0].body.before_known_as_of,saved.known_as_of);
 const viewports=[];for(const width of [1440,390]){await page.setViewportSize({width,height:900});await page.locator('.comparison-next-step').scrollIntoViewIfNeeded();const metrics=await page.evaluate(()=>({width:innerWidth,overflow:document.documentElement.scrollWidth-innerWidth,buttonHeight:document.querySelector('.comparison-next-step button').getBoundingClientRect().height}));assert.equal(metrics.overflow,0);assert.ok(metrics.buttonHeight>=44);viewports.push(metrics);await page.screenshot({path:path.join(out,`temporal-handoff-${width}.png`),fullPage:true});}
 await page.locator('.comparison-next-step button').focus();await page.keyboard.press('Enter');await page.locator('.decision-panel').waitFor();assert.equal(posts.length,2);assert.equal(posts[1].path,'/api/v1/analysis');assert.equal(posts[1].body.effective_at,posts[1].body.known_as_of);assert.notEqual(posts[1].body.effective_at,saved.effective_at);assert.equal(await page.getByRole('button',{name:'작업 초안 생성 →'}).isEnabled(),true);assert.deepEqual(errors,[]);
 fs.writeFileSync(path.join(out,'result.json'),JSON.stringify({status:'PASS',scope:'actual Chromium UI; intercepted synthetic API; backend separately tested',browser:browser.version(),viewports,requestPaths:posts.map(p=>p.path),exactSavedClocks:true,errors},null,2));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
