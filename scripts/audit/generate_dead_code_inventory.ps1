Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$outDir = Join-Path $repo 'docs\dead_code_cleanup'
$outCsv = Join-Path $outDir 'full_file_inventory.csv'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

function Normalize-RepoPath([string] $path) {
    return ($path -replace '\\', '/')
}

function Get-Classification([string] $path) {
    $p = Normalize-RepoPath $path
    if ($p -match '(^|/)(tmp|\.tmp|build|\.dart_tool|node_modules|Pods|\.gradle)(/|$)' -or
        $p -match '(^|/)(dist|coverage)(/|$)' -or
        $p -match '\.(unlinked2|linked|digest|dill|pdb|lock)$') {
        return 'GENERATED_OR_ARTIFACT'
    }
    if ($p -match '(^|/)(test|tests|rules_tests)(/|$)' -or
        $p -match '(^|/)(functions/)?(__tests__|test)(/|$)' -or
        $p -match '(_test|\.test)\.(dart|ts|js)$') {
        return 'TEST'
    }
    if ($p -match '(^|/)(scripts|infra|tools|recsys|migrations)(/|$)' -or
        $p -match '(^|/)(firebase\.json|firestore\.rules|storage\.rules|.*\.ya?ml)$' -or
        $p -match '(^|/)(\.github|\.firebaserc)(/|$)') {
        return 'OPERATIONAL_OR_PIPELINE'
    }
    if ($p -match '(^|/)docs?(/|$)' -or $p -match '\.(md|mdx|drawio|html)$') {
        return 'DOCUMENTATION'
    }
    if ($p -match '^(lib|web|android|ios|macos|windows|linux|functions/src|assets)(/|$)') {
        return 'RUNTIME_OR_PLATFORM'
    }
    return 'UNCERTAIN_OR_SEPARATE_PROJECT'
}

$workflowRefs = @(
    'lib/features/chat/screens/chat_room_screen.dart',
    'lib/features/chat/screens/group_match_screen.dart',
    'lib/features/chat/screens/premium_chat_list_screen.dart',
    'lib/features/community/screens/community_screen.dart',
    'lib/features/community/screens/post_detail_screen.dart',
    'lib/features/community/screens/post_write_screen.dart',
    'lib/features/event/screens/event_screen.dart',
    'lib/features/event/screens/match_result_screen.dart',
    'lib/features/event/screens/random_mathcing_screen.dart',
    'lib/features/event/screens/season_meeting_roulette_screen.dart',
    'lib/features/event/screens/team_setup_screen.dart',
    'lib/features/event/screens/three_vs_three_match_screen.dart',
    'lib/features/matching/screens/ai_match_card_screen.dart',
    'lib/features/matching/screens/ai_preference_screen.dart',
    'lib/features/matching/screens/mystery_card_screen.dart',
    'lib/features/matching/screens/profile_discovery_screen.dart',
    'lib/features/matching/screens/profile_specific_detail_screen.dart',
    'lib/features/profile/screens/friends_list_screen.dart',
    'lib/features/profile/screens/heart_charge_screen.dart',
    'lib/features/profile/screens/my_page_screen.dart',
    'lib/features/profile/screens/profile_edit_screen.dart',
    'lib/features/profile/screens/received_hearts_screen.dart',
    'lib/features/profile/screens/settings_screen.dart',
    'lib/features/onboarding/screens/basic_info_screen.dart',
    'lib/features/onboarding/screens/height_selection_screen.dart',
    'lib/features/onboarding/screens/ideal_height_range_screen.dart',
    'lib/features/onboarding/screens/ideal_type/ideal_age_screen.dart',
    'lib/features/onboarding/screens/ideal_type/ideal_department_screen.dart',
    'lib/features/onboarding/screens/ideal_type/ideal_lifestyle_screen.dart',
    'lib/features/onboarding/screens/ideal_type/ideal_personality_screen.dart',
    'lib/features/onboarding/screens/ideal_type/ideal_type_screen.dart',
    'lib/features/onboarding/screens/interests_selection_screen.dart',
    'lib/features/onboarding/screens/keyword_screen.dart',
    'lib/features/onboarding/screens/lifestyle_screen.dart',
    'lib/features/onboarding/screens/major_selection_screen.dart',
    'lib/features/onboarding/screens/photo_upload_screen.dart',
    'lib/features/onboarding/screens/profile_qa_screen.dart',
    'lib/features/onboarding/screens/self_introduction_screen.dart',
    'lib/features/onboarding/screens/terms_detail_sheet.dart',
    'lib/features/onboarding/screens/terms_screen.dart',
    'lib/features/tutorial/screens/ai_taste_button_tutorial_screen.dart',
    'lib/features/tutorial/screens/ai_taste_training_screen.dart',
    'lib/features/tutorial/screens/ai_taste_training_tutorial_screen.dart',
    'lib/features/tutorial/screens/bamboo_forest_intro_tutorial_screen.dart',
    'lib/features/tutorial/screens/bamboo_forest_safety_tutorial_screen.dart',
    'lib/features/tutorial/screens/bamboo_forest_write_tutorial_screen.dart',
    'lib/features/tutorial/screens/promise_agreement_tutorial_screen.dart',
    'lib/features/tutorial/screens/season_meeting_intro_screen.dart',
    'lib/features/tutorial/screens/slot_machine_tutorial_screen.dart',
    'lib/features/tutorial/screens/todays_match_tutorial_screen.dart',
    'lib/features/tutorial/screens/tutorial_screen.dart',
    'lib/features/tutorial/screens/welcome_tutorial_screen.dart'
)
$staleWorkflowRefs = @(
    'lib/features/event/screens/random_matching_screen.dart',
    'lib/features/event/screens/random_meeting_screen.dart',
    'lib/features/meeting/screens/meeting_application_screen.dart',
    'lib/features/matching/screens/ai_preference.dart'
)
$workflowSet = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
$workflowRefs | ForEach-Object { [void]$workflowSet.Add((Normalize-RepoPath $_)) }
$staleSet = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
$staleWorkflowRefs | ForEach-Object { [void]$staleSet.Add((Normalize-RepoPath $_)) }

$tracked = @(git -C $repo -c core.quotePath=false ls-files --)
$historyLines = @(git -C $repo -c core.quotePath=false log --all --name-only --format= -- . 2>$null)
$historySet = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach ($line in $historyLines) {
    $normalized = Normalize-RepoPath $line.Trim()
    if ($normalized) { [void]$historySet.Add($normalized) }
}

$rows = foreach ($rawPath in $tracked) {
    $path = Normalize-RepoPath $rawPath
    $classification = Get-Classification $path
    $exists = $false
    $size = $null
    try {
        $item = Get-Item -LiteralPath (Join-Path $repo ($path -replace '/', '\\')) -Force -ErrorAction Stop
        $exists = $true
        if (-not $item.PSIsContainer) { $size = [int64]$item.Length }
    } catch {
        $exists = $false
    }

    $workflowRelation = 'not-in-workflow-export'
    if ($workflowSet.Contains($path)) { $workflowRelation = 'explicitly-listed-current-path' }
    elseif ($staleSet.Contains($path)) { $workflowRelation = 'stale-workflow-reference' }

    $runtimeProtection = 'review-required'
    $referenceStatus = 'not-proven-dead'
    $notes = ''
    if ($workflowRelation -eq 'explicitly-listed-current-path') {
        $runtimeProtection = 'protected-by-workflow'
        $referenceStatus = 'protected; do-not-delete'
    } elseif ($classification -eq 'GENERATED_OR_ARTIFACT') {
        $runtimeProtection = 'owner-and-consumer-audit-required'
        $referenceStatus = 'artifact classification only; not deletion proof'
    } elseif ($classification -eq 'UNCERTAIN_OR_SEPARATE_PROJECT') {
        $runtimeProtection = 'separate-project-or-owner-review-required'
        $notes = 'Uncertain ownership or prototype/subproject path; preserve.'
    } elseif ($path -match '^(functions/|firebase\.json|.*\.rules$|infra/|scripts/|assets/)') {
        $runtimeProtection = 'operational-or-runtime-protected'
    }
    if ($path -like 'festival_web/*') { $notes = 'Separate first-party-looking Flutter/web project; preserve pending owner audit.' }
    if ($path -like 'tmp/*' -or $path -like '.tmp/*') { $notes = 'Operational/test/report artifact area; denied or dynamic consumers are possible.' }
    if ($workflowRelation -eq 'stale-workflow-reference') { $notes = 'Diagram path is absent in current tree; see workflow replacement map.' }

    [pscustomobject]@{
        Path = $path
        Tracked = $true
        WorktreeExists = $exists
        SizeBytes = $size
        TopLevel = (($path -split '/')[0])
        Extension = [IO.Path]::GetExtension($path)
        Classification = $classification
        WorkflowRelation = $workflowRelation
        RuntimeProtection = $runtimeProtection
        ReferenceAuditStatus = $referenceStatus
        GitHistoryStatus = $(if ($historySet.Contains($path)) { 'history-present' } else { 'no-history-found-in-all-refs' })
        Notes = $notes
    }
}
$rows | Sort-Object Path | Export-Csv -LiteralPath $outCsv -NoTypeInformation -Encoding utf8
Write-Output ("Inventory written: {0} ({1} rows)" -f $outCsv, $rows.Count)
$rows | Group-Object Classification | Sort-Object Name | ForEach-Object {
    Write-Output ("{0}: {1}" -f $_.Name, $_.Count)
}
