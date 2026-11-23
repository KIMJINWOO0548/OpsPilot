import 'dart:io';

import 'package:flutter/services.dart';

import 'desktop_theme.dart';

class DesktopAppearance {
  DesktopAppearance(List<String> arguments)
    : _file = _preferenceFile(arguments);

  static const _channel = MethodChannel('opspilot/appearance');
  final File? _file;

  static File? _preferenceFile(List<String> arguments) {
    final flag = arguments.indexOf('--appearance-dir');
    final local = Platform.environment['LOCALAPPDATA'];
    final separator = Platform.pathSeparator;
    final directory = flag >= 0 && flag + 1 < arguments.length
        ? arguments[flag + 1]
        : local == null || local.isEmpty
        ? null
        : '$local${separator}OpsPilot-X${separator}Flutter';
    if (directory == null || directory.isEmpty) return null;
    return File('$directory${separator}appearance.txt');
  }

  Future<AppearanceMode> read() async {
    final file = _file;
    if (file != null) {
      try {
        final saved = (await file.readAsString()).trim();
        for (final mode in AppearanceMode.values) {
          if (mode.name == saved) return mode;
        }
      } on FileSystemException {
        // New or unreadable preferences use the existing default.
      } on FormatException {
        // An invalid preference file does not prevent the app from starting.
      }
    }
    return AppearanceMode.dark;
  }

  Future<void> save(AppearanceMode mode) async {
    final file = _file;
    if (file == null)
      throw const FileSystemException('Appearance directory unavailable');
    await file.parent.create(recursive: true);
    final staging = await file.parent.createTemp('.appearance-');
    final candidate = File(
      '${staging.path}${Platform.pathSeparator}appearance.txt',
    );
    try {
      await candidate.writeAsString('${mode.name}\n', flush: true);
      await candidate.rename(file.path);
    } finally {
      try {
        if (await candidate.exists()) await candidate.delete();
        await staging.delete();
      } on FileSystemException {
        // Temporary-file cleanup does not change the saved preference.
      }
    }
  }

  Future<void> updateFrame(AppearanceMode mode) async {
    if (!Platform.isWindows) return;
    try {
      await _channel.invokeMethod<void>('setMode', mode.name);
    } on PlatformException {
      // The Windows frame may use system colors on unsupported systems.
    } on MissingPluginException {
      // The desktop theme is also usable without the Windows runner.
    }
  }
}
