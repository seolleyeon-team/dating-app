// =============================================================================
// 3:3 블라인드 취향 미팅 — 참여 가능 날짜 선택 및 신청 제출
// 경로: lib/features/blind_meeting/presentation/screens/blind_meeting_schedule_screen.dart
//
// 정책
//  - 여기서는 '날짜'만 고른다. 아침/오후/저녁 시간대 선택은 없다.
//  - 선택 가능 범위는 KST 기준 내일부터 총 21일
//    (blindMeetingAvailabilityWindowDays).
//  - 세부 시간은 팀 구성 후 6명 단체 채팅방의 약속잡기에서 정한다.
//
// 색·형태는 설레연 이벤트 테마(BlindMeetingPalette / kEvent*)를 그대로 쓴다.
// =============================================================================

import 'package:flutter/material.dart';

import '../../../../router/route_names.dart';
import '../../data/blind_meeting_analytics.dart';
import '../../data/blind_meeting_repository.dart';
import '../../domain/blind_meeting_application.dart';
import '../../domain/blind_meeting_availability.dart';
import '../../domain/blind_meeting_dna.dart';
import '../../domain/blind_meeting_enums.dart';
import '../blind_meeting_route_args.dart';
import '../theme/blind_meeting_palette.dart';
import '../widgets/blind_meeting_common.dart';

class BlindMeetingScheduleScreen extends StatefulWidget {
  final BlindMeetingDnaDraft draft;
  final BlindMeetingRepository? repository;
  final BlindMeetingAnalytics? analytics;

  /// 테스트에서 날짜를 고정하기 위한 기준 시각.
  final DateTime? now;

  /// 기존 신청을 불러와 선택 상태를 복구할지 여부.
  ///
  /// 위젯 테스트에서는 Firebase를 붙이지 않으므로 기본값을 끄고 쓸 수 있다.
  final bool restoreExistingSelection;

  const BlindMeetingScheduleScreen({
    super.key,
    required this.draft,
    this.repository,
    this.analytics,
    this.now,
    this.restoreExistingSelection = true,
  });

  @override
  State<BlindMeetingScheduleScreen> createState() =>
      _BlindMeetingScheduleScreenState();
}

class _BlindMeetingScheduleScreenState
    extends State<BlindMeetingScheduleScreen> {
  late final BlindMeetingRepository _repository =
      widget.repository ?? BlindMeetingRepository();

  final Set<String> _selectedDateKeys = <String>{};

  bool _waitlistOptIn = true;
  bool _submitting = false;
  bool _restoring = false;
  String? _error;

  /// 기존 신청을 불러오지 못했을 때만 채워진다 (빈 선택으로 덮어쓰지 않기 위함).
  String? _restoreError;

  /// 자정이 지나 선택 범위를 벗어난 날짜 안내.
  final List<String> _expiredDateKeys = <String>[];

  /// 캘린더가 보여주는 월 (선택 범위와 겹치는 월만 허용).
  late DateTime _visibleMonth;

  /// 화면을 오래 열어둔 경우를 대비해 제출 직전 다시 계산한다.
  DateTime get _now => widget.now ?? DateTime.now();

  List<DateTime> get _months => BlindMeetingAvailability.selectableMonths(_now);

  @override
  void initState() {
    super.initState();
    _visibleMonth = _months.first;
    (widget.analytics ?? BlindMeetingAnalytics()).log(
      BlindMeetingAnalyticsEvent.scheduleViewed,
      params: {
        'availabilityWindowDays': blindMeetingAvailabilityWindowDays,
        'crossesMonthBoundary': BlindMeetingAvailability.crossesMonthBoundary(
          _now,
        ),
      },
    );
    if (widget.restoreExistingSelection) {
      _restoreSelection();
    }
  }

  /// 기존 신청(비공개 DNA)에서 선택 날짜를 복구한다.
  ///
  /// 실패하면 빈 선택으로 덮어쓰지 않고 사용자에게 알리고 재시도를 제공한다.
  Future<void> _restoreSelection() async {
    setState(() {
      _restoring = true;
      _restoreError = null;
    });
    try {
      final dna = await _repository.loadMyDna();
      if (!mounted) return;
      final stored = dna?.availableDateKeys ?? const <String>[];
      final valid = BlindMeetingAvailability.retainWithinWindow(stored, _now);
      final expired = BlindMeetingAvailability.expiredKeys(stored, _now);
      setState(() {
        _restoring = false;
        _selectedDateKeys
          ..clear()
          ..addAll(valid);
        _expiredDateKeys
          ..clear()
          ..addAll(expired);
        if (dna != null) _waitlistOptIn = dna.waitlistOptIn;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _restoring = false;
        _restoreError = '이전에 선택한 날짜를 불러오지 못했어요. 이미 신청이 진행 중일 수 있어요.';
      });
    }
  }

  bool get _alcoholFreeRequested =>
      widget.draft.alcoholPreference == AlcoholCompanionPreference.allSober;

  List<String> get _sortedSelection =>
      BlindMeetingAvailability.normalizeDateKeys(_selectedDateKeys);

  void _toggleDate(String dateKey) {
    if (!BlindMeetingAvailability.isWithinWindow(dateKey, _now)) return;
    final analytics = widget.analytics ?? BlindMeetingAnalytics();
    final wasSelected = _selectedDateKeys.contains(dateKey);
    setState(() {
      if (wasSelected) {
        _selectedDateKeys.remove(dateKey);
      } else {
        _selectedDateKeys.add(dateKey);
      }
      _error = null;
    });
    // 실제 날짜는 보내지 않고 선택 개수만 남긴다.
    analytics.log(
      wasSelected
          ? BlindMeetingAnalyticsEvent.dateUnselected
          : BlindMeetingAnalyticsEvent.dateSelected,
      params: {'selectedDateCount': _selectedDateKeys.length},
    );
  }

  void _showMonth(DateTime month) {
    setState(() => _visibleMonth = month);
  }

  Future<void> _submit() async {
    if (_submitting) return;

    // 자정을 넘겨 화면을 오래 열어둔 경우를 대비해 범위를 다시 계산한다.
    final now = _now;
    final valid = BlindMeetingAvailability.retainWithinWindow(
      _selectedDateKeys,
      now,
    );
    final expired = BlindMeetingAvailability.expiredKeys(
      _selectedDateKeys,
      now,
    );
    if (expired.isNotEmpty) {
      setState(() {
        _selectedDateKeys
          ..clear()
          ..addAll(valid);
        _expiredDateKeys
          ..clear()
          ..addAll(expired);
        _error = '날짜가 바뀌어 선택할 수 없게 된 날짜를 제외했어요. 다시 확인해주세요.';
      });
      return;
    }
    if (valid.isEmpty) {
      setState(() => _error = '참여 가능한 날짜를 한 개 이상 선택해주세요.');
      return;
    }

    setState(() {
      _submitting = true;
      _error = null;
    });

    final dna = widget.draft.toDna(
      dateKeys: valid,
      waitlistOptIn: _waitlistOptIn,
    );

    final violations = dna.validate();
    if (violations.isNotEmpty) {
      setState(() {
        _submitting = false;
        _error = violations.first.message;
      });
      return;
    }

    try {
      final result = await _repository.submitApplication(dna);
      if (!mounted) return;
      if (!result.accepted) {
        setState(() {
          _submitting = false;
          _error = result.message ?? '참가 신청을 저장하지 못했어요. 선택한 날짜는 그대로 유지돼요.';
        });
        return;
      }
      final analytics = widget.analytics ?? BlindMeetingAnalytics();
      await analytics.log(
        BlindMeetingAnalyticsEvent.scheduleSubmitted,
        userId: dna.userId,
        params: {
          'selectedDateCount': valid.length,
          'availabilityWindowDays': blindMeetingAvailabilityWindowDays,
          'isAlcoholFree': _alcoholFreeRequested,
          'stage': result.stage.name,
        },
      );
      if (result.stage == BlindMeetingMatchingStage.matched) {
        await analytics.log(
          BlindMeetingAnalyticsEvent.groupFormed,
          userId: dna.userId,
          params: {'meetingId': result.meetingId ?? ''},
        );
      } else {
        await analytics.log(
          BlindMeetingAnalyticsEvent.waitlisted,
          userId: dna.userId,
        );
      }
      if (!mounted) return;
      Navigator.of(
        context,
      ).pushReplacementNamed(RouteNames.blindTasteMeetingWaiting);
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _submitting = false;
        _error = '참가 신청을 저장하지 못했어요. 선택한 날짜는 그대로 유지돼요.';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final palette = BlindMeetingPalette.of(context);
    final selection = _sortedSelection;

    return Scaffold(
      backgroundColor: palette.background,
      body: Column(
        children: [
          BlindMeetingAppBar(
            title: '참여 날짜 선택',
            onBack: () => Navigator.of(context).maybePop(),
          ),
          Expanded(
            child: SingleChildScrollView(
              physics: const BouncingScrollPhysics(),
              padding: const EdgeInsets.only(top: 8, bottom: 32),
              child: BlindMeetingResponsiveBody(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '참여 가능한 날짜를\n골라주세요',
                      style: BlindMeetingText.title(palette.ink),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      '여러 날짜를 선택할수록 잘 맞는 팀을 더 빠르게 찾을 수 있어요.\n'
                      '앞으로 $blindMeetingAvailabilityWindowDays일 중에서 고를 수 있어요.\n'
                      '구체적인 시간은 팀이 만들어진 뒤 단체 채팅방에서 함께 정해요.',
                      style: BlindMeetingText.caption(palette.inkSoft),
                    ),
                    const SizedBox(height: 16),
                    // 시뮬레이션 결과 3개 이상에서 매칭 확률 증가폭이 급격히 줄어든다.
                    // 강제하지 않고 권장만 한다 (1개만 골라도 신청은 가능).
                    if (selection.isNotEmpty &&
                        selection.length < kRecommendedDateCount)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 16),
                        child: _NoticeCard(
                          icon: Icons.lightbulb_outline,
                          tint: palette.accentDeep,
                          message:
                              '$kRecommendedDateCount개 이상 고르면 팀이 만들어질 확률이 크게 올라가요. '
                              '지금은 ${selection.length}개예요.',
                        ),
                      ),
                    const SizedBox(height: 4),
                    if (_alcoholFreeRequested)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 16),
                        child: BlindMeetingCard(
                          background: palette.surfaceMuted,
                          child: Row(
                            children: [
                              Icon(
                                Icons.local_cafe_outlined,
                                size: 18,
                                color: palette.positive,
                              ),
                              const SizedBox(width: 10),
                              Expanded(
                                child: Text(
                                  '무알코올 미팅으로 신청돼요. 여섯 명 모두 비음주인 미팅만 배정됩니다.',
                                  style: BlindMeetingText.caption(palette.ink),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    if (_restoreError != null)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 16),
                        child: BlindMeetingErrorState(
                          message: _restoreError!,
                          onRetry: _restoreSelection,
                        ),
                      ),
                    if (_expiredDateKeys.isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 16),
                        child: _NoticeCard(
                          icon: Icons.event_busy_outlined,
                          tint: palette.attention,
                          message:
                              '날짜가 지나 선택할 수 없게 된 날짜 '
                              '${_expiredDateKeys.length}개를 제외했어요.',
                        ),
                      ),
                    _CalendarCard(
                      visibleMonth: _visibleMonth,
                      months: _months,
                      now: _now,
                      selectedDateKeys: _selectedDateKeys,
                      loading: _restoring,
                      onMonthChanged: _showMonth,
                      onDateToggled: _toggleDate,
                    ),
                    const SizedBox(height: 16),
                    _SelectionSummaryCard(selectedDateKeys: selection),
                    const SizedBox(height: 16),
                    BlindMeetingCard(
                      child: Row(
                        children: [
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  '대기자로도 참여할게요',
                                  style: BlindMeetingText.body(palette.ink),
                                ),
                                const SizedBox(height: 4),
                                Text(
                                  '정원이 차면 대기자로 등록되고, 빈자리가 생기면 먼저 제안을 받아요.',
                                  style: BlindMeetingText.caption(
                                    palette.inkSoft,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          Switch(
                            value: _waitlistOptIn,
                            activeThumbColor: palette.accent,
                            onChanged: (value) =>
                                setState(() => _waitlistOptIn = value),
                          ),
                        ],
                      ),
                    ),
                    if (_error != null) ...[
                      const SizedBox(height: 16),
                      BlindMeetingErrorState(message: _error!),
                    ],
                  ],
                ),
              ),
            ),
          ),
          SafeArea(
            top: false,
            child: BlindMeetingResponsiveBody(
              padding: const EdgeInsets.fromLTRB(
                kEventHorizontalPadding,
                8,
                kEventHorizontalPadding,
                12,
              ),
              child: BlindMeetingPrimaryButton(
                label: selection.isEmpty
                    ? '가능한 날짜를 선택해주세요'
                    : '선택한 ${selection.length}개 날짜로 신청하기',
                icon: Icons.event_available_outlined,
                loading: _submitting,
                onPressed: selection.isEmpty ? null : _submit,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 안내 카드
// =============================================================================
class _NoticeCard extends StatelessWidget {
  final IconData icon;
  final Color tint;
  final String message;

  const _NoticeCard({
    required this.icon,
    required this.tint,
    required this.message,
  });

  @override
  Widget build(BuildContext context) {
    final palette = BlindMeetingPalette.of(context);
    return BlindMeetingCard(
      background: palette.surfaceMuted,
      child: Row(
        children: [
          Icon(icon, size: 18, color: tint),
          const SizedBox(width: 10),
          Expanded(
            child: Text(message, style: BlindMeetingText.caption(palette.ink)),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 캘린더 카드
// =============================================================================
class _CalendarCard extends StatelessWidget {
  final DateTime visibleMonth;
  final List<DateTime> months;
  final DateTime now;
  final Set<String> selectedDateKeys;
  final bool loading;
  final ValueChanged<DateTime> onMonthChanged;
  final ValueChanged<String> onDateToggled;

  const _CalendarCard({
    required this.visibleMonth,
    required this.months,
    required this.now,
    required this.selectedDateKeys,
    required this.loading,
    required this.onMonthChanged,
    required this.onDateToggled,
  });

  int get _visibleIndex => months.indexWhere(
    (m) => m.year == visibleMonth.year && m.month == visibleMonth.month,
  );

  @override
  Widget build(BuildContext context) {
    final palette = BlindMeetingPalette.of(context);
    final index = _visibleIndex;
    final hasPrevious = index > 0;
    final hasNext = index >= 0 && index < months.length - 1;

    return BlindMeetingCard(
      padding: const EdgeInsets.fromLTRB(12, 14, 12, 16),
      child: Column(
        children: [
          _MonthHeader(
            month: visibleMonth,
            onPrevious: hasPrevious
                ? () => onMonthChanged(months[index - 1])
                : null,
            onNext: hasNext ? () => onMonthChanged(months[index + 1]) : null,
          ),
          const SizedBox(height: 12),
          const _WeekdayHeader(),
          const SizedBox(height: 6),
          if (loading)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 48),
              child: CircularProgressIndicator(color: palette.accent),
            )
          else
            _MonthGrid(
              month: visibleMonth,
              now: now,
              selectedDateKeys: selectedDateKeys,
              onDateToggled: onDateToggled,
            ),
        ],
      ),
    );
  }
}

class _MonthHeader extends StatelessWidget {
  final DateTime month;
  final VoidCallback? onPrevious;
  final VoidCallback? onNext;

  const _MonthHeader({
    required this.month,
    required this.onPrevious,
    required this.onNext,
  });

  @override
  Widget build(BuildContext context) {
    final palette = BlindMeetingPalette.of(context);

    return Row(
      children: [
        _MonthArrow(
          icon: Icons.chevron_left,
          tooltip: '이전 달 보기',
          onPressed: onPrevious,
        ),
        Expanded(
          child: Text(
            '${month.year}년 ${month.month}월',
            textAlign: TextAlign.center,
            style: BlindMeetingText.cardTitle(palette.ink),
          ),
        ),
        _MonthArrow(
          icon: Icons.chevron_right,
          tooltip: '다음 달 보기',
          onPressed: onNext,
        ),
      ],
    );
  }
}

class _MonthArrow extends StatelessWidget {
  final IconData icon;
  final String tooltip;
  final VoidCallback? onPressed;

  const _MonthArrow({
    required this.icon,
    required this.tooltip,
    required this.onPressed,
  });

  @override
  Widget build(BuildContext context) {
    final palette = BlindMeetingPalette.of(context);
    final enabled = onPressed != null;
    return SizedBox(
      width: 44,
      height: 44,
      child: IconButton(
        onPressed: onPressed,
        icon: Icon(icon, size: 22),
        color: palette.accent,
        disabledColor: palette.inkFaint,
        tooltip: enabled ? tooltip : '$tooltip (선택 가능 기간이 아니에요)',
      ),
    );
  }
}

class _WeekdayHeader extends StatelessWidget {
  const _WeekdayHeader();

  @override
  Widget build(BuildContext context) {
    final palette = BlindMeetingPalette.of(context);
    return ExcludeSemantics(
      child: Row(
        children: [
          for (final label in BlindMeetingAvailability.weekdayLabels)
            Expanded(
              child: Center(
                child: Text(
                  label,
                  style: BlindMeetingText.label(palette.inkFaint),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _MonthGrid extends StatelessWidget {
  final DateTime month;
  final DateTime now;
  final Set<String> selectedDateKeys;
  final ValueChanged<String> onDateToggled;

  const _MonthGrid({
    required this.month,
    required this.now,
    required this.selectedDateKeys,
    required this.onDateToggled,
  });

  @override
  Widget build(BuildContext context) {
    final firstOfMonth = DateTime.utc(month.year, month.month);
    // 주 시작은 월요일 (앱 전체 요일 표기와 동일).
    final leadingBlanks = firstOfMonth.weekday - DateTime.monday;
    final daysInMonth = DateTime.utc(
      month.month == 12 ? month.year + 1 : month.year,
      month.month == 12 ? 1 : month.month + 1,
    ).difference(firstOfMonth).inDays;

    final cells = <Widget>[
      for (var i = 0; i < leadingBlanks; i++) const SizedBox.shrink(),
      for (var day = 1; day <= daysInMonth; day++)
        _DayCell(
          date: DateTime.utc(month.year, month.month, day),
          now: now,
          selectedDateKeys: selectedDateKeys,
          onToggled: onDateToggled,
        ),
    ];
    // 마지막 주를 7칸으로 채운다.
    while (cells.length % 7 != 0) {
      cells.add(const SizedBox.shrink());
    }

    return Column(
      children: [
        for (var row = 0; row < cells.length ~/ 7; row++)
          Row(
            children: [
              for (var col = 0; col < 7; col++)
                Expanded(child: cells[row * 7 + col]),
            ],
          ),
      ],
    );
  }
}

class _DayCell extends StatelessWidget {
  final DateTime date;
  final DateTime now;
  final Set<String> selectedDateKeys;
  final ValueChanged<String> onToggled;

  const _DayCell({
    required this.date,
    required this.now,
    required this.selectedDateKeys,
    required this.onToggled,
  });

  @override
  Widget build(BuildContext context) {
    final palette = BlindMeetingPalette.of(context);
    final dateKey = BlindMeetingAvailability.formatDateKey(date);
    final selectable = BlindMeetingAvailability.isWithinWindow(dateKey, now);
    final selected = selectedDateKeys.contains(dateKey);
    final isToday = date == BlindMeetingAvailability.today(now);

    final Color background;
    final Color foreground;
    final Border? border;
    if (selected) {
      background = palette.accent;
      foreground = Colors.white;
      border = null;
    } else if (!selectable) {
      background = Colors.transparent;
      foreground = palette.inkFaint;
      border = isToday
          ? Border.all(color: palette.accent.withValues(alpha: 0.35))
          : null;
    } else {
      background = palette.surfaceMuted;
      foreground = palette.ink;
      border = Border.all(color: palette.accent.withValues(alpha: 0.14));
    }

    final label = BlindMeetingAvailability.accessibilityLabel(dateKey);
    final semanticsLabel = selected
        ? '$label, 선택됨'
        : selectable
        ? label
        : isToday
        ? '$label, 오늘이라 선택할 수 없어요'
        : '$label, 선택할 수 없는 날짜예요';

    return Semantics(
      button: selectable,
      enabled: selectable,
      selected: selected,
      label: semanticsLabel,
      child: ExcludeSemantics(
        child: Padding(
          padding: const EdgeInsets.all(3),
          child: Material(
            color: background,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(14),
              side: border?.top ?? BorderSide.none,
            ),
            child: InkWell(
              borderRadius: BorderRadius.circular(14),
              onTap: selectable ? () => onToggled(dateKey) : null,
              child: Container(
                // 최소 터치 영역 확보.
                constraints: const BoxConstraints(minHeight: 44),
                alignment: Alignment.center,
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text(
                      '${date.day}',
                      style: TextStyle(
                        fontFamily: BlindMeetingText.fontFamily,
                        fontSize: 15,
                        // 색 외에도 굵기로 상태를 구분한다.
                        fontWeight: selected
                            ? FontWeight.w700
                            : selectable
                            ? FontWeight.w600
                            : FontWeight.w400,
                        color: foreground,
                      ),
                    ),
                    if (isToday && !selected)
                      Padding(
                        padding: const EdgeInsets.only(top: 2),
                        child: Text(
                          '오늘',
                          style: TextStyle(
                            fontFamily: BlindMeetingText.fontFamily,
                            fontSize: 9,
                            fontWeight: FontWeight.w600,
                            color: palette.accent,
                          ),
                        ),
                      ),
                    if (selected)
                      Padding(
                        padding: const EdgeInsets.only(top: 2),
                        child: Icon(Icons.check, size: 11, color: Colors.white),
                      ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

// =============================================================================
// 선택 요약
// =============================================================================
class _SelectionSummaryCard extends StatelessWidget {
  final List<String> selectedDateKeys;

  const _SelectionSummaryCard({required this.selectedDateKeys});

  /// chip을 무한히 늘리지 않고 앞부분만 보여준다.
  static const int _maxChips = 6;

  @override
  Widget build(BuildContext context) {
    final palette = BlindMeetingPalette.of(context);
    final count = selectedDateKeys.length;

    return BlindMeetingCard(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                Icons.event_available_outlined,
                size: 18,
                color: count == 0 ? palette.inkFaint : palette.accent,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  count == 0 ? '선택한 날짜 없음' : '선택한 날짜 $count개',
                  style: BlindMeetingText.cardTitle(palette.ink),
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          if (count == 0)
            Text(
              '캘린더에서 참여 가능한 날짜를 눌러주세요. 여러 날짜를 함께 선택할 수 있어요.',
              style: BlindMeetingText.caption(palette.inkSoft),
            )
          else ...[
            Text(
              BlindMeetingAvailability.selectionSummary(selectedDateKeys),
              style: BlindMeetingText.caption(palette.inkSoft),
            ),
            const SizedBox(height: 10),
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: [
                for (final key in selectedDateKeys.take(_maxChips))
                  BlindMeetingBadge(
                    label: BlindMeetingAvailability.shortLabel(key),
                    color: palette.accent,
                  ),
                if (count > _maxChips)
                  BlindMeetingBadge(
                    label: '외 ${count - _maxChips}일',
                    color: palette.accentDeep,
                  ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}
