param([switch]$Test, [string]$VcpkgRoot = "$PSScriptRoot/../../vcpkg")
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$vswhere = "${env:ProgramFiles(x86)}/Microsoft Visual Studio/Installer/vswhere.exe"
$vs = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (!$vs) { throw 'Install Visual Studio C++ Build Tools first.' }
$deps = "$repo/.build/apcpp-deps"
$msbuild = "$vs/MSBuild/Current/Bin/MSBuild.exe"
$sdk = $env:PLUGIN_SDK_DIR
if (!$sdk -or !(Test-Path -LiteralPath "$sdk/plugin_vc/plugin_vc.vcxproj")) {
    throw 'Set PLUGIN_SDK_DIR to the plugin-sdk source checkout.'
}
foreach ($dependency in @(
    @($sdk, '12487f6be7846946802497d7471f8c58473b3cd6'),
    @($VcpkgRoot, 'd7112d1a4fb50410d3639f5f586972591d848beb')
)) {
    $revision = & git -C $dependency[0] rev-parse HEAD
    if ($LASTEXITCODE -or $revision -ne $dependency[1]) {
        throw "Check out revision $($dependency[1]) in $($dependency[0])."
    }
}
Push-Location $repo
try {
    & "$VcpkgRoot/vcpkg.exe" install ixwebsocket[mbedtls]:x86-windows-static jsoncpp:x86-windows-static "--x-install-root=$deps" --disable-metrics
    if ($LASTEXITCODE) { throw 'APCpp dependency build failed.' }
    # These SDK arrays live at the given addresses; their first entries are not pointers.
    $pickupSource = [IO.File]::ReadAllText("$sdk/plugin_vc/game_vc/CPickups.cpp")
    foreach ($address in @('0x94AF48', '0x7E9B08', '0x945D30')) {
        $binding = "*(int *)$address"
        if (!$pickupSource.Contains($binding)) { throw "Unexpected SDK pickup binding: $address" }
        $pickupSource = $pickupSource.Replace($binding, $address)
    }
    New-Item -ItemType Directory -Force -Path "$repo/.build/sdk" | Out-Null
    [IO.File]::WriteAllText("$repo/.build/sdk/CPickups.cpp", $pickupSource)
    & $msbuild "$sdk/plugin_vc/plugin_vc.vcxproj" /p:Configuration=Release /p:Platform=Win32 /p:VcpkgEnabled=false "/p:OutDir=$repo/.build/sdk/lib/" "/p:IntDir=$repo/.build/sdk/obj/" "/p:ForceImportBeforeCppTargets=$PSScriptRoot/plugin_sdk.targets" /v:minimal /nologo
    if ($LASTEXITCODE) { throw 'plugin-sdk build failed.' }
    & $msbuild mod/asi/plugin/GtaVcAp.vcxproj '/p:Configuration=Release GTA-VC' /p:Platform=Win32 /v:minimal /nologo
    if ($LASTEXITCODE) { throw 'ASI build failed.' }
    if (!$Test) { return }
    $include = "/I `"$deps/x86-windows-static/include`" /I mod/asi/third_party"
    $defines = '/DNOMINMAX /DIXWEBSOCKET_USE_TLS /DIXWEBSOCKET_USE_MBED_TLS /DIXWEBSOCKET_USE_ZLIB'
    $libs = (Get-ChildItem -LiteralPath "$deps/x86-windows-static/lib" -Filter '*.lib' | ForEach-Object { '"' + $_.FullName + '"' }) -join ' '
    $systemLibs = 'ws2_32.lib crypt32.lib bcrypt.lib iphlpapi.lib userenv.lib winmm.lib shlwapi.lib advapi32.lib user32.lib dbghelp.lib ole32.lib shell32.lib'
    $common = 'mod/asi/src/native_session.cpp mod/asi/src/bridge.cpp mod/asi/src/net.cpp mod/asi/src/protocol.cpp'
    $sdkInclude = "/I `"$sdk/plugin_vc/game_vc`" /I `"$sdk/shared`" /I `"$sdk/shared/game`""
    $commands = @(
        '@echo off',
        "call `"$vs/VC/Auxiliary/Build/vcvars32.bat`" >nul",
        "cl /nologo /std:c++latest /EHsc /MT /DNOMINMAX /DGTAVC /DPLUGIN_SGV_10EN /DRW $sdkInclude /Fe:.build/sdk_selftest.exe /Fo:.build/ mod/asi/harness/sdk_selftest.cpp /link `"$repo/.build/sdk/lib/plugin_vc.lib`" $systemLibs",
        'if errorlevel 1 exit /b 1',
        'cl /nologo /std:c++17 /EHsc /MT /DNOMINMAX /I mod/asi/third_party /Fe:.build/selftest.exe /Fo:.build/ mod/asi/harness/selftest.cpp mod/asi/src/protocol.cpp',
        'if errorlevel 1 exit /b 1',
        'cl /nologo /std:c++17 /EHsc /MT /DNOMINMAX /Fe:.build/save_isolation_selftest.exe /Fo:.build/ mod/asi/harness/save_isolation_selftest.cpp',
        'if errorlevel 1 exit /b 1',
        "cl /nologo /std:c++17 /EHsc /MT $defines $include /Fe:.build/native_selftest.exe /Fo:.build/ mod/asi/harness/native_selftest.cpp $common /link $systemLibs",
        'if errorlevel 1 exit /b 1',
        "cl /nologo /std:c++17 /EHsc /MT $defines $include /Fe:.build/native_harness.exe /Fo:.build/ mod/asi/harness/native_harness.cpp mod/asi/src/ap_client.cpp $common mod/asi/third_party/apcpp/Archipelago.cpp mod/asi/third_party/apcpp/Archipelago_DataStorageSim.cpp mod/asi/third_party/apcpp/Archipelago_Gifting.cpp /link $libs $systemLibs"
    )
    Set-Content -LiteralPath .build/build-native-tests.cmd -Value $commands -Encoding ascii
    & .build/build-native-tests.cmd
    if ($LASTEXITCODE) { throw 'Native test build failed.' }
    & .build/sdk_selftest.exe
    if ($LASTEXITCODE) { throw 'SDK pickup binding regression test failed.' }
    & .build/selftest.exe
    if ($LASTEXITCODE) { throw 'Game logic regression test failed.' }
    & .build/save_isolation_selftest.exe ("$repo/.build/save-isolation-selftest-" + [guid]::NewGuid().ToString('N'))
    if ($LASTEXITCODE) { throw 'Save isolation regression test failed.' }
    & .build/native_selftest.exe ("$repo/.build/native-selftest-" + [guid]::NewGuid().ToString('N'))
    if ($LASTEXITCODE) { throw 'Native self-test failed.' }
    Write-Host 'Run: python scripts/native_interop_check.py .build/native_harness.exe'
} finally {
    Pop-Location
}
