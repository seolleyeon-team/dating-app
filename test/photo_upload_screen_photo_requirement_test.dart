import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image_picker/image_picker.dart';
import 'package:seolleyeon/features/onboarding/screens/photo_upload_screen.dart';
import 'package:seolleyeon/features/onboarding/widgets/avatar_candidate_selection_dialog.dart';
import 'package:seolleyeon/features/onboarding/widgets/avatar_generation_models.dart';
import 'package:seolleyeon/features/onboarding/widgets/avatar_generation_messages.dart';
import 'package:seolleyeon/services/avatar_generation_client.dart';
import 'package:seolleyeon/services/onboarding_photo_source_ref.dart';
import 'package:seolleyeon/services/avatar_source_photo_service.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// 온보딩 사진 최소 2장 요구사항 회귀 테스트.
///
/// production 계약:
/// - 유효 사진 0장/1장 → "다음" 비활성화
/// - 유효 사진 2장 이상 → "다음" 활성화, 아바타 생성 시작
/// - 승인된 아바타 보유(재방문) → 사진 재등록 없이 진행 가능
/// - "사진은 나중에 추가할 수 있어요" 류의 우회 카피는 존재하지 않는다
class _CountingAvatarClient extends AvatarGenerationClient {
  int beginCalls = 0;
  final List<String> polledJobIds = <String>[];

  @override
  Future<AvatarSourcePhotoUploadResult> beginFromOnboardingPhotos({
    required List<OnboardingPhotoSourceRef> sourcePhotos,
    required String uid,
    String? clientRequestId,
    bool chatPartnerRealPhotoDisclosure = false,
  }) async {
    beginCalls += 1;
    return const AvatarSourcePhotoUploadResult(
      jobId: 'avatar_job_fresh_000000001',
      photoId: '',
      avatarStatus: 'queued',
      message: 'avatar_generation_queued',
      duplicate: false,
      sourceSelectionVersion: 1,
    );
  }

  @override
  Future<AvatarCandidatesResult> getCandidates(String jobId) async {
    return _previewReady(jobId);
  }

  @override
  Future<AvatarCandidatesResult> pollUntilPreviewReady({
    required String jobId,
    Duration pollInterval = const Duration(seconds: 2),
    Duration timeout = const Duration(seconds: 150),
    bool Function()? shouldContinue,
    int maxConsecutiveErrors =
        AvatarGenerationClient.defaultMaxConsecutivePollErrors,
  }) async {
    polledJobIds.add(jobId);
    return _previewReady(jobId);
  }

  @override
  Future<AvatarApprovalResult> approveCandidate(String candidateId) async {
    return AvatarApprovalResult(
      avatarStatus: 'approved',
      approvedAvatarUrl: 'https://cdn.example/avatar.png',
      selectedCandidateId: candidateId,
      duplicate: false,
    );
  }

  AvatarCandidatesResult _previewReady(String jobId) {
    return AvatarCandidatesResult(
      jobId: jobId,
      status: AvatarJobStatus.previewReady,
      candidates: List<AvatarCandidate>.generate(
        4,
        (index) => AvatarCandidate(
          candidateId: 'cand_$index',
          previewUrl: 'https://example.invalid/avatar_$index.png',
        ),
      ),
    );
  }
}

Future<void> _useMobileSurface(WidgetTester tester) async {
  tester.view.devicePixelRatio = 1.0;
  tester.view.physicalSize = const Size(390, 1100);
  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
  });
}

const _verifiedRefs = <OnboardingPhotoSourceRef?>[
  OnboardingPhotoSourceRef(
    photoId: 'photo_0001_verified',
    slotIndex: 0,
    objectGeneration: '101',
  ),
  OnboardingPhotoSourceRef(
    photoId: 'photo_0002_verified',
    slotIndex: 1,
    objectGeneration: '102',
  ),
];

Widget _harness({
  required AvatarGenerationClient client,
  required void Function(List<String>) onNext,
  List<String?>? initialPhotos,
  List<XFile?>? initialPickedFiles,
  List<OnboardingPhotoSourceRef?>? initialSourceRefs,
  String? lockedApprovedAvatarUrl,
}) {
  return MaterialApp(
    home: PhotoUploadScreen(
      avatarGenerationClient: client,
      initialPhotosForTesting: initialPhotos ?? const <String?>[],
      initialPickedFilesForTesting: initialPickedFiles,
      initialSourceRefsForTesting: initialSourceRefs,
      lockedApprovedAvatarUrlForTesting: lockedApprovedAvatarUrl,
      onNext: onNext,
    ),
  );
}

Finder _nextButton() => find.byType(ElevatedButton).last;

void _drainExpectedImageLoadException(WidgetTester tester) {
  tester.takeException();
}

XFile _fakePickedFile(String name) {
  return XFile.fromData(
    Uint8List.fromList(List<int>.filled(64, 7)),
    name: name,
  );
}

void main() {
  group('PhotoUploadScreen photo requirement', () {
    setUp(() {
      SharedPreferences.setMockInitialValues({});
    });

    testWidgets('사진 0장이면 다음 버튼이 비활성화된다', (tester) async {
      await _useMobileSurface(tester);
      List<String>? advancedPhotos;

      await tester.pumpWidget(
        _harness(
          client: _CountingAvatarClient(),
          initialPhotos: const [],
          onNext: (photos) => advancedPhotos = photos,
        ),
      );
      await tester.pump();

      final nextButton = tester.widget<ElevatedButton>(_nextButton());
      expect(nextButton.onPressed, isNull);
      expect(find.text('최소 2장 필요'), findsOneWidget);
      expect(find.text('사진은 나중에 추가할 수 있어요'), findsNothing);

      await tester.tap(_nextButton(), warnIfMissed: false);
      await tester.pump();
      expect(advancedPhotos, isNull);
    });

    testWidgets('사진 1장이면 다음 버튼이 비활성화된다', (tester) async {
      await _useMobileSurface(tester);
      List<String>? advancedPhotos;

      await tester.pumpWidget(
        _harness(
          client: _CountingAvatarClient(),
          initialPhotos: const ['https://photo.example/p1.jpg'],
          onNext: (photos) => advancedPhotos = photos,
        ),
      );
      await tester.pump();
      _drainExpectedImageLoadException(tester);

      final nextButton = tester.widget<ElevatedButton>(_nextButton());
      expect(nextButton.onPressed, isNull);

      await tester.tap(_nextButton(), warnIfMissed: false);
      await tester.pump();
      expect(advancedPhotos, isNull);
    });

    testWidgets('사진 2장이면 다음 버튼이 활성화된다', (tester) async {
      await _useMobileSurface(tester);

      await tester.pumpWidget(
        _harness(
          client: _CountingAvatarClient(),
          initialPhotos: const [
            'https://photo.example/p1.jpg',
            'https://photo.example/p2.jpg',
          ],
          onNext: (_) {},
        ),
      );
      await tester.pump();
      _drainExpectedImageLoadException(tester);

      final nextButton = tester.widget<ElevatedButton>(_nextButton());
      expect(nextButton.onPressed, isNotNull);
    });

    testWidgets('사진을 2장에서 1장으로 삭제하면 즉시 비활성화된다', (tester) async {
      await _useMobileSurface(tester);

      await tester.pumpWidget(
        _harness(
          client: _CountingAvatarClient(),
          initialPhotos: const [
            'https://photo.example/p1.jpg',
            'https://photo.example/p2.jpg',
          ],
          onNext: (_) {},
        ),
      );
      await tester.pump();
      _drainExpectedImageLoadException(tester);

      expect(tester.widget<ElevatedButton>(_nextButton()).onPressed, isNotNull);

      await tester.tap(find.byIcon(Icons.close_rounded).first);
      await tester.pump();
      _drainExpectedImageLoadException(tester);

      expect(tester.widget<ElevatedButton>(_nextButton()).onPressed, isNull);
    });

    testWidgets('승인된 아바타가 있으면 사진 재등록 없이 진행할 수 있다', (tester) async {
      await _useMobileSurface(tester);
      List<String>? advancedPhotos;
      const approvedUrl = 'https://cdn.example/approved-avatar.png';

      await tester.pumpWidget(
        _harness(
          client: _CountingAvatarClient(),
          initialPhotos: const [approvedUrl],
          lockedApprovedAvatarUrl: approvedUrl,
          onNext: (photos) => advancedPhotos = photos,
        ),
      );
      await tester.pump();
      _drainExpectedImageLoadException(tester);

      await tester.tap(_nextButton());
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      _drainExpectedImageLoadException(tester);

      expect(advancedPhotos, [approvedUrl]);
    });

    testWidgets('다음을 누르면 검증된 사진 세트로 서버 선택 생성이 한 번 시작된다', (
      tester,
    ) async {
      await _useMobileSurface(tester);
      final client = _CountingAvatarClient();

      await tester.pumpWidget(
        _harness(
          client: client,
          initialPhotos: const [
            'https://photo.example/p1.jpg',
            'https://photo.example/p2.jpg',
          ],
          initialPickedFiles: [_fakePickedFile('p1.jpg'), null],
          initialSourceRefs: _verifiedRefs,
          onNext: (_) {},
        ),
      );
      await tester.pump();
      _drainExpectedImageLoadException(tester);

      await tester.tap(_nextButton());
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      _drainExpectedImageLoadException(tester);

      // canonical: source-set admission 한 번, legacy 단일 사진 업로드 0회.
      expect(client.beginCalls, 1);
      expect(client.polledJobIds, ['avatar_job_fresh_000000001']);
      expect(find.byType(AvatarCandidateSelectionDialog), findsOneWidget);
    });

    testWidgets('다음 버튼 연타에도 source-set admission 은 한 번만 발생한다', (
      tester,
    ) async {
      await _useMobileSurface(tester);
      final client = _CountingAvatarClient();

      await tester.pumpWidget(
        _harness(
          client: client,
          initialPhotos: const [
            'https://photo.example/p1.jpg',
            'https://photo.example/p2.jpg',
          ],
          initialPickedFiles: [_fakePickedFile('p1.jpg'), null],
          initialSourceRefs: _verifiedRefs,
          onNext: (_) {},
        ),
      );
      await tester.pump();
      _drainExpectedImageLoadException(tester);

      await tester.tap(_nextButton());
      await tester.tap(_nextButton(), warnIfMissed: false);
      await tester.tap(_nextButton(), warnIfMissed: false);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      _drainExpectedImageLoadException(tester);

      expect(client.beginCalls, 1);
    });

    testWidgets('서버 source ref 가 없으면 legacy 생성을 시작하지 않고 멈춘다', (
      tester,
    ) async {
      // NEW CLIENT + OLD FUNCTIONS: 사진은 있지만 서버가 source ref 를 돌려주지
      // 않았다. 첫 사진으로 몰래 legacy generation 을 시작하면 안 된다.
      await _useMobileSurface(tester);
      final client = _CountingAvatarClient();
      List<String>? advancedPhotos;

      await tester.pumpWidget(
        _harness(
          client: client,
          initialPhotos: const [
            'https://photo.example/p1.jpg',
            'https://photo.example/p2.jpg',
          ],
          initialPickedFiles: [_fakePickedFile('p1.jpg'), _fakePickedFile('p2.jpg')],
          onNext: (photos) => advancedPhotos = photos,
        ),
      );
      await tester.pump();
      _drainExpectedImageLoadException(tester);

      await tester.tap(_nextButton());
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      _drainExpectedImageLoadException(tester);

      expect(client.beginCalls, 0);
      expect(advancedPhotos, isNull);
      expect(find.text(avatarBackendIncompatibleMessage), findsWidgets);
      expect(find.text('다시 시도'), findsNothing);
    });
  });
}
