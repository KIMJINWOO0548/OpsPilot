// @ts-nocheck -- Built-in Node runner needs no test dependency.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {kstInput,toIso,permissions,freshForProposal} from './helpers.ts';
test('KST preserves the instant and rejects invalid input',()=>{assert.equal(toIso('2026-09-20T10:00'),'2026-09-20T01:00:00.000Z');assert.equal(kstInput(new Date('2026-09-20T01:00:00Z')),'2026-09-20T10:00');assert.throws(()=>toIso(''));});

test('historical and future analysis stays read-only in the console',()=>{
 const now=Date.parse('2026-10-22T10:00:00Z');
 assert.equal(freshForProposal('2026-10-22T09:30:00Z','2026-10-22T09:30:00Z',now),true);
 assert.equal(freshForProposal('2026-10-22T09:00:00Z','2026-10-22T09:00:00Z',now),true);
 assert.equal(freshForProposal('2026-09-20T01:00:00Z','2026-09-20T01:00:00Z',now),false);
 assert.equal(freshForProposal('2026-10-22T09:30:00Z','2026-10-22T10:00:01Z',now),false);
 assert.equal(freshForProposal('invalid','2026-10-22T10:00:00Z',now),false);
});
test('independent approval and response-loss recovery',()=>{assert.equal(permissions('approver','PENDING_APPROVAL','alice','bob').decide,true);assert.equal(permissions('approver','PENDING_APPROVAL','alice','alice').decide,false);assert.equal(permissions('viewer','APPROVED').execute,false);assert.deepEqual(permissions('approver','UNKNOWN_RECONCILE','alice','bob','bob'),{decide:false,execute:false,reconcile:true});assert.equal(permissions('approver','SUCCEEDED').execute,false);});
test('only the original approving user may execute or reconcile',()=>{
 for(const [state,action] of [['APPROVED','execute'],['UNKNOWN_RECONCILE','reconcile']]){
  assert.equal(permissions('approver',state,'alice','carol','bob')[action],false);
  assert.equal(permissions('approver',state,'alice','bob')[action],false);
  assert.equal(permissions('approver',state)[action],false);
  assert.equal(permissions('approver',state,'alice','bob','bob')[action],true);
  assert.equal(permissions('viewer',state,'alice','bob','bob')[action],false);
 }
});
