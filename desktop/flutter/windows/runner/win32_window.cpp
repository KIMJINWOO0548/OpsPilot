#include "win32_window.h"

#include <dwmapi.h>
#include <flutter_windows.h>

#include <algorithm>

#include "resource.h"

namespace {

/// Window attribute that enables dark mode window decorations.
///
/// Redefined in case the developer's machine has a Windows SDK older than
/// version 10.0.22000.0.
/// See: https://docs.microsoft.com/windows/win32/api/dwmapi/ne-dwmapi-dwmwindowattribute
#ifndef DWMWA_USE_IMMERSIVE_DARK_MODE
#define DWMWA_USE_IMMERSIVE_DARK_MODE 20
#endif

constexpr const wchar_t kWindowClassName[] = L"FLUTTER_RUNNER_WIN32_WINDOW";

// Outer tracking sizes in logical pixels, including the native frame.
constexpr int kMinimumWidth = 600;
constexpr int kMinimumHeight = 416;

// The number of Win32Window objects that currently exist.
static int g_active_window_count = 0;

using EnableNonClientDpiScaling = BOOL __stdcall(HWND hwnd);

// Convert a length, never an absolute screen coordinate, to physical pixels.
int Scale(int logical_length, UINT dpi) {
  return MulDiv(logical_length, static_cast<int>(dpi), USER_DEFAULT_SCREEN_DPI);
}

// Dynamically loads the |EnableNonClientDpiScaling| from the User32 module.
// This API is only needed for PerMonitor V1 awareness mode.
void EnableFullDpiSupportIfAvailable(HWND hwnd) {
  HMODULE user32_module = LoadLibraryA("User32.dll");
  if (!user32_module) {
    return;
  }
  auto enable_non_client_dpi_scaling =
      reinterpret_cast<EnableNonClientDpiScaling*>(
          GetProcAddress(user32_module, "EnableNonClientDpiScaling"));
  if (enable_non_client_dpi_scaling != nullptr) {
    enable_non_client_dpi_scaling(hwnd);
  }
  FreeLibrary(user32_module);
}

}  // namespace

// Manages the Win32Window's window class registration.
class WindowClassRegistrar {
 public:
  ~WindowClassRegistrar() = default;

  // Returns the singleton registrar instance.
  static WindowClassRegistrar* GetInstance() {
    if (!instance_) {
      instance_ = new WindowClassRegistrar();
    }
    return instance_;
  }

  // Returns the name of the window class, registering the class if it hasn't
  // previously been registered.
  const wchar_t* GetWindowClass();

  // Unregisters the window class. Should only be called if there are no
  // instances of the window.
  void UnregisterWindowClass();

 private:
  WindowClassRegistrar() = default;

  static WindowClassRegistrar* instance_;

  bool class_registered_ = false;
};

WindowClassRegistrar* WindowClassRegistrar::instance_ = nullptr;

const wchar_t* WindowClassRegistrar::GetWindowClass() {
  if (!class_registered_) {
    WNDCLASS window_class{};
    window_class.hCursor = LoadCursor(nullptr, IDC_ARROW);
    window_class.lpszClassName = kWindowClassName;
    window_class.style = CS_HREDRAW | CS_VREDRAW;
    window_class.cbClsExtra = 0;
    window_class.cbWndExtra = 0;
    window_class.hInstance = GetModuleHandle(nullptr);
    window_class.hIcon =
        LoadIcon(window_class.hInstance, MAKEINTRESOURCE(IDI_APP_ICON));
    window_class.hbrBackground = 0;
    window_class.lpszMenuName = nullptr;
    window_class.lpfnWndProc = Win32Window::WndProc;
    RegisterClass(&window_class);
    class_registered_ = true;
  }
  return kWindowClassName;
}

void WindowClassRegistrar::UnregisterWindowClass() {
  UnregisterClass(kWindowClassName, nullptr);
  class_registered_ = false;
}

Win32Window::Win32Window() {
  ++g_active_window_count;
}

Win32Window::~Win32Window() {
  --g_active_window_count;
  Destroy();
}

bool Win32Window::Create(const std::wstring& title, const Size& size) {
  Destroy();

  const wchar_t* window_class =
      WindowClassRegistrar::GetInstance()->GetWindowClass();

  POINT pointer{};
  GetCursorPos(&pointer);
  const HMONITOR monitor = MonitorFromPoint(pointer, MONITOR_DEFAULTTONEAREST);
  const UINT dpi = FlutterDesktopGetDpiForMonitor(monitor);
  LONG width = Scale(size.width, dpi);
  LONG height = Scale(size.height, dpi);
  LONG x = CW_USEDEFAULT;
  LONG y = CW_USEDEFAULT;
  MONITORINFO monitor_info{};
  monitor_info.cbSize = sizeof(monitor_info);
  if (GetMonitorInfo(monitor, &monitor_info)) {
    const RECT work_area = monitor_info.rcWork;
    const LONG work_width = work_area.right - work_area.left;
    const LONG work_height = work_area.bottom - work_area.top;
    width = std::min(width, work_width);
    height = std::min(height, work_height);
    x = work_area.left + (work_width - width) / 2;
    y = work_area.top + (work_height - height) / 2;
  }

  const HWND window = CreateWindow(
      window_class, title.c_str(), WS_OVERLAPPEDWINDOW, x, y, width, height,
      nullptr, nullptr, GetModuleHandle(nullptr), this);

  if (!window) {
    return false;
  }

  UpdateTheme(window, false);

  return OnCreate();
}

bool Win32Window::Show() {
  return ShowWindow(window_handle_, SW_SHOWNORMAL);
}

// static
LRESULT CALLBACK Win32Window::WndProc(HWND const window,
                                      UINT const message,
                                      WPARAM const wparam,
                                      LPARAM const lparam) noexcept {
  if (message == WM_NCCREATE) {
    auto window_struct = reinterpret_cast<CREATESTRUCT*>(lparam);
    SetWindowLongPtr(window, GWLP_USERDATA,
                     reinterpret_cast<LONG_PTR>(window_struct->lpCreateParams));

    auto that = static_cast<Win32Window*>(window_struct->lpCreateParams);
    EnableFullDpiSupportIfAvailable(window);
    that->window_handle_ = window;
  } else if (Win32Window* that = GetThisFromHandle(window)) {
    return that->MessageHandler(window, message, wparam, lparam);
  }

  return DefWindowProc(window, message, wparam, lparam);
}

LRESULT
Win32Window::MessageHandler(HWND hwnd,
                            UINT const message,
                            WPARAM const wparam,
                            LPARAM const lparam) noexcept {
  switch (message) {
    case WM_DESTROY:
      window_handle_ = nullptr;
      Destroy();
      if (quit_on_close_) {
        PostQuitMessage(0);
      }
      return 0;

    case WM_DPICHANGED: {
      const auto& suggested = *reinterpret_cast<const RECT*>(lparam);
      SetWindowPos(hwnd, nullptr, suggested.left, suggested.top,
                   suggested.right - suggested.left,
                   suggested.bottom - suggested.top,
                   SWP_NOZORDER | SWP_NOACTIVATE);

      return 0;
    }
    case WM_GETMINMAXINFO: {
      const UINT dpi = GetDpiForWindow(hwnd);
      if (dpi == 0) {
        break;
      }
      auto& limits = *reinterpret_cast<MINMAXINFO*>(lparam);
      limits.ptMinTrackSize.x = Scale(kMinimumWidth, dpi);
      limits.ptMinTrackSize.y = Scale(kMinimumHeight, dpi);
      return 0;
    }
    case WM_SIZE: {
      RECT rect = GetClientArea();
      if (child_content_ != nullptr) {
        // Size and position the child window.
        MoveWindow(child_content_, rect.left, rect.top, rect.right - rect.left,
                   rect.bottom - rect.top, TRUE);
      }
      return 0;
    }

    case WM_ACTIVATE:
      if (LOWORD(wparam) != WA_INACTIVE && !HIWORD(wparam) &&
          child_content_ != nullptr) {
        SetFocus(child_content_);
        return 0;
      }
      break;
    case WM_NCACTIVATE:
      UpdateTheme(hwnd, wparam != FALSE);
      break;

    case WM_SETTINGCHANGE:
    case WM_SYSCOLORCHANGE:
    case WM_THEMECHANGED:
    case WM_DWMCOLORIZATIONCOLORCHANGED:
      UpdateTheme(hwnd, GetActiveWindow() == hwnd);
      break;
  }

  return DefWindowProc(hwnd, message, wparam, lparam);
}

void Win32Window::Destroy() {
  OnDestroy();

  if (window_handle_) {
    DestroyWindow(window_handle_);
    window_handle_ = nullptr;
  }
  if (g_active_window_count == 0) {
    WindowClassRegistrar::GetInstance()->UnregisterWindowClass();
  }
}

Win32Window* Win32Window::GetThisFromHandle(HWND const window) noexcept {
  return reinterpret_cast<Win32Window*>(
      GetWindowLongPtr(window, GWLP_USERDATA));
}

void Win32Window::SetChildContent(HWND content) {
  child_content_ = content;
  SetParent(content, window_handle_);
  RECT frame = GetClientArea();

  MoveWindow(content, frame.left, frame.top, frame.right - frame.left,
             frame.bottom - frame.top, true);

  SetFocus(child_content_);
}

RECT Win32Window::GetClientArea() {
  RECT frame;
  GetClientRect(window_handle_, &frame);
  return frame;
}

HWND Win32Window::GetHandle() {
  return window_handle_;
}

void Win32Window::SetQuitOnClose(bool quit_on_close) {
  quit_on_close_ = quit_on_close;
}

bool Win32Window::OnCreate() {
  // No-op; provided for subclasses.
  return true;
}

void Win32Window::OnDestroy() {
  // No-op; provided for subclasses.
}

void Win32Window::SetCaptionAppearance(CaptionAppearance appearance) {
  caption_appearance_ = appearance;
  if (window_handle_) {
    UpdateTheme(window_handle_, GetActiveWindow() == window_handle_);
  }
}

void Win32Window::UpdateTheme(HWND window, bool active) {
  HIGHCONTRAST accessibility{};
  accessibility.cbSize = sizeof(accessibility);
  const BOOL high_contrast =
      SystemParametersInfo(SPI_GETHIGHCONTRAST, sizeof(accessibility),
                           &accessibility, 0) &&
      (accessibility.dwFlags & HCF_HIGHCONTRASTON) != 0;
  const BOOL dark_caption =
      !high_contrast && caption_appearance_ == CaptionAppearance::kDark;
  DwmSetWindowAttribute(window, DWMWA_USE_IMMERSIVE_DARK_MODE,
                        &dark_caption, sizeof(dark_caption));

  COLORREF background = DWMWA_COLOR_DEFAULT;
  COLORREF text = DWMWA_COLOR_DEFAULT;
  if (!high_contrast) {
    switch (caption_appearance_) {
      case CaptionAppearance::kDark:
        background = RGB(21, 24, 29);
        text = active ? RGB(237, 240, 246) : RGB(169, 179, 195);
        break;
      case CaptionAppearance::kLight:
        background = active ? RGB(237, 241, 245) : RGB(246, 248, 250);
        text = active ? RGB(32, 45, 59) : RGB(83, 98, 114);
        break;
      case CaptionAppearance::kWarm:
        background = active ? RGB(242, 230, 212) : RGB(248, 240, 228);
        text = active ? RGB(52, 40, 30) : RGB(98, 85, 69);
        break;
    }
  }
  DwmSetWindowAttribute(window, DWMWA_CAPTION_COLOR, &background,
                        sizeof(background));
  DwmSetWindowAttribute(window, DWMWA_TEXT_COLOR, &text, sizeof(text));
}
