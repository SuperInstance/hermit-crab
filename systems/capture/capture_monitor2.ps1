Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$screens = [System.Windows.Forms.Screen]::AllScreens
Write-Output "Found $($screens.Length) monitors:"
for ($i = 0; $i -lt $screens.Length; $i++) {
    $s = $screens[$i]
    Write-Output "Monitor $i : $($s.DeviceName) | Bounds: $($s.Bounds) | Primary: $($s.Primary)"
}

if ($screens.Length -ge 2) {
    $bounds = $screens[1].Bounds
    Write-Output "Capturing monitor 2: $($bounds)"
    $bmp = New-Object System.Drawing.Bitmap($bounds.Width, $bounds.Height)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($bounds.X, $bounds.Y, 0, 0, $bounds.Size)
    $g.Dispose()
    $path = Join-Path $env:TEMP "tzpro_monitor2.png"
    $bmp.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
    $bmp.Dispose()
    Write-Output "Saved to: $path"
} else {
    Write-Output "Only one monitor found"
}