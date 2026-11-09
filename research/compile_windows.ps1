param(
    [Parameter(Mandatory=$true)][string]$TerminalDirectory,
    [switch]$Checks
)
$ErrorActionPreference = 'Stop'
$terminal = (Resolve-Path -LiteralPath $TerminalDirectory).Path
$editor = Join-Path $terminal 'MetaEditor64.exe'
$marker = Join-Path $terminal '.goldlab-research-terminal'
if (!(Test-Path -LiteralPath $marker -PathType Leaf) -or !(Test-Path -LiteralPath $editor -PathType Leaf)) {
    throw 'Provide an isolated portable MT5 directory with MetaEditor64.exe and a .goldlab-research-terminal marker.'
}
$source = Join-Path $PSScriptRoot '..\mql5'
$run = Join-Path (Join-Path $terminal 'MQL5\Experts') ('GoldLab-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $run | Out-Null
Copy-Item -LiteralPath (Join-Path $source 'GoldResearchLab') -Destination $run -Recurse
Copy-Item -LiteralPath (Join-Path $source 'GoldResearchLab.mq5') -Destination $run
$expert = Join-Path $run 'GoldResearchLab.mq5'
if ($Checks) {
    Copy-Item -LiteralPath (Join-Path $source 'tests') -Destination $run -Recurse
    $expert = Join-Path $run 'tests\GoldResearchLabChecks.mq5'
}
$log = Join-Path $run 'compile.log'
$process = Start-Process -FilePath $editor -WorkingDirectory $terminal -PassThru -Wait -ArgumentList @(
    '/portable', ('/compile:"' + $expert + '"'), ('/log:"' + $log + '"')
)
$artifact = [IO.Path]::ChangeExtension($expert, '.ex5')
if (!(Test-Path -LiteralPath $artifact -PathType Leaf) -or !(Test-Path -LiteralPath $log -PathType Leaf)) {
    throw "MetaEditor exited $($process.ExitCode). No compile artifact or log at $run"
}
if ((Get-Content -LiteralPath $log -Raw) -notmatch '(?m)^Result:\s+0 errors,\s+0 warnings,') {
    throw "Read the MetaEditor diagnostics at $log"
}
[pscustomobject]@{ MetaEditorExit = $process.ExitCode; Ex5 = $artifact; Log = $log }
