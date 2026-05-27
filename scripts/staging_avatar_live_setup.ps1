param(
  [string]$Project = "seolleyeon-final",
  [string]$Region = "asia-northeast3",
  [string]$WorkerRegion = "asia-southeast1",
  [string]$Repository = "seolleyeon-repo",
  [string]$Tag = "staging-avatar-worker",
  [string]$ExpectedAccount = "seolleyeon.official@gmail.com",
  [string]$FunctionsEnvFile = "functions/.env.seolleyeon-final",
  [switch]$PrepareOnly,
  [switch]$UpdateFunctionsEnv,
  [switch]$DeployUploadFunction,
  [switch]$EnableClipWorker,
  [switch]$Apply
)

$ErrorActionPreference = "Stop"
if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
  $PSNativeCommandUseErrorActionPreference = $false
}

function Invoke-Step {
  param(
    [string]$Description,
    [scriptblock]$Command
  )

  Write-Host ""
  Write-Host "## $Description"
  if ($Apply) {
    & $Command
    if ($LASTEXITCODE -ne 0) {
      throw "Step failed with exit code ${LASTEXITCODE}: $Description"
    }
  } else {
    Write-Host "[DRY RUN] $Command"
  }
}

function Assert-Guard {
  $account = (& gcloud config get-value account 2>$null).Trim()
  $activeProject = (& gcloud config get-value project 2>$null).Trim()
  if ($account -ne $ExpectedAccount) {
    throw "gcloud account mismatch: expected $ExpectedAccount, got $account"
  }
  if ($activeProject -ne $Project) {
    throw "gcloud project mismatch: expected $Project, got $activeProject"
  }
}

function Test-GcloudExists {
  $gcloudCmd = Get-Command gcloud.cmd -ErrorAction SilentlyContinue
  if ($gcloudCmd) {
    Set-Alias -Name gcloud -Value $gcloudCmd.Source -Scope Script
    return
  }

  if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    throw "gcloud was not found in PATH."
  }
}

function Test-Gcloud {
  param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)

  $previousErrorActionPreference = $ErrorActionPreference
  $ErrorActionPreference = "SilentlyContinue"
  try {
    & gcloud @Arguments *> $null
    return $LASTEXITCODE -eq 0
  } finally {
    $ErrorActionPreference = $previousErrorActionPreference
  }
}

function Assert-PreApplyPrerequisites {
  if (-not $Apply) {
    return
  }

  if ($PrepareOnly -and ($UpdateFunctionsEnv -or $DeployUploadFunction)) {
    throw "-PrepareOnly cannot be combined with -UpdateFunctionsEnv or -DeployUploadFunction."
  }

  if (-not (Test-Path "cloudbuild.avatar-worker.yaml")) {
    throw "cloudbuild.avatar-worker.yaml was not found."
  }

  if (-not (Test-Gcloud artifacts repositories describe $Repository --location=$Region --project=$Project)) {
    throw "Artifact Registry repository '$Repository' is missing in $Region."
  }

  $requiredBuckets = @(
    "seolleyeon-final-private-source-photos",
    "seolleyeon-final-avatar-temp",
    "seolleyeon-final-approved-avatars"
  )
  foreach ($bucket in $requiredBuckets) {
    if (-not (Test-Gcloud storage buckets describe "gs://$bucket" --project=$Project)) {
      throw "Required bucket gs://$bucket is missing."
    }
  }
}

function Ensure-ServiceAccount {
  param([string]$Name, [string]$DisplayName)
  $email = "$Name@$Project.iam.gserviceaccount.com"
  if (-not (Test-Gcloud iam service-accounts describe $email --project=$Project)) {
    & gcloud iam service-accounts create $Name --project=$Project --display-name=$DisplayName
  }
}

function Ensure-Queue {
  param([string]$Name)
  if (-not (Test-Gcloud tasks queues describe $Name --location=$Region --project=$Project)) {
    & gcloud tasks queues create $Name `
      --location=$Region `
      --project=$Project `
      --max-dispatches-per-second=1 `
      --max-concurrent-dispatches=1 `
      --max-attempts=3 `
      --min-backoff=30s `
      --max-backoff=600s `
      --max-doublings=5
  }
}

function Set-EnvFileValues {
  param(
    [string]$Path,
    [hashtable]$Values
  )

  $orderedKeys = @()
  $map = [ordered]@{}
  if (Test-Path $Path) {
    foreach ($line in Get-Content -Path $Path) {
      if ($line.Trim().Length -eq 0 -or $line.TrimStart().StartsWith("#") -or -not $line.Contains("=")) {
        $orderedKeys += $line
        continue
      }
      $key = $line.Split("=", 2)[0].Trim()
      $orderedKeys += $key
      $map[$key] = $line
    }
  }

  foreach ($key in $Values.Keys) {
    $map[$key] = "$key=$($Values[$key])"
    if ($orderedKeys -notcontains $key) {
      $orderedKeys += $key
    }
  }

  $output = foreach ($key in $orderedKeys) {
    if ($map.Contains($key)) {
      $map[$key]
    } else {
      $key
    }
  }
  $utf8NoBom = [System.Text.UTF8Encoding]::new($false)
  $fullPath = [System.IO.Path]::GetFullPath($Path)
  $parent = [System.IO.Path]::GetDirectoryName($fullPath)
  if ($parent -and -not (Test-Path $parent)) {
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
  }
  [System.IO.File]::WriteAllLines($fullPath, [string[]]$output, $utf8NoBom)
}

Test-GcloudExists
Assert-Guard

$image = "$Region-docker.pkg.dev/$Project/$Repository/seolleyeon-avatar-worker:$Tag"
$avatarWorkerSa = "avatar-worker@$Project.iam.gserviceaccount.com"
$clipWorkerSa = "clip-worker@$Project.iam.gserviceaccount.com"
$taskInvokerSa = "task-invoker@$Project.iam.gserviceaccount.com"
$projectNumber = (& gcloud projects describe $Project --format="value(projectNumber)").Trim()
$cloudTasksServiceAgent = "service-$projectNumber@gcp-sa-cloudtasks.iam.gserviceaccount.com"
$functionsRuntimeSa = (& gcloud functions describe uploadAvatarSourcePhoto `
  --gen2 `
  --region=$Region `
  --project=$Project `
  --format="value(serviceConfig.serviceAccountEmail)" 2>$null).Trim()
if (-not $functionsRuntimeSa) {
  $functionsRuntimeSa = "$Project@appspot.gserviceaccount.com"
}

Write-Host "Project: $Project"
Write-Host "Region : $Region"
Write-Host "Worker : $WorkerRegion"
Write-Host "Image  : $image"
Write-Host "Fn SA  : $functionsRuntimeSa"
Write-Host "Env    : $FunctionsEnvFile"
Write-Host "Apply  : $Apply"
Write-Host "Prepare: $PrepareOnly"

Invoke-Step "Enable required APIs" {
  gcloud services enable `
    compute.googleapis.com `
    run.googleapis.com `
    cloudtasks.googleapis.com `
    cloudbuild.googleapis.com `
    artifactregistry.googleapis.com `
    iamcredentials.googleapis.com `
    secretmanager.googleapis.com `
    --project=$Project `
    --quiet
}

Assert-PreApplyPrerequisites

Invoke-Step "Create service accounts" {
  Ensure-ServiceAccount -Name "avatar-worker" -DisplayName "Seolleyeon Avatar Worker"
  if ($EnableClipWorker) {
    Ensure-ServiceAccount -Name "clip-worker" -DisplayName "Seolleyeon CLIP Worker"
  }
  Ensure-ServiceAccount -Name "task-invoker" -DisplayName "Seolleyeon Cloud Tasks Invoker"
}

Invoke-Step "Create Cloud Tasks queues" {
  Ensure-Queue -Name "avatar-generation"
  if ($EnableClipWorker) {
    Ensure-Queue -Name "clip-embedding"
  }
}

Invoke-Step "Build and push avatar worker image with Cloud Build" {
  gcloud builds submit . `
    --project=$Project `
    --config=cloudbuild.avatar-worker.yaml `
    --substitutions="_IMAGE=$image"
}

Invoke-Step "Grant pre-deploy IAM for avatar worker and task invoker" {
  gcloud projects add-iam-policy-binding $Project `
    --member="serviceAccount:$avatarWorkerSa" `
    --role="roles/datastore.user" `
    --quiet

  if ($EnableClipWorker) {
    gcloud projects add-iam-policy-binding $Project `
      --member="serviceAccount:$clipWorkerSa" `
      --role="roles/datastore.user" `
      --quiet
  }

  gcloud projects add-iam-policy-binding $Project `
    --member="serviceAccount:$functionsRuntimeSa" `
    --role="roles/cloudtasks.enqueuer" `
    --quiet

  gcloud storage buckets add-iam-policy-binding "gs://seolleyeon-final-private-source-photos" `
    --member="serviceAccount:$avatarWorkerSa" `
    --role="roles/storage.objectViewer" `
    --quiet

  if ($EnableClipWorker) {
    gcloud storage buckets add-iam-policy-binding "gs://seolleyeon-final-private-source-photos" `
      --member="serviceAccount:$clipWorkerSa" `
      --role="roles/storage.objectViewer" `
      --quiet
  }

  gcloud storage buckets add-iam-policy-binding "gs://seolleyeon-final-avatar-temp" `
    --member="serviceAccount:$avatarWorkerSa" `
    --role="roles/storage.objectAdmin" `
    --quiet

  gcloud iam service-accounts add-iam-policy-binding $taskInvokerSa `
    --project=$Project `
    --member="serviceAccount:$cloudTasksServiceAgent" `
    --role="roles/iam.serviceAccountTokenCreator" `
    --quiet

  gcloud iam service-accounts add-iam-policy-binding $taskInvokerSa `
    --project=$Project `
    --member="serviceAccount:$functionsRuntimeSa" `
    --role="roles/iam.serviceAccountUser" `
    --quiet
}

if (-not $PrepareOnly) {
  Invoke-Step "Deploy Cloud Run GPU avatar worker" {
    $workerEnv = @(
      "ENVIRONMENT=staging"
      "AVATAR_WORKER_MODE=flux"
      "AVATAR_WORKER_AUTH_MODE=cloud_run_iam"
      "AVATAR_WORKER_CLOUD_RUN_IAM_ENFORCED=true"
      "AVATAR_GPU_WORKER_ENABLED=true"
      "AVATAR_BATCHING_ENABLED=true"
      "AVATAR_BATCH_MODE=drain"
      "AVATAR_BATCH_CONCURRENCY_PER_GPU=1"
      "AVATAR_BATCH_MAX_JOBS=1"
      "AVATAR_WORKER_DEADLINE_SECONDS=1800"
      "AVATAR_WORKER_MAX_REQUEST_SECONDS=1800"
      "AVATAR_WORKER_MAX_JOB_SECONDS=1500"
      "AVATAR_WORKER_SOFT_STOP_MARGIN_SECONDS=30"
      "AVATAR_BATCH_MAX_SECONDS=1800"
      "AVATAR_BATCH_MAX_IDLE_WAIT_SECONDS=15"
      "AVATAR_DISABLE_NEW_GENERATION=false"
      "AVATAR_WORKER_DRY_RUN=false"
      "SOURCE_PHOTO_BUCKET=seolleyeon-final-private-source-photos"
      "AVATAR_TEMP_BUCKET=seolleyeon-final-avatar-temp"
      "MAX_CANDIDATES=4"
      "AVATAR_CANDIDATE_TTL_HOURS=72"
      "AVATAR_GENERATION_WIDTH=1024"
      "AVATAR_GENERATION_HEIGHT=1024"
      "AVATAR_GENERATION_STEPS=4"
      "AVATAR_GENERATION_GUIDANCE_SCALE=1.0"
      "AVATAR_FLUX_NUM_INFERENCE_STEPS=4"
      "AVATAR_FLUX_GUIDANCE_SCALE=1.0"
      "AVATAR_FACE_DETECTOR_ENABLED=true"
      "AVATAR_FACE_DETECTOR_PROVIDER=mediapipe"
      "AVATAR_MEDIAPIPE_ENABLED=true"
      "AVATAR_MEDIAPIPE_FACE_LANDMARKER_MODEL_PATH=/app/models/face_landmarker.task"
      "AVATAR_MEDIAPIPE_OUTPUT_BLENDSHAPES=true"
      "AVATAR_MEDIAPIPE_NUM_FACES=2"
      "AVATAR_MEDIAPIPE_MIN_DETECTION_CONFIDENCE=0.6"
      "AVATAR_MEDIAPIPE_MIN_PRESENCE_CONFIDENCE=0.6"
      "AVATAR_FACE_DETECTOR_MIN_CONFIDENCE=0.6"
      "AVATAR_FACE_MIN_RELATIVE_SIZE=0.08"
      "AVATAR_TRAIT_EXTRACTION_ENABLED=true"
      "AVATAR_TRAIT_MODEL_ID=microsoft/Florence-2-large-ft"
      "AVATAR_TRAIT_MAX_IMAGE_EDGE=768"
      "AVATAR_TRAIT_LOCAL_FILES_ONLY=false"
      "AVATAR_TRAIT_ATTENTION_IMPLEMENTATION=eager"
      "AVATAR_TRAIT_FLORENCE_TASK_PROMPT=MORE_DETAILED_CAPTION"
      "AVATAR_TRAIT_DRY_RUN=false"
      "AVATAR_TRAIT_REQUIRE_VALIDATED=true"
      "AVATAR_TRAIT_QWEN_FALLBACK_ENABLED=false"
      "AVATAR_TRAIT_USE_PRIVACY_REFERENCE=false"
      "AVATAR_CANDIDATE_TRAIT_QA_ENABLED=true"
      "AVATAR_REFERENCE_PRIVACY_PREPROCESS=true"
      "AVATAR_REFERENCE_PREPROCESS_MODE=region_aware_v1"
      "AVATAR_REFERENCE_FACE_EQUIVALENT_SIZE=64"
      "AVATAR_REFERENCE_FACE_BLUR_RADIUS=2.0"
      "AVATAR_REFERENCE_NONFACE_EQUIVALENT_SIZE=96"
      "AVATAR_REFERENCE_NONFACE_BLUR_RADIUS=1.5"
      "AVATAR_BACKGROUND_NEUTRALIZATION_ENABLED=true"
      "AVATAR_BACKGROUND_NEUTRAL_COLOR=#F7F2EC"
      "AVATAR_SECONDARY_FACE_BLUR_RADIUS=12"
      "AVATAR_BACKGROUND_BLUR_RADIUS=10"
      "AVATAR_BACKGROUND_DESATURATE=true"
      "AVATAR_ALLOW_SMALL_BACKGROUND_FACES_IF_REMOVED=true"
      "AVATAR_REJECT_LARGE_SECONDARY_FACE=true"
      "AVATAR_PRIMARY_FACE_MIN_SCORE_MARGIN=0.20"
      "AVATAR_PRIMARY_FACE_MIN_RELATIVE_AREA=0.04"
      "AVATAR_BACKGROUND_TEXT_LOGO_BLUR=true"
      "AVATAR_SAM_ENABLED=false"
      "AVATAR_SAM_LOAD_ON_DEMAND=true"
      "AVATAR_INITIAL_CANDIDATE_COUNT=4"
      "AVATAR_EXTRA_CANDIDATE_COUNT=4"
      "AVATAR_MIN_SAFE_CANDIDATES_BEFORE_EXTRA=2"
      "AVATAR_MAX_TOTAL_CANDIDATES=8"
      "AVATAR_PREVIEW_COUNT=4"
      "AVATAR_MIN_PREVIEW_CANDIDATES=1"
      "AVATAR_PREVIEW_REQUIRE_FOUR=false"
      "AVATAR_PREVIEW_FILL_WITH_SOFT_PASS=true"
      "AVATAR_PREVIEW_FILL_HARD_REJECT=false"
      "AVATAR_RERANK_PROVIDER=deterministic_qa_tier"
      "AVATAR_CLIP_MODEL_ID=openai/clip-vit-large-patch14"
      "AVATAR_DINO_MODEL_ID=facebook/dinov2-base"
      "AVATAR_QA_ALLOW_STAGING_HEURISTIC_PREVIEW=true"
      "AVATAR_QA_ALLOW_PHASH_HARD_REJECT_ONLY_NEAR_DUPLICATE=true"
      "AVATAR_QA_REQUIRE_RELIABLE_FACE_SIM_FOR_TOO_IDENTIFIABLE=true"
      "AVATAR_QA_PHASH_NEAR_DUPLICATE_REJECT_THRESHOLD=0.985"
      "AVATAR_QA_PHASH_REVIEW_THRESHOLD=0.92"
      "AVATAR_QA_FACE_SIMILARITY_REVIEW_THRESHOLD=0.68"
      "AVATAR_QA_FACE_SIMILARITY_REJECT_THRESHOLD=0.72"
      "CLOUD_RUN_VCPU=8"
      "CLOUD_RUN_MEMORY_GIB=32"
      "AVATAR_COST_ALERT_DAILY_USD=10"
      "AVATAR_COST_ALERT_MONTHLY_USD=200"
      "AVATAR_COST_HARD_DAILY_GENERATION_LIMIT=500"
      "AVATAR_COST_HARD_MONTHLY_GENERATION_LIMIT=10000"
      "AVATAR_COST_ENFORCE_BUDGET=true"
      "AVATAR_COST_KILL_SWITCH_ENABLED=false"
    ) -join ","

    gcloud run deploy seolleyeon-avatar-worker `
      --image=$image `
      --region=$WorkerRegion `
      --project=$Project `
      --gpu=1 `
      --gpu-type=nvidia-l4 `
      --no-gpu-zonal-redundancy `
      --cpu=8 `
      --memory=32Gi `
      --concurrency=1 `
      --min-instances=0 `
      --max-instances=1 `
      --timeout=1800s `
      --no-allow-unauthenticated `
      --service-account=$avatarWorkerSa `
      --set-env-vars=$workerEnv
  }

  Invoke-Step "Grant post-deploy IAM for avatar worker and task invoker" {
    gcloud run services add-iam-policy-binding seolleyeon-avatar-worker `
      --region=$WorkerRegion `
      --project=$Project `
      --member="serviceAccount:$taskInvokerSa" `
      --role="roles/run.invoker" `
      --quiet

  }
}

$workerUrl = "<seolleyeon-avatar-worker-url>"
if ($Apply -and -not $PrepareOnly) {
  $describedUrl = (& gcloud run services describe seolleyeon-avatar-worker `
    --region=$WorkerRegion `
    --project=$Project `
    --format="value(status.url)" 2>$null).Trim()
  if ($describedUrl) {
    $workerUrl = $describedUrl
  }
}

if ($UpdateFunctionsEnv) {
  Invoke-Step "Update local Functions env file with non-secret avatar queue settings" {
    if ($workerUrl -like "<*") {
      throw "Worker URL is unavailable; deploy seolleyeon-avatar-worker before updating env."
    }
    Set-EnvFileValues -Path $FunctionsEnvFile -Values @{
      "JOB_QUEUE_MODE" = "cloud_tasks"
      "CLOUD_TASKS_PROJECT" = $Project
      "GCP_LOCATION" = $Region
      "AVATAR_GENERATION_QUEUE_NAME" = "avatar-generation"
      "AVATAR_GENERATION_TASK_URL" = "$workerUrl/tasks/avatar-generation"
      "TASK_INVOKER_SERVICE_ACCOUNT" = $taskInvokerSa
      "AVATAR_QUEUE_DISPATCH_DEADLINE_SECONDS" = "1800"
      "AVATAR_QUEUE_MAX_DISPATCHES_PER_SECOND" = "1"
      "AVATAR_QUEUE_MAX_CONCURRENT_DISPATCHES" = "1"
      "AVATAR_QUEUE_MAX_ATTEMPTS" = "3"
      "AVATAR_QUEUE_MIN_BACKOFF_SECONDS" = "30"
      "AVATAR_QUEUE_MAX_BACKOFF_SECONDS" = "600"
      "AVATAR_QUEUE_MAX_DOUBLINGS" = "5"
      "AVATAR_QUEUE_GPU_MAX_CONCURRENT_JOBS" = "1"
      "CLIP_EMBEDDING_QUEUE_ENABLED" = "false"
    }
  }
}

if ($DeployUploadFunction) {
  Invoke-Step "Redeploy uploadAvatarSourcePhoto with current Functions env" {
    firebase deploy --only functions:uploadAvatarSourcePhoto --project $Project --non-interactive
  }
}

Write-Host ""
if ($PrepareOnly) {
  Write-Host "PrepareOnly completed/planned. Worker deploy is skipped."
  Write-Host "Prepare check: .venv\Scripts\python.exe scripts\staging_avatar_live_preflight.py --avatar_only --stage prepare"
}
Write-Host ""
Write-Host "Next manual env values after Cloud Run deploy:"
Write-Host "JOB_QUEUE_MODE=cloud_tasks"
Write-Host "CLOUD_TASKS_PROJECT=$Project"
Write-Host "GCP_LOCATION=$Region"
Write-Host "AVATAR_GENERATION_QUEUE_NAME=avatar-generation"
Write-Host "AVATAR_GENERATION_TASK_URL=$workerUrl/tasks/avatar-generation"
Write-Host "TASK_INVOKER_SERVICE_ACCOUNT=$taskInvokerSa"
Write-Host "CLIP_EMBEDDING_QUEUE_ENABLED=false"
Write-Host ""
Write-Host "Optional after Apply:"
Write-Host "  Add -PrepareOnly to prepare APIs, service accounts, queue, image, and pre-deploy IAM without deploying Cloud Run."
  Write-Host "  Before worker deploy, check: .venv\Scripts\python.exe scripts\staging_avatar_live_preflight.py --avatar_only --stage deploy"
Write-Host "  Add -UpdateFunctionsEnv to write the non-secret queue env locally."
Write-Host "  Validate local queue env: .venv\Scripts\python.exe scripts\avatar_queue_config_check.py --env_file $FunctionsEnvFile"
Write-Host "  Add -DeployUploadFunction to redeploy uploadAvatarSourcePhoto."
Write-Host "  Add -EnableClipWorker only after CLIP embedding/rerank is enabled and verified."
Write-Host "  Existing queued dry-run jobs can be recovered by duplicate upload retry or an IAM-protected worker drain call after deploy."
Write-Host "  Drain dry-run: .venv\Scripts\python.exe scripts\avatar_worker_drain_once.py --worker_url $workerUrl"
Write-Host "  Drain apply : .venv\Scripts\python.exe scripts\avatar_worker_drain_once.py --worker_url $workerUrl --apply --use_gcloud_token --gcloud_token_without_audience"
Write-Host "  Verify with: .venv\Scripts\python.exe scripts\staging_avatar_live_verify.py --output_report_json out\avatar_live_verify.json"
Write-Host "  After app upload, verify job evidence: .venv\Scripts\python.exe scripts\staging_avatar_live_verify.py --uid <kakao_uid> --require_preview_ready --output_report_json out\avatar_live_verify.json"
