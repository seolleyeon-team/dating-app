/// 관심사 선택 화면이 호출된 목적.
enum InterestsSelectionMode {
  /// 기존 온보딩의 한 단계로 진입한다.
  onboarding,

  /// 블라인드 미팅 자격 조건을 보완하기 위해 진입한다.
  prerequisiteRepair,
}

/// 관심사 선택 화면의 typed route arguments.
///
/// 인자가 없는 기존 호출은 [InterestsSelectionMode.onboarding]으로
/// 해석되어 기존 온보딩 흐름과 호환된다.
class InterestsSelectionRouteArgs {
  final InterestsSelectionMode mode;

  const InterestsSelectionRouteArgs({
    this.mode = InterestsSelectionMode.onboarding,
  });

  const InterestsSelectionRouteArgs.prerequisiteRepair()
    : mode = InterestsSelectionMode.prerequisiteRepair;
}
