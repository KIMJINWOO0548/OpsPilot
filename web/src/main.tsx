import {StrictMode,useEffect,useRef,useState,type FormEvent,type KeyboardEvent,type ReactNode} from 'react';
import {createRoot} from 'react-dom/client';
import {readGuidance,label,actionLabel,kstInput,toIso,formatTime,permissions,reasonLabel,freshForProposal,reviewComparisonInput,currentAnalysisInput,sameDraftRequest,type DraftAttempt,type Input} from './helpers';
import './styles.css';
type Session={user_id:string;role:string;tenant:string;team:string;csrf_token:string};
type Citation={evidence_id:string;source_id:string;source_version:string|number;locator:string;checksum:string};
type Evidence=Citation&{authority:string;text:string;value:string;valid_from:string;valid_to?:string;recorded_at:string;supersedes?:string[];score?:number;temporal_status:string};
type Analysis={state:string;recommended_action?:string;reason:string;citations:Citation[];effective_at:string;known_as_of:string};
type Comparison={before:Analysis;after:Analysis;changed:boolean;changes:{state_changed:boolean;action_changed:boolean;added_citations:Citation[];removed_citations:Citation[]}};
type Proposal={proposal_id:string;state:string;action:string;created_at?:string;owner_user?:string;decided_by?:string|null;asset_id?:string;fingerprint?:string;citations?:Citation[];evidence_reviewable?:boolean;review_context?:{claim_key:string;effective_at:string;known_as_of:string}|null;receipt?:unknown;receipt_id?:string;review_version:number;assigned_approver?:string|null;handover_allowed?:boolean;approval_valid?:boolean;[key:string]:unknown};
type ProposalRow=Pick<Proposal,'proposal_id'|'state'|'asset_id'|'owner_user'|'created_at'|'decided_by'|'fingerprint'>&{action?:string;review_due_at?:string|null};
const hasAsset=(p:ProposalRow)=>typeof p.asset_id==='string'&&p.asset_id.length>0;
const privateRow=(row:ProposalRow):ProposalRow=>({proposal_id:row.proposal_id,state:row.state});
type Audit={approved_documents?:(Citation&{text:string})[];kind:string;actor:string|Record<string,unknown>;logged_at:string;details?:{from_approver?:string|null;to_approver?:string|null;reason?:string}|null};
class ApiError extends Error {
 constructor(readonly status:number,message:string){super(message);}
}
const pages=[{id:'investigation',title:'근거 조사',en:'Investigation',icon:'⌕'},{id:'timeline',title:'근거 타임라인',en:'Evidence Timeline',icon:'▤'},{id:'approval',title:'승인함',en:'Approval Inbox',icon:'☑'}] as const;
type Page=typeof pages[number]['id'];
type ReviewQueue='all'|'pending'|'overdue'|'unscheduled';
const hasReviewDueFilter=(queue:ReviewQueue)=>queue==='overdue'||queue==='unscheduled';
function moveReviewFocus(event:KeyboardEvent<HTMLButtonElement>){
 const move=event.key==='ArrowDown'?1:event.key==='ArrowUp'?-1:0;
 if(!move)return;
 const rows=event.currentTarget.closest('tbody')?.querySelectorAll<HTMLButtonElement>('button.proposal-link:enabled');
 if(!rows)return;
 const index=Array.from(rows).indexOf(event.currentTarget);
 const next=rows[index+move];
 if(next){event.preventDefault();next.focus();}
}
function Badge({state}:{state:string}){return <span className={`badge ${['SUPPORTED','APPROVED','SUCCEEDED','current','VALID'].includes(state)?'good':['CONFLICT','CONFLICTING','REJECTED','FAILED'].includes(state)?'bad':'warn'}`}><i/>{label(state)}</span>}
function Empty({title,children}:{title:string;children:ReactNode}){return <div className="empty"><span className="empty-icon">▤</span><h3>{title}</h3><p>{children}</p></div>}
function Details({data,title='원본 상세'}:{data:unknown;title?:string}){return <details className="raw"><summary>{title}</summary><pre>{JSON.stringify(data,null,2)}</pre></details>}
function Brand(){return <span className="brand"><span className="brand-mark">O<span>✦</span></span>OpsPilot<span className="brand-x">-X</span></span>}
function Citations({items}:{items:Citation[]}){return items.length?<div className="table-wrap"><table><thead><tr><th>근거 / 출처</th><th>버전</th><th>문서 위치</th><th>무결성</th></tr></thead><tbody>{items.map(c=><tr key={c.evidence_id}><td><strong>{c.evidence_id}</strong><small>{c.source_id}</small></td><td><span className="version">v{c.source_version}</span></td><td>{c.locator}</td><td><code title={c.checksum}>{c.checksum?.slice(0,12)}…</code></td></tr>)}</tbody></table></div>:<p className="inset muted">표시할 인용 근거가 없습니다.</p>}
function App(){
 const [session,setSession]=useState<Session|null>(null),[checking,setChecking]=useState(true),[busy,setBusy]=useState(''),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const [page,setPage]=useState<Page>('investigation'),[username,setUsername]=useState(''),[password,setPassword]=useState('');
 const [asset,setAsset]=useState('A-103'),[query,setQuery]=useState(''),[effective,setEffective]=useState(()=>kstInput()),[known,setKnown]=useState(()=>kstInput()),[assets,setAssets]=useState<string[]>([]);
 const [analysis,setAnalysis]=useState<Analysis|null>(null),[analyzedInput,setAnalyzedInput]=useState<Input|null>(null),[evidence,setEvidence]=useState<Evidence[]>([]),[searched,setSearched]=useState(false);
 const [laterKnown,setLaterKnown]=useState(()=>kstInput()),[comparison,setComparison]=useState<Comparison|null>(null);
 const [comparisonRequestId,setComparisonRequestId]=useState<string|null>(null);
 const [proposals,setProposals]=useState<ProposalRow[]>([]),[selected,setSelected]=useState<Proposal|null>(null),[audit,setAudit]=useState<Audit[]>([]),[health,setHealth]=useState<boolean|null>(null);
 const [draftAttempt,setDraftAttempt]=useState<DraftAttempt|null>(null),[handoverReason,setHandoverReason]=useState('');
 const [reviewDue,setReviewDue]=useState(''),[reviewQueue,setReviewQueue]=useState<ReviewQueue>('all'),[queueAsOf,setQueueAsOf]=useState<string|null>(null);
 const [detailLoading,setDetailLoading]=useState(false);
 const queueFilter=useRef<ReviewQueue>('all');
 const proposalHeading=useRef<HTMLHeadingElement>(null);
 const reviewHeading=useRef<HTMLHeadingElement>(null);
 const returningToReview=useRef(false);
 const approvalFeedback=useRef<HTMLDivElement>(null);
 const sessionGeneration=useRef(0), detailGeneration=useRef(0), listGeneration=useRef(0);
 const restrictedAt=useRef(new Map<string,number>()), disclosureSequence=useRef(0), selectedId=useRef<string|null>(null);
 function clearData(){restrictedAt.current.clear();selectedId.current=null;queueFilter.current='all';++sessionGeneration.current;++detailGeneration.current;++listGeneration.current;setAssets([]);setAnalysis(null);setAnalyzedInput(null);setSelected(null);setDetailLoading(false);setAudit([]);setProposals([]);setEvidence([]);setSearched(false);setComparison(null);setComparisonRequestId(null);setDraftAttempt(null);setHandoverReason('');setReviewDue('');setReviewQueue('all');setQueueAsOf(null);}
 async function api<T>(path:string,body?:unknown,headers:Record<string,string>={}):Promise<T>{
  const generation=sessionGeneration.current;
  const r=await fetch(path,{credentials:'same-origin',method:body===undefined?'GET':'POST',headers:{...(body===undefined?{}:{'Content-Type':'application/json'}),...(session?.csrf_token?{'X-CSRF-Token':session.csrf_token}:{}),...headers},body:body===undefined?undefined:JSON.stringify(body)}).catch(()=>{
   throw new Error('API에 연결하지 못했습니다. 연결 상태를 확인하고 다시 조회하세요.');
  });
  const data=await r.json().catch(()=>{
   if(r.ok)throw new Error('서버 응답을 읽을 수 없습니다. 다시 조회하세요.');
   return {detail:'서버 응답을 읽을 수 없습니다.'};
  });
  if(generation!==sessionGeneration.current)throw new Error('세션이 변경되었습니다.');
  if(!r.ok){if(r.status===401){setSession(null);clearData();}throw new ApiError(r.status,r.status===401?'세션이 만료되었습니다. 다시 로그인하세요.':r.status===403?'이 작업을 수행할 권한이 없습니다.':typeof data?.detail==='string'?data.detail:`요청 실패 (${r.status}). 입력과 서버 상태를 확인하세요.`);}
  return data as T;
 }
 async function run(name:string,task:()=>Promise<void>){if(busy)return;setBusy(name);setError('');setNotice('');try{await task();}catch(e){setError(e instanceof Error?e.message:'연결에 실패했습니다. 서버 상태를 확인하세요.');}finally{setBusy('');}}
 useEffect(()=>{fetch('/api/v1/auth/me',{credentials:'same-origin'}).then(async r=>{if(r.ok)setSession(await r.json());else if(r.status!==401)setError('로그인 상태를 확인할 수 없습니다.');}).catch(()=>setError('API에 연결할 수 없습니다. 서버를 확인하세요.')).finally(()=>setChecking(false));fetch('/health').then(r=>r.json()).then(h=>setHealth(h.ok===true)).catch(()=>setHealth(false));},[]);
 useEffect(()=>{
  if(session)void run('목록 조회',async()=>{
   await Promise.all([
    loadProposals(),
    api<{assets:string[]}>('/api/v1/demo/scenarios').then(data=>setAssets(data.assets)),
    session.role==='engineer'?loadDraftAttempt():null,
   ]);
  });
 },[session]);
 useEffect(()=>{
  if(page==='approval'&&returningToReview.current){
   returningToReview.current=false;
   reviewHeading.current?.focus();
  }
 },[page]);
 const input=():Input=>({asset_id:asset.trim(),claim_key:'inspection_priority',effective_at:toIso(effective),known_as_of:toIso(known)});
 function invalidate(){setAnalysis(null);setAnalyzedInput(null);setSearched(false);setEvidence([]);setComparison(null);setComparisonRequestId(null);setNotice('');}
 async function searchEvidence(req:Input){const params=new URLSearchParams({q:query,asset_id:req.asset_id,effective_at:req.effective_at,known_as_of:req.known_as_of});setEvidence((await api<{items:Evidence[]}>(`/api/v1/evidence?${params}`)).items);setSearched(true);}
 async function analyze(e:FormEvent){e.preventDefault();void run('근거 분석',async()=>{const req=input();setAnalysis(null);setAnalyzedInput(null);const result=await api<Analysis>('/api/v1/analysis',req);setAnalysis(result);setAnalyzedInput(req);await searchEvidence(req);setNotice('지정한 두 시점과 접근 권한을 기준으로 판정했습니다.');});}
 async function compareTimes(e:FormEvent){
  e.preventDefault();
  void run('시점 비교',async()=>{
   setComparison(null);
   const req=input(),afterKnown=toIso(laterKnown);
   if(!req.asset_id)throw new Error('조사 조건에서 자산 ID를 입력하세요.');
   if(Date.parse(req.known_as_of)>Date.parse(afterKnown))throw new Error('비교 관측 시점은 기준 관측 시점과 같거나 이후여야 합니다.');
   const result=await api<Comparison>('/api/v1/analysis/compare',{asset_id:req.asset_id,claim_key:req.claim_key,effective_at:req.effective_at,before_known_as_of:req.known_as_of,after_known_as_of:afterKnown});
   setComparison(result);
   setNotice('같은 업무 유효 시점에서 두 관측 시점의 판정을 비교했습니다. 비교는 읽기 전용입니다.');
  });
 }
 async function compareDraft(){
  if(!selected)return;
  const req=reviewComparisonInput(selected);
  if(!req)return;
  invalidate();setComparisonRequestId(selected.proposal_id);setAsset(req.asset_id);setQuery('');setEffective(kstInput(new Date(req.effective_at)));setKnown(kstInput(new Date(req.before_known_as_of)));setLaterKnown(kstInput(new Date(req.after_known_as_of)));setPage('timeline');
  const result=await api<Comparison>('/api/v1/analysis/compare',req);
  setComparison(result);setNotice('저장된 초안의 정확한 시점과 현재 관측을 비교했습니다. 승인 상태는 바뀌지 않았습니다.');
 }
 function returnToReview(){
  if(!comparisonRequestId)return;
  returningToReview.current=true;
  setPage('approval');
  void run('요청 상태 조회',()=>refreshProposals(comparisonRequestId));
 }
 async function analyzeCurrent(){
  const req=currentAnalysisInput(asset);
  invalidate();setEffective(kstInput(new Date(req.effective_at)));setKnown(kstInput(new Date(req.known_as_of)));setQuery('');setPage('investigation');
  const result=await api<Analysis>('/api/v1/analysis',req);
  setAnalysis(result);setAnalyzedInput(req);setNotice('현재 시점으로 새로 분석했습니다. 초안 생성과 독립 승인은 별도 단계입니다.');
 }
 async function loadProposals(){
  const generation=++listGeneration.current, started=disclosureSequence.current, queue=queueFilter.current;
  const dueFilter=hasReviewDueFilter(queue);
  if(dueFilter){setQueueAsOf(null);setProposals([]);}
  let data:{items:ProposalRow[];as_of?:string};
  try{data=await api<typeof data>('/api/v1/proposals'+(dueFilter?'?review_queue='+queue:''));}
  catch(error){
   if(generation!==listGeneration.current)return;
   if(error instanceof ApiError && [403,404].includes(error.status)){
    selectedId.current=null;++detailGeneration.current;setSelected(null);setDetailLoading(false);setAudit([]);setProposals([]);proposalHeading.current?.focus();
   }
   throw error;
  }
  if(generation!==listGeneration.current)return;
  if(!Array.isArray(data?.items))throw new Error('작업 요청 목록 응답을 확인할 수 없습니다. 다시 조회하세요.');
  if(dueFilter){
   const asOf=data.as_of;
   if(typeof asOf!=='string'||!Number.isFinite(Date.parse(asOf))||data.items.some(row=>
    !hasAsset(row)||row.state!=='PENDING_APPROVAL'||(queue==='unscheduled'?row.review_due_at!==null:
     typeof row.review_due_at!=='string'||!Number.isFinite(Date.parse(row.review_due_at))||row.review_due_at>=asOf))){
    throw new Error('검토 기한 목록 응답을 확인할 수 없습니다. 다시 조회하세요.');
   }
   const visible=data.items.filter(row=>(restrictedAt.current.get(row.proposal_id)??0)<=started);
   for(const row of visible)restrictedAt.current.delete(row.proposal_id);
   setProposals(visible);setQueueAsOf(asOf);
   return visible;
  }
  for(const row of data.items){
   if(!hasAsset(row)){
    restrictedAt.current.set(row.proposal_id,++disclosureSequence.current);
    if(selectedId.current===row.proposal_id){
     setSelected(prev=>prev&&hasAsset(prev)?null:prev);setAudit([]);
    }
   }
  }
  setProposals(data.items.map(row=>restrictedAt.current.has(row.proposal_id)?privateRow(row):row));
 }
 async function openProposal(id:string){
  const generation=++detailGeneration.current, started=disclosureSequence.current, dueFilter=hasReviewDueFilter(queueFilter.current);
  selectedId.current=id;
  setSelected(null);setDetailLoading(true);setAudit([]);setHandoverReason('');
  const path=`/api/v1/proposals/${encodeURIComponent(id)}`;
  try {
   const detail=api<Proposal>(path).then(p=>{
    if(p?.proposal_id!==id)throw new Error('작업 요청 또는 감사 기록 응답을 확인할 수 없습니다. 다시 조회하세요.');
    if(generation===detailGeneration.current&&!hasAsset(p)){
     restrictedAt.current.set(id,++disclosureSequence.current);
     setProposals(rows=>dueFilter?rows.filter(row=>row.proposal_id!==id):rows.map(row=>row.proposal_id===id?privateRow(p):row));
     setAudit([]);
    }
    return p;
   });
   const [p,history]=await Promise.all([detail,api<{items:Audit[]}>(`${path}/audit`)]);
   if(generation!==detailGeneration.current)return;
   if(!Array.isArray(history?.items))throw new Error('작업 요청 또는 감사 기록 응답을 확인할 수 없습니다. 다시 조회하세요.');
   if(dueFilter&&!hasAsset(p)){selectedId.current=null;proposalHeading.current?.focus();return;}
   if(dueFilter&&p.state!=='PENDING_APPROVAL'){selectedId.current=null;setProposals(rows=>rows.filter(row=>row.proposal_id!==id));proposalHeading.current?.focus();return;}
   if(hasAsset(p)){
    if((restrictedAt.current.get(id)??0)>started)return;
    restrictedAt.current.delete(id);
    setProposals(rows=>rows.map(row=>row.proposal_id===id?{
     proposal_id:id,state:p.state,action:p.action,owner_user:p.owner_user,asset_id:p.asset_id,
     decided_by:p.decided_by,created_at:p.created_at,fingerprint:p.fingerprint,review_due_at:row.review_due_at,
    }:row));
   }
   setSelected(p);setAudit(hasAsset(p)?history.items:[]);
  } catch(error) {
   if(generation!==detailGeneration.current)return;
   if(error instanceof ApiError && [401,403,404].includes(error.status)){
    selectedId.current=null;++detailGeneration.current;++listGeneration.current;setDetailLoading(false);setProposals([]);proposalHeading.current?.focus();
   }
   throw error;
  } finally {if(generation===detailGeneration.current)setDetailLoading(false);}
 }
 async function refreshProposals(id?:string){
  if(hasReviewDueFilter(queueFilter.current)){
   selectedId.current=null;++detailGeneration.current;setSelected(null);setDetailLoading(false);setAudit([]);setHandoverReason('');
   const visible=await loadProposals();
   if(id&&visible?.some(row=>row.proposal_id===id))await openProposal(id);
   else if(id)proposalHeading.current?.focus();
   return;
  }
  const results=await Promise.allSettled([loadProposals(),...(id?[openProposal(id)]:[])]);
  const failed=results.find(result=>result.status==='rejected');
  if(failed?.status==='rejected')throw failed.reason;
 }
 function chooseReviewQueue(queue:ReviewQueue){
  if(queueFilter.current===queue||busy)return;
  queueFilter.current=queue;setReviewQueue(queue);setQueueAsOf(null);
  selectedId.current=null;++detailGeneration.current;++listGeneration.current;
  setSelected(null);setDetailLoading(false);setAudit([]);setHandoverReason('');setProposals([]);
  void run('승인함 조회',async()=>{await loadProposals();});
 }
 async function mutateProposal(suffix:string,body:unknown){
  if(!selected)return;
  const id=selected.proposal_id;
  let result:{state:string};
  try{result=await api(`/api/v1/proposals/${encodeURIComponent(id)}/${suffix}`,body);}
  catch(e){
   // A rejected or lost response may still have changed server state.
   // Refresh both views, retaining the original operation error if refresh also fails.
   await refreshProposals(id).catch(()=>{});
   approvalFeedback.current?.focus();
   throw e;
  }
  if(queueFilter.current!=='all'&&result?.state&&result.state!=='PENDING_APPROVAL'){
   queueFilter.current='all';setReviewQueue('all');setQueueAsOf(null);
  }
  setNotice(suffix==='handover'?'검토 담당을 인계했습니다.':suffix==='reconcile'?'저장된 영수증과 실행 상태를 확인했습니다.':`요청 상태가 갱신되었습니다. ${result?.state?label(result.state):''}`);
  try{await refreshProposals(id);}
  catch(e){
   if(e instanceof ApiError&&e.status===401)throw e;
   throw new Error('처리는 완료됐지만 최신 상태를 불러오지 못했습니다. 상태를 다시 조회하세요.');
  } finally {approvalFeedback.current?.focus();}
 }
 async function loadDraftAttempt(){
  const {attempt}=await api<{attempt:DraftAttempt|null}>('/api/v1/draft-intent');
  setDraftAttempt(attempt);
 }
 async function submitDraft(request?:Input){
  if(session?.role!=='engineer')return;
  let attempt=draftAttempt;
  if(request){
   if(!freshForProposal(request.effective_at,request.known_as_of))throw new Error('현재 시점으로 다시 분석하세요.');
   const due=reviewDue?toIso(reviewDue):undefined;
   try{
    ({attempt}=await api<{attempt:DraftAttempt}>('/api/v1/draft-intent',{request,review_due_at:due}));
    if(!attempt?.key||!attempt.request)throw new Error('서버에서 저장된 초안 요청을 확인할 수 없습니다.');
   }catch(e){
    await loadDraftAttempt().catch(()=>{});
    throw e;
   }
   setDraftAttempt(attempt);
   if(!sameDraftRequest(attempt.request,request,attempt.review_due_at,due))throw new Error('먼저 저장된 초안 요청을 다시 확인하세요.');
  }
  if(!attempt)throw new Error('다시 시도할 저장된 초안 요청이 없습니다.');
  const clearAttempt=async()=>{
   const result=await api<{ok:boolean}>('/api/v1/draft-intent/clear',{key:attempt.key});
   if(result?.ok!==true)throw new Error('저장된 초안 요청을 정리하지 못했습니다. 다시 시도하세요.');
   setDraftAttempt(null);
  };
  let result;
  try{
   result=await api<{proposal_id:string}>('/api/v1/proposals',{request:attempt.request,review_due_at:attempt.review_due_at},{'Idempotency-Key':attempt.key});
  }catch(e){
   if(e instanceof ApiError&&e.status===422)await clearAttempt();
   throw e;
  }
  if(typeof result?.proposal_id!=='string'||!result.proposal_id)throw new Error('서버 응답에서 초안 ID를 확인할 수 없습니다. 저장된 요청을 다시 시도하세요.');
  await clearAttempt();
  setReviewDue('');
  invalidate();
  queueFilter.current='all';setReviewQueue('all');
  setPage('approval');
  setNotice('초안을 확인했습니다. 다른 승인자 계정의 검토가 필요합니다.');
  await refreshProposals(result.proposal_id);
 }
 async function decideProposal(decision:'approve'|'reject'|'cancel'){
  if(selected?.fingerprint)await mutateProposal('decision',{decision,expected_hash:selected.fingerprint,expected_version:selected.review_version});
 }
 function handover(e:FormEvent){
  e.preventDefault();
  const reason=handoverReason.trim();
  if(selected?.handover_allowed&&selected.fingerprint&&reason){
   void run('검토 담당 인계',()=>mutateProposal('handover',{reason,expected_hash:selected.fingerprint,expected_version:selected.review_version}));
  }
 }
 const current=pages.find(p=>p.id===page)!;
 const freshProposal=!!analyzedInput&&freshForProposal(analyzedInput.effective_at,analyzedInput.known_as_of);
 if(checking)return <div className="boot" role="status">OpsPilot-X · 세션 확인 중…</div>;
 if(!session)return <main className="login-shell"><section className="login-story"><Brand/><div><p className="eyebrow">EVIDENCE → DECISION → ACTION</p><h1>근거에서 시작하는<br/>책임 있는 의사결정.</h1><p>문서의 유효 시점과 관측 시점을 함께 확인하고,<br/>독립된 승인으로 작업의 경계를 지킵니다.</p><div className="login-flow"><span>01 근거 조사</span><span>02 시점 검증</span><span>03 사람 승인</span></div></div><small>로컬 검증 환경 · 합성 자료 · 실제 설비 제어 없음</small></section><section className="login-form"><form onSubmit={e=>{e.preventDefault();void run('로그인',async()=>{const user=await api<Session>('/api/v1/auth/login',{username,password});clearData();setSession(user);setPassword('');});}}><p className="eyebrow">OPERATIONS WORKSPACE</p><h2>워크스페이스 로그인</h2><p className="muted">관리자가 발급한 계정으로 로그인하세요.</p><label htmlFor="username">사용자 이름</label><input id="username" autoComplete="username" required value={username} onChange={e=>setUsername(e.target.value)}/><label htmlFor="password">비밀번호</label><input id="password" type="password" autoComplete="current-password" required value={password} onChange={e=>setPassword(e.target.value)}/><button className="primary full-width" disabled={!!busy}>{busy?`${busy} 중…`:'로그인 →'}</button>{error&&<div role="alert" className="message error">{error}</div>}<p className="login-note">사용자 권한은 서버에서 확인합니다.<br/>승인자는 작성자와 다른 계정이어야 합니다.</p></form></section></main>;
 const allowed=permissions(session.role,selected?.state??'',selected?.owner_user,session.user_id,selected?.decided_by,selected?.evidence_reviewable===true,{approver:selected?.assigned_approver,approvalValid:selected?.approval_valid});
 const guidance=selected?readGuidance(selected.guidance,selected.review_version):null;
 const hasAction=(action:string)=>guidance?.actions.includes(action)===true;
 allowed.execute=allowed.execute&&guidance?.reason==='NONE';
 allowed.decide=allowed.decide&&guidance?.reason==='NONE';
 allowed.reconcile=hasAction('CHECK_RECEIPT');
 const pending=(proposal:ProposalRow)=>proposal.state==='PENDING_APPROVAL';
 const visibleProposals=reviewQueue==='pending'?proposals.filter(pending):reviewQueue==='all'?[...proposals].sort((a,b)=>Number(pending(b))-Number(pending(a))):proposals;
 const canCancel=guidance?.reason==='NONE'&&session.role==='approver'&&selected?.decided_by===session.user_id&&!selected.receipt_id;
 return <div className="app-shell"><a className="skip" href="#workspace">본문으로 이동</a><aside className="sidebar"><button className="brand-button" onClick={()=>setPage('investigation')} aria-label="OpsPilot-X 근거 조사"><Brand/></button><div className="workspace-switch"><span className="workspace-icon">OP</span><span>운영 검증 워크스페이스<small>{session.tenant} / {session.team}</small></span><span>⌄</span></div><p className="nav-label">WORKSPACE</p><nav aria-label="주 메뉴">{pages.map(p=><button key={p.id} className={`nav-item ${page===p.id?'active':''}`} onClick={()=>setPage(p.id)} aria-current={page===p.id?'page':undefined}><span className="nav-icon">{p.icon}</span><span>{p.title}<small>{p.en}</small></span>{p.id==='approval'&&<span className="nav-count">{proposals.filter(p=>p.state==='PENDING_APPROVAL').length}</span>}</button>)}</nav><div className="sidebar-bottom"><div className="safety-note"><span>◇</span><strong>사람의 승인 후 실행</strong><p>모든 작업은 mock입니다.<br/>실제 업무 시스템에 연결되지 않습니다.</p></div><div className="profile"><span className="avatar">{session.user_id.slice(0,2).toUpperCase()}</span><div><strong>{session.user_id}</strong><small>{session.role} · {session.team}</small></div><button className="logout" aria-label="로그아웃" title="로그아웃" disabled={!!busy} onClick={()=>void run('로그아웃',async()=>{await api('/api/v1/auth/logout',{});setSession(null);clearData();})}>↪</button></div></div></aside><div className="main-shell"><header className="topbar"><div><span className="muted">워크스페이스</span><span className="breadcrumb">/</span><strong>{current.title}</strong></div><div className="topbar-right"><span className={`connection ${health?'connected':''}`}><i/>{health?'API 연결됨':health===false?'연결 확인 필요':'연결 확인 중'}</span><span className="env-label">LOCAL</span></div></header><main id="workspace" tabIndex={-1}><div className={page==='approval'?'page-heading approval-page-heading':'page-heading'}><div>{page!=='approval'&&<p className="eyebrow">{current.en.toUpperCase()}</p>}<h1>{current.title}</h1>{page!=='approval'&&<p>{page==='investigation'?'현재의 판단을, 그 시점의 근거로 확인하세요.':'업무상 유효한 시간과 시스템이 알게 된 시간을 나란히 확인하세요.'}</p>}</div><span className="date-label">KST · UTC+09:00</span></div>{page!=='approval'&&<><div aria-live="polite" role="status">{busy&&<div className="message loading">◌ {busy} 중…</div>}{notice&&<div className="message success">✓ {notice}</div>}</div>{error&&<div className="message error" role="alert">{error}<button aria-label="오류 닫기" onClick={()=>setError('')}>×</button></div>}</>}
 {session.role==='engineer'&&draftAttempt&&<div className="info-strip"><span>◇</span><div><strong>처리 결과를 확인할 초안 요청</strong><p>{draftAttempt.request.asset_id} · 유효 {formatTime(draftAttempt.request.effective_at)} · 관측 {formatTime(draftAttempt.request.known_as_of)} KST{draftAttempt.review_due_at?` · 검토 기한 ${formatTime(draftAttempt.review_due_at)} KST`:''}</p><button className="text-button" disabled={!!busy} onClick={()=>void run('초안 요청 재시도',()=>submitDraft())}>저장된 초안 요청 재시도 →</button></div></div>}
 {page!=='approval'&&<form className="panel query-panel" onSubmit={page==='investigation'?analyze:e=>{e.preventDefault();void run('근거 검색',()=>searchEvidence(input()));}}><div className="panel-heading"><h2>조사 조건</h2><span className="muted">접근 가능한 근거만 조회합니다</span></div><div className="query-grid"><div><label htmlFor="asset">자산 ID</label><input id="asset" list="assets" maxLength={80} required value={asset} disabled={!!busy} onChange={e=>{setAsset(e.target.value);invalidate();}}/><datalist id="assets">{assets.map(a=><option key={a} value={a}/>)}</datalist></div><div><label htmlFor="query">문서 검색어</label><input id="query" maxLength={1000} placeholder="sensor, inspection, SOP-A103…" value={query} disabled={!!busy} onChange={e=>{setQuery(e.target.value);invalidate();}}/></div><div><label htmlFor="effective">유효 시점 <span title="업무상 이 시점에 유효한 근거">ⓘ</span></label><input id="effective" type="datetime-local" required value={effective} disabled={!!busy} onChange={e=>{setEffective(e.target.value);invalidate();}}/></div><div><label htmlFor="known">알려진 시점 <span title="시스템이 이 시점까지 관측한 근거">ⓘ</span></label><input id="known" type="datetime-local" required value={known} disabled={!!busy} onChange={e=>{setKnown(e.target.value);invalidate();}}/></div></div><div className="query-footer"><span className="muted">유효 시점 = 업무 기준 · 알려진 시점 = 당시 관측 기준</span><div className="button-row"><button type="button" className="secondary" disabled={!!busy} onClick={()=>{setEffective(kstInput());setKnown(kstInput());invalidate();}}>현재 시점</button><button className="primary" disabled={!!busy}>{page==='investigation'?'근거 분석 →':'근거 조회 →'}</button></div></div></form>}
 {page==='investigation'&&<><div className="section-heading"><h2>판정 결과</h2><span className="muted">규칙 기반 근거 검증 · 생성형 답변 아님</span></div>{analysis?<><section className={`panel decision-panel ${analysis.state==='SUPPORTED'?'supported':'attention'}`}><div className="decision-top"><span className="decision-icon">{analysis.state==='SUPPORTED'?'✓':'!'}</span><div><Badge state={analysis.state}/><h2>{actionLabel(analysis.recommended_action)}</h2><p>{reasonLabel(analysis.reason)}</p></div><div className="decision-action">{session.role==='engineer'&&<label>검토 요청 기한 (KST, 선택)<input type="datetime-local" value={reviewDue} onChange={e=>setReviewDue(e.target.value)} disabled={!!busy||!!draftAttempt}/></label>}<button className="primary" disabled={!!busy||!!draftAttempt||analysis.state!=='SUPPORTED'||session.role!=='engineer'||!analyzedInput||!freshProposal} onClick={()=>{if(analyzedInput)void run('초안 생성',()=>submitDraft(analyzedInput));}}>작업 초안 생성 →</button><small>{!freshProposal?'과거·미래 시점 분석은 읽기 전용입니다. 현재 시점으로 다시 분석하세요.':session.role==='engineer'?'승인 전에는 실행되지 않습니다':'초안 생성은 engineer 권한이 필요합니다'}</small></div></div><div className="decision-meta"><span>자산 <strong>{analyzedInput?.asset_id}</strong></span><span>유효 <strong>{formatTime(analysis.effective_at)}</strong></span><span>관측 <strong>{formatTime(analysis.known_as_of)}</strong></span><span>인용 <strong>{analysis.citations.length}건</strong></span></div></section><section className="panel"><div className="panel-heading"><h2>판정에 사용한 근거 <span className="count">{analysis.citations.length}</span></h2><button className="text-button" onClick={()=>setPage('timeline')}>타임라인에서 보기 ↗</button></div><Citations items={analysis.citations}/><Details data={analysis} title="판정 원본 상세"/></section></>:<section className="panel"><Empty title="조사할 자산과 시점을 선택하세요">분석하면 판정, 권장 조치, 인용 근거를 이곳에서 확인할 수 있습니다.</Empty><div className="example-row"><span className="muted">합성 예시</span><button className="text-button" disabled={!!busy} onClick={()=>{setAsset('A-103');setEffective(kstInput());setKnown(kstInput());invalidate();}}>A-103 · 현재 근거</button><button className="text-button" disabled={!!busy} onClick={()=>{setAsset('A-104');setEffective('2026-09-20T10:00');setKnown('2026-09-20T10:00');invalidate();}}>A-104 · 과거 시점 재현</button></div></section>}<div className="info-strip"><span>◇</span><div><strong>근거가 일치해도 실행에는 별도 승인이 필요합니다.</strong><p>시간·권한·충돌 여부는 서버 정책으로 판정합니다. 검색어는 문서 검색에만 사용됩니다.</p></div></div></>}
 {page==='timeline'&&<section className="panel comparison-panel" aria-labelledby="comparison-heading">
  <div className="panel-heading"><div><h2 id="comparison-heading">관측 시점 비교</h2><p className="comparison-intro">같은 업무 유효 시점에서, 나중에 알려진 근거가 판정을 바꿨는지 확인하세요.</p></div><span className="readonly-label">읽기 전용</span></div>
  {comparisonRequestId&&<div className="comparison-review-context"><button className="secondary" disabled={!!busy} onClick={returnToReview}>← 요청 검토로 돌아가기</button><span>요청 <code>{comparisonRequestId.slice(0,14)}</code></span></div>}
  <form className="comparison-form" onSubmit={compareTimes}>
   <dl className="comparison-conditions"><div><dt>비교할 자산</dt><dd>{asset.trim()||'자산 ID를 입력하세요'}</dd></div><div><dt>고정할 업무 유효 시점</dt><dd>{effective?`${effective.replace('T',' ')} KST`:'유효 시점을 입력하세요'}</dd></div><div><dt>기준 관측 시점</dt><dd>{known?`${known.replace('T',' ')} KST`:'알려진 시점을 입력하세요'}</dd></div></dl>
   <div className="comparison-controls"><div><label htmlFor="later-known">비교 관측 시점 (KST)</label><input id="later-known" type="datetime-local" required value={laterKnown} disabled={!!busy} aria-describedby="comparison-time-hint" onChange={e=>{setLaterKnown(e.target.value);setComparison(null);setNotice('');}}/><small id="comparison-time-hint">조사 조건의 알려진 시점과 같거나 이후로 선택하세요.</small></div><div className="button-row"><button type="button" className="secondary" disabled={!!busy} onClick={()=>{setAsset('A-104');setEffective('2026-09-20T10:00');setKnown('2026-09-20T10:00');setLaterKnown('2026-10-06T10:00');invalidate();setNotice('');}}>A-104 사후 정정 예시</button><button className="primary" disabled={!!busy}>두 시점 비교 →</button></div></div>
   <p className="comparison-note">현재 접근 권한으로 비교합니다. 당시의 사용자 권한 이력은 재현하지 않습니다. 문서 검색어는 판정 비교에 사용되지 않습니다.</p>
  </form>
  {comparison?<div className="comparison-results">
   <div className={`comparison-summary ${comparison.changed?'changed':''}`} role="status"><strong>{comparison.changed?'두 관측 시점의 판정 또는 인용 근거가 달라졌습니다.':'두 관측 시점의 판정과 인용 근거가 같습니다.'}</strong><p>{comparison.changes.state_changed?'판정 상태 변경':'판정 상태 유지'} · {comparison.changes.action_changed?'권장 조치 변경':'권장 조치 유지'}</p></div>
   <div className="comparison-grid">{[{title:'기준 관측 시점',data:comparison.before},{title:'비교 관측 시점',data:comparison.after}].map(side=><section className="comparison-card" key={side.title} aria-label={side.title+' 판정'}><div className="comparison-card-heading"><h3>{side.title}</h3><p>{formatTime(side.data.known_as_of)} KST</p><Badge state={side.data.state}/><h4>{actionLabel(side.data.recommended_action)}</h4><p className="comparison-reason">{reasonLabel(side.data.reason)}</p></div><Citations items={side.data.citations}/></section>)}</div>
   <div className="comparison-next-step"><div><strong>현재 작업 판단으로 이어가기</strong><p>과거 비교는 읽기 전용입니다. 같은 자산을 현재 유효·관측 시점으로 새로 분석한 뒤 초안을 검토하세요.</p></div><button className="primary" disabled={!!busy} onClick={()=>void run('현재 근거 재분석',analyzeCurrent)}>현재 근거로 새로 분석 →</button></div>
   <div className="comparison-delta"><h3>인용 근거 변화</h3><p>각 시점의 판정에 사용한 근거를 비교합니다. 문서 삭제나 접근 권한 변경 이력을 뜻하지 않습니다.</p><div className="comparison-grid"><section aria-label="비교 시점에 새로 인용한 근거"><h4>비교 시점에 새로 인용 <span className="count">{comparison.changes.added_citations.length}</span></h4>{comparison.changes.added_citations.length?<Citations items={comparison.changes.added_citations}/>:<p className="inset muted">새로 인용한 근거가 없습니다.</p>}</section><section aria-label="기준 시점에만 인용한 근거"><h4>기준 시점에만 인용 <span className="count">{comparison.changes.removed_citations.length}</span></h4>{comparison.changes.removed_citations.length?<Citations items={comparison.changes.removed_citations}/>:<p className="inset muted">기준 시점에만 인용한 근거가 없습니다.</p>}</section></div></div>
  </div>:<Empty title="관측 시점에 따른 판단의 변화를 비교하세요">기준 시점은 위 조사 조건에서, 비교 시점은 이 패널에서 정하세요. 비교해도 초안이나 작업은 생성되지 않습니다.</Empty>}
 </section>}
 {page==='timeline'&&<section className="panel"><div className="panel-heading"><h2>근거 이력 <span className="count">{evidence.length}</span></h2><span className="muted">유효 구간 + 관측 기록</span></div>{evidence.length?<><div className="timeline-legend"><span><i className="valid-line"/>업무상 유효 구간</span><span><i className="observed-dot"/>시스템 관측 시점</span><span>정정 이력은 supersedes로 연결됩니다</span></div><div className="table-wrap"><table className="timeline-table"><thead><tr><th>문서 / 근거</th><th>유효 시간축 (KST)</th><th>관측 시간축 (KST)</th><th>버전 / 상태</th></tr></thead><tbody>{evidence.map(e=><tr key={e.evidence_id}><td><strong>{e.source_id}</strong><small>{e.evidence_id}</small><p className="evidence-text">{e.text}</p><details><summary>출처·체크섬 상세</summary><dl><dt>권위</dt><dd>{e.authority}</dd><dt>위치</dt><dd>{e.locator}</dd><dt>체크섬</dt><dd className="hash">{e.checksum}</dd><dt>값</dt><dd>{e.value}</dd></dl></details></td><td><div className="time-axis"><span>{formatTime(e.valid_from)}</span><div className="valid-line"/><span>{e.valid_to?formatTime(e.valid_to):'종료 없음'}</span></div></td><td><div className="observed"><i className="observed-dot"/>{formatTime(e.recorded_at)}</div></td><td><span className="version">v{e.source_version}</span><div className="status-cell"><Badge state={e.temporal_status}/></div><small>{e.supersedes?.length?`대체: ${e.supersedes.join(", ")}`:'최초 기록 / 대체 대상 없음'}</small></td></tr>)}</tbody></table></div></>:<Empty title={searched?'조건에 맞는 근거가 없습니다':'근거의 두 시간을 살펴보세요'}>{searched?'자산, 검색어, 시점 또는 접근 권한을 확인하세요.':'조회하면 유효 구간과 관측 시점, 버전 간 대체 관계를 확인할 수 있습니다.'}</Empty>}</section>}
 {page==='approval'&&<div className="approval-workbench">
  <div className="approval-toolbar" role="group" aria-label="승인함 도구">
   <label htmlFor="approval-queue">승인함 필터</label>
   <select id="approval-queue" value={reviewQueue} disabled={!!busy} onChange={e=>chooseReviewQueue(e.target.value as ReviewQueue)}>
    <option value="all">전체 요청</option>
    <option value="overdue">연체 승인 대기</option>
    <option value="unscheduled">기한 미지정</option>
    <option value="pending">승인 대기만</option>
   </select>
   <button className="secondary" disabled={!!busy} onClick={()=>void run('목록 조회',()=>refreshProposals(selected?.proposal_id))}>↻ 새로고침</button>
   {!hasReviewDueFilter(reviewQueue)&&<span className="approval-pending-count">승인 대기 <strong>{proposals.filter(p=>p.state==='PENDING_APPROVAL').length}</strong>건</span>}
   {queueAsOf&&<span className="approval-pending-count" role="status">조회 기준 {formatTime(queueAsOf)} KST</span>}
  </div>
  <div className="approval-layout">
   <section className="panel proposal-list" aria-labelledby="approval-list-title">
    <div className="panel-heading">
     <h2 id="approval-list-title" ref={proposalHeading} tabIndex={-1}>
      작업 요청 {(!hasReviewDueFilter(reviewQueue)||queueAsOf)&&<span className="count">{visibleProposals.length}</span>}
     </h2>
    </div>
    {visibleProposals.length?<div className="table-wrap"><table>
     <thead><tr><th scope="col">조치 / 자산</th><th scope="col">상태</th></tr></thead>
     <tbody>{visibleProposals.map(p=>{
      const isSelected=selected?.proposal_id===p.proposal_id;
      const title=p.action?actionLabel(p.action):'작업 요청';
      const shortId=p.proposal_id.slice(0,14);
      return <tr key={p.proposal_id} className={isSelected?'selected':''}>
       <th scope="row">
        <button className="proposal-link" disabled={!!busy} aria-label={[title,p.asset_id,`요청 ${shortId}`].filter(Boolean).join(' · ')} aria-current={isSelected?true:undefined} aria-controls="approval-detail"
         onClick={()=>{setError('');setNotice('');void openProposal(p.proposal_id).catch(e=>setError(e instanceof Error?e.message:'요청을 불러오지 못했습니다.'));}}
         onKeyDown={moveReviewFocus}>{title}</button>
        <small className="request-row-meta">{p.asset_id&&<span>{p.asset_id}</span>}<code>{shortId}</code></small>
        {p.review_due_at?<small>검토 기한 {formatTime(p.review_due_at)} KST</small>:reviewQueue==='unscheduled'&&<small>검토 기한 미지정</small>}
       </th>
       <td><Badge state={p.state}/><small>{formatTime(p.created_at)}</small></td>
      </tr>;
     })}</tbody>
    </table></div>:<p className="approval-empty" role="status">
     {busy?'승인함 조회 중…':error?'승인함 목록을 확인할 수 없습니다. 새로고침하세요.':reviewQueue==='all'?'아직 작업 요청이 없습니다':hasReviewDueFilter(reviewQueue)&&!queueAsOf?'승인함 목록을 확인할 수 없습니다. 새로고침하세요.':'조건에 맞는 승인 대기 요청이 없습니다.'}
    </p>}
   </section>
   <section className="panel proposal-detail" id="approval-detail" aria-labelledby="approval-detail-title">
    <div className="panel-heading">
     <h2 id="approval-detail-title" ref={reviewHeading} tabIndex={-1}>요청 검토</h2>
     {selectedId.current&&<button className="text-button" disabled={!!busy||detailLoading} onClick={()=>void run('상태 조회',()=>refreshProposals(selectedId.current??undefined))}>↻ 상태 조회</button>}
    </div>
    <div className="approval-feedback" aria-live="polite" role="status" ref={approvalFeedback} tabIndex={-1}>
     {(busy||detailLoading)&&<div className="message loading">{busy||'요청 조회'} 중…</div>}
     {notice&&<div className="message success">{notice}</div>}
    </div>
    {error&&<div className="message error approval-error" role="alert">{error}<button aria-label="오류 닫기" onClick={()=>setError('')}>×</button></div>}
    {selected?<div className="approval-detail-body">
     <div className="approval-request-heading">
      <h3 className="action-title">{selected.action?actionLabel(selected.action):'작업 요청'}</h3>
      <Badge state={selected.state}/>
     </div>
     <p className="mono muted proposal-id">{selected.proposal_id}</p>
     <dl className="approval-essential">
      <div><dt>자산</dt><dd>{selected.asset_id??'—'}</dd></div>
      <div><dt>작성자</dt><dd>{selected.owner_user??'—'}</dd></div>
      <div><dt>검토 담당</dt><dd>{selected.assigned_approver??'미지정'}</dd></div>
      <div><dt>승인자</dt><dd>{selected.decided_by??'미승인'}</dd></div>
      <div><dt>검토 버전</dt><dd>{selected.review_version}</dd></div>
      {typeof selected.review_due_at==='string'&&<div><dt>검토 기한</dt><dd>{formatTime(selected.review_due_at)} KST</dd></div>}
     </dl>
     <section className="approval-evidence" aria-labelledby="approval-evidence-title">
      <div className="approval-evidence-heading">
       <h4 id="approval-evidence-title">인용 근거</h4>
       <button className="text-button" disabled={!!busy||!selected.evidence_reviewable||!selected.review_context} onClick={()=>void run('초안 시점 비교',compareDraft)}>초안 이후 근거 변화 비교 →</button>
      </div>
      {selected.citations?.length?<ul className="citation-list">
       {selected.citations.map(c=><li key={c.evidence_id}>
        <div><strong>{c.evidence_id}</strong><span className="version">v{c.source_version}</span></div>
        <span>출처 {c.source_id}</span><span>{c.locator}</span>
       </li>)}
      </ul>:<p className="muted">현재 표시할 수 있는 인용 근거가 없습니다.</p>}
     </section>
     <section className="approval-actions" aria-labelledby="approval-actions-title">
      <h4 id="approval-actions-title">다음 조치</h4>
      {!guidance&&<p><strong>행동 정보 미확인</strong> · 상태를 다시 조회하세요.</p>}
      {guidance?.reason==='REVIEW_REQUIRED'&&<p><strong>검토 담당 확인 필요</strong> · {hasAction('TAKE_HANDOVER')?'인계 사유를 적고 검토 담당을 넘겨받으세요.':'현재 역할에서 인계할 수 없습니다.'}</p>}
      {selected.evidence_reviewable!==true&&<div className="review-warning">
       <strong>현재 근거 검토 불가</strong>
       <p>현재 권한으로 이 초안의 근거를 확인할 수 없습니다. 상태 조회로 다시 확인하세요.</p>
       {['PENDING_APPROVAL','APPROVED'].includes(selected.state)&&<p>승인과 최초 실행이 잠겼습니다.</p>}
       {selected.state==='UNKNOWN_RECONCILE'&&<p>이미 실행한 mock 작업의 영수증 복구는 허용된 담당자가 할 수 있습니다.</p>}
       <button className="text-button" disabled={!!busy||!hasAction('REINVESTIGATE')} onClick={()=>{setAsset('');setQuery('');setEffective(kstInput());setKnown(kstInput());invalidate();setPage('investigation');}}>현재 근거 재조사 →</button>
      </div>}
      {hasAction('TAKE_HANDOVER')&&selected.fingerprint&&<form className="approval-handover" onSubmit={handover}>
       <label htmlFor="handover-reason">검토 담당 인계 사유</label>
       <input id="handover-reason" value={handoverReason} maxLength={500} required disabled={!!busy} onChange={e=>setHandoverReason(e.target.value)}/>
       <button className="secondary" disabled={!!busy||!handoverReason.trim()}>내 계정으로 검토 인계</button>
      </form>}
      {selected.state==='PENDING_APPROVAL'&&<>
       <p>{selected.evidence_reviewable!==true?'검토 가능한 근거가 확인되어야 승인 또는 거절할 수 있습니다.':allowed.decide?'근거와 조치를 확인해 승인하거나 거절하세요.':selected.assigned_approver?'지정된 담당자가 승인하거나 거절할 수 있습니다.':'작성자와 다른 승인자 계정으로 로그인해야 승인할 수 있습니다.'}</p>
       <div className="button-row">
        <button className="secondary danger" disabled={!!busy||!allowed.decide||!selected.fingerprint} onClick={()=>void run('거절',()=>decideProposal('reject'))}>거절</button>
        <button className="primary" disabled={!!busy||!allowed.decide||!selected.fingerprint} onClick={()=>void run('승인',()=>decideProposal('approve'))}>검토 후 승인</button>
       </div>
      </>}
      {selected.state==='APPROVED'&&guidance?.reason!=='OUTCOME_UNKNOWN'&&<>
       <p>{selected.evidence_reviewable!==true?'현재 근거를 확인할 수 없어 최초 실행이 잠겼습니다.':allowed.execute?'승인한 작업을 mock 원장에 실행할 수 있습니다.':'이 요청을 승인한 계정으로 로그인해야 실행할 수 있습니다.'}</p>
       <div className="button-row">
        <button className="primary" disabled={!!busy||!allowed.execute} onClick={()=>void run('mock 실행',()=>mutateProposal('execute',{simulate_response_loss:false}))}>mock 작업 실행 →</button>
        <button className="secondary" disabled={!!busy||!allowed.execute} onClick={()=>void run('응답 유실 주입',()=>mutateProposal('execute',{simulate_response_loss:true}))}>응답 유실 시나리오 실행</button>
        {canCancel&&<button className="secondary danger" disabled={!!busy||!selected.fingerprint} onClick={()=>void run('승인 취소',()=>decideProposal('cancel'))}>승인 취소</button>}
       </div>
      </>}
      {guidance?.reason==='OUTCOME_UNKNOWN'&&<>
       <p className="amber">{allowed.reconcile?'실행 응답이 유실됐습니다. 재실행 전에 저장된 영수증을 조회하세요.':selected.assigned_approver?'지정된 담당자가 영수증을 복구할 수 있습니다.':'이 요청을 승인한 계정으로 로그인해야 영수증을 복구할 수 있습니다.'}</p>
       <button className="primary" disabled={!!busy||!allowed.reconcile} onClick={()=>void run('영수증 복구',()=>mutateProposal('reconcile',{}))}>영수증 확인으로 복구 →</button>
      </>}
      {guidance?.reason==='RECEIPT_AVAILABLE'&&<div className="completion">✓ 실행 완료 · 추가 실행이 필요하지 않습니다.</div>}
      {selected.state==='REJECTED'&&<p>거절된 요청입니다. 근거를 다시 조사해 새 초안을 생성하세요.</p>}
      {selected.state==='EXPIRED'&&<p>유효기간이 종료된 요청입니다. 현재 시점의 근거를 다시 조사해 새 초안을 생성하세요.</p>}
      {selected.state==='CANCELLED'&&<p>승인이 취소된 요청입니다.</p>}
     </section>
     {hasAction('VIEW_RECEIPT')&&(selected.receipt!=null||selected.receipt_id)&&<div className="receipt">
      <h4>✓ mock 실행 영수증</h4>
      <p className="hash">{selected.receipt_id}</p>
      <Details data={selected.receipt??{receipt_id:selected.receipt_id}} title="영수증 상세 확인"/>
     </div>}
     <details className="approval-context">
      <summary>검토 시점과 초안 해시</summary>
      <dl className="review-meta">
       {selected.review_context&&<>
        <dt>검토 주장</dt><dd>{selected.review_context.claim_key}</dd>
        <dt>유효 시점</dt><dd>{formatTime(selected.review_context.effective_at)} KST</dd>
        <dt>관측 시점</dt><dd>{formatTime(selected.review_context.known_as_of)} KST</dd>
       </>}
       <dt>초안 해시</dt><dd className="hash">{selected.fingerprint??'조회되지 않음'}</dd>
      </dl>
      <p className="muted">승인은 이 해시에 결합되며 변경된 초안은 서버에서 거부됩니다.</p>
     </details>
     <h4>감사 이력 <span className="count">{audit.length}</span></h4>
     {audit.length?<ol className="audit-list">{audit.map((a,i)=><li key={i}><i/><div>
      <strong>{label(a.kind)}</strong>
      <small>{typeof a.actor==='string'?a.actor:JSON.stringify(a.actor)} · {formatTime(a.logged_at)}</small>
      {a.kind==='APPROVED'&&(a.approved_documents?.length?<details>
       <summary>승인 당시 문서 열기</summary>
       {a.approved_documents.map(d=><section key={d.evidence_id}><h5>{d.source_id} · v{d.source_version}</h5><p>{d.locator}</p><p className="evidence-text">{d.text}</p><code className="hash">{d.checksum}</code></section>)}
      </details>:<small>승인 당시 문서가 기록되지 않았거나 현재 열람할 수 없습니다.</small>)}
      {a.kind==='HANDOVER'&&a.details&&<><small>{a.details.from_approver??'미지정'} → {a.details.to_approver??'미지정'}</small><small>사유 {a.details.reason}</small></>}
     </div></li>)}</ol>:<p className="muted">기록된 감사 이력이 없습니다.</p>}
     <Details data={selected} title="요청 원본 상세"/>
    </div>:!detailLoading&&<p className="approval-empty">{error?'요청을 다시 선택하거나 목록을 새로고침하세요.':'목록에서 검토할 요청을 선택하세요.'}</p>}
   </section>
  </div>
 </div>}
 <footer className="workspace-footer"><span>OpsPilot-X · 근거 검증 워크스페이스</span><span>합성 자료 · 결정적 정책 판정 · mock 실행</span></footer></main></div></div>;
}
createRoot(document.getElementById('root')!).render(<StrictMode><App/></StrictMode>);


