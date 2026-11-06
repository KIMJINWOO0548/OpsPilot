export const labels: Record<string,string> = {SUPPORTED:'근거 일치',CONFLICT:'근거 충돌',CONFLICTING:'근거 충돌',INSUFFICIENT:'근거 부족',ABSTAIN:'판정 보류',STALE:'유효 근거 없음',PENDING_APPROVAL:'승인 대기',APPROVED:'승인 완료',REJECTED:'거절',SUCCEEDED:'실행 완료',UNKNOWN_RECONCILE:'영수증 확인 필요',FAILED:'실행 실패',current:'현재 유효',superseded:'대체됨',future:'미래 기록',expired:'유효기간 종료'};
export const label=(s?:string)=>s?(labels[s]??s):'미확인';
Object.assign(labels,{VALID:'현재 유효',SUPERSEDED:'대체됨',NOT_YET_EFFECTIVE:'아직 유효하지 않음',EXPIRED:'유효기간 종료',CREATED:'초안 생성',APPROVE:'승인',REJECT:'거절',EXECUTE:'mock 실행',RECONCILE:'영수증 복구',RESPONSE_LOST:'응답 유실',RECONCILED:'영수증 복구 완료',EVIDENCE_CHANGED:'근거 변경으로 만료'});
export const reasonLabel=(s:string)=>({'No currently valid authorized evidence':'선택한 시점에 유효하고 접근 가능한 근거가 없습니다.','No sufficient authorized evidence':'접근 가능한 근거가 충분하지 않아 판정을 보류합니다.','No valid authoritative instruction':'유효한 승인 지침을 확인할 수 없습니다.','Conflicting authorized instructions with no unambiguous precedence':'접근 가능한 지침이 충돌하며 우선순위를 확정할 수 없습니다.','One consistent authorized current instruction; approval still required':'유효한 승인 지침이 하나의 조치를 지지합니다. 실행하려면 독립된 승인이 필요합니다.'}[s]??s);
export const actionLabel=(s?:string)=>({sensor_diagnostic_first:'센서 진단 우선',inspection_first:'현장 점검 우선',manual_inspection:'수동 점검',stop_and_escalate:'중지 및 담당자 확인'}[s??'']??s??'조치 없음');
export function kstInput(d=new Date()){return new Date(d.getTime()+9*3600000).toISOString().slice(0,16);}
export function freshForProposal(effectiveAt:string,knownAsOf:string,now=Date.now()){
 return [effectiveAt,knownAsOf].every(value=>{const age=now-Date.parse(value);return Number.isFinite(age)&&age>=0&&age<=3600000;});
}
export function toIso(v:string){const d=new Date(v+':00+09:00');if(!v||Number.isNaN(d.getTime()))throw new Error('올바른 KST 시점을 입력하세요.');return d.toISOString();}
export function formatTime(v?:string|null){return v?new Intl.DateTimeFormat('ko-KR',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(v)):'—';}
export function permissions(role:string,state:string,owner?:string,user?:string,decidedBy?:string,evidenceReviewable=false){const approvedByUser=role==='approver'&&!!user&&decidedBy===user;return{decide:evidenceReviewable&&role==='approver'&&state==='PENDING_APPROVAL'&&!!owner&&owner!==user,execute:evidenceReviewable&&approvedByUser&&state==='APPROVED',reconcile:approvedByUser&&state==='UNKNOWN_RECONCILE'};}

export function currentAnalysisInput(asset:string,now=new Date()){
 const instant=now.toISOString();
 return {asset_id:asset.trim(),claim_key:'inspection_priority',effective_at:instant,known_as_of:instant};
}
export function reviewComparisonInput(proposal:{asset_id?:string;evidence_reviewable?:boolean;review_context?:{claim_key:string;effective_at:string;known_as_of:string}|null},now=new Date()){
 if(proposal.evidence_reviewable!==true||!proposal.asset_id||!proposal.review_context)return null;
 const saved=proposal.review_context;
 return {asset_id:proposal.asset_id,claim_key:saved.claim_key,effective_at:saved.effective_at,before_known_as_of:saved.known_as_of,after_known_as_of:now.toISOString()};
}
