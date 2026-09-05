import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/onboarding/services/avatar_resume_policy.dart';
import 'package:seolleyeon/features/onboarding/widgets/avatar_generation_messages.dart';

AvatarGenerationStatusSnapshot snap(
  String status, {
  bool sourceLocked = true,
  String candidateAvailability = 'none',
  bool retryAllowed = false,
  bool approved = false,
  String jobId = 'avatar_job_abcdefgh',
}) {
  return AvatarGenerationStatusSnapshot.fromMap({
    'sourceLocked': sourceLocked,
    'jobId': jobId,
    'sourceSelectionVersion': 3,
    'status': status,
    'candidateAvailability': candidateAvailability,
    'retryAllowed': retryAllowed,
    'approved': approved,
    'safeReasonCode': null,
  });
}

void main() {
  group('planAvatarResume', () {
    test('active server work resumes generation and never shows failure', () {
      for (final status in const [
        'queued',
        'source_selecting',
        'running',
        'qa_pending',
        'approval_copying',
      ]) {
        final plan = planAvatarResume(snap(status));
        expect(
          plan.action,
          AvatarResumeAction.resumeGenerating,
          reason: '$status must resume, not fail',
        );
        expect(plan.message, isEmpty, reason: '$status must not show an error');
        expect(plan.retryAllowed, isFalse);
        expect(plan.blocksPhotoEditing, isTrue);
      }
    });

    test('preview_ready with safe candidates resumes the preview', () {
      final plan = planAvatarResume(
        snap('preview_ready', candidateAvailability: 'preview_safe'),
      );
      expect(plan.action, AvatarResumeAction.resumePreview);
      expect(plan.message, isEmpty);
    });

    test('preview_ready without safe candidates keeps waiting', () {
      final plan = planAvatarResume(snap('preview_ready'));
      expect(plan.action, AvatarResumeAction.resumeGenerating);
      expect(plan.message, isEmpty);
    });

    test('approved resumes the approved state', () {
      final plan = planAvatarResume(
        snap('approved', approved: true, jobId: ''),
      );
      expect(plan.action, AvatarResumeAction.resumeApproved);
      expect(plan.blocksPhotoEditing, isTrue);
    });

    test('needs_review is not a generation failure and offers no retry', () {
      final plan = planAvatarResume(snap('needs_review'));
      expect(plan.action, AvatarResumeAction.showNeedsReview);
      expect(plan.retryAllowed, isFalse);
      expect(plan.message, avatarNeedsReviewMessage);
      expect(plan.message, isNot(contains('실패')));
      expect(plan.message, isNot(contains('다시 시도')));
    });

    test('retryable failures offer retry only when the server allows it', () {
      final allowed = planAvatarResume(
        snap('retryable_failed', retryAllowed: true),
      );
      expect(allowed.action, AvatarResumeAction.showRetryable);
      expect(allowed.retryAllowed, isTrue);

      // 서버가 재시도를 허용하지 않으면 UI도 재시도를 제안하지 않는다.
      final refused = planAvatarResume(snap('retryable_failed'));
      expect(refused.retryAllowed, isFalse);
    });

    test('terminal failure is distinct from a transient retry failure', () {
      final plan = planAvatarResume(snap('terminal_failed'));
      expect(plan.action, AvatarResumeAction.showTerminal);
      expect(plan.retryAllowed, isFalse);
      expect(plan.message, isNot(avatarGenerationFailedMessage));
    });

    test('no active source means the screen is a normal upload screen', () {
      final plan = planAvatarResume(snap('queued', sourceLocked: false));
      expect(plan.action, AvatarResumeAction.none);
      expect(plan.blocksPhotoEditing, isFalse);
    });

    test('an unreadable status leaves local state untouched', () {
      expect(planAvatarResume(null).action, AvatarResumeAction.unavailable);
      final plan = planAvatarResume(snap('something_unknown'));
      expect(plan.action, AvatarResumeAction.unavailable);
      expect(plan.message, isEmpty);
    });

    test('provider outcome unknown is its own state, not QA review', () {
      // 유료 생성이 이미 일어났을 수 있다. 재시도도, "사진 바꿔 다시 만들기"도
      // 재조정이 끝나기 전에는 제안하면 안 된다.
      final plan = planAvatarResume(snap('reconciliation_required'));
      expect(plan.action, AvatarResumeAction.showReconciliation);
      expect(plan.retryAllowed, isFalse);
      expect(plan.allowsNewGeneration, isFalse);
      expect(plan.message, avatarReconciliationRequiredMessage);
      expect(plan.message, isNot(avatarNeedsReviewMessage));
    });

    test('needs_review allows an explicit new generation, not a retry', () {
      final plan = planAvatarResume(snap('needs_review'));
      expect(plan.action, AvatarResumeAction.showNeedsReview);
      expect(plan.retryAllowed, isFalse);
      // 같은 generation 재시도가 아니라 새 사진으로 새 generation.
      expect(plan.allowsNewGeneration, isTrue);
    });

    test('terminal failure allows starting over with different photos', () {
      final plan = planAvatarResume(snap('terminal_failed'));
      expect(plan.allowsNewGeneration, isTrue);
      expect(plan.retryAllowed, isFalse);
    });

    test('active generation never offers a new generation', () {
      for (final status in const ['queued', 'running', 'qa_pending']) {
        expect(planAvatarResume(snap(status)).allowsNewGeneration, isFalse);
      }
    });
  });
}
