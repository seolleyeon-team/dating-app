// =============================================================================
// 설레연 공통 하단 네비게이션 바
// 경로: lib/shared/widgets/seolleyeon_bottom_navigation_bar.dart
//
// Instagram-inspired minimal tab layout + Seolleyeon neumorphism/glassmorphism
// 5개 탭 화면 모두 이 위젯 하나로 통합
// =============================================================================

import 'dart:ui';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' show Theme, Brightness;
import 'package:flutter/services.dart';

import '../../core/constants/app_colors.dart';

// =============================================================================
// 탭 enum
// =============================================================================
enum BottomNavTab { matching, chat, event, community, profile }

// =============================================================================
// 공통 bottom navigation bar
// =============================================================================
class SeolleyeonBottomNavigationBar extends StatelessWidget {
  /// 현재 활성 탭
  final BottomNavTab currentTab;

  /// 탭 선택 콜백 (인덱스 기반 — MainScaffold의 CupertinoTabController와 호환)
  final Function(int index)? onTap;

  /// 채팅 탭 뱃지 표시 여부
  final bool showChatBadge;

  const SeolleyeonBottomNavigationBar({
    super.key,
    required this.currentTab,
    this.onTap,
    this.showChatBadge = false,
  });

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final seol = Theme.of(context).extension<SeolThemeColors>()!;

    // ── Bar background ──
    // Light: translucent ivory-white + soft lavender tint (frosted)
    // Dark: translucent charcoal-plum glass
    final navBg = isDark
        ? const Color(0xFF221A28).withValues(alpha: 0.92)
        : CupertinoColors.white.withValues(alpha: 0.95);

    // ── Bar border ──
    final navBorder = isDark
        ? const Color(0xFF302838)
        : const Color(0xFFF3F4F6); // _AppColors.gray100

    return ClipRRect(
      borderRadius: BorderRadius.circular(32),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 24),
          decoration: BoxDecoration(
            color: navBg,
            borderRadius: BorderRadius.circular(32),
            border: Border.all(color: navBorder),
            boxShadow: [
              BoxShadow(
                color: CupertinoColors.black.withValues(alpha: 0.05),
                blurRadius: 20,
                offset: const Offset(0, 4),
              ),
            ],
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              _SeolNavItem(
                icon: CupertinoIcons.heart_fill,
                label: '설레연',
                isActive: currentTab == BottomNavTab.matching,
                onTap: () {
                  HapticFeedback.selectionClick();
                  onTap?.call(0);
                },
              ),
              _SeolNavItem(
                icon: currentTab == BottomNavTab.chat
                    ? CupertinoIcons.chat_bubble_fill
                    : CupertinoIcons.chat_bubble,
                label: '채팅',
                isActive: currentTab == BottomNavTab.chat,
                showBadge: showChatBadge,
                onTap: () {
                  HapticFeedback.selectionClick();
                  onTap?.call(1);
                },
              ),
              _SeolNavItem(
                icon: currentTab == BottomNavTab.event
                    ? CupertinoIcons.calendar_today
                    : CupertinoIcons.calendar,
                label: '이벤트',
                isActive: currentTab == BottomNavTab.event,
                onTap: () {
                  HapticFeedback.selectionClick();
                  onTap?.call(2);
                },
              ),
              _SeolNavItem(
                icon: CupertinoIcons.tree,
                label: '대나무숲',
                isActive: currentTab == BottomNavTab.community,
                onTap: () {
                  HapticFeedback.selectionClick();
                  onTap?.call(3);
                },
              ),
              _SeolNavItem(
                icon: currentTab == BottomNavTab.profile
                    ? CupertinoIcons.person_fill
                    : CupertinoIcons.person,
                label: '내 페이지',
                isActive: currentTab == BottomNavTab.profile,
                onTap: () {
                  HapticFeedback.selectionClick();
                  onTap?.call(4);
                },
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// =============================================================================
// 개별 nav 아이템
// =============================================================================
class _SeolNavItem extends StatelessWidget {
  final IconData icon;
  final String label;
  final bool isActive;
  final bool showBadge;
  final VoidCallback? onTap;

  const _SeolNavItem({
    required this.icon,
    required this.label,
    this.isActive = false,
    this.showBadge = false,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final primary = Theme.of(context).colorScheme.primary;
    final inactiveColor = Theme.of(context).brightness == Brightness.dark
        ? const Color(0xFF7A6B76)
        : const Color(0xFF9CA3AF); // gray400

    return Semantics(
      label: label,
      button: true,
      selected: isActive,
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        minSize: 0,
        onPressed: onTap,
        child: SizedBox(
          width: 48,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Stack(
                clipBehavior: Clip.none,
                children: [
                  Icon(
                    icon,
                    size: 24,
                    color: isActive ? primary : inactiveColor,
                  ),
                  if (showBadge)
                    Positioned(
                      right: -2,
                      top: -2,
                      child: Container(
                        width: 8,
                        height: 8,
                        decoration: const BoxDecoration(
                          color: Color(0xFF10B981),
                          shape: BoxShape.circle,
                        ),
                      ),
                    ),
                ],
              ),
              const SizedBox(height: 4),
              Text(
                label,
                style: TextStyle(
                  fontFamily: 'Pretendard',
                  fontSize: 10,
                  fontWeight: isActive ? FontWeight.w600 : FontWeight.w500,
                  color: isActive ? primary : inactiveColor,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// =============================================================================
// Helper: Positioned wrapper
// 모든 화면에서 동일한 위치에 bottom nav를 배치하기 위한 유틸 위젯
// 기준: my_page_screen.dart — left:24, right:24, bottom:bottomPadding+16
// =============================================================================
class SeolleyeonBottomNavPositioned extends StatelessWidget {
  final BottomNavTab currentTab;
  final Function(int index)? onTap;
  final bool showChatBadge;

  const SeolleyeonBottomNavPositioned({
    super.key,
    required this.currentTab,
    this.onTap,
    this.showChatBadge = false,
  });

  @override
  Widget build(BuildContext context) {
    final bottomPadding = MediaQuery.of(context).padding.bottom;

    return Positioned(
      left: 16,
      right: 16,
      bottom: bottomPadding + 16,
      child: SeolleyeonBottomNavigationBar(
        currentTab: currentTab,
        onTap: onTap,
        showChatBadge: showChatBadge,
      ),
    );
  }
}
