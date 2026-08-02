# Kiro PreToolUse shell gate  (v2: adds script-execution enforcement)
#
# Reads the hook payload (JSON) from stdin and inspects the shell command.
#   exit 2  -> block (stderr is forwarded to the agent)
#   exit 0  -> allow (stdout must stay empty)
#   other   -> Kiro ignores it silently, so internal errors also exit 0 (fail open)
#
# LOCATION MATTERS. Deploy this to C:\Users\Mickey\.kiro-guards\kiro-shell-gate.ps1
# permissions.yaml denies agent writes there, so the agent cannot edit its own guard.
#
# ASCII ONLY. Windows PowerShell 5.1 reads BOM-less .ps1 as ANSI, so non-ASCII
# characters corrupt the file and break parsing.
#
# Policy
#   - Local repo modification is allowed.
#   - Sending data outside the repo, granting outside access, and tampering with
#     the guards are blocked.
#   - Inbound package installs are allowed.
#   - Executing a local script is allowed only if the script is committed and
#     clean in git AND its contents pass a content scan. This turns the
#     "read the script before running it" steering rule into a mechanism.
#
# Fail-open vs fail-closed
#   - Internal gate errors fail OPEN, so a gate bug cannot halt all work.
#   - Script execution fails CLOSED: if the target cannot be resolved, read, or
#     checked against git, it is blocked. Script execution is the main bypass
#     path and these commands are rare, so the friction is acceptable.
#
# Known residual hole: `flutter test` / `dart test` are NOT commit-gated,
# because gating them would break normal test-driven work. Test files are still
# arbitrary code.

param(
    [string]$WorkspaceRoot = 'C:\Users\Mickey\StudioProjects\dating-app-1'
)

$ErrorActionPreference = 'Stop'

$logDir  = Join-Path $PSScriptRoot 'logs'
$logFile = Join-Path $logDir 'shell-gate.log'

function Write-GateLog {
    param([string]$Decision, [string]$Detail)
    try {
        if (-not (Test-Path $logDir)) {
            New-Item -ItemType Directory -Path $logDir -Force | Out-Null
        }
        $stamp = Get-Date -Format 'yyyy-MM-ddTHH:mm:ss.fffK'
        Add-Content -LiteralPath $logFile -Value ('{0} [{1}] {2}' -f $stamp, $Decision, $Detail) -Encoding UTF8
    } catch {
    }
}

function Deny {
    param([string]$Reason, [string]$Command, [string]$AgentMessage)
    $short = ''
    if ($Command) { $short = $Command.Substring(0, [Math]::Min(300, $Command.Length)) }
    Write-GateLog 'BLOCK' ("[$Reason] " + $short)
    [Console]::Error.Write("shell-gate BLOCKED: $Reason. $AgentMessage")
    exit 2
}

# --- payload ----------------------------------------------------------------

function Find-StringProperty {
    param($Node, [string[]]$Names, [int]$Depth = 0)

    if ($null -eq $Node -or $Depth -gt 6) { return $null }
    if ($Node -is [string]) { return $null }

    if ($Node -is [System.Collections.IEnumerable]) {
        foreach ($item in $Node) {
            $found = Find-StringProperty -Node $item -Names $Names -Depth ($Depth + 1)
            if ($found) { return $found }
        }
        return $null
    }

    if ($Node.PSObject -and $Node.PSObject.Properties) {
        foreach ($prop in $Node.PSObject.Properties) {
            if (($Names -contains $prop.Name) -and ($prop.Value -is [string])) {
                if ($prop.Value.Trim()) { return [string]$prop.Value }
            }
        }
        foreach ($prop in $Node.PSObject.Properties) {
            $found = Find-StringProperty -Node $prop.Value -Names $Names -Depth ($Depth + 1)
            if ($found) { return $found }
        }
    }

    return $null
}

# --- command parsing --------------------------------------------------------

function Split-Segments {
    param([string]$Command)
    return [regex]::Split($Command, '(?:;|\|\||&&|\|)')
}

function Get-LeadingToken {
    param([string]$Segment)

    $s = $Segment.Trim()
    if (-not $s) { return $null }
    $s = $s -replace '^[\(\{\s]+', ''
    $s = $s -replace '^[&\.]\s+', ''
    if (-not $s) { return $null }

    $token = ($s -split '\s+', 2)[0]
    $token = $token.Trim().TrimEnd(',', ';', ')', '}')
    return $token.ToLowerInvariant()
}

function Test-QuotesBalanced {
    param([string]$Segment)
    $single = ([regex]::Matches($Segment, "'")).Count
    $double = ([regex]::Matches($Segment, '"')).Count
    return (($single % 2) -eq 0) -and (($double % 2) -eq 0)
}

# The policy engine parses shell commands with a tree-sitter PowerShell grammar
# that cannot handle comma-separated argument lists. Each such comma produces a
# "missing node" parse error, the rule match then fails, and the engine falls
# back to asking the user. Blocking here turns that approval prompt into an
# immediate, self-correctable error.
#
# Commas inside parentheses are fine: Substring(0,200), [Math]::Min(1,2).
# Returns the index of the offending comma, or -1 when none is found.
function Find-CommaOutsideParens {
    param([string]$Command)

    $depth    = 0
    $inSingle = $false
    $inDouble = $false

    for ($i = 0; $i -lt $Command.Length; $i++) {
        $c = $Command[$i]

        if ($c -eq "'" -and -not $inDouble) { $inSingle = -not $inSingle; continue }
        if ($c -eq '"' -and -not $inSingle) { $inDouble = -not $inDouble; continue }
        if ($inSingle -or $inDouble) { continue }

        if ($c -eq '(') { $depth++; continue }
        if ($c -eq ')') { if ($depth -gt 0) { $depth-- }; continue }
        if ($c -eq ',' -and $depth -eq 0) { return $i }
    }

    return -1
}

# File reading and code search must go through the agent tools (grep_search,
# read_file, file_search), which bypass shell evaluation entirely. Reading Kiro's
# own logs is exempt because those live outside the workspace and the search
# tools cannot reach them.
$shellSearchTokens = @(
    'select-string', 'sls',
    'get-content', 'gc', 'cat', 'type',
    'findstr', 'grep'
)

function Test-LogDiagnosticExempt {
    param([string]$Command)
    return ($Command -match '\.kiro[\\/]logs|kiro\.log|shell-gate\.log')
}

function Get-SegmentArgs {
    param([string]$Segment)
    $s = $Segment.Trim() -replace '^[\(\{\s]+', ''
    $parts = @([regex]::Matches($s, '"[^"]*"|''[^'']*''|\S+') | ForEach-Object { $_.Value.Trim('"', "'") })
    if ($parts.Count -le 1) { return @() }
    return @($parts[1..($parts.Count - 1)])
}

# --- blocklists -------------------------------------------------------------

$blockedLeadingTokens = @(
    'remove-item', 'remove-itemproperty', 'ri', 'rm', 'del', 'erase', 'rd', 'rmdir',
    'clear-content', 'clear-item',
    'diskpart', 'format', 'cipher', 'takeown', 'icacls', 'cacls', 'attrib', 'set-acl',
    'new-localuser', 'set-localuser', 'new-localgroup', 'add-localgroupmember', 'net',
    'enable-psremoting', 'winrm', 'winrs', 'invoke-command', 'new-pssession',
    'enter-pssession', 'new-smbshare', 'netsh',
    'new-netfirewallrule', 'set-netfirewallrule', 'remove-netfirewallrule',
    'schtasks', 'register-scheduledtask', 'new-scheduledtask', 'new-service', 'sc.exe',
    'invoke-webrequest', 'iwr', 'invoke-restmethod', 'curl', 'curl.exe',
    'wget', 'wget.exe', 'start-bitstransfer', 'bitsadmin', 'certutil',
    'ssh', 'scp', 'sftp', 'ftp', 'tftp', 'telnet', 'nc', 'ncat', 'netcat', 'rsync',
    'send-mailmessage', 'invoke-sqlcmd',
    'nslookup', 'resolve-dnsname', 'test-netconnection', 'ping', 'tracert',
    'invoke-expression', 'iex', 'start-process', 'saps', 'add-type',
    'mshta', 'rundll32', 'regsvr32', 'wscript', 'cscript',
    'set-executionpolicy',
    'npx', 'npx.cmd', 'pnpx', 'bunx', 'dlx',
    'aws', 'gcloud', 'az', 'azcopy', 'kubectl', 'helm', 'terraform',
    'heroku', 'vercel', 'netlify', 'serverless', 'sam', 'eb',
    'gh', 'glab', 'docker', 'podman', 'ssh-keygen'
)

$blockedPatterns = [ordered]@{
    # Guard paths. The logs subdirectory is readable so the audit trail can be
    # inspected, but writes to it are caught by 'guard log tampering' below.
    'guard tampering'             = 'kiro-shell-gate|\.kiro-guards(?![\\/]logs)|\.kiro[\\/]hooks|\.kiro[\\/]steering|Kiro[\\/]User[\\/]settings\.json|\.kiro[\\/]settings|\.vscode[\\/]settings\.json'
    'guard log tampering'         = '(Set-Content|Add-Content|Out-File|Clear-Content|New-Item|Copy-Item|Move-Item|Rename-Item)[^;|&]*\.kiro-guards|>>?\s*["'']?\S*\.kiro-guards'
    'dotnet destructive file api' = '\[[^\]]*\]::\s*(Delete|Move|WriteAllText|WriteAllBytes|AppendAllText|Copy)\b'
    'dotnet network api'          = 'System\.Net\.|\[\s*Net\.|\]::\s*(DownloadString|DownloadFile|DownloadData|UploadString|UploadFile|UploadData|GetAsync|PostAsync|PutAsync|SendAsync|GetStringAsync)\b'
    'dynamic assembly load'       = '\[[^\]]*Reflection[^\]]*\]::\s*(Load|LoadFile|LoadFrom|LoadWithPartialName)'
    'git push (outbound)'         = 'git\s+push\b'
    'git remote add/set-url'      = 'git\s+remote\s+(add|set-url)\b'
    'git config (exec vectors)'   = 'git\s+config\b'
    'git reset --hard'            = 'git\s+reset\s+(--\S+\s+)*--hard'
    'git clean -f'                = 'git\s+clean\s+-[a-zA-Z]*f'
    'dart/flutter pub run'        = '\bdart\s+(pub\s+)?run\b|\bflutter\s+pub\s+run\b'
    'package publish/auth'        = '\b(npm|pnpm|yarn)\s+(publish|login|adduser|token)\b|\b(dart|flutter)\s+pub\s+(publish|token|login)\b'
    'container image push'        = '\bdocker\s+(push|login)\b'
    'firebase deploy/config'      = '\bfirebase\s+(deploy|login|logout|apps:create|projects:create|hosting:channel:deploy)\b|\bfirebase\s+functions:(config|secrets):set\b'
    'iam / privilege grant'       = 'add-iam-policy-binding|iam\s+(put|attach|create|add)-|role\s+assignment\s+create|authorized_keys'
    'powershell profile write'    = '\$PROFILE|WindowsPowerShell[\\/]profile|WindowsPowerShell[\\/]Microsoft\.PowerShell_profile'
    'inline code eval'            = '\b(node|python|python3|ruby|perl|php)\s+(-e|-c|--eval)\b'
    'secret file path'            = '(^|[\s"''=\\/])\.env(\b|\.)|key\.properties|\.jks\b|\.pem\b|\.p12\b|\.keystore\b|serviceaccount[^\s"'']*\.json|google-services\.json|GoogleService-Info\.plist'
    'encoded command'             = '-[eE]ncoded[cC]ommand'
    'remote script execution'     = '(iwr|curl|wget|invoke-webrequest|invoke-restmethod)[^;|&]*\|\s*(iex|invoke-expression)'
}

# Applied to the CONTENTS of a script that is about to be executed.
$blockedScriptPatterns = [ordered]@{
    'script: network module'  = 'require\s*\(\s*[''"](node:)?(https?|net|tls|dgram|dns)[''"]|from\s+[''"](node:)?(https?|net|tls)[''"]|\bnode-fetch\b|\baxios\b|\bXMLHttpRequest\b|\bWebSocket\b|\bfetch\s*\('
    'script: child process'   = 'child_process|\bexecSync\s*\(|\bspawnSync\s*\(|\bspawn\s*\(|\bexecFile\s*\('
    'script: destructive fs'  = 'fs\.(unlink|rm|rmdir)(Sync)?\s*\(|\brimraf\b|fs\.promises\.(unlink|rm|rmdir)'
    'script: secret access'   = '\.env\b|key\.properties|serviceAccount|process\.env\.[A-Za-z_]*(KEY|SECRET|TOKEN|PASSWORD|CREDENTIAL)'
    'script: dynamic eval'    = '\beval\s*\(|new\s+Function\s*\(|vm\.runIn'
}

# --- reusable checks --------------------------------------------------------

function Get-CommandBlockReason {
    param([string]$Command)

    foreach ($name in $blockedPatterns.Keys) {
        if ($Command -match $blockedPatterns[$name]) { return $name }
    }
    foreach ($segment in (Split-Segments $Command)) {
        if (-not (Test-QuotesBalanced $segment)) { continue }
        $token = Get-LeadingToken $segment
        if (-not $token) { continue }
        if ($blockedLeadingTokens -contains $token) { return "leading token: $token" }
    }
    return $null
}

function Get-ContentBlockReason {
    param([string]$Content)

    foreach ($name in $blockedScriptPatterns.Keys) {
        if ($Content -match $blockedScriptPatterns[$name]) { return $name }
    }
    foreach ($name in $blockedPatterns.Keys) {
        if ($name -eq 'secret file path') { continue }
        if ($name -eq 'guard tampering') { continue }
        if ($Content -match $blockedPatterns[$name]) { return "content -> $name" }
    }
    return $null
}

# --- script execution detection --------------------------------------------

function Get-ScriptTargets {
    param([string]$Command)

    $targets = @()

    foreach ($segment in (Split-Segments $Command)) {
        if (-not (Test-QuotesBalanced $segment)) { continue }
        $token = Get-LeadingToken $segment
        if (-not $token) { continue }
        $sargs = Get-SegmentArgs $segment

        if ($token -match '^(node|node\.exe|bun|deno|ts-node|tsx|python|python3|ruby|perl|php)$') {
            foreach ($a in $sargs) {
                if ($a -like '-*') { continue }
                $targets += [pscustomobject]@{ Kind = 'file'; Value = $a }
                break
            }
        }
        elseif ($token -match '^(powershell|powershell\.exe|pwsh|pwsh\.exe)$') {
            for ($i = 0; $i -lt $sargs.Count; $i++) {
                if ($sargs[$i] -match '^-(File|f)$' -and ($i + 1) -lt $sargs.Count) {
                    $targets += [pscustomobject]@{ Kind = 'file'; Value = $sargs[$i + 1] }
                }
            }
        }
        elseif ($token -eq 'dart') {
            foreach ($a in $sargs) {
                if ($a -like '-*') { continue }
                if ($a -like '*.dart') { $targets += [pscustomobject]@{ Kind = 'file'; Value = $a } }
                break
            }
        }
        elseif ($token -match '^(npm|pnpm|yarn)$') {
            if ($sargs.Count -ge 2 -and $sargs[0] -eq 'run') {
                $targets += [pscustomobject]@{ Kind = 'npm-script'; Value = $sargs[1] }
            }
            elseif ($token -eq 'yarn' -and $sargs.Count -ge 1 -and $sargs[0] -notlike '-*' -and
                    @('install','add','remove','why','list','info','outdated','upgrade','cache') -notcontains $sargs[0]) {
                $targets += [pscustomobject]@{ Kind = 'npm-script'; Value = $sargs[0] }
            }
        }
        elseif ($token -match '\.(ps1|js|mjs|cjs|cmd|bat)$') {
            $targets += [pscustomobject]@{ Kind = 'file'; Value = $token }
        }
    }

    return $targets
}

function Resolve-TargetPath {
    param([string]$Path, [string]$Root)

    $candidates = @()
    if ([System.IO.Path]::IsPathRooted($Path)) {
        $candidates += $Path
    } else {
        $candidates += (Join-Path $Root $Path)
        $candidates += (Join-Path (Join-Path $Root 'functions') $Path)
    }

    foreach ($c in $candidates) {
        try {
            if (Test-Path -LiteralPath $c -PathType Leaf) { return (Resolve-Path -LiteralPath $c).Path }
        } catch { }
    }
    return $null
}

function Test-GitClean {
    param([string]$FullPath, [string]$Root)

    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $null = & git -C $Root ls-files --error-unmatch -- "$FullPath" 2>$null
        if ($LASTEXITCODE -ne 0) { return 'not committed to git' }

        $status = & git -C $Root status --porcelain -- "$FullPath" 2>$null
        if ($LASTEXITCODE -ne 0) { return 'git status failed' }
        if ($status) { return 'has uncommitted changes' }

        return $null
    } catch {
        return ('git check failed: ' + $_.Exception.Message)
    } finally {
        $ErrorActionPreference = $prev
    }
}

function Read-Capped {
    param([string]$FullPath)
    try {
        $bytes = [System.IO.File]::ReadAllBytes($FullPath)
        $take  = [Math]::Min(262144, $bytes.Length)
        return [System.Text.Encoding]::UTF8.GetString($bytes, 0, $take)
    } catch {
        return $null
    }
}

# --- main -------------------------------------------------------------------

try {
    $raw = [Console]::In.ReadToEnd()

    if ([string]::IsNullOrWhiteSpace($raw)) {
        Write-GateLog 'PASS' 'empty payload'
        exit 0
    }

    $command    = $null
    $payloadCwd = $null
    try {
        $payload    = $raw | ConvertFrom-Json
        $command    = Find-StringProperty -Node $payload -Names @('command', 'cmd', 'commandLine', 'command_line')
        $payloadCwd = Find-StringProperty -Node $payload -Names @('cwd', 'workingDirectory', 'working_directory', 'workspaceRoot')
    } catch {
        Write-GateLog 'SCHEMA-ERROR' ('json parse failed: ' + $_.Exception.Message)
    }

    if (-not $command) {
        $snippet = $raw.Substring(0, [Math]::Min(600, $raw.Length))
        Write-GateLog 'SCHEMA-UNKNOWN' ('no command property; payload=' + $snippet)
        exit 0
    }

    $root = $WorkspaceRoot
    if ($payloadCwd) {
        try { if (Test-Path -LiteralPath $payloadCwd -PathType Container) { $root = $payloadCwd } } catch { }
    }

    # 1. command-level checks
    $reason = Get-CommandBlockReason -Command $command
    if ($reason) {
        Deny -Reason $reason -Command $command `
             -AgentMessage "Do not work around this. Use the delete_file tool for deletions, and report anything else to the user."
    }

    # 1b. comma outside parentheses -> would fall back to an approval prompt
    $commaAt = Find-CommaOutsideParens -Command $command
    if ($commaAt -ge 0) {
        $near = $command.Substring([Math]::Max(0, $commaAt - 20), [Math]::Min(40, $command.Length - [Math]::Max(0, $commaAt - 20)))
        Deny -Reason "comma in argument list at position $commaAt" -Command $command `
             -AgentMessage "Near: '$near'. The policy engine's PowerShell parser cannot handle comma-separated argument lists, so this would trigger an approval prompt. Rewrite without commas: pass one value per parameter, or build strings with '+' instead of property lists. Commas inside parentheses are fine."
    }

    # 1b-2. other constructs the policy engine's PowerShell parser cannot handle.
    # Each of these has been observed in the log as a tree-sitter parse error,
    # which makes the engine fall back to an approval prompt.
    $parserHostile = [ordered]@{
        'byte size suffix (1MB / 1GB)' = '\b\d+(KB|MB|GB|TB|PB)\b'
        'subexpression interpolation $( )' = '\$\('
    }
    foreach ($name in $parserHostile.Keys) {
        if ($command -match $parserHostile[$name]) {
            Deny -Reason "parser-hostile syntax: $name" -Command $command `
                 -AgentMessage "The policy engine's PowerShell parser fails on this and would trigger an approval prompt. Rewrite it plainly: compute values into variables first, divide by explicit numbers instead of 1MB/1GB, and build strings with '+' instead of `$( ) interpolation. Keep the command trivially simple."
        }
    }

    # 1c. file reading / code search must use the agent tools, not the shell
    if (-not (Test-LogDiagnosticExempt -Command $command)) {
        foreach ($segment in (Split-Segments $command)) {
            if (-not (Test-QuotesBalanced $segment)) { continue }
            $token = Get-LeadingToken $segment
            if (-not $token) { continue }
            if ($shellSearchTokens -contains $token) {
                Deny -Reason "shell used for file read/search ('$token')" -Command $command `
                     -AgentMessage "Use the tools instead: grep_search for content search, read_file to read a file, file_search to find paths, list_directory for structure. They bypass shell evaluation, so no approval prompt and no parse errors."
            }
        }
    }

    # 2. script execution: committed + clean in git, and contents must pass
    foreach ($t in (Get-ScriptTargets -Command $command)) {

        if ($t.Kind -eq 'npm-script') {
            $pkg = Resolve-TargetPath -Path 'package.json' -Root $root
            if (-not $pkg) {
                Deny -Reason "npm script '$($t.Value)': package.json not found" -Command $command `
                     -AgentMessage "Script execution fails closed. Tell the user what you wanted to run."
            }
            $pkgText = Read-Capped $pkg
            if (-not $pkgText) {
                Deny -Reason "npm script '$($t.Value)': package.json unreadable" -Command $command `
                     -AgentMessage "Script execution fails closed. Report this to the user."
            }
            $gitReason = Test-GitClean -FullPath $pkg -Root $root
            if ($gitReason) {
                Deny -Reason "npm script '$($t.Value)': package.json $gitReason" -Command $command `
                     -AgentMessage "Scripts must be reviewed and committed before they run. Show the user the diff and ask them to commit."
            }

            $pkgJson = $null
            try { $pkgJson = $pkgText | ConvertFrom-Json } catch { }
            $scriptBody = $null
            if ($pkgJson -and $pkgJson.scripts -and ($pkgJson.scripts.PSObject.Properties.Name -contains $t.Value)) {
                $scriptBody = [string]$pkgJson.scripts.($t.Value)
            }
            if (-not $scriptBody) {
                Deny -Reason "npm script '$($t.Value)' not found in package.json" -Command $command `
                     -AgentMessage "Script execution fails closed. Report this to the user."
            }

            $r = Get-CommandBlockReason -Command $scriptBody
            if ($r) {
                Deny -Reason "npm script '$($t.Value)' -> $r" -Command $scriptBody `
                     -AgentMessage "The package.json script itself is not allowed. Report it to the user."
            }
            continue
        }

        $targetPath = Resolve-TargetPath -Path $t.Value -Root $root
        if (-not $targetPath) {
            Deny -Reason "script target not resolvable: $($t.Value)" -Command $command `
                 -AgentMessage "Script execution fails closed when the file cannot be located. Report this to the user."
        }

        $gitReason = Test-GitClean -FullPath $targetPath -Root $root
        if ($gitReason) {
            Deny -Reason "script $($t.Value): $gitReason" -Command $command `
                 -AgentMessage "Scripts must be committed and unmodified before they run. Show the user the file or diff and ask them to review and commit it."
        }

        $content = Read-Capped $targetPath
        if ($null -eq $content) {
            Deny -Reason "script $($t.Value): unreadable" -Command $command `
                 -AgentMessage "Script execution fails closed. Report this to the user."
        }

        $r = Get-ContentBlockReason -Content $content
        if ($r) {
            Deny -Reason "script $($t.Value) -> $r" -Command $command `
                 -AgentMessage "The script contents are not allowed. Do not edit the script to get past this. Report what the script does and let the user decide."
        }
    }

    Write-GateLog 'PASS' $command.Substring(0, [Math]::Min(300, $command.Length))
    exit 0

} catch {
    Write-GateLog 'GATE-ERROR' $_.Exception.Message
    exit 0
}
