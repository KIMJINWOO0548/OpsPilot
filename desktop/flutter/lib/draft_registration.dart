import 'dart:async';

import 'package:flutter/material.dart';

import 'desktop_api.dart';
import 'desktop_theme.dart';

class DraftRegistration extends StatefulWidget {
  const DraftRegistration({
    super.key,
    required this.api,
    required this.onSubmitted,
    required this.onSessionExpired,
  });

  final DesktopApi api;
  final Future<void> Function(String id) onSubmitted;
  final VoidCallback onSessionExpired;

  @override
  State<DraftRegistration> createState() => _DraftRegistrationState();
}

class _DraftRegistrationState extends State<DraftRegistration> {
  final _query = TextEditingController();
  List<String> _assets = [];
  Map<String, List<String>> _claimsByAsset = {};
  String? _asset, _claim;
  Json? _attempt, _preview, _reviewedInput, _hybrid;
  bool _busy = false, _loaded = false;
  bool _managedWorkspace = false;
  String? _status, _rejectedKey;

  @override
  void initState() {
    super.initState();
    unawaited(_run(_load));
  }

  @override
  void dispose() {
    _query.dispose();
    super.dispose();
  }

  Json? _readAttempt(Json reply) {
    if (reply.containsKey('attempt') && reply['attempt'] == null) return null;
    final attempt = jsonObject(reply['attempt']);
    final request = jsonObject(attempt['request']);
    if (field(attempt, 'key').isEmpty ||
        field(request, 'asset_id').isEmpty ||
        DateTime.tryParse(field(request, 'effective_at')) == null ||
        DateTime.tryParse(field(request, 'known_as_of')) == null) {
      throw const FormatException('저장된 등록 요청을 확인할 수 없습니다.');
    }
    return attempt;
  }

  Future<void> _load() async {
    final api = widget.api;
    final attempt = _readAttempt(await api.read('draft-intent'));
    if (!mounted) return;
    _attempt = attempt;
    _rejectedKey = null;
    if (attempt != null) {
      _loaded = true;
      return;
    }
    final scenarios = await api.read('demo/scenarios');
    if (!mounted) return;
    final assets = scenarios['assets'];
    if (assets is! List) {
      throw const FormatException('조회할 수 있는 자산 목록을 확인할 수 없습니다.');
    }
    _assets = assets.whereType<String>().where((id) => id.isNotEmpty).toList();
    final catalog = scenarios['claims_by_asset'];
    _claimsByAsset = catalog is Map<String, dynamic>
        ? {
            for (final entry in catalog.entries)
              if (entry.value is List)
                entry.key: (entry.value as List).whereType<String>().toList(),
          }
        : {};
    _managedWorkspace = scenarios['managed_workspace'] == true;
    if (!_assets.contains(_asset)) {
      _asset = _claim = null;
    } else if (!_claims.contains(_claim)) {
      _claim = _defaultClaim(_asset);
    }
    _loaded = true;
  }

  Future<void> _run(Future<void> Function() task) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _status = null;
    });
    try {
      await task();
    } on ServerError catch (error) {
      if (!mounted) return;
      if (error.status == 401 || error.status == 403) {
        widget.onSessionExpired();
      } else if (error.status == 422 && _rejectedKey != null) {
        _status = '기준 시각 또는 근거가 달라져 서버가 등록을 거절했습니다.';
      } else if (_attempt == null) {
        _status = '서버가 요청을 처리하지 못했습니다 (오류 ${error.status}). 현재 상태를 다시 확인하세요.';
      } else {
        _status ??= _retryMessage;
      }
    } on FormatException catch (error) {
      if (mounted) _status = error.message.toString();
    } on Object {
      if (mounted) _status ??= _retryMessage;
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  String get _retryMessage => _attempt == null
      ? '서버 응답을 확인하지 못했습니다. 연결 또는 현재 상태를 다시 확인하세요.'
      : '등록 결과를 확인하지 못했습니다. 저장된 등록 결과를 다시 확인하세요.';

  void _choose(String? asset) {
    setState(() {
      _asset = asset;
      _claim = _defaultClaim(asset);
      _preview = _reviewedInput = _hybrid = null;
      _status = null;
    });
  }

  List<String> get _claims => _claimsByAsset[_asset] ?? const [];

  String? _defaultClaim(String? asset) {
    if (asset == null) return null;
    final claims = _claimsByAsset[asset] ?? const <String>[];
    return claims.isEmpty || claims.contains('inspection_priority')
        ? 'inspection_priority'
        : claims.first;
  }

  void _chooseClaim(String? claim) {
    setState(() {
      _claim = claim;
      _preview = _reviewedInput = _hybrid = null;
      _status = null;
    });
  }

  String _claimLabel(String claim) => switch (claim) {
    'inspection_priority' => '우선 점검',
    'first_action' => '첫 조치',
    _ => claim.replaceAll('_', ' '),
  };

  Json _currentRequest() {
    final stamp = DateTime.now().toUtc().toIso8601String();
    return <String, dynamic>{
      'asset_id': _asset,
      'claim_key': _claim,
      'effective_at': stamp,
      'known_as_of': stamp,
    };
  }

  Future<void> _checkEvidence() async {
    _preview = _reviewedInput = _hybrid = null;
    final request = _currentRequest();
    final response = await widget.api.send('analysis', request);
    objects(response['citations']);
    if (mounted) {
      _preview = response;
      _reviewedInput = request;
    }
  }

  bool get _canRunHybrid =>
      widget.api.modelConfigured &&
      !_busy &&
      _claim != null &&
      _query.text.trim().isNotEmpty;

  void _startHybrid() {
    if (_canRunHybrid) unawaited(_run(_checkHybrid));
  }

  Future<void> _checkHybrid() async {
    _preview = _reviewedInput = _hybrid = null;
    final request = _currentRequest();
    final Json response;
    try {
      response = await widget.api.hybridAnalysis({
        ...request,
        'query': _query.text.trim(),
      });
    } on TimeoutException {
      _status = '로컬 AI의 응답 시간이 지났습니다. 다시 시도하거나 규칙으로 근거를 확인하세요.';
      return;
    } on ServerError catch (error) {
      if (error.status != 503) rethrow;
      _status = '로컬 AI가 연결되지 않았습니다. 실행 환경을 확인하거나 규칙으로 근거를 확인하세요.';
      return;
    }
    if (!mounted) return;
    final analysis = jsonObject(response['analysis']);
    _hybrid = response;
    final status = field(response, 'model_status');
    if (status == 'DRAFT_READY' || status == 'POLICY_BLOCKED') {
      _preview = analysis;
      _reviewedInput = request;
    }
  }

  void _queryChanged(String _) {
    setState(() {
      if (_hybrid != null) _preview = _reviewedInput = null;
      _hybrid = null;
      _status = null;
    });
  }

  Future<void> _openSource(Json citation) async {
    final request = _reviewedInput;
    if (request == null) return;
    final Json source;
    try {
      source = await widget.api.read('evidence/source', {
        'evidence_id': field(citation, 'evidence_id'),
        'known_as_of': field(request, 'known_as_of'),
      });
    } on ServerError catch (error) {
      if (error.status != 404) rethrow;
      _status = '현재 권한으로 원문을 열 수 없습니다. 근거를 다시 확인하세요.';
      return;
    }
    if ([
      'evidence_id',
      'source_version',
      'checksum',
    ].any((key) => field(source, key) != field(citation, key))) {
      throw const FormatException('원문 버전 또는 해시가 달라졌습니다. 근거를 다시 확인하세요.');
    }
    if (!mounted) return;
    await showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(
          '${field(source, 'source_id')} v${field(source, 'source_version')}',
        ),
        content: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 580, maxHeight: 400),
          child: SingleChildScrollView(
            child: SelectableText(
              '${field(source, 'locator')}\n\n${field(source, 'text')}',
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('닫기'),
          ),
        ],
      ),
    );
  }

  bool _sameRequest(Json left, Json right) =>
      field(left, 'asset_id') == field(right, 'asset_id') &&
      field(left, 'claim_key') == field(right, 'claim_key') &&
      ['effective_at', 'known_as_of'].every((fieldName) {
        final a = DateTime.tryParse(field(left, fieldName));
        final b = DateTime.tryParse(field(right, fieldName));
        return a != null && b != null && a.isAtSameMomentAs(b);
      });

  bool get _supported =>
      field(_preview, 'state') == 'SUPPORTED' &&
      field(_preview, 'recommended_action').isNotEmpty &&
      objects(_preview?['citations']).isNotEmpty;

  Future<void> _sendForApproval() async {
    final request = _reviewedInput;
    if (request == null || !_supported) return;
    final age = DateTime.now().difference(
      DateTime.parse(field(request, 'effective_at')),
    );
    if (age.isNegative || age >= const Duration(hours: 1)) {
      _preview = _reviewedInput = null;
      _status = '확인 시점이 지났습니다. 근거를 다시 확인한 뒤 등록하세요.';
      return;
    }
    final api = widget.api;
    _loaded = false;
    final staged = _readAttempt(
      await api.send('draft-intent', {'request': request}),
    );
    if (!mounted) return;
    if (staged == null) {
      throw const FormatException('서버에서 저장된 등록 요청을 확인할 수 없습니다.');
    }
    _attempt = staged;
    _loaded = true;
    if (staged['review_due_at'] != null ||
        !_sameRequest(jsonObject(staged['request']), request)) {
      _status = '먼저 서버에 남아 있는 등록 요청을 확인하세요.';
      return;
    }
    await _submitAttempt();
  }

  Future<void> _submitAttempt() async {
    final attempt = _attempt;
    if (attempt == null) return;
    final api = widget.api;
    final key = field(attempt, 'key');
    _rejectedKey = null;
    final Json result;
    try {
      result = await api.submitStagedDraft({
        'request': jsonObject(attempt['request']),
        if (attempt['review_due_at'] != null)
          'review_due_at': attempt['review_due_at'],
      }, key);
    } on ServerError catch (error) {
      if (mounted && error.status == 422) _rejectedKey = key;
      rethrow;
    }
    final id = field(result, 'proposal_id');
    if (!RegExp(
      r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$',
    ).hasMatch(id)) {
      throw const FormatException(
        '서버가 반환한 요청 번호를 확인할 수 없습니다. 등록 결과를 다시 확인하세요.',
      );
    }
    if (!mounted) return;
    _status = '요청을 등록했습니다. 저장 상태를 정리하지 못하면 등록 결과를 다시 확인하세요.';
    final cleared = await api.send('draft-intent/clear', {'key': key});
    if (!mounted) return;
    if (cleared['ok'] != true) {
      throw const FormatException('요청을 등록했습니다. 저장된 등록 결과를 다시 확인하세요.');
    }
    _attempt = _preview = _reviewedInput = null;
    _status = '승인 요청을 보냈습니다.';
    await widget.onSubmitted(id);
  }

  Future<void> _discardRejectedAttempt() async {
    final key = _rejectedKey;
    if (key == null || field(_attempt, 'key') != key) return;
    final reply = await widget.api.send('draft-intent/clear', {'key': key});
    if (!mounted) return;
    if (reply['ok'] != true) {
      throw const FormatException('저장된 입력을 지웠는지 확인할 수 없습니다.');
    }
    _attempt = _preview = _reviewedInput = null;
    _rejectedKey = null;
    _loaded = false;
    await _load();
  }

  String _actionLabel(String action) => switch (action) {
    'sensor_diagnostic_first' => '센서 진단 우선',
    'inspection_first' => '현장 점검 우선',
    'manual_inspection' => '수동 점검',
    'stop_and_escalate' => '중지 후 담당자 확인',
    _ => '서버가 확인한 조치 ${action.replaceAll('_', ' ')}',
  };

  String get _condition => switch (field(_preview, 'state')) {
    'CONFLICT' => '문서의 지시가 서로 달라 승인 요청을 보낼 수 없습니다.',
    'STALE' => '현재 시점에 유효한 근거가 없습니다.',
    _ => '등록에 필요한 근거를 확인할 수 없습니다.',
  };

  String get _hybridState => switch (field(_hybrid, 'model_status')) {
    'DRAFT_READY' => '원문과 대조한 AI 인용',
    'POLICY_BLOCKED' => '규칙 판정에서 차단되어 AI를 호출하지 않았습니다.',
    'MODEL_UNAVAILABLE' => '로컬 AI에 연결하지 못했습니다. 다시 시도하거나 규칙으로 확인하세요.',
    'MODEL_REVIEW_REQUIRED' => 'AI 인용을 확인하지 못했습니다. 원문을 규칙으로 확인하세요.',
    'CONTEXT_LIMIT' => '검색할 근거가 로컬 AI 처리 한도를 넘었습니다. 규칙으로 확인하세요.',
    _ => 'AI 분석 상태를 확인하지 못했습니다. 규칙으로 근거를 확인하세요.',
  };

  @override
  Widget build(BuildContext context) {
    final attempt = _attempt;
    final preview = _preview;
    final rejected =
        _rejectedKey != null && field(attempt, 'key') == _rejectedKey;
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(24, 20, 24, 24),
      child: Align(
        alignment: Alignment.topLeft,
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 720),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text('요청 등록', style: Theme.of(context).textTheme.headlineSmall),
              const SizedBox(height: 4),
              Text(
                '자산을 선택하고 현재 근거를 확인한 뒤 승인함으로 보냅니다.',
                style: TextStyle(color: DeskColors.of(context).muted),
              ),
              const Divider(height: 26),
              if (!_loaded) ...[
                if (_busy) const LinearProgressIndicator(),
                if (!_busy)
                  Align(
                    alignment: Alignment.centerLeft,
                    child: OutlinedButton(
                      onPressed: () => unawaited(_run(_load)),
                      child: const Text('서버에 저장된 요청 확인'),
                    ),
                  ),
              ] else if (attempt != null) ...[
                Text(
                  '저장된 등록 요청 · ${field(jsonObject(attempt['request']), 'asset_id')}',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                const SizedBox(height: 6),
                Text(
                  rejected
                      ? '거절된 입력을 지운 뒤 현재 근거로 새 요청을 등록할 수 있습니다.'
                      : '먼저 같은 요청의 등록 결과를 확인하세요.',
                ),
                const SizedBox(height: 12),
                Align(
                  alignment: Alignment.centerLeft,
                  child: FilledButton(
                    onPressed: _busy
                        ? null
                        : () => unawaited(
                            _run(
                              rejected
                                  ? _discardRejectedAttempt
                                  : _submitAttempt,
                            ),
                          ),
                    child: Text(rejected ? '등록이 거절된 입력 지우기' : '저장된 등록 결과 확인'),
                  ),
                ),
              ] else if (_assets.isEmpty) ...[
                const Text('현재 계정에서 근거를 확인할 수 있는 자산이 없습니다.'),
                const SizedBox(height: 8),
                Align(
                  alignment: Alignment.centerLeft,
                  child: OutlinedButton(
                    onPressed: _busy ? null : () => unawaited(_run(_load)),
                    child: const Text('자산 목록 다시 확인'),
                  ),
                ),
              ] else ...[
                Wrap(
                  spacing: 10,
                  runSpacing: 8,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    SizedBox(
                      width: 235,
                      child: InputDecorator(
                        decoration: const InputDecoration(
                          labelText: '업무 대상 자산',
                        ),
                        child: DropdownButtonHideUnderline(
                          child: DropdownButton<String>(
                            isDense: true,
                            isExpanded: true,
                            value: _assets.contains(_asset) ? _asset : null,
                            hint: const Text('자산 선택'),
                            items: [
                              for (final id in _assets)
                                DropdownMenuItem(value: id, child: Text(id)),
                            ],
                            onChanged: _busy ? null : _choose,
                          ),
                        ),
                      ),
                    ),
                    if (_claims.isNotEmpty &&
                        (_managedWorkspace || _claims.length > 1))
                      SizedBox(
                        width: 210,
                        child: InputDecorator(
                          decoration: const InputDecoration(labelText: '검토 항목'),
                          child: DropdownButtonHideUnderline(
                            child: DropdownButton<String>(
                              isDense: true,
                              isExpanded: true,
                              value: _claims.contains(_claim) ? _claim : null,
                              items: [
                                for (final claim in _claims)
                                  DropdownMenuItem(
                                    value: claim,
                                    child: Text(_claimLabel(claim)),
                                  ),
                              ],
                              onChanged: _busy ? null : _chooseClaim,
                            ),
                          ),
                        ),
                      ),
                    if (!_managedWorkspace && _assets.contains('A-103'))
                      OutlinedButton(
                        onPressed: _busy ? null : () => _choose('A-103'),
                        child: const Text('A-103 예시 선택'),
                      ),
                  ],
                ),
                const SizedBox(height: 12),
                if (widget.api.modelConfigured) ...[
                  Semantics(
                    identifier: 'hybrid-query',
                    child: TextField(
                      controller: _query,
                      enabled: !_busy,
                      maxLength: 400,
                      onChanged: _queryChanged,
                      onSubmitted: (_) => _startHybrid(),
                      decoration: InputDecoration(
                        labelText: '근거를 찾을 질문',
                        hintText: _managedWorkspace
                            ? '이 상황에서 어떤 조치를 먼저 해야 하나요?'
                            : '필터를 교체하기 전에 무엇을 확인해야 하나요?',
                        counterText: '',
                      ),
                    ),
                  ),
                  const SizedBox(height: 8),
                ],
                Wrap(
                  spacing: 8,
                  runSpacing: 6,
                  children: [
                    if (widget.api.modelConfigured)
                      Semantics(
                        identifier: 'hybrid-run',
                        child: FilledButton(
                          onPressed: _canRunHybrid ? _startHybrid : null,
                          child: const Text('AI로 근거 조회'),
                        ),
                      ),
                    OutlinedButton(
                      onPressed: _busy || _claim == null
                          ? null
                          : () => unawaited(_run(_checkEvidence)),
                      child: const Text('규칙으로 근거 확인'),
                    ),
                  ],
                ),
                if (_busy) const LinearProgressIndicator(),
                if (_hybrid != null) ...[
                  const SizedBox(height: 12),
                  Semantics(liveRegion: true, child: Text(_hybridState)),
                  if (_hybrid?['draft'] case final Map<String, dynamic> draft)
                    for (final citation in objects(draft['citations']))
                      Padding(
                        padding: const EdgeInsets.only(top: 6),
                        child: SelectableText(
                          '${field(citation, 'source_id')} v${field(citation, 'source_version')} · '
                          '${field(citation, 'locator')}\n${field(citation, 'quote')}',
                        ),
                      ),
                ],
                if (preview != null) ...[
                  const Divider(height: 26),
                  Text('규칙 판정', style: Theme.of(context).textTheme.titleMedium),
                  const SizedBox(height: 6),
                  if (_supported)
                    Text(_actionLabel(field(preview, 'recommended_action'))),
                  if (!_supported) Text(_condition),
                  for (final citation in objects(preview['citations']))
                    Wrap(
                      spacing: 8,
                      crossAxisAlignment: WrapCrossAlignment.center,
                      children: [
                        Text(
                          '${field(citation, 'source_id')} v${field(citation, 'source_version')}  ·  ${field(citation, 'locator')}',
                          style: TextStyle(color: DeskColors.of(context).muted),
                        ),
                        OutlinedButton(
                          onPressed: _busy
                              ? null
                              : () => unawaited(
                                  _run(() => _openSource(citation)),
                                ),
                          child: const Text('원문 보기'),
                        ),
                      ],
                    ),
                  if (_supported) ...[
                    const SizedBox(height: 12),
                    Align(
                      alignment: Alignment.centerLeft,
                      child: FilledButton(
                        onPressed: _busy
                            ? null
                            : () => unawaited(_run(_sendForApproval)),
                        child: const Text('승인 요청 보내기'),
                      ),
                    ),
                  ],
                ],
              ],
              if (_status != null) ...[
                const SizedBox(height: 12),
                Semantics(liveRegion: true, child: Text(_status!)),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
