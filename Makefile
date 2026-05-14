export CODEX_GENERATED_IMAGES_DIR ?= $(HOME)/.codex/generated_images

.PHONY: ai-image-dry-run ai-image-prepare-smoke ai-image-prepare-pilot ai-image-prepare-720 ai-image-next ai-image-next-distribution-chunk ai-image-recover ai-image-qa ai-image-file-qa ai-image-retry ai-image-summary ai-image-contact-sheets ai-image-visual-asset-qa-instructions ai-image-visual-identity-qa-instructions ai-image-visual-distribution-audit-instructions ai-image-apply-visual-asset-qa ai-image-apply-visual-identity-qa ai-image-apply-visual-distribution-audit ai-image-distribution-audit ai-image-completion-check ai-image-bounded-chunk-plan ai-image-bounded-chunk-run ai-image-bounded-chunk-resume ai-image-bounded-chunk-status ai-image-bounded-chunk-qa ai-image-bounded-chunk-finalize ai-image-autopilot-chunks-720 ai-image-supervisor-720 ai-image-supervisor-chunk-only ai-image-supervisor-identity-only ai-image-supervisor-asset-only

ai-image-dry-run:
	python scripts/prepare_ai_image_assets_v3.py --root . --female_count 1 --male_count 0 --reserve_female_count 0 --reserve_male_count 0 --limit 3 --dry_run --replace_manifest --force

ai-image-prepare-smoke:
	python scripts/prepare_ai_image_assets_v3.py --root . --female_count 2 --male_count 1 --reserve_female_count 0 --reserve_male_count 0 --limit 9 --replace_manifest

ai-image-prepare-pilot:
	python scripts/prepare_ai_image_assets_v3.py --root . --female_count 12 --male_count 12 --reserve_female_count 0 --reserve_male_count 0 --limit 72 --replace_manifest

ai-image-prepare-720:
	python scripts/run_ai_image_pipeline_v3.py prepare-720 --root .

ai-image-next:
	python scripts/next_codex_imagegen_prompt_v3.py --root .

ai-image-next-distribution-chunk:
	python scripts/next_distribution_aware_imagegen_chunk_v3.py \
	  --root . \
	  --chunk_identities 24

ai-image-recover:
	python scripts/recover_pending_imagegen_v3.py \
	  --pending ai_image/manifests/pending-imagegen.json \
	  --generated_root "$$CODEX_GENERATED_IMAGES_DIR" \
	  --out_dir ai_image

ai-image-file-qa:
	python scripts/run_ai_image_pipeline_v3.py file-qa --root .

ai-image-qa: ai-image-file-qa

ai-image-retry:
	python scripts/retry_ai_images_v3.py --root .

ai-image-summary:
	python scripts/summarize_ai_images_v3.py --root .

ai-image-contact-sheets:
	python scripts/run_ai_image_pipeline_v3.py contact-sheets --root .

ai-image-visual-asset-qa-instructions:
	python scripts/run_ai_image_pipeline_v3.py visual-asset-qa-instructions --root .

ai-image-visual-identity-qa-instructions:
	python scripts/run_ai_image_pipeline_v3.py visual-identity-qa-instructions --root .

ai-image-visual-distribution-audit-instructions:
	python scripts/run_ai_image_pipeline_v3.py visual-distribution-audit-instructions --root .

ai-image-apply-visual-asset-qa:
	python scripts/run_ai_image_pipeline_v3.py apply-visual-asset-qa --root . --visual_json ai_image/reports/visual_verdict/asset_qa_latest.json

ai-image-apply-visual-identity-qa:
	python scripts/run_ai_image_pipeline_v3.py apply-visual-identity-qa --root . --visual_json ai_image/reports/visual_verdict/identity_qa_latest.json

ai-image-apply-visual-distribution-audit:
	python scripts/run_ai_image_pipeline_v3.py apply-visual-distribution-audit --root . --visual_json ai_image/reports/visual_verdict/distribution_audit_latest.json

ai-image-distribution-audit:
	python scripts/run_ai_image_pipeline_v3.py distribution-audit --root .

ai-image-completion-check:
	python scripts/run_ai_image_pipeline_v3.py completion-check --root .

ai-image-bounded-chunk-plan:
	python scripts/run_ai_image_pipeline_v3.py bounded-chunk-plan --root . --production

ai-image-bounded-chunk-run:
	python scripts/run_ai_image_pipeline_v3.py bounded-chunk-run --root .

ai-image-bounded-chunk-resume:
	python scripts/run_ai_image_pipeline_v3.py bounded-chunk-resume --root .

ai-image-bounded-chunk-status:
	python scripts/run_ai_image_pipeline_v3.py bounded-chunk-status --root .

ai-image-bounded-chunk-qa:
	python scripts/run_ai_image_pipeline_v3.py bounded-chunk-qa --root .

ai-image-bounded-chunk-finalize:
	python scripts/run_ai_image_pipeline_v3.py bounded-chunk-finalize --root .

ai-image-autopilot-chunks-720:
	python scripts/run_hermes_image_pipeline_v3.py --root . --execution-mode autopilot --allow-real-imagegen

ai-image-supervisor-720:
	python scripts/run_ai_image_pipeline_v3.py supervisor-720 --root .

ai-image-supervisor-chunk-only:
	python scripts/run_ai_image_pipeline_v3.py supervisor-chunk-only --root .

ai-image-supervisor-identity-only:
	python scripts/run_ai_image_pipeline_v3.py supervisor-identity-only --root .

ai-image-supervisor-asset-only:
	python scripts/run_ai_image_pipeline_v3.py supervisor-asset-only --root .
