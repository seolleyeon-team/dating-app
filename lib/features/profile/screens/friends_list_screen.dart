// =============================================================================
// 친구 목록 화면
// 경로: lib/features/friends/screens/friends_list_screen.dart
//
// 사용 예시:
// Navigator.push(
//   context,
//   CupertinoPageRoute(builder: (_) => const FriendsListScreen()),
// );
// =============================================================================

import 'dart:ui';
import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';

// =============================================================================
// 색상 상수
// =============================================================================
class _AppColors {
  static const Color primary = Color(0xFFFF8FAB);
  static const Color secondary = Color(0xFFD4B2FF);
  static const Color backgroundLight = Color(0xFFFFFFFF);
  static const Color surfaceLight = Color(0xFFF9FAFB);
  static const Color textLight = Color(0xFF1F2937);
  static const Color textMuted = Color(0xFF6B7280);
  static const Color borderLight = Color(0xFFE5E7EB);
  static const Color blue500 = Color(0xFF3B82F6);
}

// =============================================================================
// 친구 모델
// =============================================================================
class _Friend {
  final String id;
  final String username;
  final String displayName;
  final String? detail;
  final String imageUrl;
  final bool hasStory;
  final bool isOnline;
  final bool hasNewPost;

  const _Friend({
    required this.id,
    required this.username,
    required this.displayName,
    this.detail,
    required this.imageUrl,
    this.hasStory = false,
    this.isOnline = false,
    this.hasNewPost = false,
  });
}

// =============================================================================
// 메인 화면
// =============================================================================
class FriendsListScreen extends StatefulWidget {
  final VoidCallback? onBack;
  final Function(String)? onMessage;
  final Function(int)? onTabChanged;

  const FriendsListScreen({
    super.key,
    this.onBack,
    this.onMessage,
    this.onTabChanged,
  });

  @override
  State<FriendsListScreen> createState() => _FriendsListScreenState();
}

class _FriendsListScreenState extends State<FriendsListScreen> {
  int _selectedTab = 0;
  int _selectedFilter = 0;
  final List<String> _tabs = ['친구', '팔로잉', '차단', '초대'];
  final List<String> _filters = ['최근 추가', '활동 중', '같은 학과', '24학번'];
  final TextEditingController _searchController = TextEditingController();

  final List<_Friend> _friends = const [
    _Friend(
      id: '1',
      username: 'junse0_06',
      displayName: '권준서',
      imageUrl:
          'https://lh3.googleusercontent.com/aida-public/AB6AXuAa0UY181kgkM55t7yaeeN4Q9-JOjnCBu8rOgGYGRM3tsO_x4ebBLqIc40yLNVTwYHwro56hXC2m8ZeyobvaoePlpF3ptooVr-1c3Cw4rxg4wr5e2Gr2KERcwVFjG7_BK5mQ8xrnz1wpHtMngacVuB2gyMq1w3FsLgEa8QSPZ5d2EJKvOvavjjr00Bd9uaNNtKd86q2FGR6wmJVOOzbE1wtwuj8BdTNcuQZtj6LSrMifGXDIIn68ntb8KQHkkLwPG2IfwGz7eXDKww',
      hasStory: true,
      isOnline: true,
      hasNewPost: true,
    ),
    _Friend(
      id: '2',
      username: 'fuertofista._.7',
      displayName: '경영학과',
      detail: "'01",
      imageUrl:
          'https://lh3.googleusercontent.com/aida-public/AB6AXuCKHgw3m130TcE3P-Z-HHnzPsm4w9iu2a2G6-v6t4OkAk88n_GXuEZ40GMpwbTNQhdE8mUkkdHS92tJZN8iWBYY5nH1N-nHCtU0999MdfXdZS9RoN8xpe7MzoJmlRvWAdbCJTlRJcTbeFeVkEfy5uM1868yefPDba6t46jGWdKRpqLbpiKCwXlxy_cepJ4zPbPue2TOEcRtr-esyYlU8gId4kx92SRXwv8gHBK5G_tb5iPGf-H0S_E1XIKvNzJ4bAmyyIP2glxf_tk',
    ),
    _Friend(
      id: '3',
      username: 'dowon_songs',
      displayName: '김도원 미학',
      imageUrl:
          'https://lh3.googleusercontent.com/aida-public/AB6AXuDyDo9HJleK2gLICN5vjDiJhUj6PFTVzIQcdbdOmius7LTAgEYvb7jD7-WcHyr7XdoTDGGR4cf9ko9WZm2OMulckRqMsBOsoQ78HQow0mzHcKLedlOy33p13z1dbn4gdG4u7Jnnf56OptZSioWuIeH_c9wJhP6bV3NKTdVO9SmXnG1YGZsIlLddNOM6JM4i8YV_TaIg3Uy6EXg_uQXBlbxaa6cqNK8Vlz13pc0S1-yO-zfsZIH02COIiSUmxBdUF77785KtGXEvonM',
      hasStory: true,
      isOnline: true,
      hasNewPost: true,
    ),
    _Friend(
      id: '4',
      username: 'the_d1ary_21',
      displayName: '<일기장>',
      imageUrl:
          'https://lh3.googleusercontent.com/aida-public/AB6AXuBIPepSplnEBD_mCsDTz7ai362iwLFy6VFR8kRs9s0oV3j315wS5qXnAdECoXVUR3SZbmUSZC2C8GfpV3Y8sO2yxL5qsY3sMa88zTKlFQyfkWbd3AyHyAFPrnhqSh-_GhO5zFHpGwq5SnZSu2F6DGVZD1Gjb87iGVPz02RsOOfaIqW6wBks0YqnFsT714FDZk6ygS8nTox90lNsFdZ5GOfABk3TeSdUrgARX9_Da31XxJcWp-GdaY7m66YONVD2mzwWA2R2rE5os1Q',
    ),
    _Friend(
      id: '5',
      username: 'yv_beomy',
      displayName: '이윤범',
      detail: '산업디자인',
      imageUrl:
          'https://lh3.googleusercontent.com/aida-public/AB6AXuDRq2_Hc110Cys3rbxdqwIU2EK7uy2_kPMhS9j9svuE1HBySqQLPFrnizaTyQKLeIl1toucBs6thZuboH9gdqvJsMuufdLrEULVbVF0X4pawwtx_kLHCf4QWPHlXCL7rW7m_AJBzb_7-n1ajW_2o2MCeu4umDVFjrPSEDihbDpXaaGKw7Qep38XRYilFzU2bLEnX4VmmMYNtgm-fQRfVeG1JMMjcN5EFnPZ25oEcG3JRebUqUXlIzi2-7mocXM42hO-wUcpv0viQwI',
      hasStory: true,
      isOnline: true,
      hasNewPost: true,
    ),
    _Friend(
      id: '6',
      username: 'woojinjeong',
      displayName: '정우진',
      imageUrl:
          'https://lh3.googleusercontent.com/aida-public/AB6AXuCnw3bsBQkmzHmRqhxXSLOAirwsVrhAWZxVqC_DdwMqXknLr_SUVWmSRaHvglHLOqM3wTEdKVVcZ_B9K1rc57OmHFxn67VCKqQ-dQoyQKlUT1LkvEi5f8rdkdDMNWp2tl5pSvY5ukPolH-indE2J3_3-GIAJoEQ9bnC_ExCHdzs1bL11Dq3eDS13kiEa1jJP9mA3Y7Ov94Gh0s1XPZL4rSuT7D1aYQz3C7Dosq9M0fo3jO_UqXTbhWRLJt1dA2VhLup3z3d0o9sM-Y',
    ),
    _Friend(
      id: '7',
      username: 'nosin_wsbin',
      displayName: '왕성빈',
      imageUrl:
          'https://lh3.googleusercontent.com/aida-public/AB6AXuBhamgFZH9V5s7nA9KBmRidYB0BronuTfmmKhBE6iMZ43BdQgxD6E49gKcDy9ux_nfd8aygLhE_n8Clw77LHGMybI6PJ7O2AfgWF1nE8mnHy7v4jl-SYxwKxMsc5iPWtEuzs5Ff8dCe5CbQsz96LsyZQMUqqV1NTee1ln2sFCBIlVt3gtaaCn3RaRU1ajET6vcI3A1kb_CK9ekNJ7DkApDZW2UAYIg9uwRCEFu_R6aPMIIIL0XNkpbYWE02HDX947BN2pkoY51_fPk',
    ),
  ];

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final bottomPadding = MediaQuery.of(context).padding.bottom;

    return CupertinoPageScaffold(
      backgroundColor: _AppColors.backgroundLight,
      child: Stack(
        children: [
          // 배경 글로우
          Positioned(
            top: -80,
            right: -80,
            child: Container(
              width: 384,
              height: 384,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: _AppColors.secondary.withValues(alpha: 0.1),
              ),
            ),
          ),
          Positioned(
            top: 160,
            left: -80,
            child: Container(
              width: 288,
              height: 288,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: _AppColors.primary.withValues(alpha: 0.05),
              ),
            ),
          ),
          // 메인 콘텐츠
          SafeArea(
            child: Column(
              children: [
                // 헤더
                _Header(onBack: widget.onBack),
                // 탭 바
                _TabBar(
                  tabs: _tabs,
                  selectedIndex: _selectedTab,
                  onTabChanged: (index) {
                    setState(() => _selectedTab = index);
                    widget.onTabChanged?.call(index);
                  },
                ),
                // 검색 & 필터
                Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    children: [
                      // 안내 메시지
                      Container(
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: _AppColors.surfaceLight,
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Icon(
                              CupertinoIcons.info_circle,
                              size: 14,
                              color: _AppColors.textMuted,
                            ),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Text(
                                '지인을 차단하면 추천 목록에서 영구적으로 제외돼요. 안심하고 새로운 인연을 찾아보세요.',
                                style: TextStyle(
                                  fontFamily: 'Noto Sans KR',
                                  fontSize: 12,
                                  height: 1.5,
                                  color: _AppColors.textMuted,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 16),
                      // 검색창
                      CupertinoTextField(
                        controller: _searchController,
                        placeholder: '이름 또는 학과 검색',
                        placeholderStyle: const TextStyle(
                          fontFamily: 'Noto Sans KR',
                          color: CupertinoColors.placeholderText,
                        ),
                        prefix: Padding(
                          padding: const EdgeInsets.only(left: 12),
                          child: Icon(
                            CupertinoIcons.search,
                            size: 20,
                            color: _AppColors.textMuted,
                          ),
                        ),
                        padding: const EdgeInsets.fromLTRB(8, 14, 16, 14),
                        decoration: BoxDecoration(
                          color: _AppColors.surfaceLight,
                          borderRadius: BorderRadius.circular(20),
                        ),
                        style: const TextStyle(
                          fontFamily: 'Noto Sans KR',
                          fontSize: 14,
                        ),
                      ),
                      const SizedBox(height: 12),
                      // 필터 칩
                      SizedBox(
                        height: 32,
                        child: ListView.separated(
                          scrollDirection: Axis.horizontal,
                          itemCount: _filters.length,
                          separatorBuilder: (_, __) => const SizedBox(width: 8),
                          itemBuilder: (context, index) {
                            final isSelected = _selectedFilter == index;
                            return CupertinoButton(
                              padding: EdgeInsets.zero,
                              onPressed: () =>
                                  setState(() => _selectedFilter = index),
                              child: Container(
                                padding: const EdgeInsets.symmetric(
                                  horizontal: 16,
                                ),
                                decoration: BoxDecoration(
                                  color: isSelected
                                      ? _AppColors.primary
                                      : _AppColors.surfaceLight,
                                  borderRadius: BorderRadius.circular(16),
                                  border: isSelected
                                      ? null
                                      : Border.all(
                                          color: _AppColors.borderLight,
                                        ),
                                  boxShadow: isSelected
                                      ? [
                                          BoxShadow(
                                            color: _AppColors.primary
                                                .withValues(alpha: 0.2),
                                            blurRadius: 8,
                                            offset: const Offset(0, 2),
                                          ),
                                        ]
                                      : null,
                                ),
                                child: Center(
                                  child: Text(
                                    _filters[index],
                                    style: TextStyle(
                                      fontFamily: 'Noto Sans KR',
                                      fontSize: 12,
                                      fontWeight: FontWeight.w500,
                                      color: isSelected
                                          ? CupertinoColors.white
                                          : _AppColors.textMuted,
                                    ),
                                  ),
                                ),
                              ),
                            );
                          },
                        ),
                      ),
                    ],
                  ),
                ),
                // 친구 목록 헤더
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Row(
                        children: [
                          const Text(
                            '친구 목록',
                            style: TextStyle(
                              fontFamily: 'Noto Sans KR',
                              fontSize: 14,
                              fontWeight: FontWeight.w600,
                              color: _AppColors.textLight,
                            ),
                          ),
                          const SizedBox(width: 4),
                          Text(
                            '${_friends.length}',
                            style: const TextStyle(
                              fontFamily: 'Noto Sans KR',
                              fontSize: 14,
                              fontWeight: FontWeight.w600,
                              color: _AppColors.primary,
                            ),
                          ),
                        ],
                      ),
                      CupertinoButton(
                        padding: EdgeInsets.zero,
                        onPressed: () {},
                        child: Row(
                          children: [
                            Text(
                              '정렬 기준 기본',
                              style: TextStyle(
                                fontFamily: 'Noto Sans KR',
                                fontSize: 12,
                                color: _AppColors.textMuted,
                              ),
                            ),
                            const SizedBox(width: 4),
                            Icon(
                              CupertinoIcons.sort_down,
                              size: 14,
                              color: _AppColors.textMuted,
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
                // 친구 리스트
                Expanded(
                  child: ListView.builder(
                    padding: EdgeInsets.fromLTRB(16, 8, 16, bottomPadding + 16),
                    itemCount: _friends.length,
                    itemBuilder: (context, index) => _FriendItem(
                      friend: _friends[index],
                      onMessage: () =>
                          widget.onMessage?.call(_friends[index].id),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// 헤더
// =============================================================================
class _Header extends StatelessWidget {
  final VoidCallback? onBack;

  const _Header({this.onBack});

  @override
  Widget build(BuildContext context) {
    return ClipRect(
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          color: _AppColors.backgroundLight.withValues(alpha: 0.8),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              CupertinoButton(
                padding: EdgeInsets.zero,
                onPressed: () {
                  HapticFeedback.lightImpact();
                  if (onBack != null) {
                    onBack!.call();
                  } else {
                    Navigator.of(context).pop();
                  }
                },
                child: const Icon(
                  CupertinoIcons.back,
                  size: 24,
                  color: _AppColors.textLight,
                ),
              ),
              const Text(
                '친구',
                style: TextStyle(
                  fontFamily: 'Noto Sans KR',
                  fontSize: 18,
                  fontWeight: FontWeight.w700,
                  color: _AppColors.textLight,
                ),
              ),
              Row(
                children: [
                  CupertinoButton(
                    padding: EdgeInsets.zero,
                    onPressed: () {},
                    child: const Icon(
                      CupertinoIcons.search,
                      size: 24,
                      color: _AppColors.textLight,
                    ),
                  ),
                  CupertinoButton(
                    padding: EdgeInsets.zero,
                    onPressed: () {},
                    child: const Icon(
                      CupertinoIcons.line_horizontal_3_decrease,
                      size: 24,
                      color: _AppColors.textLight,
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// =============================================================================
// 탭 바
// =============================================================================
class _TabBar extends StatelessWidget {
  final List<String> tabs;
  final int selectedIndex;
  final ValueChanged<int> onTabChanged;

  const _TabBar({
    required this.tabs,
    required this.selectedIndex,
    required this.onTabChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        border: Border(
          bottom: BorderSide(color: _AppColors.borderLight, width: 1),
        ),
      ),
      child: Row(
        children: tabs.asMap().entries.map((entry) {
          final isSelected = entry.key == selectedIndex;
          return Expanded(
            child: CupertinoButton(
              padding: EdgeInsets.zero,
              onPressed: () => onTabChanged(entry.key),
              child: Container(
                padding: const EdgeInsets.symmetric(vertical: 12),
                decoration: BoxDecoration(
                  border: Border(
                    bottom: BorderSide(
                      color: isSelected
                          ? _AppColors.primary
                          : CupertinoColors.white.withValues(alpha: 0),
                      width: 2,
                    ),
                  ),
                ),
                child: Text(
                  entry.value,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontFamily: 'Noto Sans KR',
                    fontSize: 14,
                    fontWeight: isSelected ? FontWeight.w600 : FontWeight.w500,
                    color: isSelected
                        ? _AppColors.primary
                        : _AppColors.textMuted,
                  ),
                ),
              ),
            ),
          );
        }).toList(),
      ),
    );
  }
}

// =============================================================================
// 친구 아이템
// =============================================================================
class _FriendItem extends StatelessWidget {
  final _Friend friend;
  final VoidCallback? onMessage;

  const _FriendItem({required this.friend, this.onMessage});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        children: [
          // 아바타
          Stack(
            children: [
              Container(
                width: 56,
                height: 56,
                padding: const EdgeInsets.all(2),
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  gradient: friend.hasStory
                      ? const LinearGradient(
                          begin: Alignment.topLeft,
                          end: Alignment.bottomRight,
                          colors: [
                            Color(0xFFFACC15),
                            Color(0xFFEF4444),
                            Color(0xFFA855F7),
                          ],
                        )
                      : null,
                  border: friend.hasStory
                      ? null
                      : Border.all(color: _AppColors.borderLight),
                ),
                child: Container(
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    border: Border.all(
                      color: _AppColors.backgroundLight,
                      width: 2,
                    ),
                  ),
                  child: ClipOval(
                    child: Image.network(
                      friend.imageUrl,
                      fit: BoxFit.cover,
                      errorBuilder: (_, __, ___) =>
                          Container(color: _AppColors.surfaceLight),
                    ),
                  ),
                ),
              ),
              if (friend.isOnline)
                Positioned(
                  bottom: 0,
                  right: 0,
                  child: Container(
                    width: 14,
                    height: 14,
                    decoration: BoxDecoration(
                      color: _AppColors.blue500,
                      shape: BoxShape.circle,
                      border: Border.all(
                        color: _AppColors.backgroundLight,
                        width: 2,
                      ),
                    ),
                  ),
                ),
            ],
          ),
          const SizedBox(width: 16),
          // 정보
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  friend.username,
                  style: const TextStyle(
                    fontFamily: 'Noto Sans KR',
                    fontSize: 14,
                    fontWeight: FontWeight.w700,
                    color: _AppColors.textLight,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  friend.detail != null
                      ? '${friend.displayName} · ${friend.detail}'
                      : friend.displayName,
                  style: TextStyle(
                    fontFamily: 'Noto Sans KR',
                    fontSize: 12,
                    color: _AppColors.textMuted,
                  ),
                ),
                if (friend.hasNewPost) ...[
                  const SizedBox(height: 2),
                  const Text(
                    '새 게시물 1개',
                    style: TextStyle(
                      fontFamily: 'Noto Sans KR',
                      fontSize: 10,
                      fontWeight: FontWeight.w500,
                      color: _AppColors.blue500,
                    ),
                  ),
                ],
              ],
            ),
          ),
          // 버튼
          CupertinoButton(
            padding: EdgeInsets.zero,
            onPressed: onMessage,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              decoration: BoxDecoration(
                color: friend.hasNewPost
                    ? _AppColors.primary.withValues(alpha: 0.1)
                    : _AppColors.surfaceLight,
                borderRadius: BorderRadius.circular(16),
                border: friend.hasNewPost
                    ? null
                    : Border.all(color: _AppColors.borderLight),
              ),
              child: Text(
                '메시지',
                style: TextStyle(
                  fontFamily: 'Noto Sans KR',
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                  color: friend.hasNewPost
                      ? _AppColors.primary
                      : _AppColors.textLight,
                ),
              ),
            ),
          ),
          const SizedBox(width: 4),
          CupertinoButton(
            padding: EdgeInsets.zero,
            onPressed: () {},
            child: Icon(
              CupertinoIcons.ellipsis,
              size: 20,
              color: _AppColors.textMuted,
            ),
          ),
        ],
      ),
    );
  }
}
