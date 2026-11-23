import 'dart:convert';
import 'dart:io';

import '../lib/desktop_api.dart';

void require(bool result, String message) {
  if (!result) throw StateError(message);
}

Future<void> main(List<String> args) async {
  if (args.length != 3) {
    throw ArgumentError(
      'Usage: check_portfolio.dart BUNDLE FRESH_PROFILE CREDENTIALS',
    );
  }
  final credentials = jsonObject(
    jsonDecode(await File(args[2]).readAsString()),
  );
  final author = jsonObject(credentials['author']);
  final reviewer = jsonObject(credentials['reviewer']);
  Future<DesktopApi> connect() => DesktopApi.start(
    args[0],
    args[1],
    chatPort: Platform.environment['OPSPILOT_CHAT_PORT'],
    embeddingPort: Platform.environment['OPSPILOT_EMBED_PORT'],
    modelKey: Platform.environment['OPSPILOT_MODEL_KEY'],
  );
  Future<Json> login(DesktopApi api, Json account) =>
      api.login(field(account, 'username'), field(account, 'password'));

  final clock = DateTime.now().toUtc().toIso8601String();
  final request = {
    'asset_id': 'A-103',
    'claim_key': 'inspection_priority',
    'effective_at': clock,
    'known_as_of': clock,
  };
  const question = 'What should I do before replacing the filter on A-103?';
  late String proposalId;
  late String auditHash;
  final first = await connect();
  try {
    require(
      (await login(first, author))['role'] == 'engineer',
      'Author is not an engineer',
    );
    final analysis = await first.hybridAnalysis({
      ...request,
      'query': question,
    });
    require(
      analysis['model_status'] == 'DRAFT_READY',
      'Real model did not return a verified draft',
    );
    final draft = jsonObject(analysis['draft']);
    final citations = objects(draft['citations']);
    require(
      draft['action'] == 'sensor_diagnostic_first' &&
          citations.any(
            (citation) =>
                citation['evidence_id'] == 'SOP-A103-v2' &&
                field(citation, 'quote').isNotEmpty,
          ),
      'Verified original citation missing',
    );
    final conflict = await first.hybridAnalysis({
      ...request,
      'asset_id': 'A-105',
      'query': 'Which maintenance policy should I follow?',
    });
    require(
      conflict['model_status'] == 'POLICY_BLOCKED' && conflict['draft'] == null,
      'Conflicting SOPs did not block the model',
    );

    final staged = await first.send('draft-intent', {'request': request});
    final key = field(jsonObject(staged['attempt']), 'key');
    final proposal = await first.submitStagedDraft({'request': request}, key);
    proposalId = field(proposal, 'proposal_id');
    require(proposalId.isNotEmpty, 'No registered proposal');
    final path = 'proposals/$proposalId';
    final pending = await first.read(path);
    final decision = {
      'expected_hash': pending['fingerprint'],
      'expected_version': pending['review_version'],
      'decision': 'approve',
    };
    try {
      await first.send('$path/decision', decision);
      throw StateError('The request author could approve their own request');
    } on ServerError catch (error) {
      require(error.status == 403, 'Unexpected author refusal');
    }
    await first.send('auth/logout', {});
    require(
      (await login(first, reviewer))['role'] == 'approver',
      'Reviewer lacks approval role',
    );
    await first.send('$path/decision', decision);
    final executed = await first.send('$path/execute', {
      'output': 'pdf',
      'simulate_response_loss': true,
    });
    require(
      executed['state'] == 'UNKNOWN_RECONCILE' &&
          executed['receipt_id'] == null,
      'Response-loss test did not enter an unknown state',
    );
    final events = objects((await first.read('$path/audit'))['items']);
    final creation = events.singleWhere(
      (event) => event['kind'] == 'PDF_CREATED',
    );
    auditHash = field(jsonObject(creation['details']), 'sha256');
    require(
      RegExp(r'^[0-9a-f]{64}$').hasMatch(auditHash),
      'No report hash in the audit record',
    );
  } finally {
    await first.close();
  }

  final reopened = await connect();
  try {
    await login(reopened, reviewer);
    final path = 'proposals/$proposalId';
    require(
      (await reopened.read(path))['state'] == 'UNKNOWN_RECONCILE',
      'Restart lost pending reconciliation',
    );
    final recovered = await reopened.send('$path/reconcile', {});
    final receiptId = field(recovered, 'receipt_id');
    require(
      receiptId.isNotEmpty && recovered['state'] == 'SUCCEEDED',
      'No recovered receipt',
    );
    final report = await reopened.saveApprovedReport(proposalId, receiptId);
    final second = await reopened.saveApprovedReport(proposalId, receiptId);
    require(
      report.path != second.path,
      'Second download overwrote the first report',
    );
    require(report.sha256 == second.sha256, 'Report bytes changed');
    require(report.sha256 == auditHash, 'Report differs from the audit record');
    final confirmed = await reopened.read(path);
    require(
      confirmed['receipt_id'] == receiptId &&
          confirmed['report_available'] == true,
      'The report was not linked to the recovered receipt',
    );
    final events = objects((await reopened.read('$path/audit'))['items']);
    require(
      events.where((event) => event['kind'] == 'PDF_CREATED').length == 1,
      'Multiple PDFs were generated',
    );
    stdout.writeln(
      jsonEncode({
        'asset': 'A-103',
        'verified_model_citation': true,
        'conflict_blocked': true,
        'author_rejected': true,
        'independent_approval': true,
        'reconciled_after_restart': true,
        'receipt': receiptId,
        'sha256': report.sha256,
        'pdf': report.path,
        'save_without_overwrite': true,
      }),
    );
  } finally {
    await reopened.close();
  }
}
