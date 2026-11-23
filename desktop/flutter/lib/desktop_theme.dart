import 'package:flutter/material.dart';

enum AppearanceMode { dark, light, warm }

// Semantic roles shared by the window, queue, evidence, and decision bar.
@immutable
final class DeskColors extends ThemeExtension<DeskColors> {
  const DeskColors({
    required this.canvas,
    required this.rail,
    required this.surface,
    required this.hover,
    required this.selected,
    required this.line,
    required this.ink,
    required this.muted,
    required this.accent,
    required this.primary,
    required this.onPrimary,
    required this.ready,
  });

  final Color canvas;
  final Color rail;
  final Color surface;
  final Color hover;
  final Color selected;
  final Color line;
  final Color ink;
  final Color muted;
  final Color accent;
  final Color primary;
  final Color onPrimary;
  final Color ready;

  static DeskColors of(BuildContext context) =>
      Theme.of(context).extension<DeskColors>()!;

  static DeskColors forMode(AppearanceMode mode) => switch (mode) {
    AppearanceMode.dark => const DeskColors(
      canvas: Color(0xff191c22),
      rail: Color(0xff15181d),
      surface: Color(0xff20242c),
      hover: Color(0xff272d38),
      selected: Color(0xff26334b),
      line: Color(0xff353c48),
      ink: Color(0xffedf0f6),
      muted: Color(0xffa9b3c3),
      accent: Color(0xffa7c0ff),
      primary: Color(0xff9ab6fc),
      onPrimary: Color(0xff121e37),
      ready: Color(0xff91d0b3),
    ),
    AppearanceMode.light => const DeskColors(
      canvas: Color(0xfff8fafc),
      rail: Color(0xffedf1f5),
      surface: Color(0xffffffff),
      hover: Color(0xffe5edf6),
      selected: Color(0xffd9e8fb),
      line: Color(0xffb3c0cf),
      ink: Color(0xff202d3b),
      muted: Color(0xff526176),
      accent: Color(0xff214c84),
      primary: Color(0xff245494),
      onPrimary: Color(0xffffffff),
      ready: Color(0xff236347),
    ),
    AppearanceMode.warm => const DeskColors(
      canvas: Color(0xfffbf5eb),
      rail: Color(0xfff2e6d4),
      surface: Color(0xfffffaf1),
      hover: Color(0xffefe1ca),
      selected: Color(0xfff1dfc0),
      line: Color(0xffc7b59d),
      ink: Color(0xff34281e),
      muted: Color(0xff645344),
      accent: Color(0xff724218),
      primary: Color(0xff7b451e),
      onPrimary: Color(0xfffffaf1),
      ready: Color(0xff365c3d),
    ),
  };

  @override
  DeskColors copyWith({
    Color? canvas,
    Color? rail,
    Color? surface,
    Color? hover,
    Color? selected,
    Color? line,
    Color? ink,
    Color? muted,
    Color? accent,
    Color? primary,
    Color? onPrimary,
    Color? ready,
  }) => DeskColors(
    canvas: canvas ?? this.canvas,
    rail: rail ?? this.rail,
    surface: surface ?? this.surface,
    hover: hover ?? this.hover,
    selected: selected ?? this.selected,
    line: line ?? this.line,
    ink: ink ?? this.ink,
    muted: muted ?? this.muted,
    accent: accent ?? this.accent,
    primary: primary ?? this.primary,
    onPrimary: onPrimary ?? this.onPrimary,
    ready: ready ?? this.ready,
  );

  @override
  DeskColors lerp(covariant DeskColors? other, double t) {
    if (other == null) return this;
    return DeskColors(
      canvas: Color.lerp(canvas, other.canvas, t)!,
      rail: Color.lerp(rail, other.rail, t)!,
      surface: Color.lerp(surface, other.surface, t)!,
      hover: Color.lerp(hover, other.hover, t)!,
      selected: Color.lerp(selected, other.selected, t)!,
      line: Color.lerp(line, other.line, t)!,
      ink: Color.lerp(ink, other.ink, t)!,
      muted: Color.lerp(muted, other.muted, t)!,
      accent: Color.lerp(accent, other.accent, t)!,
      primary: Color.lerp(primary, other.primary, t)!,
      onPrimary: Color.lerp(onPrimary, other.onPrimary, t)!,
      ready: Color.lerp(ready, other.ready, t)!,
    );
  }
}

ThemeData reviewDeskTheme(AppearanceMode mode) {
  final colors = DeskColors.forMode(mode);
  final dark = mode == AppearanceMode.dark;
  final scheme = ColorScheme(
    brightness: dark ? Brightness.dark : Brightness.light,
    primary: colors.primary,
    onPrimary: colors.onPrimary,
    primaryContainer: colors.selected,
    onPrimaryContainer: colors.ink,
    secondary: colors.accent,
    onSecondary: colors.onPrimary,
    secondaryContainer: colors.selected,
    onSecondaryContainer: colors.ink,
    error: dark ? const Color(0xffffb4ab) : const Color(0xffa52c24),
    onError: dark ? const Color(0xff490d0b) : Colors.white,
    surface: colors.surface,
    onSurface: colors.ink,
    onSurfaceVariant: colors.muted,
    surfaceContainerHigh: colors.rail,
    surfaceContainerHighest: colors.hover,
    outline: colors.line,
    outlineVariant: colors.line,
    surfaceTint: Colors.transparent,
  );
  final shape = RoundedRectangleBorder(borderRadius: BorderRadius.circular(5));
  final outline = BorderSide(color: colors.line);
  final focusOutline = BorderSide(color: colors.accent, width: 2);
  final action =
      OutlinedButton.styleFrom(
        foregroundColor: colors.ink,
        disabledForegroundColor: colors.muted,
        shape: shape,
        minimumSize: const Size(36, 32),
        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
        textStyle: const TextStyle(fontSize: 13, fontWeight: FontWeight.w500),
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      ).copyWith(
        side: WidgetStateProperty.resolveWith(
          (states) =>
              states.contains(WidgetState.focused) ? focusOutline : outline,
        ),
        overlayColor: WidgetStateProperty.resolveWith(
          (states) =>
              states.contains(WidgetState.hovered) ||
                  states.contains(WidgetState.focused) ||
                  states.contains(WidgetState.pressed)
              ? colors.hover
              : Colors.transparent,
        ),
      );
  final primary =
      FilledButton.styleFrom(
        backgroundColor: colors.primary,
        foregroundColor: colors.onPrimary,
        disabledBackgroundColor: colors.hover,
        disabledForegroundColor: colors.muted,
        shape: shape,
        minimumSize: const Size(78, 34),
        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
        textStyle: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
      ).copyWith(
        side: WidgetStateProperty.resolveWith(
          (states) => states.contains(WidgetState.focused)
              ? BorderSide(color: colors.onPrimary, width: 2)
              : BorderSide.none,
        ),
      );
  final inputBorder = OutlineInputBorder(
    borderRadius: BorderRadius.circular(5),
    borderSide: outline,
  );

  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    extensions: [colors],
    scaffoldBackgroundColor: colors.canvas,
    canvasColor: colors.surface,
    fontFamily: 'Segoe UI',
    fontFamilyFallback: const ['Malgun Gothic'],
    dividerTheme: DividerThemeData(color: colors.line, thickness: 1, space: 1),
    visualDensity: VisualDensity.compact,
    outlinedButtonTheme: OutlinedButtonThemeData(style: action),
    filledButtonTheme: FilledButtonThemeData(style: primary),
    drawerTheme: DrawerThemeData(backgroundColor: colors.rail),
    dialogTheme: DialogThemeData(backgroundColor: colors.surface),
    segmentedButtonTheme: SegmentedButtonThemeData(
      style: ButtonStyle(
        backgroundColor: WidgetStateProperty.resolveWith(
          (states) => states.contains(WidgetState.selected)
              ? colors.selected
              : colors.surface,
        ),
        foregroundColor: WidgetStateProperty.resolveWith(
          (states) => states.contains(WidgetState.selected)
              ? colors.accent
              : colors.ink,
        ),
        side: WidgetStateProperty.resolveWith(
          (states) =>
              states.contains(WidgetState.focused) ? focusOutline : outline,
        ),
        overlayColor: WidgetStatePropertyAll(
          colors.accent.withValues(alpha: .12),
        ),
      ),
    ),
    textSelectionTheme: TextSelectionThemeData(
      cursorColor: colors.accent,
      selectionColor: colors.selected,
      selectionHandleColor: colors.accent,
    ),
    inputDecorationTheme: InputDecorationTheme(
      isDense: true,
      contentPadding: const EdgeInsets.all(10),
      border: inputBorder,
      enabledBorder: inputBorder,
      focusedBorder: inputBorder.copyWith(borderSide: focusOutline),
    ),
  );
}
