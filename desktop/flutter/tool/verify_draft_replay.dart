import 'dart:convert';
import 'dart:io';

import '../lib/desktop_api.dart';

Future<void> main(List<String> args) async {
  final credentials = jsonObject(
    jsonDecode(await File(args[2]).readAsString()),
  );
  final api = await DesktopApi.start(args[0], args[1]);
  try {
    await api.login(
      field(credentials, 'author'),
      field(credentials, 'password'),
    );
    final baseline = objects((await api.read('proposals'))['items']).length;
    final now = DateTime.now().toUtc().toIso8601String();
    final input = {
      'asset_id': 'A-103',
      'claim_key': 'inspection_priority',
      'effective_at': now,
      'known_as_of': now,
    };
    String conflictCheck;
    try {
      final conflict = await api.send('analysis', {
        ...input,
        'asset_id': 'A-105',
      });
      conflictCheck = field(conflict, 'state');
    } on ServerError catch (error) {
      conflictCheck = 'HTTP ${error.status}';
    }
    final attempt = jsonObject(
      (await api.send('draft-intent', {'request': input}))['attempt'],
    );
    final key = field(attempt, 'key');
    final body = {'request': jsonObject(attempt['request'])};
    final original = await api.submitStagedDraft(body, key);
    await api.send('auth/logout', {});
    await api.login(
      field(credentials, 'author'),
      field(credentials, 'password'),
    );
    final recovered = jsonObject((await api.read('draft-intent'))['attempt']);
    if (field(recovered, 'key') != key) throw StateError('Saved key changed');
    final replayed = await api.submitStagedDraft({
      'request': jsonObject(recovered['request']),
    }, key);
    final id = field(original, 'proposal_id');
    final count = objects((await api.read('proposals'))['items']).length;
    if (id.isEmpty ||
        field(replayed, 'proposal_id') != id ||
        count != baseline + 1) {
      throw StateError('Retry must recover the original proposal');
    }
    await api.send('draft-intent/clear', {'key': key});
    if ((await api.read('draft-intent'))['attempt'] != null) {
      throw StateError('The confirmed intent was not cleared');
    }
    stdout.writeln(
      jsonEncode({
        'same_request_after_relogin': true,
        'a105_analysis': conflictCheck,
        'requests_before': baseline,
        'requests_after': count,
      }),
    );
  } finally {
    api.close();
  }
}
