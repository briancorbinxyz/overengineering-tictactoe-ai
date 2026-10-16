<#
.SYNOPSIS
  The ratchet experiment on an RTX 5090 with llama.cpp: stronger embedders and rerankers, same
  configurations, same golden set. Writes results\5090-<run>.md and .jsonl, then story.py's verdicts.

.DESCRIPTION
  For each run in the lineup (python ratchet\llamacpp.py list), this script starts llama-server for
  the embedder on port 8090 and for the reranker on port 8091 (models fetched with -hf into the
  Hugging Face cache on first use), waits for /health, runs run.py, and stops both servers, even on
  error. It never touches another llama-server (your chat server on its own port keeps running) and
  never edits any OpenCode configuration.

  Resumable: a run whose .md and .jsonl both exist is skipped unless -Force.
  Log: results\5090-run.log (plus results\5090-<run>-<role>.server.log per server).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File tools\ratchet-proto\run_5090.ps1
.EXAMPLE
  .\tools\ratchet-proto\run_5090.ps1 -Models nomic,qwen3-emb-8b
.EXAMPLE
  .\tools\ratchet-proto\run_5090.ps1 -List
#>
[CmdletBinding()]
param(
    [string[]]$Models = @(),          # run names (default: the default lineup); see -List
    [switch]$Force,                   # rerun runs whose results already exist
    [switch]$List,                    # print the lineup, the server command lines and the download sizes, then stop
    [string]$Spectastic = '',         # spectastic checkout (default: $env:SPECTASTIC, else ..\spectastic next to the repo)
    [string]$Python = '',             # a Python 3.11+ to build the venv with (default: py -3, python3, python)
    [int]$EmbedPort = 8090,
    [int]$RerankPort = 8091,
    [int]$StartTimeoutMinutes = 60,   # per server, including the first download
    [switch]$SkipTests,
    [string[]]$ExtraArgs = @()        # passed through to run.py, e.g. -ExtraArgs '--only','A,S4' (from a PowerShell prompt, not -File)
)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$OnWindows = ($PSVersionTable.PSVersion.Major -lt 6) -or $IsWindows

$Here = $PSScriptRoot
$Repo = (Resolve-Path (Join-Path (Join-Path $Here '..') '..')).Path
$Results = Join-Path $Here 'results'
New-Item -ItemType Directory -Force -Path $Results | Out-Null
$script:Log = Join-Path $Results '5090-run.log'
$PinnedSpectastic = 'c64d41c2e5d0d42c4fefd1b506cb083b9812bf6c'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

function Log([string]$msg) {
    $line = '[{0}] {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg
    Write-Host $line
    Add-Content -LiteralPath $script:Log -Value $line -Encoding UTF8
}

function Fail([string]$msg) {
    Log "ERROR: $msg"
    exit 1
}

# Runs a native command, echoing and logging every line of stdout and stderr; returns its exit code.
function Invoke-Logged([string]$exe, [string[]]$argv) {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $exe @argv 2>&1 | ForEach-Object {
            if ($_ -is [System.Management.Automation.ErrorRecord]) { $s = $_.Exception.Message } else { $s = "$_" }
            Write-Host $s
            Add-Content -LiteralPath $script:Log -Value $s -Encoding UTF8
        }
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $prev
    }
}

# Runs a native command and returns its output as one string (stderr included), without logging.
function Invoke-Quiet([string]$exe, [string[]]$argv) {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $out = & $exe @argv 2>&1 | ForEach-Object {
            if ($_ -is [System.Management.Automation.ErrorRecord]) { $_.Exception.Message } else { "$_" }
        }
        return @{ Code = $LASTEXITCODE; Text = ($out -join "`n") }
    } catch {
        return @{ Code = 9009; Text = "$_" }
    } finally {
        $ErrorActionPreference = $prev
    }
}

function Test-PortOpen([int]$port) {
    $c = New-Object System.Net.Sockets.TcpClient
    try {
        $iar = $c.BeginConnect('127.0.0.1', $port, $null, $null)
        if ($iar.AsyncWaitHandle.WaitOne(500)) {
            try { $c.EndConnect($iar); return $true } catch { return $false }
        }
        return $false
    } catch {
        return $false
    } finally {
        $c.Close()
    }
}

Log "== run_5090.ps1 started (PowerShell $($PSVersionTable.PSVersion))"

# --- prerequisites -------------------------------------------------------------------------------

if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Fail 'git is not on PATH (winget install Git.Git)' }

$ls = Get-Command llama-server -ErrorAction SilentlyContinue
if (-not $ls) {
    Fail 'llama-server is not on PATH. Install llama.cpp (winget install llama.cpp, or unzip the CUDA build from https://github.com/ggml-org/llama.cpp/releases and add it to PATH).'
}
$LlamaServer = $ls.Source
$v = Invoke-Quiet $LlamaServer @('--version')
Log "llama-server: $LlamaServer"
$vl = @(($v.Text -split "`n") | Where-Object { $_ -match 'version|built' } | Select-Object -First 2) -join ' / '
Log "llama-server --version: $vl"

# a base Python 3.11+, only to create the venv
$candidates = @()
if ($Python) { $candidates += , @($Python) }
else {
    if (Get-Command py -ErrorAction SilentlyContinue) { $candidates += , @('py', '-3') }
    if (Get-Command python3 -ErrorAction SilentlyContinue) { $candidates += , @('python3') }
    if (Get-Command python -ErrorAction SilentlyContinue) { $candidates += , @('python') }
}
$BasePy = $null
foreach ($c in $candidates) {
    $exe = $c[0]
    $pre = @()
    if ($c.Count -gt 1) { $pre = @($c[1..($c.Count - 1)]) }
    $r = Invoke-Quiet $exe ($pre + @('-c', 'import sys; print(''%d.%d'' % sys.version_info[:2])'))
    if ($r.Code -eq 0 -and $r.Text -match '^(\d+)\.(\d+)') {
        $ver = [version]$Matches[0]
        if ($ver -ge [version]'3.11') { $BasePy = @{ Exe = $exe; Pre = $pre; Ver = $Matches[0] }; break }
        Log "skipping $($c -join ' '): Python $($Matches[0]) is older than 3.11"
    }
}
if (-not $BasePy) { Fail 'no Python 3.11+ found (winget install Python.Python.3.12; the Microsoft Store alias does not count). Or pass -Python <path to python.exe>.' }
Log "base Python: $($BasePy.Exe) $($BasePy.Pre -join ' ') ($($BasePy.Ver))"

# --- the plan (one source of truth: ratchet\llamacpp.py, standard library only) ----------------

$planPy = Join-Path (Join-Path $Here 'ratchet') 'llamacpp.py'
$planArgs = @($planPy, 'plan', '--embed-port', "$EmbedPort", '--rerank-port', "$RerankPort")
if ($Models.Count -gt 0) { $planArgs += @('--runs', ($Models -join ',')) }
$p = Invoke-Quiet $BasePy.Exe ($BasePy.Pre + $planArgs)
if ($p.Code -ne 0) { Fail "plan: $($p.Text)" }
$Plan = @()
foreach ($x in ($p.Text | ConvertFrom-Json)) { $Plan += $x }  # Windows PowerShell 5.1 does not enumerate a JSON array

if ($List) {
    $l = Invoke-Quiet $BasePy.Exe ($BasePy.Pre + @($planPy, 'list', '--embed-port', "$EmbedPort", '--rerank-port', "$RerankPort"))
    Write-Host $l.Text
    $gb = 0.0
    $seen = @{}
    foreach ($r in $Plan) {
        foreach ($s in @($r.embedder, $r.reranker)) {
            if ($s -and -not $seen.ContainsKey($s.hf)) { $seen[$s.hf] = 1; $gb += [double]$s.size_gb }
        }
    }
    Write-Host ("`nSelected runs: {0}; downloads on first use: {1:N1} GB" -f (($Plan | ForEach-Object { $_.name }) -join ', '), $gb)
    exit 0
}

if (-not $Spectastic) { $Spectastic = $env:SPECTASTIC }
if (-not $Spectastic) { $Spectastic = Join-Path (Split-Path $Repo -Parent) 'spectastic' }
if (-not (Test-Path (Join-Path $Spectastic 'specs'))) {
    Fail "no spectastic checkout at $Spectastic. Clone it next to the repo: git -c core.autocrlf=false clone --depth 1 --branch v0.1.0-pre.28 https://github.com/spectastic/spectastic.git `"$Spectastic`""
}
$Spectastic = (Resolve-Path $Spectastic).Path
$at = (Invoke-Quiet git @('-C', $Spectastic, 'rev-parse', 'HEAD')).Text.Trim()
if ($at -ne $PinnedSpectastic) {
    Log "WARNING: spectastic at $Spectastic is at '$at', not the pinned $PinnedSpectastic (tag v0.1.0-pre.28): the numbers are a new baseline, not a comparison."
} else {
    Log "spectastic: $Spectastic at the pinned commit $PinnedSpectastic"
}

# --- venv: numpy and tiktoken only -----------------------------------------------------------------

if ($OnWindows) { $VenvPy = Join-Path (Join-Path (Join-Path $Here '.venv') 'Scripts') 'python.exe' }
else { $VenvPy = Join-Path (Join-Path (Join-Path $Here '.venv') 'bin') 'python' }
if (-not (Test-Path $VenvPy)) {
    Log "creating venv in $(Join-Path $Here '.venv')"
    $code = Invoke-Logged $BasePy.Exe ($BasePy.Pre + @('-m', 'venv', (Join-Path $Here '.venv')))
    if ($code -ne 0 -or -not (Test-Path $VenvPy)) { Fail 'could not create the venv' }
}
$code = Invoke-Logged $VenvPy @('-m', 'pip', 'install', '-q', '--disable-pip-version-check', 'numpy', 'tiktoken')
if ($code -ne 0) { Fail 'pip install numpy tiktoken failed' }

$fts = Invoke-Quiet $VenvPy @('-c', "import sqlite3; c = sqlite3.connect(':memory:'); c.execute('create virtual table t using fts5(x)'); print(sqlite3.sqlite_version)")
if ($fts.Code -ne 0) {
    Fail "this Python's sqlite3 has no FTS5 (the BM25 index needs it): $($fts.Text). Use a python.org or winget CPython build, which ship SQLite with FTS5."
}
Log "SQLite $($fts.Text.Trim()) with FTS5"

if (-not $SkipTests) {
    Log 'running the offline tests'
    $code = Invoke-Logged $VenvPy @('-m', 'unittest', 'discover', '-s', (Join-Path $Here 'tests'))
    if ($code -ne 0) { Fail 'tests failed; not running the experiment' }
}

if ($EmbedPort -eq 8080 -or $RerankPort -eq 8080) { Log 'WARNING: port 8080 is llama-server''s default and may be your chat server; pick another' }

$others = @(Get-Process -Name 'llama-server' -ErrorAction SilentlyContinue)
if ($others.Count -gt 0) {
    Log ("other llama-server processes are running (left alone): pid " + (($others | ForEach-Object { $_.Id }) -join ', ') + '. They hold VRAM.')
}
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    $g = Invoke-Quiet nvidia-smi @('--query-gpu=name,memory.used,memory.total', '--format=csv,noheader,nounits')
    if ($g.Code -eq 0) {
        $f = $g.Text.Split("`n")[0].Split(',')
        $free = ([double]$f[2] - [double]$f[1]) / 1024
        Log ("GPU: {0}, {1:N1} GB free of {2:N1} GB" -f $f[0].Trim(), $free, ([double]$f[2] / 1024))
        $need = ($Plan | ForEach-Object { [double]$_.gb } | Measure-Object -Maximum).Maximum + 4
        if ($free -lt $need) {
            Log ("WARNING: the largest run needs about {0:N0} GB of VRAM (weights + buffers) and {1:N1} GB is free; a server that does not fit will fail to start (nothing is offloaded silently: -ngl 99)." -f $need, $free)
        }
    }
}

# --- servers ---------------------------------------------------------------------------------------

function Start-LlamaServer($spec, [string]$tag) {
    if (Test-PortOpen $spec.port) {
        throw "port $($spec.port) is already in use; not starting $($spec.alias) there (stop whatever listens on it, or pass -EmbedPort/-RerankPort)"
    }
    $errLog = Join-Path $Results "5090-$tag.server.log"
    $outLog = Join-Path $Results "5090-$tag.server.out.log"
    Log "starting llama-server for $($spec.alias) on port $($spec.port) ($($spec.hf), $($spec.size_gb) GB on first download)"
    Log ("  llama-server " + ($spec.args -join ' '))
    $proc = Start-Process -FilePath $LlamaServer -ArgumentList $spec.args -PassThru -NoNewWindow `
        -RedirectStandardError $errLog -RedirectStandardOutput $outLog
    $started = Get-Date
    $deadline = $started.AddMinutes($StartTimeoutMinutes)
    $nextNote = $started.AddSeconds(60)
    while ($true) {
        if ($proc.HasExited) {
            $tail = (Get-Content -LiteralPath $errLog -Tail 20 -ErrorAction SilentlyContinue) -join "`n"
            throw "llama-server for $($spec.alias) exited before it was ready. Last lines of ${errLog}:`n$tail"
        }
        try {
            $resp = Invoke-WebRequest -Uri "$($spec.url)/health" -UseBasicParsing -TimeoutSec 5
            if ($resp.StatusCode -eq 200) { break }
        } catch { }
        if ((Get-Date) -gt $deadline) {
            Stop-LlamaServer @{ Proc = $proc; Port = $spec.port; Alias = $spec.alias; Started = $started }
            throw "llama-server for $($spec.alias) was not ready after $StartTimeoutMinutes minutes (see $errLog)"
        }
        if ((Get-Date) -gt $nextNote) {
            $last = Get-Content -LiteralPath $errLog -Tail 1 -ErrorAction SilentlyContinue
            Log "  still waiting for $($spec.alias) (downloading or loading): $last"
            $nextNote = (Get-Date).AddSeconds(60)
        }
        Start-Sleep -Seconds 2
    }
    Log ("  ready after {0:N0} s (pid {1})" -f ((Get-Date) - $started).TotalSeconds, $proc.Id)
    return @{ Proc = $proc; Port = $spec.port; Alias = $spec.alias; Started = $started }
}

function Stop-LlamaServer($s) {
    if (-not $s) { return }
    $proc = $s.Proc
    if ($proc -and -not $proc.HasExited) {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        $null = $proc.WaitForExit(20000)
    }
    if (Test-PortOpen $s.Port) {
        # a launcher shim can leave the real server behind: stop a llama-server that listens on *our*
        # port and started after we started it; never anything else
        if (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue) {
            $owners = Get-NetTCPConnection -LocalPort $s.Port -State Listen -ErrorAction SilentlyContinue |
                ForEach-Object { Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue }
            foreach ($o in $owners) {
                if ($o.ProcessName -like 'llama-server*' -and $o.StartTime -ge $s.Started.AddSeconds(-2)) {
                    Stop-Process -Id $o.Id -Force -ErrorAction SilentlyContinue
                }
            }
            Start-Sleep -Seconds 2
        }
        if (Test-PortOpen $s.Port) { Log "WARNING: port $($s.Port) is still in use after stopping $($s.Alias)" }
    }
    Log "stopped llama-server for $($s.Alias)"
}

# --- the runs --------------------------------------------------------------------------------------

$done = @(); $skipped = @(); $failed = @()
foreach ($r in $Plan) {
    $out = Join-Path $Results "5090-$($r.name)"
    if ((Test-Path "$out.md") -and (Test-Path "$out.jsonl") -and -not $Force) {
        Log "== $($r.name): results exist ($out.md), skipped (use -Force to rerun)"
        $skipped += $r.name
        continue
    }
    Log "== $($r.name): $($r.why)"
    if ($Force) { Remove-Item -LiteralPath "$out.md", "$out.jsonl" -ErrorAction SilentlyContinue }
    $servers = @()
    $t0 = Get-Date
    try {
        $servers += Start-LlamaServer $r.embedder "$($r.name)-embed"
        $pyArgs = @('-u', (Join-Path $Here 'run.py'), '--spectastic', $Spectastic,
            '--embedder', "llamacpp:$($r.embedder.alias)", '--llamacpp-url', $r.embedder.url,
            '--out', $out)
        if ($r.reranker) {
            $servers += Start-LlamaServer $r.reranker "$($r.name)-rerank"
            $pyArgs += @('--reranker', "llamacpp:$($r.reranker.alias)", '--llamacpp-rerank-url', $r.reranker.url)
        }
        $pyArgs += $ExtraArgs
        $code = Invoke-Logged $VenvPy $pyArgs
        if ($code -ne 0) { throw "run.py exited with code $code" }
        Log ("== $($r.name): done in {0:N1} min -> $out.md" -f ((Get-Date) - $t0).TotalMinutes)
        $done += $r.name
    } catch {
        Log "== $($r.name) FAILED: $_"
        $failed += $r.name
    } finally {
        foreach ($s in $servers) { Stop-LlamaServer $s }
    }
}

# --- the story -------------------------------------------------------------------------------------

$all = @(Get-ChildItem -LiteralPath $Results -Filter '5090-*.jsonl' | Sort-Object Name | ForEach-Object { $_.FullName })
$all += @(Get-ChildItem -LiteralPath $Results -Filter 'mac-*.jsonl' -ErrorAction SilentlyContinue | Sort-Object Name | ForEach-Object { $_.FullName })
if ($all.Count -gt 0) {
    Log '== story.py'
    $storyOut = Join-Path $Results '5090-story.md'
    $s = Invoke-Quiet $VenvPy (@((Join-Path $Here 'story.py'), '--md') + $all)
    Set-Content -LiteralPath $storyOut -Value $s.Text -Encoding UTF8
    $null = Invoke-Logged $VenvPy (@((Join-Path $Here 'story.py')) + $all)
    Log "story written to $storyOut"
}

Log ("finished: done [{0}], skipped [{1}], failed [{2}]" -f ($done -join ', '), ($skipped -join ', '), ($failed -join ', '))
if ($failed.Count -gt 0) { exit 1 }
exit 0
