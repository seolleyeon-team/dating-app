import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../constants/academic_grade_options.dart';
import '../../../constants/campus_life_zones.dart';
import '../../../constants/yonsei_departments.dart';
import '../../../services/campus_life_zone_repair_service.dart';

/// 생활권 보충 화면.
///
/// 추천·미팅은 생활권(신촌/송도)이 같은 사용자끼리만 연결한다. 기존 사용자
/// 중 학년·학과를 저장한 적이 없는 계정은 생활권이 계산된 적이 없어 추천이
/// 비어 있는데, 이 화면에서 부족한 값만 보충하면 기존 분류 로직이 생활권을
/// 만들어 준다.
///
/// 전체 온보딩을 다시 시키지 않는다. 생활권 판정에 실제로 쓰이는 값만 받는다.
/// 분류 자체는 [CampusLifeZoneResolver] 가 하며 이 화면은 재구현하지 않는다.
class CampusLifeZoneRepairScreen extends StatefulWidget {
  const CampusLifeZoneRepairScreen({super.key, this.service});

  /// 테스트 주입용. 기본값은 실제 Firestore 경로를 쓴다.
  final CampusLifeZoneRepairService? service;

  @override
  State<CampusLifeZoneRepairScreen> createState() =>
      _CampusLifeZoneRepairScreenState();
}

class _CampusLifeZoneRepairScreenState
    extends State<CampusLifeZoneRepairScreen> {
  late final CampusLifeZoneRepairService _service =
      widget.service ?? CampusLifeZoneRepairService();

  bool _isLoading = true;
  bool _isSaving = false;
  String? _errorMessage;

  String? _grade;
  String? _major;
  String? _department;
  bool _isRa = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final status = await _service.loadStatus();
    if (!mounted) return;
    setState(() {
      _isLoading = false;
      if (status == null) {
        _errorMessage = '로그인 정보를 확인할 수 없어요. 다시 로그인해주세요.';
        return;
      }
      final prefill = status.prefill;
      _grade = academicGradeOptions.contains(prefill.grade)
          ? prefill.grade
          : null;
      _major = YonseiDepartments.hasMajor(prefill.major) ? prefill.major : null;
      final departments = YonseiDepartments.departmentsFor(_major);
      _department = departments.contains(prefill.department)
          ? prefill.department
          : null;
      _isRa = prefill.isRa;
    });
  }

  bool get _canSubmit =>
      !_isSaving &&
      _grade != null &&
      _major != null &&
      (_department != null && _department!.isNotEmpty);

  Future<void> _submit() async {
    if (!_canSubmit) return;
    // 중복 탭 방지.
    setState(() {
      _isSaving = true;
      _errorMessage = null;
    });

    final result = await _service.repair(
      grade: _grade,
      major: _major,
      department: _department,
      isRa: _isRa,
    );
    if (!mounted) return;

    if (result.isSuccess) {
      Navigator.of(context).pop(true);
      return;
    }

    setState(() {
      _isSaving = false;
      _errorMessage = switch (result.error) {
        CampusLifeZoneRepairError.notSignedIn =>
          '로그인 정보를 확인할 수 없어요. 다시 로그인해주세요.',
        CampusLifeZoneRepairError.nothingToSave => '학년과 학과를 모두 선택해주세요.',
        // 저장은 됐지만 생활권이 만들어지지 않은 경우. 화면에 남는다.
        _ =>
          '선택한 정보로는 생활권을 확인하지 못했어요.\n'
              '학년과 학과를 다시 확인해주시고, 계속 같은 문제가 생기면 문의해주세요.',
      };
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.white,
      appBar: AppBar(
        backgroundColor: Colors.white,
        elevation: 0,
        foregroundColor: const Color(0xFF1F2937),
        title: const Text('생활권 설정'),
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : SafeArea(
              child: Column(
                children: [
                  Expanded(
                    child: SingleChildScrollView(
                      padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text(
                            '어디에서 주로 생활하는지 알려주세요',
                            style: TextStyle(
                              fontSize: 20,
                              fontWeight: FontWeight.w700,
                              color: Color(0xFF1F2937),
                            ),
                          ),
                          const SizedBox(height: 8),
                          const Text(
                            '신촌·송도 중 실제로 만날 수 있는 상대만 추천하기 위해\n'
                            '학년과 학과 정보가 필요해요.',
                            style: TextStyle(
                              fontSize: 14,
                              height: 1.5,
                              color: Color(0xFF6B7280),
                            ),
                          ),
                          const SizedBox(height: 28),
                          _Section(
                            label: '학년',
                            child: _ChipGroup(
                              options: academicGradeOptions,
                              selected: _grade,
                              onSelect: (value) {
                                HapticFeedback.selectionClick();
                                setState(() => _grade = value);
                              },
                            ),
                          ),
                          _Section(
                            label: '계열',
                            child: _ChipGroup(
                              options: YonseiDepartments.majorLabels.keys
                                  .toList(),
                              selected: _major,
                              labelOf: YonseiDepartments.labelFor,
                              onSelect: (value) {
                                HapticFeedback.selectionClick();
                                setState(() {
                                  _major = value;
                                  // 계열이 바뀌면 학과 선택을 초기화한다.
                                  _department = null;
                                });
                              },
                            ),
                          ),
                          if (_major != null)
                            _Section(
                              label: '학과',
                              child: _ChipGroup(
                                options: YonseiDepartments.departmentsFor(
                                  _major,
                                ),
                                selected: _department,
                                onSelect: (value) {
                                  HapticFeedback.selectionClick();
                                  setState(() => _department = value);
                                },
                              ),
                            ),
                          _Section(
                            label: 'RA (기숙사 조교)',
                            child: SwitchListTile.adaptive(
                              contentPadding: EdgeInsets.zero,
                              value: _isRa,
                              title: const Text(
                                'RA로 활동하고 있어요',
                                style: TextStyle(fontSize: 15),
                              ),
                              onChanged: (value) {
                                HapticFeedback.selectionClick();
                                setState(() => _isRa = value);
                              },
                            ),
                          ),
                          if (_errorMessage != null) ...[
                            const SizedBox(height: 8),
                            Container(
                              width: double.infinity,
                              padding: const EdgeInsets.all(14),
                              decoration: BoxDecoration(
                                color: const Color(0xFFFFF1F6),
                                borderRadius: BorderRadius.circular(12),
                              ),
                              child: Text(
                                _errorMessage!,
                                style: const TextStyle(
                                  fontSize: 13,
                                  height: 1.5,
                                  color: Color(0xFF9F1239),
                                ),
                              ),
                            ),
                          ],
                        ],
                      ),
                    ),
                  ),
                  Padding(
                    padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
                    child: SizedBox(
                      width: double.infinity,
                      height: 52,
                      child: ElevatedButton(
                        onPressed: _canSubmit ? _submit : null,
                        style: ElevatedButton.styleFrom(
                          backgroundColor: const Color(0xFF3E3548),
                          disabledBackgroundColor: const Color(0xFFD8D2DA),
                          foregroundColor: Colors.white,
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(14),
                          ),
                        ),
                        child: _isSaving
                            ? const SizedBox(
                                width: 22,
                                height: 22,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                  color: Colors.white,
                                ),
                              )
                            : const Text(
                                '생활권 설정 완료',
                                style: TextStyle(
                                  fontSize: 16,
                                  fontWeight: FontWeight.w700,
                                ),
                              ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
    );
  }
}

class _Section extends StatelessWidget {
  const _Section({required this.label, required this.child});

  final String label;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: const TextStyle(
              fontSize: 14,
              fontWeight: FontWeight.w700,
              color: Color(0xFF1F2937),
            ),
          ),
          const SizedBox(height: 10),
          child,
        ],
      ),
    );
  }
}

class _ChipGroup extends StatelessWidget {
  const _ChipGroup({
    required this.options,
    required this.selected,
    required this.onSelect,
    this.labelOf,
  });

  final List<String> options;
  final String? selected;
  final ValueChanged<String> onSelect;
  final String Function(String value)? labelOf;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: options.map((option) {
        final isSelected = option == selected;
        return ChoiceChip(
          label: Text(labelOf?.call(option) ?? option),
          selected: isSelected,
          onSelected: (_) => onSelect(option),
          showCheckmark: false,
          labelStyle: TextStyle(
            fontSize: 14,
            fontWeight: isSelected ? FontWeight.w700 : FontWeight.w500,
            color: isSelected ? Colors.white : const Color(0xFF4B5563),
          ),
          selectedColor: const Color(0xFF3E3548),
          backgroundColor: const Color(0xFFF3F4F6),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(20),
            side: BorderSide(
              color: isSelected
                  ? const Color(0xFF3E3548)
                  : const Color(0xFFE5E7EB),
            ),
          ),
        );
      }).toList(),
    );
  }
}

/// 생활권 라벨 (안내 문구용).
String campusLifeZoneLabel(String zone) => CampusLifeZones.labels[zone] ?? zone;
