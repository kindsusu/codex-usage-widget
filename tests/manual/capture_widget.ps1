param(
    [Parameter(Mandatory = $true)]
    [int]$ProcessId,
    [Parameter(Mandatory = $true)]
    [string]$OutputPath,
    [switch]$ScreenOnly,
    [int]$WindowIndex = 0
)

Add-Type -AssemblyName System.Drawing
Add-Type @'
using System;
using System.Runtime.InteropServices;

public static class WidgetCaptureNative {
    public delegate bool EnumWindowsProc(IntPtr hwnd, IntPtr lParam);

    [StructLayout(LayoutKind.Sequential)]
    public struct Rect { public int Left, Top, Right, Bottom; }

    [DllImport("user32.dll")]
    public static extern bool EnumWindows(EnumWindowsProc callback, IntPtr lParam);

    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint processId);

    [DllImport("user32.dll")]
    public static extern bool IsWindowVisible(IntPtr hwnd);

    [DllImport("user32.dll")]
    public static extern bool GetWindowRect(IntPtr hwnd, out Rect rect);

    [DllImport("user32.dll")]
    public static extern bool PrintWindow(IntPtr hwnd, IntPtr deviceContext, uint flags);
}
'@

$matches = [System.Collections.Generic.List[object]]::new()
$callback = [WidgetCaptureNative+EnumWindowsProc]{
    param([IntPtr]$hwnd, [IntPtr]$lParam)
    $owner = [uint32]0
    [void][WidgetCaptureNative]::GetWindowThreadProcessId($hwnd, [ref]$owner)
    $rect = [WidgetCaptureNative+Rect]::new()
    if ($owner -eq $ProcessId -and [WidgetCaptureNative]::IsWindowVisible($hwnd) -and [WidgetCaptureNative]::GetWindowRect($hwnd, [ref]$rect)) {
        $width = $rect.Right - $rect.Left
        $height = $rect.Bottom - $rect.Top
        if ($width -gt 20 -and $height -gt 20) {
            $matches.Add([pscustomobject]@{ Hwnd = $hwnd; Rect = $rect; Area = $width * $height })
        }
    }
    return $true
}
[void][WidgetCaptureNative]::EnumWindows($callback, [IntPtr]::Zero)

$window = $matches | Sort-Object Area -Descending | Select-Object -Skip $WindowIndex -First 1
if ($null -eq $window) { throw "Visible widget window not found for process $ProcessId" }

$rect = $window.Rect
$width = $rect.Right - $rect.Left
$height = $rect.Bottom - $rect.Top
$bitmap = [System.Drawing.Bitmap]::new($width, $height)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
try {
    if ($ScreenOnly) {
        $graphics.CopyFromScreen($rect.Left, $rect.Top, 0, 0, $bitmap.Size)
    } else {
        $deviceContext = $graphics.GetHdc()
        try {
            $printed = [WidgetCaptureNative]::PrintWindow($window.Hwnd, $deviceContext, 2)
        } finally {
            $graphics.ReleaseHdc($deviceContext)
        }
        if (-not $printed) {
            $graphics.CopyFromScreen($rect.Left, $rect.Top, 0, 0, $bitmap.Size)
        }
    }
    $directory = Split-Path -Parent $OutputPath
    if ($directory) { [System.IO.Directory]::CreateDirectory($directory) | Out-Null }
    $bitmap.Save($OutputPath, [System.Drawing.Imaging.ImageFormat]::Png)
} finally {
    $graphics.Dispose()
    $bitmap.Dispose()
}

[pscustomobject]@{
    Hwnd = $window.Hwnd
    Left = $rect.Left
    Top = $rect.Top
    Width = $width
    Height = $height
    Output = (Resolve-Path $OutputPath).Path
}
