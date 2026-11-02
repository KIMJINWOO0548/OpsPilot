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
test('independent approval and response-loss recovery',()=>{
 assert.equal(permissions('approver','PENDING_APPROVAL','alice','bob',undefined,true).decide,true);
 assert.equal(permissions('approver','PENDING_APPROVAL','alice','alice',undefined,true).decide,false);
 assert.equal(permissions('viewer','PENDING_APPROVAL','alice','bob',undefined,true).decide,false);
 assert.equal(permissions('approver','PENDING_APPROVAL',undefined,'bob',undefined,true).decide,false);
 assert.equal(permissions('viewer','APPROVED','alice','bob','bob',true).execute,false);
 assert.deepEqual(permissions('approver','UNKNOWN_RECONCILE','alice','bob','bob'),{decide:false,execute:false,reconcile:true});
 assert.equal(permissions('approver','SUCCEEDED','alice','bob','bob',true).execute,false);
});
test('only the original approving user may execute or reconcile',()=>{
 for(const [state,action] of [['APPROVED','execute'],['UNKNOWN_RECONCILE','reconcile']]){
  assert.equal(permissions('approver',state,'alice','carol','bob',true)[action],false);
  assert.equal(permissions('approver',state,'alice','bob',undefined,true)[action],false);
  assert.equal(permissions('approver',state,'alice',undefined,'bob',true)[action],false);
  assert.equal(permissions('approver',state,'alice','bob','bob',true)[action],true);
  assert.equal(permissions('viewer',state,'alice','bob','bob',true)[action],false);
 }
});
test('unverifiable evidence blocks decisions and first execution, preserving receipt recovery',()=>{
 assert.equal(permissions('approver','PENDING_APPROVAL','alice','bob',undefined,false).decide,false);
 assert.equal(permissions('approver','PENDING_APPROVAL','alice','bob',undefined,true).decide,true);
 assert.equal(permissions('approver','APPROVED','alice','bob','bob',false).execute,false);
 assert.equal(permissions('approver','APPROVED','alice','bob','bob',true).execute,true);
 assert.equal(permissions('approver','APPROVED','alice','bob','bob').execute,false);
 assert.equal(permissions('approver','UNKNOWN_RECONCILE','alice','bob','bob',false).reconcile,true);
 assert.equal(permissions('approver','UNKNOWN_RECONCILE','alice','carol','bob',false).reconcile,false);
});
