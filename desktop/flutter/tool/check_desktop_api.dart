import 'dart:convert';
import 'dart:io';

import '../lib/desktop_api.dart';

void require(bool pass, String message) {
  if (!pass) throw StateError(message);
}

Future<void> main(List<String> args) async {
  final layout = Directory(args[1]).absolute.path;
  final password = field(
    jsonObject(
      jsonDecode(await File('$layout/credentials.json').readAsString()),
    ),
    'password',
  );
  final api = await DesktopApi.start(args[0], '$layout/dart-contract');
  try {
    final author = await api.login('qa-engineer', password);
    final rows = objects((await api.read('proposals'))['items']);
    require(rows.length == 2, 'Expected same two fixture proposals');
    final selected = field(rows.last, 'proposal_id');
    final path = 'proposals/$selected';
    final detail = await api.read(path);
    final version = detail['review_version'];
    require(author['role'] == 'engineer', 'Expected author role');
    try {
      await api.send('$path/decision', {
        'expected_hash': detail['fingerprint'],
        'expected_version': version,
        'decision': 'approve',
      });
      throw StateError('Writer must not approve');
    } on ServerError catch (error) {
      require(error.status == 403, 'Expected explicit author denial');
    }
    await api.send('auth/logout', {});
    final reviewer = await api.login('qa-first', password);
    require(reviewer['role'] == 'approver', 'Expected independent reviewer');
    final review = await api.read(path);
    final context = jsonObject(review['review_context']);
    require(
      review['evidence_reviewable'] == true,
      'Server says evidence unavailable',
    );
    final compare = await api.send('analysis/compare', {
      'asset_id': 'A-103',
      'claim_key': context['claim_key'],
      'effective_at': context['effective_at'],
      'before_known_as_of': context['known_as_of'],
      'after_known_as_of': DateTime.now().toUtc().toIso8601String(),
    });
    require(compare['changed'] is bool, 'Real comparison expected');
    final bulk = await api.read('evidence', {
      'asset_id': 'A-103',
      'effective_at': field(context, 'effective_at'),
      'known_as_of': field(context, 'known_as_of'),
    });
    final citation = objects(review['citations']).single;
    final evidenceId = field(citation, 'evidence_id');
    final candidates = objects(bulk['items']);
    require(
      candidates.length == 30 &&
          candidates.every((row) => row['evidence_id'] != evidenceId),
      'Seed must place the approval citation outside bulk search results',
    );
    final source = await api.readCitedSource(
      citation,
      field(context, 'known_as_of'),
    );
    require(source['evidence_id'] == evidenceId, 'Expected the exact original');
    try {
      await api.readCitedSource({
        ...citation,
        'source_version': 'wrong-version',
      }, field(context, 'known_as_of'));
      throw StateError('Mismatched citation was accepted');
    } on FormatException {
      // A mismatched original cannot enable approval.
    }
    await api.send('$path/decision', {
      'expected_hash': review['fingerprint'],
      'expected_version': review['review_version'],
      'decision': 'approve',
    });
    final started = await api.send('$path/execute', {
      'simulate_response_loss': true,
    });
    require(
      started['state'] == 'UNKNOWN_RECONCILE' && started['receipt_id'] == null,
      'Expected ambiguous original execution',
    );
    await api.send('auth/logout', {});
    await api.login('qa-second', password);
    final transferable = await api.read(path);
    final guidance = jsonObject(transferable['guidance']);
    require(
      transferable['handover_allowed'] == true &&
          (guidance['actions'] as List).contains('TAKE_HANDOVER'),
      'Expected the server to allow a different reviewer to take handover',
    );
    const reason = 'Synthetic reviewer handover after response loss';
    final handover = await api.send('$path/handover', {
      'expected_hash': transferable['fingerprint'],
      'expected_version': transferable['review_version'],
      'reason': reason,
    });
    require(
      handover['assigned_approver'] == 'qa-second' &&
          handover['state'] == 'UNKNOWN_RECONCILE',
      'Handover must preserve the unknown execution state',
    );
    final recovered = await api.send('$path/reconcile', {});
    final receipt = field(recovered, 'receipt_id');
    require(
      receipt.isNotEmpty && recovered['state'] == 'SUCCEEDED',
      'Stored receipt was not recovered',
    );
    final again = await api.read(path);
    require(
      again['receipt_id'] == receipt,
      'Receipt changed after status read',
    );
    final audit = objects((await api.read('$path/audit'))['items']);
    require(
      audit.any(
        (row) =>
            row['kind'] == 'APPROVED' &&
            objects(row['approved_documents']).isNotEmpty,
      ),
      'Missing approved original',
    );
    require(
      audit.where((row) => row['kind'] == 'RECONCILED').length == 1,
      'Expected exactly one reconciliation',
    );
    require(
      jsonObject(
            audit.singleWhere((row) => row['kind'] == 'HANDOVER')['details'],
          )['reason'] ==
          reason,
      'The handover reason was not audited',
    );
    stdout.writeln(
      jsonEncode({
        'asset': 'A-103',
        'selected_id': selected,
        'author_rejected': true,
        'authorized_comparison': true,
        'original_outside_bulk_results': true,
        'mismatched_version_rejected': true,
        'approved': true,
        'ambiguous_response': true,
        'handover_reason_audited': true,
        'same_receipt': true,
        'approved_original_preserved': true,
        'receipt': receipt,
      }),
    );
  } finally {
    await api.close();
  }
}
