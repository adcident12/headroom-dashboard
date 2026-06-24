param(
    [Parameter(Position=0)]
    [ValidateSet("on","off","status","")]
    [string]$Command = ""
)

$ProxyPort = 8787
$ProxyUrl = "http://127.0.0.1:$ProxyPort"
$HeadroomExe = "C:\laragon\bin\python\python-3.10\Scripts\headroom.exe"

function Test-ProxyRunning {
    try {
        $r = Invoke-WebRequest -Uri "$ProxyUrl/health" -TimeoutSec 2 -ErrorAction Stop
        return $r.StatusCode -eq 200
    } catch {
        return $false
    }
}

# ── UI Helpers ────────────────────────────────────────────────────────

function Format-Tokens {
    param([double]$N)
    if ($N -ge 1000000) { return "{0:N1}M" -f ($N / 1000000) }
    if ($N -ge 1000)    { return "{0:N1}K" -f ($N / 1000) }
    return "{0:N0}" -f $N
}

function Format-Duration {
    param([double]$Sec)
    if ($Sec -ge 86400) { return "{0}d {1}h" -f [math]::Floor($Sec/86400), [math]::Floor(($Sec%86400)/3600) }
    if ($Sec -ge 3600)  { return "{0}h {1}m" -f [math]::Floor($Sec/3600), [math]::Floor(($Sec%3600)/60) }
    if ($Sec -ge 60)    { return "{0}m {1}s" -f [math]::Floor($Sec/60), [math]::Floor($Sec%60) }
    return "{0:N0}s" -f $Sec
}

function Format-USD {
    param([double]$V)
    if ($V -ge 1)    { return "`${0:N2}" -f $V }
    if ($V -ge 0.01) { return "`${0:N3}" -f $V }
    if ($V -gt 0)    { return "`${0:N4}" -f $V }
    return "`$0.00"
}

function Write-Bar {
    param([double]$Pct, [int]$W = 22, [string]$Label = "")
    $p = [math]::Min(100, [math]::Max(0, $Pct))
    $filled = [math]::Round($W * $p / 100)
    $empty  = $W - $filled
    $color  = if ($p -ge 80) { "Red" } elseif ($p -ge 60) { "Yellow" } else { "Green" }
    $bar    = [string][char]0x2588 * $filled
    $rest   = [string][char]0x2591 * $empty
    Write-Host "  $Label " -NoNewline
    Write-Host $bar -ForegroundColor $color -NoNewline
    Write-Host $rest -ForegroundColor DarkGray -NoNewline
    Write-Host (" {0,5:N1}%" -f $p)
}

function Write-Section {
    param([string]$Title)
    $line = [string][char]0x2500 * 48
    Write-Host ""
    Write-Host "  $Title" -ForegroundColor Cyan
    Write-Host "  $line" -ForegroundColor DarkGray
}

function Write-KV {
    param([string]$K, [string]$V, [string]$C = "White", [int]$Pad = 22)
    Write-Host ("  " + $K.PadRight($Pad)) -ForegroundColor Gray -NoNewline
    Write-Host $V -ForegroundColor $C
}

function Write-Dot {
    param([string]$Name, [string]$Status)
    $dot   = if ($Status -eq "healthy") { [char]0x25CF } elseif ($Status -eq "disabled") { [char]0x25CB } else { [char]0x25CF }
    $color = if ($Status -eq "healthy") { "Green" } elseif ($Status -eq "disabled") { "DarkGray" } else { "Red" }
    Write-Host "  $dot " -ForegroundColor $color -NoNewline
    Write-Host $Name.PadRight(18) -ForegroundColor Gray -NoNewline
    Write-Host $Status -ForegroundColor $color
}

# ── Dashboard ─────────────────────────────────────────────────────────

function Show-Status {
    $running = Test-ProxyRunning
    $health  = $null
    $stats   = $null
    if ($running) {
        try { $health = Invoke-RestMethod -Uri "$ProxyUrl/health" -TimeoutSec 3 -ErrorAction Stop } catch {}
        try { $stats  = Invoke-RestMethod -Uri "$ProxyUrl/stats"  -TimeoutSec 3 -ErrorAction Stop } catch {}
    }

    # ── Banner ──
    $bdr = [string][char]0x2500 * 50
    $tl = [char]0x256D; $tr = [char]0x256E; $bl = [char]0x2570; $br = [char]0x256F; $vl = [char]0x2502
    Write-Host ""
    if ($running) {
        Write-Host "  $tl$bdr$tr" -ForegroundColor Green
        Write-Host "  $vl  HEADROOM DASHBOARD                              $vl" -ForegroundColor Green
        Write-Host "  $bl$bdr$br" -ForegroundColor Green
    } else {
        Write-Host "  $tl$bdr$tr" -ForegroundColor Red
        Write-Host "  $vl  HEADROOM DASHBOARD            PROXY OFFLINE     $vl" -ForegroundColor Red
        Write-Host "  $bl$bdr$br" -ForegroundColor Red
    }

    # ── Proxy ──
    Write-Section "PROXY"
    if ($running) {
        Write-Host "  Status                " -NoNewline -ForegroundColor Gray
        Write-Host "$([char]0x25CF) RUNNING" -ForegroundColor Green
        if ($health) {
            $ver = if ($health.version) { $health.version } else { "?" }
            Write-KV "Version" "v$ver"
            Write-KV "Uptime" (Format-Duration $health.uptime_seconds)
            Write-KV "PID" "$($health.config.pid)"
        }
        Write-KV "Endpoint" $ProxyUrl
    } else {
        Write-Host "  Status                " -NoNewline -ForegroundColor Gray
        Write-Host "$([char]0x25CF) STOPPED" -ForegroundColor Red
    }

    # ── Environment ──
    Write-Section "ENVIRONMENT"
    $envVal = [System.Environment]::GetEnvironmentVariable("ANTHROPIC_BASE_URL", "User")
    if ($envVal) {
        Write-KV "ANTHROPIC_BASE_URL" $envVal "Green"
    } else {
        Write-KV "ANTHROPIC_BASE_URL" "(not set)" "DarkGray"
    }
    $sessionEnv = $env:ANTHROPIC_BASE_URL
    if ($sessionEnv) {
        Write-KV "Session env" $sessionEnv "Green"
    } else {
        Write-KV "Session env" "(not inherited)" "Yellow"
    }

    if (-not $running) {
        Write-Host ""
        Write-Host "  Start with: " -ForegroundColor DarkGray -NoNewline
        Write-Host ".\headroom.ps1 on" -ForegroundColor Yellow
        Write-Host ""
        return
    }
    if (-not $stats) {
        Write-Host ""
        Write-Host "  (could not fetch stats)" -ForegroundColor DarkGray
        Write-Host ""
        return
    }

    # ── Subscription Window ──
    $sw = $stats.subscription_window
    if ($sw -and $sw.latest) {
        Write-Section "SUBSCRIPTION USAGE"

        $five = $sw.latest.five_hour
        if ($five) {
            Write-Bar -Pct $five.utilization_pct -W 24 -Label "5-Hour Window   "
            Write-Host "                          resets in $(Format-Duration $five.seconds_to_reset)" -ForegroundColor DarkGray
        }
        $seven = $sw.latest.seven_day
        if ($seven) {
            Write-Bar -Pct $seven.utilization_pct -W 24 -Label "7-Day Window    "
            Write-Host "                          resets in $(Format-Duration $seven.seconds_to_reset)" -ForegroundColor DarkGray
        }
        $extra = $sw.latest.extra_usage
        if ($extra -and $extra.is_enabled) {
            $used  = if ($extra.used_credits_usd) { Format-USD $extra.used_credits_usd } else { "`$0.00" }
            $limit = if ($extra.monthly_limit_usd) { Format-USD $extra.monthly_limit_usd } else { "unlimited" }
            $epct  = if ($extra.utilization_pct) { $extra.utilization_pct } else { 0 }
            Write-Bar -Pct $epct -W 24 -Label "Extra Usage     "
            Write-Host "                          $used / $limit" -ForegroundColor DarkGray
        }

        $wt = $sw.window_tokens
        if ($wt -and $wt.total_raw -gt 0) {
            Write-Host ""
            Write-Host "  Window Tokens:" -ForegroundColor Gray
            Write-KV "    Input" (Format-Tokens $wt.input)
            Write-KV "    Output" (Format-Tokens $wt.output)
            Write-KV "    Cache Reads" (Format-Tokens $wt.cache_reads) "DarkCyan"
            Write-KV "    Cache Writes" (Format-Tokens $wt.cache_writes_total)
            Write-KV "    Total" (Format-Tokens $wt.total_raw) "White"

            if ($wt.by_model) {
                Write-Host ""
                Write-Host "  By Model:" -ForegroundColor Gray
                foreach ($prop in $wt.by_model.PSObject.Properties) {
                    $m = $prop.Value
                    $totalM = $m.input + $m.output + $m.cache_reads + $m.cache_writes_total
                    Write-KV "    $($prop.Name)" (Format-Tokens $totalM)
                }
            }
        }
    }

    # ── Requests ──
    $req = $stats.requests
    Write-Section "REQUESTS"
    Write-KV "Total" ("{0:N0}" -f $req.total)
    if ($req.cached -gt 0)       { Write-KV "Cached" ("{0:N0}" -f $req.cached) "DarkCyan" }
    if ($req.rate_limited -gt 0) { Write-KV "Rate Limited" ("{0:N0}" -f $req.rate_limited) "Yellow" }
    if ($req.failed -gt 0)       { Write-KV "Failed" ("{0:N0}" -f $req.failed) "Red" }

    if ($req.by_model) {
        $modelProps = $req.by_model.PSObject.Properties
        if ($modelProps.Count -gt 0) {
            Write-Host "  By Model:" -ForegroundColor Gray
            foreach ($p in $modelProps) { Write-KV "    $($p.Name)" ("{0:N0}" -f $p.Value) }
        }
    }

    # ── Token Savings ──
    $tok = $stats.tokens
    Write-Section "TOKEN SAVINGS"
    Write-KV "Input Tokens" (Format-Tokens $tok.input)
    Write-KV "Output Tokens" (Format-Tokens $tok.output)

    $totalSaved = if ($tok.all_layers_saved -gt 0) { $tok.all_layers_saved } else { $tok.saved }
    $savPct     = if ($tok.all_layers_savings_percent -gt 0) { $tok.all_layers_savings_percent } else { $tok.savings_percent }
    if ($totalSaved -gt 0) {
        Write-Host ""
        Write-Host "  Tokens Saved          " -NoNewline -ForegroundColor Gray
        Write-Host "$(Format-Tokens $totalSaved)" -NoNewline -ForegroundColor Green
        if ($savPct -gt 0) { Write-Host " ($("{0:N1}" -f $savPct)%)" -ForegroundColor Green }
        else { Write-Host "" }

        if ($tok.proxy_compression_saved -gt 0) { Write-KV "    Compression" (Format-Tokens $tok.proxy_compression_saved) }
        if ($tok.cli_filtering_saved -gt 0)     { Write-KV "    CLI Filtering" (Format-Tokens $tok.cli_filtering_saved) }
        if ($tok.rtk_saved -gt 0)               { Write-KV "    RTK" (Format-Tokens $tok.rtk_saved) }
    } else {
        Write-KV "Tokens Saved" "0 (no activity)" "DarkGray"
    }

    # ── Cost ──
    $cost = $stats.cost
    Write-Section "COST"
    if ($cost.total_input_cost_usd -gt 0 -or $cost.savings_usd -gt 0) {
        Write-KV "Input Cost" (Format-USD $cost.total_input_cost_usd)
        Write-KV "With Headroom" (Format-USD $cost.cost_with_headroom_usd)
        Write-Host "  Total Saved           " -NoNewline -ForegroundColor Gray
        Write-Host (Format-USD $cost.savings_usd) -ForegroundColor Green
        if ($cost.compression_savings_usd -gt 0) { Write-KV "    Compression" (Format-USD $cost.compression_savings_usd) }
        if ($cost.cache_savings_usd -gt 0)       { Write-KV "    Cache" (Format-USD $cost.cache_savings_usd) }
    } else {
        Write-KV "Status" "No cost activity yet" "DarkGray"
    }

    # ── Lifetime ──
    $ps = $stats.persistent_savings
    if ($ps -and $ps.lifetime -and $ps.lifetime.requests -gt 0) {
        Write-Section "LIFETIME"
        Write-KV "Requests" ("{0:N0}" -f $ps.lifetime.requests)
        Write-KV "Tokens Saved" (Format-Tokens $ps.lifetime.tokens_saved) "Green"
        Write-KV "Total Input" (Format-Tokens $ps.lifetime.total_input_tokens)
        Write-KV "Savings" (Format-USD $ps.lifetime.compression_savings_usd) "Green"
    }

    # ── Session ──
    $ds = $stats.display_session
    if ($ds -and $ds.requests -gt 0) {
        Write-Section "SESSION"
        Write-KV "Requests" ("{0:N0}" -f $ds.requests)
        Write-KV "Tokens Saved" (Format-Tokens $ds.tokens_saved) "Green"
        if ($ds.savings_percent -gt 0) { Write-KV "Savings Rate" ("{0:N1}%" -f $ds.savings_percent) }
        if ($ds.started_at) { Write-KV "Started" $ds.started_at "DarkGray" }
    }

    # ── Performance ──
    if ($stats.latency.total_requests -gt 0) {
        Write-Section "PERFORMANCE"
        Write-KV "TTFB (avg)" ("{0:N0}ms" -f $stats.ttfb.average_ms)
        Write-KV "TTFB (range)" ("{0:N0} ~ {1:N0}ms" -f $stats.ttfb.min_ms, $stats.ttfb.max_ms)
        Write-KV "Overhead (avg)" ("{0:N0}ms" -f $stats.overhead.average_ms)
        Write-KV "Latency (avg)" ("{0:N0}ms" -f $stats.latency.average_ms)
    }

    # ── Strategies ──
    if ($stats.compressions_by_strategy) {
        $sp = $stats.compressions_by_strategy.PSObject.Properties
        if ($sp.Count -gt 0) {
            Write-Section "COMPRESSION STRATEGIES"
            foreach ($p in $sp) {
                $sv = 0
                if ($stats.tokens_saved_by_strategy -and $stats.tokens_saved_by_strategy.PSObject.Properties[$p.Name]) {
                    $sv = $stats.tokens_saved_by_strategy.PSObject.Properties[$p.Name].Value
                }
                Write-KV "  $($p.Name)" ("{0:N0}x  {1} saved" -f $p.Value, (Format-Tokens $sv))
            }
        }
    }

    # ── Prefix Cache ──
    $pc = $stats.prefix_cache
    if ($pc -and $pc.totals -and $pc.totals.requests -gt 0) {
        Write-Section "PREFIX CACHE"
        Write-KV "Requests" ("{0:N0}" -f $pc.totals.requests)
        Write-KV "Hit Rate" ("{0:N0}%" -f $pc.totals.request_hit_rate)
        Write-KV "Cache Reads" (Format-Tokens $pc.totals.cache_read_tokens)
        Write-KV "Cache Writes" (Format-Tokens $pc.totals.cache_write_tokens)
        if ($pc.totals.net_savings_usd -ne 0) { Write-KV "Net Savings" (Format-USD $pc.totals.net_savings_usd) "Green" }
        if ($pc.totals.bust_count -gt 0)      { Write-KV "Cache Busts" ("{0:N0}" -f $pc.totals.bust_count) "Yellow" }
    }

    # ── Services Health ──
    if ($health -and $health.checks) {
        Write-Section "SERVICES"
        foreach ($p in $health.checks.PSObject.Properties) {
            Write-Dot $p.Name $p.Value.status
        }
    }

    # ── Config ──
    if ($health -and $health.config) {
        Write-Section "CONFIGURATION"
        $cfg = $health.config
        Write-KV "Backend" $cfg.backend
        $on  = @()
        $off = @()
        foreach ($f in @("optimize","cache","rate_limit","memory","learn","code_graph")) {
            $val = $cfg.PSObject.Properties[$f]
            if ($val -and $val.Value) { $on += $f.Replace("_","-") }
            else                      { $off += $f.Replace("_","-") }
        }
        Write-Host "  Enabled               " -NoNewline -ForegroundColor Gray
        if ($on.Count -gt 0) { foreach ($f in $on) { Write-Host "$f " -NoNewline -ForegroundColor Green } }
        else { Write-Host "(none)" -NoNewline -ForegroundColor DarkGray }
        Write-Host ""
        if ($off.Count -gt 0) {
            Write-Host "  Disabled              " -NoNewline -ForegroundColor Gray
            foreach ($f in $off) { Write-Host "$f " -NoNewline -ForegroundColor DarkGray }
            Write-Host ""
        }
    }

    # ── Footer ──
    Write-Host ""
    Write-Host "  $([string][char]0x2500 * 50)" -ForegroundColor DarkGray
    $ts = Get-Date -Format "HH:mm:ss"
    Write-Host "  $ts" -ForegroundColor DarkGray -NoNewline
    Write-Host " $([char]0x2502) " -ForegroundColor DarkGray -NoNewline
    Write-Host ".\headroom.ps1 off" -ForegroundColor DarkGray -NoNewline
    Write-Host " to stop  " -ForegroundColor DarkGray -NoNewline
    Write-Host "$([char]0x2502) " -ForegroundColor DarkGray -NoNewline
    Write-Host "$ProxyUrl/stats" -ForegroundColor DarkGray -NoNewline
    Write-Host " raw JSON" -ForegroundColor DarkGray
    Write-Host ""
}

function Start-Headroom {
    if (Test-ProxyRunning) {
        Write-Host ""
        Write-Host "  [Headroom] Already running on $ProxyUrl" -ForegroundColor Yellow
        Show-Status
        return
    }

    Write-Host ""
    Write-Host "  [Headroom] Starting proxy on port $ProxyPort ..." -ForegroundColor Cyan

    Start-Process -FilePath $HeadroomExe `
        -ArgumentList "proxy","--no-telemetry","--code-aware","--port",$ProxyPort `
        -WindowStyle Minimized

    $tries = 0
    while ($tries -lt 15) {
        Start-Sleep -Seconds 1
        if (Test-ProxyRunning) { break }
        $tries++
    }

    if (-not (Test-ProxyRunning)) {
        Write-Host "  [Headroom] ERROR: Proxy did not start within 15 seconds." -ForegroundColor Red
        return
    }

    [System.Environment]::SetEnvironmentVariable("ANTHROPIC_BASE_URL", $ProxyUrl, "User")
    $env:ANTHROPIC_BASE_URL = $ProxyUrl

    Write-Host ""
    Write-Host "  +------------------------------------------------+" -ForegroundColor Green
    Write-Host "  |  HEADROOM: ON                                   |" -ForegroundColor Green
    Write-Host "  |  Proxy:    $ProxyUrl                  |" -ForegroundColor Green
    Write-Host "  |  Stats:    $ProxyUrl/stats            |" -ForegroundColor Green
    Write-Host "  +------------------------------------------------+" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Claude Code sessions started AFTER this point" -ForegroundColor White
    Write-Host "  will route through Headroom automatically." -ForegroundColor White
    Write-Host ""
    Write-Host "  Restart VSCode or open a new terminal to apply." -ForegroundColor DarkGray
    Write-Host "  To stop:  .\headroom.ps1 off" -ForegroundColor DarkGray
    Write-Host ""
}

function Stop-Headroom {
    if (-not (Test-ProxyRunning)) {
        Write-Host ""
        Write-Host "  [Headroom] Not running. Nothing to stop." -ForegroundColor DarkGray
        [System.Environment]::SetEnvironmentVariable("ANTHROPIC_BASE_URL", $null, "User")
        $env:ANTHROPIC_BASE_URL = $null
        return
    }

    Write-Host ""
    Write-Host "  [Headroom] Stopping proxy ..." -ForegroundColor Cyan

    try { Get-Process -Name "headroom" -ErrorAction Stop | Stop-Process -Force } catch {}

    Start-Sleep -Seconds 1

    [System.Environment]::SetEnvironmentVariable("ANTHROPIC_BASE_URL", $null, "User")
    $env:ANTHROPIC_BASE_URL = $null

    Write-Host ""
    Write-Host "  +------------------------------------------------+" -ForegroundColor Red
    Write-Host "  |  HEADROOM: OFF                                  |" -ForegroundColor Red
    Write-Host "  |  Proxy stopped. Env var removed.                |" -ForegroundColor Red
    Write-Host "  +------------------------------------------------+" -ForegroundColor Red
    Write-Host ""
    Write-Host "  Claude Code will connect directly to Anthropic API." -ForegroundColor White
    Write-Host ""
    Write-Host "  Restart VSCode or open a new terminal to apply." -ForegroundColor DarkGray
    Write-Host ""
}

# --- Main ---
switch ($Command) {
    "on"     { Start-Headroom }
    "off"    { Stop-Headroom }
    "status" { Show-Status }
    ""       {
        if (Test-ProxyRunning) { Stop-Headroom }
        else                   { Start-Headroom }
    }
}
