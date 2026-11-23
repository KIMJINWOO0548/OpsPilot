import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:crypto/crypto.dart';

typedef Json = Map<String, dynamic>;

Json jsonObject(Object? input) {
  if (input is Map<String, dynamic>) return input;
  throw const FormatException('서버가 올바른 응답을 보내지 않았습니다.');
}

String field(Json? data, String key) => data?[key]?.toString() ?? '';
List<Json> objects(Object? value) =>
    value is List ? value.map(jsonObject).toList() : const [];

final class ServerError implements Exception {
  const ServerError(this.status);
  final int status;
}

final class DesktopApi {
  DesktopApi._(
    this._process,
    this._origin,
    this._token,
    this._data,
    this.modelConfigured,
  );

  final Process _process;
  final Uri _origin;
  final String _token;
  final Directory _data;
  final bool modelConfigured;
  final HttpClient _http = HttpClient()
    ..findProxy = ((_) => 'DIRECT')
    ..connectionTimeout = const Duration(seconds: 5);
  Cookie? _session;
  String _csrf = '';
  static const _timeout = Duration(seconds: 15);
  static const _modelTimeout = Duration(seconds: 95);
  static const _cookieName = 'opspilot_session';
  static final _uuid = RegExp(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
  );

  static String _windowsPath(String value) =>
      value.replaceAll('/', r'\').toLowerCase();

  static Future<DesktopApi> start(
    String bundlePath,
    String dataPath, {
    String? chatPort,
    String? embeddingPort,
    String? modelKey,
  }) async {
    final bundle = Directory(bundlePath).absolute;
    final data = Directory(dataPath).absolute;
    final sep = Platform.pathSeparator;
    final python = '${bundle.path}${sep}backend${sep}python${sep}python.exe';
    final web = '${bundle.path}${sep}backend${sep}web${sep}dist';
    if (!await File(python).exists() ||
        !await File('${data.path}${sep}opspilot.sqlite3').exists()) {
      throw const FormatException('작업공간 데이터와 앱 엔진을 확인하세요.');
    }
    if (!RegExp(r'^[a-zA-Z]:[\\/]').hasMatch(data.path) ||
        !RegExp(r'^[a-zA-Z]:[\\/]').hasMatch(bundle.path) ||
        _windowsPath(await data.resolveSymbolicLinks()) !=
            _windowsPath(data.path) ||
        _windowsPath(await bundle.resolveSymbolicLinks()) !=
            _windowsPath(bundle.path)) {
      throw const FormatException('실제 로컬 작업 폴더를 선택하세요.');
    }
    final restricted = <String, String>{};
    for (final key in ['SystemRoot', 'SystemDrive', 'TEMP', 'TMP']) {
      final value = Platform.environment[key];
      if (value != null && value.codeUnits.every((unit) => unit < 128)) {
        restricted[key] = value;
      }
    }
    final modelConfigured =
        chatPort != null || embeddingPort != null || modelKey != null;
    if (modelConfigured) {
      bool validPort(String? value) =>
          value != null &&
          RegExp(r'^[1-9][0-9]{0,4}$').hasMatch(value) &&
          int.parse(value) <= 65535;
      if (!validPort(chatPort) ||
          !validPort(embeddingPort) ||
          chatPort == embeddingPort ||
          (modelKey != null && !RegExp(r'^[0-9a-f]{64}$').hasMatch(modelKey))) {
        throw const FormatException('로컬 AI 설정을 확인하세요.');
      }
      restricted['OPSPILOT_CHAT_PORT'] = chatPort!;
      restricted['OPSPILOT_EMBED_PORT'] = embeddingPort!;
      if (modelKey != null) restricted['OPSPILOT_MODEL_KEY'] = modelKey;
    }
    final process = await Process.start(
      python,
      [
        '-I',
        '-B',
        '-u',
        '-m',
        'opspilot_x.desktop_runtime',
        '--data-dir',
        data.path,
        '--web-dir',
        web,
      ],
      workingDirectory: bundle.path,
      includeParentEnvironment: false,
      environment: restricted,
    );
    unawaited(process.stderr.drain<void>());
    final token = List.generate(
      32,
      (_) => Random.secure().nextInt(256).toRadixString(16).padLeft(2, '0'),
    ).join();
    final output = StreamIterator(
      process.stdout.transform(utf8.decoder).transform(const LineSplitter()),
    );
    try {
      process.stdin.writeln(jsonEncode({'token': token}));
      await process.stdin.flush();
      if (!await output.moveNext().timeout(_timeout) ||
          output.current.length > 8192) {
        throw const FormatException('로컬 서비스가 시작되지 않았습니다.');
      }
      final ready = jsonObject(jsonDecode(output.current));
      final address = field(ready, 'origin');
      if (ready['event'] != 'ready' ||
          ready['token'] != token ||
          !RegExp(r'^http://127\.0\.0\.1:[1-9][0-9]{0,4}$').hasMatch(address)) {
        throw const FormatException('격리 서비스의 준비 응답을 확인하지 못했습니다.');
      }
      final origin = Uri.parse(address);
      if (origin.port > 65535) throw const FormatException('잘못된 포트입니다.');
      await output.cancel();
      final api = DesktopApi._(process, origin, token, data, modelConfigured);
      try {
        final health = await api._request(Uri(path: '/health'));
        if (health['ok'] != true) throw const FormatException('서비스 검증 실패');
        return api;
      } catch (_) {
        await api.close();
        rethrow;
      }
    } catch (_) {
      await output.cancel();
      process.kill();
      rethrow;
    }
  }

  Future<Json> read(String path, [Map<String, String>? query]) =>
      _request(Uri(path: '/api/v1/$path', queryParameters: query));

  Future<Json> readCitedSource(Json citation, String knownAsOf) async {
    final original = await read('evidence/source', {
      'evidence_id': field(citation, 'evidence_id'),
      'known_as_of': knownAsOf,
    });
    final text = original['text'];
    final matches = ['evidence_id', 'source_id', 'source_version', 'checksum']
        .every((key) {
          final expected = field(citation, key);
          return expected.isNotEmpty && original[key] == expected;
        });
    if (!matches ||
        text is! String ||
        text.trim().isEmpty ||
        sha256.convert(utf8.encode(text)).toString() != citation['checksum']) {
      throw const FormatException('원문 버전 또는 해시가 달라졌습니다. 근거를 다시 확인하세요.');
    }
    return original;
  }

  Future<Json> send(String path, Json data) =>
      _request(Uri(path: '/api/v1/$path'), data);

  Future<Json> hybridAnalysis(Json data) =>
      _request(Uri(path: '/api/v1/analysis/hybrid'), data, null, _modelTimeout);

  Future<({String path, String sha256})> saveApprovedReport(
    String proposalId,
    String receiptId,
  ) async {
    if (!_uuid.hasMatch(proposalId) || !_uuid.hasMatch(receiptId)) {
      throw const FormatException('요청과 영수증 식별자를 확인할 수 없습니다.');
    }
    final detail = await read('proposals/$proposalId');
    if (detail['state'] != 'SUCCEEDED' ||
        detail['receipt_id'] != receiptId ||
        detail['report_available'] != true) {
      throw const FormatException('저장할 PDF의 영수증을 먼저 확인하세요.');
    }
    final response = await _openRequest(
      Uri(path: '/api/v1/proposals/$proposalId/report'),
      accept: 'application/pdf',
    );
    if (response.headers.contentType?.mimeType != 'application/pdf') {
      await response.drain<void>().timeout(_timeout);
      throw const FormatException('서버가 PDF를 반환하지 않았습니다.');
    }
    final bytes = await _readBytes(response, _timeout);
    final digest = sha256.convert(bytes).toString();
    if (bytes.length < 16 ||
        String.fromCharCodes(bytes.take(5)) != '%PDF-' ||
        !String.fromCharCodes(bytes.skip(bytes.length - 16))
            .trimRight()
            .endsWith('%%EOF') ||
        response.headers.value(HttpHeaders.etagHeader) != '"$digest"') {
      throw const FormatException('PDF 무결성을 확인할 수 없습니다.');
    }
    final sep = Platform.pathSeparator;
    final reports = Directory('${_data.path}${sep}reports');
    await reports.create();
    if (_windowsPath(await reports.resolveSymbolicLinks()) !=
        _windowsPath(reports.path)) {
      throw const FormatException('PDF 저장 폴더가 격리 작업 폴더를 벗어났습니다.');
    }
    // A new directory is reserved atomically for every export. Existing files
    // never participate in the write, even when two clients export together.
    final export = await reports.createTemp('receipt-$receiptId-');
    final file = File('${export.path}${sep}approved-report.pdf');
    await file.create(exclusive: true);
    await file.writeAsBytes(bytes, flush: true);
    return (path: file.path, sha256: digest);
  }

  Future<Json> submitStagedDraft(Json data, String key) {
    if (!RegExp(
      r'^intent:[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$',
    ).hasMatch(key)) {
      throw const FormatException('저장된 등록 요청의 식별자를 확인할 수 없습니다.');
    }
    return _request(Uri(path: '/api/v1/proposals'), data, key);
  }

  Future<HttpClientResponse> _openRequest(
    Uri path, {
    Json? data,
    String? draftKey,
    String accept = 'application/json',
    Duration timeout = _timeout,
  }) async {
    final url = _origin.resolveUri(path);
    if (url.scheme != _origin.scheme ||
        url.host != _origin.host ||
        url.port != _origin.port ||
        (url.path != '/health' && !url.path.startsWith('/api/v1/'))) {
      throw const FormatException('허용된 로컬 API가 아닙니다.');
    }
    final req = await _http.openUrl(data == null ? 'GET' : 'POST', url);
    req.followRedirects = false;
    req.headers.set('X-OpsPilot-Desktop-Token', _token);
    req.headers.set('Accept', accept);
    final session = _session;
    if (session != null) req.cookies.add(session);
    if (data != null) {
      req.headers.contentType = ContentType.json;
      if (_csrf.isNotEmpty) req.headers.set('X-CSRF-Token', _csrf);
      if (draftKey != null) req.headers.set('Idempotency-Key', draftKey);
      req.add(utf8.encode(jsonEncode(data)));
    }
    final response = await req.close().timeout(timeout);
    if (response.statusCode < 200 || response.statusCode >= 300) {
      await response.drain<void>().timeout(timeout);
      throw ServerError(response.statusCode);
    }
    return response;
  }

  Future<List<int>> _readBytes(
    HttpClientResponse response,
    Duration timeout,
  ) async {
    final bytes = BytesBounded(4 * 1024 * 1024);
    await for (final chunk in response.timeout(timeout)) {
      bytes.add(chunk);
    }
    return bytes.data;
  }

  Future<Json> _request(
    Uri path, [
    Json? data,
    String? draftKey,
    Duration timeout = _timeout,
  ]) async {
    final response = await _openRequest(
      path,
      data: data,
      draftKey: draftKey,
      timeout: timeout,
    );
    final reply = jsonObject(
      jsonDecode(utf8.decode(await _readBytes(response, timeout))),
    );
    for (final cookie in response.cookies) {
      if (cookie.name == _cookieName &&
          cookie.httpOnly &&
          (cookie.domain == null || cookie.domain == '127.0.0.1') &&
          cookie.path == '/') {
        _session = cookie.value.isEmpty || cookie.maxAge == 0
            ? null
            : Cookie(cookie.name, cookie.value);
      }
    }
    return reply;
  }

  Future<Json> login(String user, String password) async {
    clearIdentity();
    final identity = await send('auth/login', {
      'username': user,
      'password': password,
    });
    _csrf = field(identity, 'csrf_token');
    if (_session == null ||
        _csrf.isEmpty ||
        field(identity, 'user_id').isEmpty) {
      clearIdentity();
      throw const FormatException('현재 계정의 세션을 확인하지 못했습니다.');
    }
    return identity;
  }

  void clearIdentity() {
    _session = null;
    _csrf = '';
  }

  Future<void> close() async {
    clearIdentity();
    _http.close(force: true);
    await _process.stdin.close().catchError((Object _) {});
    await _process.exitCode.timeout(
      const Duration(seconds: 5),
      onTimeout: () {
        _process.kill();
        return 1;
      },
    );
  }
}

final class BytesBounded {
  BytesBounded(this.limit);
  final int limit;
  final List<int> data = [];

  void add(List<int> chunk) {
    if (data.length + chunk.length > limit) {
      throw const FormatException('로컬 서비스 응답 크기 초과');
    }
    data.addAll(chunk);
  }
}
