using System.Windows;
using System.Windows.Controls;
namespace OpsPilot.Desktop;

internal sealed class SetupWindow : Window
{
    public object? Accounts { get; private set; }
    public SetupWindow(Window owner)
    {
        Owner = owner; Title = "OpsPilot-X · 최초 계정 설정"; Width = 540; Height = 800; ResizeMode = ResizeMode.NoResize; WindowStartupLocation = WindowStartupLocation.CenterOwner;
        FontFamily = new System.Windows.Media.FontFamily("Segoe UI"); FontSize = 14; Background = System.Windows.Media.Brushes.White;
        var panel = new StackPanel { Margin = new Thickness(28) };
        Content = new ScrollViewer { Content = panel };
        panel.Children.Add(new TextBlock { Text = "최초 계정 설정", FontSize = 24, Margin = new Thickness(0,0,0,12) });
        panel.Children.Add(new TextBlock { Text = "합성 workspace · mock 작업 전용입니다. engineer는 조사·초안 작성, approver는 독립 승인 역할입니다. 기본 계정은 없으며 자동 로그인하지 않습니다.", TextWrapping = TextWrapping.Wrap });
        var engineer = AccountFields(panel, "Engineer · 조사 / 작성");
        var approver = AccountFields(panel, "Approver · 독립 승인");
        var error = new TextBlock { TextWrapping = TextWrapping.Wrap, Foreground = System.Windows.Media.Brushes.Firebrick, Margin = new Thickness(0,12,0,8) }; panel.Children.Add(error);
        var buttons = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right }; panel.Children.Add(buttons);
        var cancel = new Button { Content = "취소", IsCancel = true, Padding = new Thickness(16,7,16,7), Margin = new Thickness(0,0,8,0) }; buttons.Children.Add(cancel);
        var save = new Button { Content = "두 계정 생성", IsDefault = true, Padding = new Thickness(16,7,16,7) }; buttons.Children.Add(save);
        save.Background = new System.Windows.Media.SolidColorBrush(System.Windows.Media.Color.FromRgb(8,126,128)); save.Foreground = System.Windows.Media.Brushes.White;
        save.Click += (_, _) =>
        {
            var e = engineer.User.Text.Trim(); var a = approver.User.Text.Trim();
            if (e.Length == 0 || a.Length == 0 || e.Equals(a, StringComparison.OrdinalIgnoreCase) || engineer.Password.Password.Length < 12 || approver.Password.Password.Length < 12 || engineer.Password.Password != engineer.Confirm.Password || approver.Password.Password != approver.Confirm.Password)
            { error.Text = "서로 다른 계정명과 12자 이상 비밀번호를 입력하고 확인 값을 일치시키세요."; return; }
            Accounts = new { engineer = new { username = e, password = engineer.Password.Password }, approver = new { username = a, password = approver.Password.Password } };
            engineer.Password.Clear(); engineer.Confirm.Clear(); approver.Password.Clear(); approver.Confirm.Clear(); DialogResult = true;
        };
    }
    private static (TextBox User, PasswordBox Password, PasswordBox Confirm) AccountFields(Panel panel, string role)
    {
        panel.Children.Add(new TextBlock { Text = role, FontWeight = FontWeights.SemiBold, Margin = new Thickness(0,18,0,4) });
        var user = new TextBox { MaxLength = 80, Height = 36, Padding = new Thickness(8,5,8,5) }; panel.Children.Add(new Label { Content = "계정명", Target = user }); panel.Children.Add(user);
        var password = new PasswordBox { MaxLength = 1024, Height = 36, Padding = new Thickness(8,5,8,5) }; panel.Children.Add(new Label { Content = "새 비밀번호 (12자 이상)", Target = password }); panel.Children.Add(password);
        var confirm = new PasswordBox { MaxLength = 1024, Height = 36, Padding = new Thickness(8,5,8,5) }; panel.Children.Add(new Label { Content = "비밀번호 확인", Target = confirm }); panel.Children.Add(confirm);
        return (user, password, confirm);
    }
}
