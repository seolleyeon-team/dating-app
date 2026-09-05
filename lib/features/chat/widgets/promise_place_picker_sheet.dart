import 'package:flutter/cupertino.dart';
import 'package:geolocator/geolocator.dart';

import '../data/promise_campus_places.dart';
import '../models/promise_place.dart';
import '../services/promise_place_service.dart';
import '../utils/promise_map_launch.dart';
import '../../../constants/campus_life_zones.dart';

class _PickerColors {
  static const Color primary = Color(0xFF9B7FD8);
  static const Color primarySoft = Color(0xFFC6A9FE);
  static const Color textMain = Color(0xFF201F1D);
  static const Color textSubtle = Color(0xFF868E96);
  static const Color stone100 = Color(0xFFF5F5F4);
  static const Color stone200 = Color(0xFFE7E5E4);
  static const double fillAlpha = 0.29;
}

/// `PromisePlace.category` 키(`cafe` 등)와 대응하는 필터.
enum _PlaceCategoryFilter { all, cafe, restaurant, bar, campus, other }

bool _placeMatchesFilter(PromisePlace p, _PlaceCategoryFilter f) {
  switch (f) {
    case _PlaceCategoryFilter.all:
      return true;
    case _PlaceCategoryFilter.cafe:
      return p.category == PromisePlaceCategory.cafe;
    case _PlaceCategoryFilter.restaurant:
      return p.category == PromisePlaceCategory.restaurant;
    case _PlaceCategoryFilter.bar:
      return p.category == PromisePlaceCategory.bar;
    case _PlaceCategoryFilter.campus:
      return p.category == PromisePlaceCategory.campus;
    case _PlaceCategoryFilter.other:
      return p.category == PromisePlaceCategory.extra;
  }
}

/// 약속 장소 선택: 카테고리 필터 → 행 탭 시 같은 목록 안에서 펼쳐 상세 표시.
class PromisePlacePickerSheet extends StatelessWidget {
  const PromisePlacePickerSheet({
    super.key,
    this.initialPlaceId,
    this.campusLifeZones = const <String>{},
    this.showcase = false,
  });

  final String? initialPlaceId;
  final Set<String> campusLifeZones;
  final bool showcase;

  static Future<PromisePlace?> show(
    BuildContext context, {
    String? initialPlaceId,
    required Set<String> campusLifeZones,
  }) {
    return showCupertinoModalPopup<PromisePlace>(
      context: context,
      builder: (ctx) => PromisePlacePickerSheet(
        initialPlaceId: initialPlaceId,
        campusLifeZones: campusLifeZones,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.bottomCenter,
      child: Container(
        height: MediaQuery.of(context).size.height * 0.88,
        decoration: const BoxDecoration(
          color: CupertinoColors.systemBackground,
          borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
        ),
        child: CupertinoPageScaffold(
          backgroundColor: CupertinoColors.systemBackground,
          navigationBar: CupertinoNavigationBar(
            backgroundColor: CupertinoColors.systemBackground,
            border: const Border(
              bottom: BorderSide(color: _PickerColors.stone200, width: 0.5),
            ),
            middle: const Text(
              '장소 선택',
              style: TextStyle(
                fontFamily: 'NanumSquareRound',
                fontWeight: FontWeight.w700,
                color: _PickerColors.textMain,
              ),
            ),
            trailing: CupertinoButton(
              padding: EdgeInsets.zero,
              onPressed: () => Navigator.of(context).pop(),
              child: const Text(
                '닫기',
                style: TextStyle(
                  fontFamily: 'NanumSquareRound',
                  fontWeight: FontWeight.w600,
                  color: _PickerColors.primary,
                ),
              ),
            ),
          ),
          child: SafeArea(
            top: false,
            child: _PromisePlaceListBody(
              initialPlaceId: initialPlaceId,
              campusLifeZones: campusLifeZones,
              showcase: showcase,
            ),
          ),
        ),
      ),
    );
  }
}

class _PromisePlaceListBody extends StatefulWidget {
  const _PromisePlaceListBody({
    this.initialPlaceId,
    required this.campusLifeZones,
    this.showcase = false,
  });

  final String? initialPlaceId;
  final Set<String> campusLifeZones;
  final bool showcase;

  @override
  State<_PromisePlaceListBody> createState() => _PromisePlaceListBodyState();
}

class _PromisePlaceListBodyState extends State<_PromisePlaceListBody> {
  PromisePlaceService? _service;
  List<PromisePlace> _places = [];
  bool _loading = true;
  String? _error;
  _PlaceCategoryFilter _filter = _PlaceCategoryFilter.all;
  String? _expandedPlaceId;

  @override
  void initState() {
    super.initState();
    if (widget.showcase) {
      _loading = false;
      return;
    }
    _service = PromisePlaceService();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final list = await _service!.loadPlaces(
        campusLifeZones: widget.campusLifeZones,
      );
      if (!mounted) return;
      setState(() {
        _places = list;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _places = [];
        _loading = false;
        _error = e.toString();
      });
    }
  }

  List<PromisePlace> get _visiblePlaces {
    final allPlaces = [..._campusPlaces, ..._places];
    return allPlaces.where((e) => _placeMatchesFilter(e, _filter)).toList();
  }

  List<PromisePlace> get _campusPlaces {
    final zones = widget.showcase
        ? const <String>{CampusLifeZones.songdo}
        : widget.campusLifeZones;
    return PromiseCampusPlaces.options
        .where((place) => zones.contains(place.campusLifeZone))
        .toList();
  }

  void _setFilter(_PlaceCategoryFilter f) {
    setState(() {
      _filter = f;
      final visible = [
        ..._campusPlaces,
        ..._places,
      ].where((e) => _placeMatchesFilter(e, f)).toList();
      if (_expandedPlaceId != null &&
          !visible.any((e) => e.placeId == _expandedPlaceId)) {
        _expandedPlaceId = null;
      }
    });
  }

  void _toggleExpand(String placeId) {
    setState(() {
      _expandedPlaceId = _expandedPlaceId == placeId ? null : placeId;
    });
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Center(child: CupertinoActivityIndicator());
    }

    if (_places.isEmpty && _campusPlaces.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Text(
                '표시할 장소가 없어요',
                style: TextStyle(
                  fontFamily: 'NanumSquareRound',
                  fontSize: 16,
                  fontWeight: FontWeight.w600,
                  color: _PickerColors.textMain,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                _error != null
                    ? _error!
                    : 'Firebase에 place_catalog_items 를 추가하고,\n'
                          'place_catalog_meta/current 의 version 을 올려 주세요.\n'
                          '(오프라인이면 마지막으로 받아 둔 캐시만 씁니다)',
                textAlign: TextAlign.center,
                style: const TextStyle(
                  fontFamily: 'NanumSquareRound',
                  fontSize: 12,
                  height: 1.35,
                  color: _PickerColors.textSubtle,
                ),
              ),
            ],
          ),
        ),
      );
    }

    final visible = _visiblePlaces;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 12, 20, 4),
          child: Row(
            children: [
              const Expanded(
                child: Text(
                  '카테고리',
                  style: TextStyle(
                    fontFamily: 'NanumSquareRound',
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                    color: _PickerColors.textSubtle,
                  ),
                ),
              ),
              CupertinoButton(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                minimumSize: Size.zero,
                onPressed: () async {
                  setState(() => _loading = true);
                  await _service!.refreshFromRemote(
                    campusLifeZones: widget.campusLifeZones,
                  );
                  await _load();
                },
                child: const Text(
                  '새로고침',
                  style: TextStyle(
                    fontFamily: 'NanumSquareRound',
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                    color: _PickerColors.primary,
                  ),
                ),
              ),
            ],
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 0, 20, 10),
          child: Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _FilterChip(
                label: '캠퍼스 안',
                selected: _filter == _PlaceCategoryFilter.campus,
                onTap: () => _setFilter(_PlaceCategoryFilter.campus),
              ),
              _FilterChip(
                label: '전체',
                selected: _filter == _PlaceCategoryFilter.all,
                onTap: () => _setFilter(_PlaceCategoryFilter.all),
              ),
              _FilterChip(
                label: '카페',
                selected: _filter == _PlaceCategoryFilter.cafe,
                onTap: () => _setFilter(_PlaceCategoryFilter.cafe),
              ),
              _FilterChip(
                label: '식당',
                selected: _filter == _PlaceCategoryFilter.restaurant,
                onTap: () => _setFilter(_PlaceCategoryFilter.restaurant),
              ),
              _FilterChip(
                label: '술집/바',
                selected: _filter == _PlaceCategoryFilter.bar,
                onTap: () => _setFilter(_PlaceCategoryFilter.bar),
              ),
              _FilterChip(
                label: '그 외 장소',
                selected: _filter == _PlaceCategoryFilter.other,
                onTap: () => _setFilter(_PlaceCategoryFilter.other),
              ),
            ],
          ),
        ),
        if (visible.isEmpty)
          const Expanded(
            child: Center(
              child: Padding(
                padding: EdgeInsets.all(24),
                child: Text(
                  '이 카테고리에 해당하는 장소가 없어요',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontFamily: 'NanumSquareRound',
                    fontSize: 14,
                    color: _PickerColors.textSubtle,
                  ),
                ),
              ),
            ),
          )
        else
          Expanded(
            child: ListView.builder(
              padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
              itemCount:
                  visible.length +
                  (_filter == _PlaceCategoryFilter.campus &&
                          (widget.showcase ||
                              widget.campusLifeZones.contains(
                                CampusLifeZones.songdo,
                              ))
                      ? 1
                      : 0),
              itemBuilder: (context, i) {
                if (i == visible.length) {
                  return Padding(
                    padding: const EdgeInsets.only(bottom: 10),
                    child: _CustomCampusPlaceCard(
                      onTap: _showCustomCampusPlaceDialog,
                    ),
                  );
                }
                final p = visible[i];
                final isInitial = widget.initialPlaceId == p.placeId;
                final expanded = _expandedPlaceId == p.placeId;
                return Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: _ExpandablePlaceCard(
                    place: p,
                    isInitial: isInitial,
                    expanded: expanded,
                    onHeaderTap: () => _toggleExpand(p.placeId),
                    onSelect: () => Navigator.of(context).pop(p),
                  ),
                );
              },
            ),
          ),
      ],
    );
  }

  Future<void> _showCustomCampusPlaceDialog() async {
    final controller = TextEditingController();
    final place = await showCupertinoDialog<PromisePlace>(
      context: context,
      builder: (dialogContext) => CupertinoAlertDialog(
        title: const Text('장소 직접 입력'),
        content: Column(
          children: [
            const SizedBox(height: 12),
            CupertinoTextField(
              controller: controller,
              autofocus: true,
              placeholder: '예) 학생회관 1층 앞',
              textCapitalization: TextCapitalization.words,
            ),
          ],
        ),
        actions: [
          CupertinoDialogAction(
            onPressed: () => Navigator.of(dialogContext).pop(),
            child: const Text('취소'),
          ),
          CupertinoDialogAction(
            isDefaultAction: true,
            onPressed: () {
              final name = controller.text.trim();
              if (name.isEmpty) return;
              Navigator.of(dialogContext).pop(PromiseCampusPlaces.custom(name));
            },
            child: const Text('선택'),
          ),
        ],
      ),
    );
    controller.dispose();
    if (place != null && mounted) Navigator.of(context).pop(place);
  }
}

class _CustomCampusPlaceCard extends StatelessWidget {
  const _CustomCampusPlaceCard({required this.onTap});

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: onTap,
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 15),
        decoration: BoxDecoration(
          color: CupertinoColors.white,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: _PickerColors.primarySoft),
        ),
        child: const Row(
          children: [
            Icon(CupertinoIcons.pencil, color: _PickerColors.primary, size: 18),
            SizedBox(width: 10),
            Text(
              '직접 입력',
              style: TextStyle(
                fontFamily: 'NanumSquareRound',
                fontSize: 15,
                fontWeight: FontWeight.w700,
                color: _PickerColors.primary,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _FilterChip extends StatelessWidget {
  const _FilterChip({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: Size.zero,
      onPressed: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(
          color: selected
              ? _PickerColors.primarySoft.withValues(
                  alpha: _PickerColors.fillAlpha,
                )
              : CupertinoColors.white,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: selected ? _PickerColors.primary : _PickerColors.stone100,
          ),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontFamily: 'NanumSquareRound',
            fontSize: 13,
            fontWeight: FontWeight.w700,
            color: selected ? _PickerColors.primary : _PickerColors.textMain,
          ),
        ),
      ),
    );
  }
}

class _ExpandablePlaceCard extends StatelessWidget {
  const _ExpandablePlaceCard({
    required this.place,
    required this.isInitial,
    required this.expanded,
    required this.onHeaderTap,
    required this.onSelect,
  });

  final PromisePlace place;
  final bool isInitial;
  final bool expanded;
  final VoidCallback onHeaderTap;
  final VoidCallback onSelect;

  @override
  Widget build(BuildContext context) {
    return AnimatedContainer(
      duration: const Duration(milliseconds: 220),
      curve: Curves.easeInOut,
      decoration: BoxDecoration(
        color: isInitial
            ? _PickerColors.primarySoft.withValues(
                alpha: _PickerColors.fillAlpha,
              )
            : CupertinoColors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: expanded || isInitial
              ? _PickerColors.primary
              : _PickerColors.stone100,
          width: expanded ? 1.5 : 1,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          CupertinoButton(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
            onPressed: onHeaderTap,
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    place.name,
                    maxLines: expanded ? 3 : 2,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontFamily: 'NanumSquareRound',
                      fontSize: 15,
                      fontWeight: FontWeight.w700,
                      color: isInitial
                          ? _PickerColors.primary
                          : _PickerColors.textMain,
                    ),
                  ),
                ),
                Text(
                  PromisePlaceCategory.label(place.category),
                  style: const TextStyle(
                    fontFamily: 'NanumSquareRound',
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                    color: _PickerColors.textSubtle,
                  ),
                ),
                const SizedBox(width: 6),
                Icon(
                  expanded
                      ? CupertinoIcons.chevron_up
                      : CupertinoIcons.chevron_down,
                  size: 18,
                  color: _PickerColors.textSubtle,
                ),
              ],
            ),
          ),
          AnimatedCrossFade(
            duration: const Duration(milliseconds: 240),
            sizeCurve: Curves.easeInOut,
            firstCurve: Curves.easeInOut,
            secondCurve: Curves.easeInOut,
            crossFadeState: expanded
                ? CrossFadeState.showSecond
                : CrossFadeState.showFirst,
            firstChild: const SizedBox.shrink(),
            secondChild: _InlinePlaceDetail(
              key: ValueKey(place.placeId),
              place: place,
              onSelect: onSelect,
            ),
          ),
        ],
      ),
    );
  }
}

class _InlinePlaceDetail extends StatefulWidget {
  const _InlinePlaceDetail({
    super.key,
    required this.place,
    required this.onSelect,
  });

  final PromisePlace place;
  final VoidCallback onSelect;

  @override
  State<_InlinePlaceDetail> createState() => _InlinePlaceDetailState();
}

class _InlinePlaceDetailState extends State<_InlinePlaceDetail> {
  String? _distanceLabel;
  bool _locLoading = true;
  String? _locNote;

  @override
  void initState() {
    super.initState();
    if (widget.place.category != PromisePlaceCategory.campus &&
        !widget.place.isCustomInput &&
        widget.place.hasCoordinates) {
      _resolveDistance();
    } else {
      _locLoading = false;
    }
  }

  Future<void> _resolveDistance() async {
    final p = widget.place;
    try {
      var perm = await Geolocator.checkPermission();
      if (perm == LocationPermission.denied) {
        perm = await Geolocator.requestPermission();
      }
      if (perm == LocationPermission.deniedForever ||
          perm == LocationPermission.denied) {
        if (mounted) {
          setState(() {
            _locLoading = false;
            _locNote = '위치 권한이 없어 거리를 표시할 수 없어요';
          });
        }
        return;
      }

      final pos = await Geolocator.getCurrentPosition();
      final meters = Geolocator.distanceBetween(
        pos.latitude,
        pos.longitude,
        p.lat,
        p.lng,
      );
      String label;
      if (meters < 1000) {
        label = '${meters.round()}m';
      } else {
        label = '${(meters / 1000).toStringAsFixed(1)}km';
      }
      if (mounted) {
        setState(() {
          _distanceLabel = label;
          _locLoading = false;
        });
      }
    } catch (_) {
      if (mounted) {
        setState(() {
          _locLoading = false;
          _locNote = '현재 위치를 가져오지 못했어요';
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final p = widget.place;
    final showDetails = p.category != PromisePlaceCategory.campus;
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Container(height: 1, color: _PickerColors.stone100),
          const SizedBox(height: 14),
          if (showDetails) ...[
            Text(
              p.description.isNotEmpty ? p.description : '설명이 아직 없어요.',
              style: const TextStyle(
                fontFamily: 'NanumSquareRound',
                fontSize: 14,
                height: 1.45,
                color: _PickerColors.textMain,
              ),
            ),
            const SizedBox(height: 12),
            if (!p.isCustomInput)
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Padding(
                    padding: EdgeInsets.only(top: 2),
                    child: Icon(
                      CupertinoIcons.placemark,
                      size: 18,
                      color: _PickerColors.textSubtle,
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      p.address.isNotEmpty ? p.address : '주소 정보 없음',
                      style: const TextStyle(
                        fontFamily: 'NanumSquareRound',
                        fontSize: 14,
                        height: 1.4,
                        color: _PickerColors.textMain,
                      ),
                    ),
                  ),
                ],
              ),
          ],
          if (!p.isCustomInput &&
              p.category != PromisePlaceCategory.campus) ...[
            const SizedBox(height: 12),
            if (_locLoading)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 8),
                child: Center(child: CupertinoActivityIndicator()),
              )
            else if (_distanceLabel != null)
              Text(
                '내 위치 기준 약 $_distanceLabel',
                style: const TextStyle(
                  fontFamily: 'NanumSquareRound',
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                  color: _PickerColors.primary,
                ),
              )
            else if (_locNote != null)
              Text(
                _locNote!,
                style: const TextStyle(
                  fontFamily: 'NanumSquareRound',
                  fontSize: 12,
                  color: _PickerColors.textSubtle,
                ),
              ),
            const SizedBox(height: 16),
            Row(
              children: [
                Expanded(
                  child: CupertinoButton(
                    padding: EdgeInsets.zero,
                    onPressed: () {
                      PromiseMapLaunch.openNaverMap(
                        lat: p.lat,
                        lng: p.lng,
                        name: p.name,
                        naverPlaceId: p.externalLinks.naverPlaceId,
                      );
                    },
                    child: Container(
                      height: 48,
                      alignment: Alignment.center,
                      decoration: BoxDecoration(
                        color: const Color(0xFF03C75A),
                        borderRadius: BorderRadius.circular(14),
                      ),
                      child: const Text(
                        '네이버지도',
                        style: TextStyle(
                          fontFamily: 'NanumSquareRound',
                          fontSize: 14,
                          fontWeight: FontWeight.w800,
                          color: CupertinoColors.white,
                        ),
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: CupertinoButton(
                    padding: EdgeInsets.zero,
                    onPressed: () {
                      PromiseMapLaunch.openKakaoMap(
                        lat: p.lat,
                        lng: p.lng,
                        name: p.name,
                        kakaoPlaceId: p.externalLinks.kakaoPlaceId,
                      );
                    },
                    child: Container(
                      height: 48,
                      alignment: Alignment.center,
                      decoration: BoxDecoration(
                        color: const Color(0xFFFEE500),
                        borderRadius: BorderRadius.circular(14),
                      ),
                      child: const Text(
                        '카카오맵',
                        style: TextStyle(
                          fontFamily: 'NanumSquareRound',
                          fontSize: 14,
                          fontWeight: FontWeight.w800,
                          color: Color(0xFF191919),
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ],
          const SizedBox(height: 14),
          CupertinoButton(
            padding: EdgeInsets.zero,
            onPressed: widget.onSelect,
            child: Container(
              width: double.infinity,
              height: 52,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: _PickerColors.primary,
                borderRadius: BorderRadius.circular(16),
              ),
              child: const Text(
                '이 장소 선택',
                style: TextStyle(
                  fontFamily: 'NanumSquareRound',
                  fontSize: 15,
                  fontWeight: FontWeight.w700,
                  color: CupertinoColors.white,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
