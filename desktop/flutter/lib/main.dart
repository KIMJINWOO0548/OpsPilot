import 'dart:async';
import 'dart:convert';
import 'dart:io' show FileSystemException, Platform;

import 'package:crypto/crypto.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'desktop_api.dart';
import 'desktop_appearance.dart';
import 'desktop_theme.dart';
import 'draft_registration.dart';

Future<void> main(List<String> arguments) async {
  WidgetsFlutterBinding.ensureInitialized();
  final appearance = DesktopAppearance(arguments);
  final initialMode = await appearance.read();
  runApp(
    ReviewApplication(
      arguments: arguments,
      appearance: appearance,
      initialMode: initialMode,
    ),
  );
}

enum _DeskSection { intake, review, settings }

class ReviewApplication extends StatefulWidget {
  const ReviewApplication({
    super.key,
    required this.arguments,
    required this.appearance,
    required this.initialMode,
  });
  final List<String> arguments;
  final DesktopAppearance appearance;
  final AppearanceMode initialMode;

  @override
  State<ReviewApplication> createState() => _ReviewApplicationState();
}

class _ReviewApplicationState extends State<ReviewApplication> {
  late AppearanceMode _mode;
  bool _savingMode = false;
  String? _appearanceNotice;

  @override
  void initState() {
    super.initState();
    _mode = widget.initialMode;
    unawaited(widget.appearance.updateFrame(_mode));
  }

  Future<void> _setMode(AppearanceMode mode) async {
    if (_savingMode || mode == _mode && _appearanceNotice == null) return;
    setState(() {
      _mode = mode;
      _savingMode = true;
      _appearanceNotice = null;
    });
    unawaited(widget.appearance.updateFrame(mode));
    try {
      await widget.appearance.save(mode);
    } on FileSystemException {
      _appearanceNotice = '색상 모드를 적용했습니다. 다음 실행에 사용할 선택은 저장하지 못했습니다.';
    } finally {
      if (mounted) setState(() => _savingMode = false);
    }
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'OpsPilot-X · 문서 검토실',
    debugShowCheckedModeBanner: false,
    theme: reviewDeskTheme(_mode),
    themeAnimationDuration: Duration.zero,
    home: ReviewDesk(
      arguments: widget.arguments,
      appearanceMode: _mode,
      onAppearanceChanged: _savingMode
          ? null
          : (mode) => unawaited(_setMode(mode)),
      appearanceNotice: _appearanceNotice,
    ),
  );
}

class ReviewDesk extends StatefulWidget {
  const ReviewDesk({
    super.key,
    required this.arguments,
    required this.appearanceMode,
    required this.onAppearanceChanged,
    required this.appearanceNotice,
  });
  final List<String> arguments;
  final AppearanceMode appearanceMode;
  final ValueChanged<AppearanceMode>? onAppearanceChanged;
  final String? appearanceNotice;

  @override
  State<ReviewDesk> createState() => _ReviewDeskState();
}

class _ReviewDeskState extends State<ReviewDesk> {
  final _account = TextEditingController();
  final _password = TextEditingController();
  final _approveFocus = FocusNode(debugLabel: '독립 승인');
  final _panelFocus = FocusNode(debugLabel: '왼쪽 패널');
  final _windowScaffold = GlobalKey<ScaffoldState>();
  DesktopApi? _api;
  List<Json> _rows = [];
  Json? _identity, _detail, _comparison;
  String? _selectedId;
  List<Json> _evidence = [];
  bool _busy = false, _panelExpanded = true;
  _DeskSection _section = _DeskSection.review;
  String _status = '로컬 서비스 준비 중';
  DeskColors get _colors => DeskColors.of(context);
  bool get _isAuthor => _identity?['role'] == 'engineer';
  String get _inboxLabel => _isAuthor ? '내 요청' : '승인함';

  @override
  void initState() {
    super.initState();
    unawaited(_run(_connect));
  }

  @override
  void dispose() {
    unawaited(_api?.close());
    _account.dispose();
    _password.dispose();
    _approveFocus.dispose();
    _panelFocus.dispose();
    super.dispose();
  }

  Future<void> _connect() async {
    final args = widget.arguments;
    String option(String name) {
      final index = args.indexOf(name);
      if (index < 0 || index + 1 >= args.length)
        throw const FormatException('작업공간 데이터와 Windows 엔진을 지정해 시작하세요.');
      return args[index + 1];
    }

    final api = await DesktopApi.start(
      option('--bundle'),
      option('--data-dir'),
      chatPort: Platform.environment['OPSPILOT_CHAT_PORT'],
      embeddingPort: Platform.environment['OPSPILOT_EMBED_PORT'],
      modelKey: Platform.environment['OPSPILOT_MODEL_KEY'],
    );
    if (!mounted) {
      await api.close();
      return;
    }
    _api = api;
    _status = '로컬 연결 완료 · 계정으로 로그인하세요.';
  }

  Future<void> _run(
    Future<void> Function() task, {
    bool isWrite = false,
  }) async {
    if (_busy) return;
    setState(() {
      _busy = true;
    });
    try {
      await task();
    } on Object catch (error) {
      _detail = _comparison = null;
      _evidence = [];
      if (error is ServerError &&
          (error.status == 401 || error.status == 403)) {
        _forgetAccount('계정 권한을 확인하지 못했습니다. 다시 로그인하세요.');
      } else if (isWrite) {
        _status = '처리 결과 미확인 · 기존 요청과 영수증을 먼저 다시 조회하세요.';
      } else if (error is FormatException) {
        _status = error.message.toString();
      } else {
        _status = '로컬 응답을 확인하지 못했습니다. 연결 또는 새로 고침을 확인하세요.';
      }
    } finally {
      if (mounted)
        setState(() {
          _busy = false;
        });
    }
  }

  Future<void> _login() async {
    final user = _account.text.trim(), password = _password.text;
    _password.clear();
    _identity = await _api!.login(user, password);
    _section = _isAuthor ? _DeskSection.intake : _DeskSection.review;
    await _refresh();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted && _identity != null && _section == _DeskSection.review) {
        _panelFocus.requestFocus();
      }
    });
  }

  void _forgetAccount(String message) {
    _api?.clearIdentity();
    _identity = _detail = _comparison = null;
    _selectedId = null;
    _rows = [];
    _evidence = [];
    _account.clear();
    _status = message;
  }

  void _changeSection(_DeskSection section) {
    if (_busy || section == _section) return;
    setState(() {
      _section = section;
      if (section != _DeskSection.review) _status = '로컬 서비스 연결';
    });
    if (section == _DeskSection.review) unawaited(_run(_refresh));
  }

  Future<void> _openSubmitted(String id) => _run(() async {
    _selectedId = id;
    _section = _DeskSection.review;
    await _refresh();
    _status = '요청 ${_shortId(id)} 등록 완료 · 검토자의 승인함에 표시됩니다.';
  });

  Future<void> _signOut() async {
    await _api!.send('auth/logout', {});
    _forgetAccount('로그아웃했습니다. 다른 계정으로 로그인할 수 있습니다.');
  }

  Future<void> _identityCheck() async {
    final current = await _api!.read('auth/me');
    if (_identity == null ||
        [
          'user_id',
          'role',
          'tenant',
          'team',
          'csrf_token',
        ].any((key) => field(current, key) != field(_identity, key))) {
      throw const ServerError(401);
    }
  }

  Future<void> _refresh() async {
    await _identityCheck();
    _rows = objects((await _api!.read('proposals'))['items']);
    if (_rows.isEmpty) {
      _selectedId = null;
      _detail = _comparison = null;
      _evidence = [];
      _status = '현재 계정에 표시할 요청이 없습니다.';
      return;
    }
    final previous = _selectedId;
    await _load(
      _rows.any((r) => r['proposal_id'] == previous)
          ? previous!
          : field(_rows.first, 'proposal_id'),
    );
  }

  Future<void> _load(String id) async {
    if (!RegExp(r'^[a-zA-Z0-9-]{1,64}$').hasMatch(id)) {
      throw const FormatException('잘못된 요청 식별자입니다.');
    }
    _selectedId = id;
    _detail = _comparison = null;
    _evidence = [];
    await _identityCheck();
    final detail = await _api!.read('proposals/$id');
    final guidance = jsonObject(detail['guidance']);
    if (detail['proposal_id'] != id ||
        guidance['version'] != 1 ||
        guidance['review_version'] != detail['review_version'] ||
        guidance['actions'] is! List) {
      throw const FormatException('서버 요청 상태를 확인하지 못했습니다.');
    }
    _detail = detail;
    if (detail['evidence_reviewable'] == true &&
        detail['review_context'] is Map) {
      final review = jsonObject(detail['review_context']);
      final fixed = field(review, 'effective_at');
      final pinnedKnown = field(review, 'known_as_of');
      final asset = field(detail, 'asset_id');
      final compare = await _api!.send('analysis/compare', {
        'asset_id': asset,
        'claim_key': field(review, 'claim_key'),
        'effective_at': fixed,
        'before_known_as_of': pinnedKnown,
        'after_known_as_of': DateTime.now().toUtc().toIso8601String(),
      });
      final before = jsonObject(compare['before']),
          after = jsonObject(compare['after']);
      if (!_sameTime(field(before, 'effective_at'), fixed) ||
          !_sameTime(field(after, 'effective_at'), fixed) ||
          !_sameTime(field(before, 'known_as_of'), pinnedKnown) ||
          compare['changed'] is! bool) {
        throw const FormatException('동일한 업무 유효 시점을 비교하지 못했습니다.');
      }
      final source = await _api!.read('evidence', {
        'asset_id': asset,
        'effective_at': fixed,
        'known_as_of': pinnedKnown,
      });
      final pins = objects(detail['citations']);
      bool matches(Json entry, Json citation) =>
          field(entry, 'text').trim().isNotEmpty &&
          sha256.convert(utf8.encode(field(entry, 'text'))).toString() ==
              field(citation, 'checksum') &&
          ['evidence_id', 'source_id', 'source_version', 'checksum'].every(
            (key) =>
                field(entry, key).isNotEmpty &&
                field(entry, key) == field(citation, key),
          );
      final originals = objects(source['items']);
      _evidence =
          pins.every((pin) => originals.any((entry) => matches(entry, pin)))
          ? originals
                .where((entry) => pins.any((pin) => matches(entry, pin)))
                .toList()
          : [];
      _comparison = compare;
    }
    _status = '서버에서 현재 요청 상태를 확인했습니다.';
  }

  static bool _sameTime(String left, String right) {
    final a = DateTime.tryParse(left), b = DateTime.tryParse(right);
    return a != null && b != null && a.isAtSameMomentAs(b);
  }

  Json? get _guidance {
    final guidance = _detail?['guidance'];
    return guidance is Json ? guidance : null;
  }

  bool _allows(String action) {
    final allowed = _guidance?['actions'];
    return allowed is List && allowed.contains(action);
  }

  String get _state => field(_detail, 'state');
  bool get _independent =>
      _identity?['role'] == 'approver' &&
      field(_identity, 'user_id').isNotEmpty &&
      field(_detail, 'owner_user').isNotEmpty &&
      _identity?['user_id'] != _detail?['owner_user'];
  bool get _readyEvidence =>
      _detail?['evidence_reviewable'] == true &&
      _comparison != null &&
      _evidence.isNotEmpty;
  bool get _canApprove =>
      !_busy &&
      _state == 'PENDING_APPROVAL' &&
      _readyEvidence &&
      _independent &&
      _guidance?['reason'] == 'NONE' &&
      _detail?['review_version'] is int &&
      RegExp(r'^[0-9a-f]{64}$').hasMatch(field(_detail, 'fingerprint')) &&
      (field(_detail, 'assigned_approver').isEmpty ||
          _detail?['assigned_approver'] == _identity?['user_id']);
  bool get _canExecute =>
      !_busy &&
      _state == 'APPROVED' &&
      _readyEvidence &&
      _independent &&
      _guidance?['reason'] == 'NONE' &&
      _detail?['approval_valid'] == true &&
      _detail?['decided_by'] == _identity?['user_id'];

  Future<void> _write(String path, Json body) async {
    final id = _selectedId;
    if (id == null) return;
    await _identityCheck();
    await _api!.send('proposals/$id/$path', body);
    await _refresh();
  }

  void _approve() {
    if (!_canApprove) return;
    final body = <String, dynamic>{
      'expected_hash': field(_detail, 'fingerprint'),
      'expected_version': _detail?['review_version'],
      'decision': 'approve',
    };
    unawaited(_run(() => _write('decision', body), isWrite: true));
  }

  void _createReport({bool simulateLoss = false}) {
    if (!_canExecute) return;
    unawaited(
      _run(
        () => _write('execute', {
          'output': 'pdf',
          'simulate_response_loss': simulateLoss,
        }),
        isWrite: true,
      ),
    );
  }

  void _saveReport() {
    final id = _selectedId;
    final receipt = field(_detail, 'receipt_id');
    if (_busy ||
        id == null ||
        receipt.isEmpty ||
        _detail?['report_available'] != true) {
      return;
    }
    _openInspector('승인 PDF 저장 완료', () async {
      try {
        final report = await _api!.saveApprovedReport(id, receipt);
        return '${report.path}\n\n영수증 $receipt\nSHA-256 ${report.sha256}';
      } on FileSystemException {
        throw const FormatException('PDF를 저장하지 못했습니다. 격리 작업 폴더의 쓰기 권한을 확인하세요.');
      }
    });
  }

  void _openInspector(String title, Future<String> Function() read) {
    unawaited(
      _run(() async {
        await _identityCheck();
        final content = await read();
        if (!mounted) return;
        await showDialog<void>(
          context: context,
          builder: (context) => AlertDialog(
            title: Text(title),
            content: SizedBox(
              width: 550,
              child: SingleChildScrollView(child: SelectableText(content)),
            ),
            actions: [
              OutlinedButton(
                onPressed: () => Navigator.pop(context),
                child: const Text('닫기'),
              ),
            ],
          ),
        );
      }),
    );
  }

  String _label(String state) => switch (state) {
    'PENDING_APPROVAL' => '승인 대기',
    'APPROVED' => '승인 완료',
    'UNKNOWN_RECONCILE' => '실행 결과 미확인',
    'SUCCEEDED' => '실행 완료',
    'REJECTED' => '거절',
    _ => state.isEmpty ? '확인 필요' : state,
  };

  String _title(Json? item) => switch (field(item, 'action')) {
    'sensor_diagnostic_first' => '센서 진단 우선',
    'inspection_first' => '현장 점검 우선',
    'manual_inspection' => '수동 점검',
    'stop_and_escalate' => '중지 후 담당자 확인',
    _ => '검토 요청',
  };

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, bounds) {
      final compact = bounds.maxWidth < 960;
      return Scaffold(
        key: _windowScaffold,
        drawerEnableOpenDragGesture: false,
        drawer: compact && _identity != null
            ? Drawer(
                shape: const RoundedRectangleBorder(),
                width: 248,
                child: _sidebar(
                  close: () => _windowScaffold.currentState?.closeDrawer(),
                ),
              )
            : null,
        onDrawerChanged: (open) {
          if (!open && mounted && _identity != null) _panelFocus.requestFocus();
        },
        body: _appBody(compact),
      );
    },
  );

  Widget _appBody(bool compact) => Column(
    children: [
      Expanded(
        child: _identity == null ? _loginView() : _workspaceView(compact),
      ),
      Container(
        width: double.infinity,
        decoration: BoxDecoration(
          color: _colors.rail,
          border: Border(top: BorderSide(color: _colors.line)),
        ),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 7),
        child: Row(
          children: [
            Icon(
              _api == null ? Icons.link_off : Icons.link,
              size: 15,
              color: _api == null ? _colors.muted : _colors.ready,
            ),
            const SizedBox(width: 8),
            Expanded(
              child: Semantics(
                liveRegion: true,
                child: Text(
                  _status,
                  style: TextStyle(fontSize: 12, color: _colors.muted),
                ),
              ),
            ),
            if (_section == _DeskSection.review && _canApprove)
              Text(
                'F6  승인으로 이동',
                style: TextStyle(fontSize: 12, color: _colors.muted),
              ),
          ],
        ),
      ),
    ],
  );

  Widget _loginView() => Center(
    child: SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: SizedBox(
        width: 360,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              _api == null ? '로컬 서비스' : 'OpsPilot 로그인',
              style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 16),
            if (_api == null)
              OutlinedButton(
                onPressed: _busy ? null : () => unawaited(_run(_connect)),
                child: const Text('로컬 서비스 다시 시작'),
              )
            else ...[
              Semantics(
                identifier: 'reviewer-account',
                child: TextField(
                  controller: _account,
                  autofocus: true,
                  decoration: const InputDecoration(labelText: '계정'),
                ),
              ),
              const SizedBox(height: 8),
              Semantics(
                identifier: 'reviewer-password',
                child: TextField(
                  controller: _password,
                  obscureText: true,
                  onSubmitted: (_) => unawaited(_run(_login)),
                  decoration: const InputDecoration(labelText: '비밀번호'),
                ),
              ),
              const SizedBox(height: 16),
              FilledButton(
                onPressed: _busy ? null : () => unawaited(_run(_login)),
                child: const Text('로그인'),
              ),
            ],
          ],
        ),
      ),
    ),
  );

  void _togglePanel(bool compact) {
    if (!compact) {
      setState(() => _panelExpanded = !_panelExpanded);
      return;
    }
    final scaffold = _windowScaffold.currentState;
    if (scaffold == null) return;
    if (scaffold.isDrawerOpen) {
      scaffold.closeDrawer();
    } else {
      scaffold.openDrawer();
    }
  }

  Widget _workspaceView(bool compact) {
    final docked = !compact && _panelExpanded;
    final title = switch (_section) {
      _DeskSection.intake => '요청 등록',
      _DeskSection.review => _inboxLabel,
      _DeskSection.settings => '설정',
    };
    return CallbackShortcuts(
      bindings: {
        const SingleActivator(LogicalKeyboardKey.keyB, control: true): () =>
            _togglePanel(compact),
        if (_section == _DeskSection.review && _canApprove)
          const SingleActivator(LogicalKeyboardKey.f6): () =>
              _approveFocus.requestFocus(),
      },
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          ColoredBox(
            color: _colors.rail,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 5),
              child: Row(
                children: [
                  OutlinedButton.icon(
                    focusNode: _panelFocus,
                    onPressed: () => _togglePanel(compact),
                    icon: Icon(docked ? Icons.menu_open : Icons.menu, size: 16),
                    label: Text(docked ? '패널 접기' : '패널 열기'),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      title,
                      style: const TextStyle(fontWeight: FontWeight.w600),
                    ),
                  ),
                  if (_section == _DeskSection.review) ...[
                    if (_isAuthor) ...[
                      OutlinedButton.icon(
                        onPressed: _busy
                            ? null
                            : () => _changeSection(_DeskSection.intake),
                        icon: const Icon(Icons.add, size: 16),
                        label: const Text('새 요청'),
                      ),
                      const SizedBox(width: 6),
                    ],
                    OutlinedButton(
                      onPressed: _busy ? null : () => unawaited(_run(_refresh)),
                      child: const Text('요청 새로 고침'),
                    ),
                    const SizedBox(width: 12),
                  ],
                  Text(
                    _isAuthor ? '요청 작성자' : '승인 검토자',
                    style: TextStyle(fontSize: 12, color: _colors.muted),
                  ),
                ],
              ),
            ),
          ),
          const Divider(height: 1),
          Expanded(
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                if (docked) ...[
                  SizedBox(width: 248, child: _sidebar()),
                  const VerticalDivider(width: 1),
                ],
                Expanded(
                  key: const ValueKey('workspace-content'),
                  child: _workspaceContent(),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _sidebar({VoidCallback? close}) => ColoredBox(
    color: _colors.rail,
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(14, 10, 10, 9),
          child: Row(
            children: [
              const Expanded(
                child: Text(
                  '작업 메뉴',
                  style: TextStyle(fontWeight: FontWeight.w600),
                ),
              ),
              if (close != null)
                IconButton(
                  tooltip: '패널 닫기',
                  onPressed: close,
                  icon: const Icon(Icons.close, size: 18),
                  constraints: const BoxConstraints(
                    minWidth: 32,
                    minHeight: 32,
                  ),
                ),
            ],
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(10, 0, 10, 10),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _navigationButton(_DeskSection.intake, Icons.add, '요청 등록', close),
              const SizedBox(height: 4),
              _navigationButton(
                _DeskSection.review,
                Icons.inbox_outlined,
                _inboxLabel,
                close,
              ),
              const SizedBox(height: 4),
              _navigationButton(
                _DeskSection.settings,
                Icons.settings_outlined,
                '설정',
                close,
              ),
            ],
          ),
        ),
        const Divider(height: 1),
        if (_section == _DeskSection.review) ...[
          Padding(
            padding: const EdgeInsets.fromLTRB(14, 10, 14, 8),
            child: Row(
              children: [
                const Expanded(
                  child: Text(
                    '검토 요청',
                    style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
                  ),
                ),
                Text(
                  '${_rows.length}건',
                  style: TextStyle(fontSize: 12, color: _colors.muted),
                ),
              ],
            ),
          ),
          const Divider(height: 1),
          Expanded(child: _requestList(close: close)),
        ] else
          const Spacer(),
        const Divider(height: 1),
        Padding(
          padding: const EdgeInsets.fromLTRB(14, 9, 14, 9),
          child: Text(
            field(_identity, 'user_id'),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(fontSize: 12, color: _colors.muted),
          ),
        ),
      ],
    ),
  );

  Widget _workspaceContent() => switch (_section) {
    _DeskSection.intake when _isAuthor => DraftRegistration(
      api: _api!,
      onSubmitted: _openSubmitted,
      onSessionExpired: () => setState(() {
        _forgetAccount('작성자 계정을 확인하지 못했습니다. 다시 로그인하세요.');
      }),
    ),
    _DeskSection.intake => _workspacePanel([
      const Text('요청 등록', style: _panelTitle),
      const SizedBox(height: 8),
      const Text('검토 대상과 근거를 정해 승인 요청을 보내는 곳입니다.'),
      const SizedBox(height: 10),
      const Text('요청 작성자 계정으로 로그인하면 등록할 수 있습니다.'),
      const SizedBox(height: 16),
      Align(
        alignment: Alignment.centerLeft,
        child: OutlinedButton(
          onPressed: () => _changeSection(_DeskSection.settings),
          child: const Text('계정 설정 열기'),
        ),
      ),
    ]),
    _DeskSection.review => LayoutBuilder(
      builder: (context, bounds) => _reviewBody(bounds.maxWidth < 870),
    ),
    _DeskSection.settings => _settingsView(),
  };

  Widget _navigationButton(
    _DeskSection section,
    IconData icon,
    String label,
    VoidCallback? close,
  ) {
    final active = _section == section;
    return Semantics(
      selected: active,
      child: OutlinedButton.icon(
        onPressed: _busy
            ? null
            : () {
                close?.call();
                _changeSection(section);
              },
        icon: Icon(icon, size: 16),
        label: Text(label),
        style: OutlinedButton.styleFrom(
          alignment: Alignment.centerLeft,
          backgroundColor: active ? _colors.selected : null,
          foregroundColor: active ? _colors.accent : null,
          overlayColor: active ? Colors.transparent : null,
        ),
      ),
    );
  }

  static const _panelTitle = TextStyle(
    fontSize: 21,
    fontWeight: FontWeight.w600,
  );

  Widget _workspacePanel(List<Widget> children) => SingleChildScrollView(
    padding: const EdgeInsets.fromLTRB(22, 20, 22, 24),
    child: Align(
      alignment: Alignment.topLeft,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 680),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: children,
        ),
      ),
    ),
  );

  Widget _settingsView() => _workspacePanel([
    const Text('설정', style: _panelTitle),
    const SizedBox(height: 18),
    const Text(
      '색상 모드',
      style: TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
    ),
    const Divider(height: 20),
    Align(
      alignment: Alignment.centerLeft,
      child: SegmentedButton<AppearanceMode>(
        segments: const [
          ButtonSegment(
            value: AppearanceMode.dark,
            label: Text('다크'),
            icon: Icon(Icons.dark_mode_outlined),
          ),
          ButtonSegment(
            value: AppearanceMode.light,
            label: Text('라이트'),
            icon: Icon(Icons.light_mode_outlined),
          ),
          ButtonSegment(
            value: AppearanceMode.warm,
            label: Text('따뜻한 톤'),
            icon: Icon(Icons.wb_twilight_outlined),
          ),
        ],
        selected: {widget.appearanceMode},
        onSelectionChanged: switch (widget.onAppearanceChanged) {
          final change? => (modes) => change(modes.single),
          null => null,
        },
      ),
    ),
    if (widget.appearanceNotice case final notice?) ...[
      const SizedBox(height: 8),
      Semantics(liveRegion: true, child: Text(notice)),
    ],
    const SizedBox(height: 22),
    const Text(
      '계정 및 연결',
      style: TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
    ),
    const Divider(height: 20),
    Text('로그인 계정  ${field(_identity, 'user_id')}'),
    const SizedBox(height: 6),
    Text(_isAuthor ? '요청 작성자 · 요청 등록 및 내 요청 확인' : '승인 검토자 · 담당 요청 검토 및 승인'),
    const SizedBox(height: 12),
    Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        OutlinedButton(
          onPressed: _busy
              ? null
              : () => unawaited(
                  _run(() async {
                    await _identityCheck();
                    _status = '로컬 서비스 연결과 현재 계정을 확인했습니다.';
                  }),
                ),
          child: const Text('연결 상태 확인'),
        ),
        OutlinedButton(
          onPressed: _busy ? null : () => unawaited(_run(_signOut)),
          child: const Text('로그아웃 · 계정 바꾸기'),
        ),
      ],
    ),
    const SizedBox(height: 22),
    const Text(
      '화면',
      style: TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
    ),
    const Divider(height: 20),
    CheckboxListTile(
      contentPadding: EdgeInsets.zero,
      controlAffinity: ListTileControlAffinity.leading,
      title: const Text('넓은 창에서 왼쪽 패널 펼치기'),
      subtitle: const Text('이번 실행에 적용됩니다.'),
      value: _panelExpanded,
      onChanged: (value) => setState(() => _panelExpanded = value ?? true),
    ),
  ]);

  Widget _requestList({VoidCallback? close}) => ListView.separated(
    itemCount: _rows.length,
    separatorBuilder: (_, _) => const Divider(height: 1),
    itemBuilder: (context, i) {
      final item = _rows[i], id = field(_rows[i], 'proposal_id');
      final selected = id == _selectedId;
      void select() {
        close?.call();
        if (!selected) unawaited(_run(() => _load(id)));
      }

      return Semantics(
        selected: selected,
        child: OutlinedButton(
          onPressed: _busy ? null : select,
          style:
              OutlinedButton.styleFrom(
                backgroundColor: selected ? _colors.selected : _colors.rail,
                alignment: Alignment.centerLeft,
                shape: const RoundedRectangleBorder(),
                padding: const EdgeInsets.fromLTRB(14, 8, 10, 8),
                overlayColor: Colors.transparent,
              ).copyWith(
                side: WidgetStateProperty.resolveWith(
                  (states) => states.contains(WidgetState.focused)
                      ? BorderSide(color: _colors.accent, width: 2)
                      : BorderSide.none,
                ),
              ),
          child: Row(
            children: [
              Padding(
                padding: const EdgeInsets.only(right: 8),
                child: Icon(
                  selected
                      ? Icons.radio_button_checked
                      : Icons.radio_button_unchecked,
                  color: selected ? _colors.accent : _colors.muted,
                  size: 13,
                ),
              ),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      _title(item),
                      style: const TextStyle(fontWeight: FontWeight.w600),
                    ),
                    Text(
                      [
                        if (field(item, 'asset_id').isNotEmpty)
                          field(item, 'asset_id'),
                        _label(field(item, 'state')),
                      ].join(' · '),
                      style: TextStyle(fontSize: 12, color: _colors.muted),
                    ),
                  ],
                ),
              ),
              Text(
                _shortId(id),
                style: TextStyle(
                  fontSize: 11,
                  color: _colors.muted,
                  fontFeatures: [FontFeature.tabularFigures()],
                ),
              ),
            ],
          ),
        ),
      );
    },
  );

  Widget _reviewBody(bool condensed) {
    final detail = _detail;
    if (detail == null)
      return Center(
        child: Text(_busy ? '현재 요청 상태를 조회하고 있습니다.' : '검토할 요청을 선택하세요.'),
      );
    final review = detail['review_context'];
    final asset = field(detail, 'asset_id');
    final owner = field(detail, 'owner_user');
    final requestId = _shortId(field(detail, 'proposal_id'));
    final evidence = _evidence.isEmpty ? null : _evidence.first;
    final current = _comparison?['after'];
    final currentCitations = current is Json && current['citations'] is List
        ? (current['citations'] as List).whereType<Json>().toList()
        : const <Json>[];
    final pinnedPanel = _evidenceSummary(
      '요청 당시 근거',
      [
        if (review is Json) '확인 기준 ${_time(field(review, 'known_as_of'))}',
        if (evidence != null)
          '${field(evidence, 'source_id')} v${field(evidence, 'source_version')}',
        if (evidence != null) field(evidence, 'text') else '확인 가능한 원문 없음',
      ],
      action: OutlinedButton(
        onPressed: _readyEvidence && !_busy ? _openSource : null,
        child: const Text('원문 보기'),
      ),
    );
    final currentPanel = _evidenceSummary('현재 근거', [
      if (current is Json) '확인 기준 ${_time(field(current, 'known_as_of'))}',
      if (currentCitations.isNotEmpty)
        '${field(currentCitations.first, 'source_id')} '
            'v${field(currentCitations.first, 'source_version')}'
            '${currentCitations.length > 1 ? ' 외 ${currentCitations.length - 1}개' : ''}',
      if (current is Json && field(current, 'recommended_action').isNotEmpty)
        '권고 조치  ${_title({'action': current['recommended_action']})}',
      if (_comparison == null) '현재 근거를 확인할 수 없습니다.',
    ]);
    final changed = _comparison?['changed'];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 13, 20, 9),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      asset.isEmpty
                          ? _title(detail)
                          : '${_title(detail)} · $asset',
                      style: TextStyle(
                        color: _colors.ink,
                        fontSize: 19,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      [
                        if (requestId.isNotEmpty) '요청 $requestId',
                        _label(_state),
                        if (owner.isNotEmpty) '작성 $owner',
                      ].join(' · '),
                      style: TextStyle(
                        fontSize: 12,
                        color: _colors.muted,
                        fontFeatures: [FontFeature.tabularFigures()],
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 10),
              OutlinedButton(
                onPressed: _busy ? null : _openHistory,
                child: const Text('요청 이력'),
              ),
            ],
          ),
        ),
        const Divider(height: 1),
        Expanded(
          child: SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(20, 9, 20, 9),
                  child: Wrap(
                    spacing: 12,
                    runSpacing: 4,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: [
                      Text(
                        switch (changed) {
                          true => '판정 또는 근거 변경',
                          false => '판정과 근거에 변경 없음',
                          _ => '비교 결과 확인 필요',
                        },
                        style: TextStyle(
                          color: changed == false
                              ? _colors.ready
                              : _colors.accent,
                          fontSize: 13,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      if (review is Json)
                        Text(
                          '업무 적용 기준 ${_time(field(review, 'effective_at'))}',
                          style: TextStyle(fontSize: 12, color: _colors.muted),
                        ),
                    ],
                  ),
                ),
                const Divider(height: 1),
                ColoredBox(
                  color: _colors.surface,
                  child: condensed
                      ? Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            pinnedPanel,
                            const Divider(height: 1),
                            currentPanel,
                          ],
                        )
                      : IntrinsicHeight(
                          child: Row(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              Expanded(child: pinnedPanel),
                              const VerticalDivider(width: 1),
                              Expanded(child: currentPanel),
                            ],
                          ),
                        ),
                ),
                const Divider(height: 1),
              ],
            ),
          ),
        ),
        const Divider(height: 1),
        ColoredBox(
          color: _colors.surface,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 8, 20, 8),
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        _nextStepTitle(),
                        style: const TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      const SizedBox(height: 3),
                      if (_allows('VIEW_RECEIPT'))
                        SelectableText(
                          '영수증 ${field(detail, 'receipt_id')}',
                          style: TextStyle(fontSize: 12, color: _colors.muted),
                        )
                      else
                        Text(
                          _decisionMessage(),
                          style: TextStyle(fontSize: 12, color: _colors.muted),
                        ),
                    ],
                  ),
                ),
                const SizedBox(width: 12),
                Wrap(
                  spacing: 6,
                  runSpacing: 4,
                  children: [
                    if (_state == 'PENDING_APPROVAL')
                      Semantics(
                        identifier: 'review-approve',
                        child: FilledButton(
                          focusNode: _approveFocus,
                          onPressed: _canApprove ? _approve : null,
                          child: const Text('요청 승인'),
                        ),
                      ),
                    if (_state == 'APPROVED')
                      Semantics(
                        identifier: 'review-create-report',
                        child: FilledButton(
                          onPressed: _canExecute ? _createReport : null,
                          child: const Text('승인 PDF 생성'),
                        ),
                      ),
                    if (_state == 'APPROVED')
                      OutlinedButton(
                        onPressed: _canExecute
                            ? () => _createReport(simulateLoss: true)
                            : null,
                        child: const Text('응답 유실 시연'),
                      ),
                    if (_allows('CHECK_RECEIPT'))
                      FilledButton(
                        onPressed: _busy
                            ? null
                            : () => unawaited(
                                _run(
                                  () => _write('reconcile', {}),
                                  isWrite: true,
                                ),
                              ),
                        child: const Text('실행 결과 확인'),
                      ),
                    if (_state == 'SUCCEEDED' &&
                        detail['report_available'] == true)
                      Semantics(
                        identifier: 'review-save-report',
                        child: FilledButton(
                          onPressed: _busy ? null : _saveReport,
                          child: const Text('PDF 저장'),
                        ),
                      ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  String _shortId(String id) => id.length > 8 ? id.substring(0, 8) : id;

  void _openSource() => _openInspector('요청 당시 원문', () async {
    await _load(_selectedId!);
    if (_evidence.isEmpty) return '지금은 이 요청의 원문을 확인할 수 없습니다.';
    return _evidence
        .map(
          (source) => [
            '${field(source, 'source_id')} v${field(source, 'source_version')}',
            field(source, 'locator'),
            field(source, 'text'),
          ].join('\n'),
        )
        .join('\n\n');
  });

  void _openHistory() => _openInspector('요청 이력', () async {
    final reply = await _api!.read('proposals/${_selectedId!}/audit');
    final events = objects(reply['items']);
    if (events.isEmpty) return '표시할 요청 이력이 없습니다.';
    return events
        .map((item) {
          final kind = field(item, 'kind');
          final label = switch (kind) {
            'CREATED' => '요청 등록',
            'APPROVED' => '요청 승인',
            'HANDOVER' => '승인 담당 변경',
            'PDF_CREATED' => '승인 PDF 생성',
            'RESPONSE_LOST' => '실행 응답 유실',
            'RECONCILED' => '저장된 영수증 확인',
            _ => kind,
          };
          final originals = objects(item['approved_documents']).map(
            (doc) =>
                '${field(doc, 'source_id')} v${field(doc, 'source_version')}\n${field(doc, 'text')}',
          );
          return [
            '$label  ${_time(field(item, 'logged_at'))}',
            ...originals,
          ].join('\n');
        })
        .join('\n\n');
  });

  String _nextStepTitle() => switch (_state) {
    'PENDING_APPROVAL' when _canApprove => '근거 확인 후 요청 승인',
    'PENDING_APPROVAL' when _isAuthor => '검토자 승인 대기',
    'PENDING_APPROVAL' => '승인할 수 없음',
    'APPROVED' => '요청 승인 완료',
    'UNKNOWN_RECONCILE' => '실행 결과 확인 필요',
    'SUCCEEDED' => '실행 결과 확인 완료',
    _ => _label(_state),
  };

  String _decisionMessage() {
    if (_busy) return '현재 상태 확인 중입니다.';
    if (_canApprove) return '두 근거를 비교하세요. 승인하면 당시 근거 버전이 기록됩니다.';
    return switch (_state) {
      'PENDING_APPROVAL' when _isAuthor =>
        '승인은 독립 검토자가 합니다. 이 화면에서 처리 상태를 확인하세요.',
      'PENDING_APPROVAL' when !_readyEvidence =>
        '두 시점의 근거를 확인할 수 없습니다. 원문 접근 권한을 확인하세요.',
      'PENDING_APPROVAL' when _guidance?['reason'] == 'REVIEW_REQUIRED' =>
        '현재 검토 기준을 다시 확인해야 합니다. 요청을 새로 고치세요.',
      'PENDING_APPROVAL'
          when field(_detail, 'assigned_approver').isNotEmpty &&
              _detail?['assigned_approver'] != _identity?['user_id'] =>
        '다른 검토자에게 배정된 요청입니다.',
      'PENDING_APPROVAL' => '현재 계정으로 이 요청을 승인할 수 없습니다.',
      'UNKNOWN_RECONCILE' when _allows('CHECK_RECEIPT') =>
        '한 번 시작한 작업의 저장된 영수증을 찾습니다.',
      'UNKNOWN_RECONCILE' => '담당 검토자가 실행 결과를 확인할 수 있습니다.',
      'APPROVED' when _canExecute => '승인 당시 근거와 영수증을 담은 로컬 PDF를 생성합니다.',
      'APPROVED' => '이 계정이나 근거 상태에서는 PDF를 생성할 수 없습니다.',
      _ => '',
    };
  }

  Widget _evidenceSummary(
    String heading,
    List<String> rows, {
    Widget? action,
  }) => Container(
    width: double.infinity,
    padding: const EdgeInsets.fromLTRB(20, 9, 20, 11),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(
              child: Text(
                heading,
                style: TextStyle(
                  color: _colors.accent,
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
            if (action != null) action,
          ],
        ),
        const SizedBox(height: 3),
        for (final row in rows)
          Text(
            row,
            style: TextStyle(
              fontSize: 13,
              color: _colors.ink,
              height: 1.35,
              fontFeatures: [FontFeature.tabularFigures()],
            ),
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
          ),
      ],
    ),
  );

  String _time(String input) {
    final time = DateTime.tryParse(input)?.toUtc();
    if (time == null) return '미확인';
    final kst = time.add(const Duration(hours: 9));
    return '${kst.month}.${kst.day} ${kst.toIso8601String().substring(11, 19)} KST';
  }
}
