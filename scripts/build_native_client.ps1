param([switch]$Test, [string]$VcpkgRoot = "$PSScriptRoot/../../vcpkg")
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$vswhere = "${env:ProgramFiles(x86)}/Microsoft Visual Studio/Installer/vswhere.exe"
$vs = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (!$vs) { throw 'Install Visual Studio C++ Build Tools first.' }
$deps = "$repo/.build/apcc-deps"
Push-Location $repo
try {
    & "$VcpkgRoot/vcpkg.exe" install jansson:x86-windows-static libwebsockets:x86-windows-static glib:x86-windows-static "--x-install-root=$deps" --disable-metrics
    if ($LASTEXITCODE) { throw 'APCc dependency build failed.' }
    if (!$Test) {
        & "$vs/MSBuild/Current/Bin/MSBuild.exe" mod/asi/plugin/GtaVcAp.vcxproj '/p:Configuration=Release GTA-VC' /p:Platform=Win32 /v:minimal /nologo
        if ($LASTEXITCODE) { throw 'ASI build failed.' }
        return
    }
    $include = "/I `"$deps/x86-windows-static/include`" /I `"$deps/x86-windows-static/include/glib-2.0`" /I `"$deps/x86-windows-static/lib/glib-2.0/include`" /I mod/asi/third_party"
    $defines = '/DNOMINMAX /DGLIB_STATIC_COMPILATION /DJANSSON_STATIC /DLWS_STATIC'
    $libs = (Get-ChildItem -LiteralPath "$deps/x86-windows-static/lib" -Filter '*.lib' | ForEach-Object { '"' + $_.FullName + '"' }) -join ' '
    $systemLibs = 'ws2_32.lib crypt32.lib bcrypt.lib iphlpapi.lib userenv.lib winmm.lib shlwapi.lib advapi32.lib user32.lib dbghelp.lib ole32.lib shell32.lib'
    $common = 'mod/asi/src/native_session.cpp mod/asi/src/bridge.cpp mod/asi/src/net.cpp mod/asi/src/protocol.cpp'
    $commands = @(
        '@echo off',
        "call `"$vs/VC/Auxiliary/Build/vcvars32.bat`" >nul",
        "cl /nologo /std:c17 /TC /MT $defines $include /c mod/asi/third_party/apcc/APCc.c /Fo:.build/APCc.obj",
        'if errorlevel 1 exit /b 1',
        "cl /nologo /std:c++17 /EHsc /MT $defines $include /Fe:.build/native_selftest.exe /Fo:.build/ mod/asi/harness/native_selftest.cpp $common /link $systemLibs",
        'if errorlevel 1 exit /b 1',
        "cl /nologo /std:c++17 /EHsc /MT $defines $include /Fe:.build/native_harness.exe /Fo:.build/ mod/asi/harness/native_harness.cpp mod/asi/src/ap_client.cpp $common .build/APCc.obj /link $libs $systemLibs"
    )
    Set-Content -LiteralPath .build/build-native-tests.cmd -Value $commands -Encoding ascii
    & .build/build-native-tests.cmd
    if ($LASTEXITCODE) { throw 'Native test build failed.' }
    & .build/native_selftest.exe ("build/native-selftest-" + [guid]::NewGuid().ToString('N'))
    if ($LASTEXITCODE) { throw 'Native self-test failed.' }
    Write-Host 'Run: python scripts/native_interop_check.py .build/native_harness.exe'
} finally {
    Pop-Location
}
