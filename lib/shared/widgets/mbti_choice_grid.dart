import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../constants/profile_options.dart';

const _primary = Color(0xFFF5468C);
const _surface = Color(0xFFFFFFFF);
const _textSub = Color(0xFF6B7280);

/// The E/N/F/J · I/S/T/P selector shared by onboarding and profile editing.
///
/// Its sizing and decoration intentionally preserve the onboarding design.
class MbtiChoiceGrid extends StatelessWidget {
  final String selectedValue;
  final void Function(int dimensionIndex, String value) onSelect;
  final EdgeInsetsGeometry padding;

  const MbtiChoiceGrid({
    super.key,
    required this.selectedValue,
    required this.onSelect,
    this.padding = const EdgeInsets.all(8),
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: padding,
      child: Row(
        children: [
          for (
            var index = 0;
            index < profileMbtiDimensions.length;
            index++
          ) ...[
            if (index > 0) const SizedBox(width: 16),
            Expanded(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  _MbtiChoiceButton(
                    text: profileMbtiDimensions[index].first,
                    isSelected:
                        selectedValue.length > index &&
                        selectedValue[index] ==
                            profileMbtiDimensions[index].first,
                    onTap: () =>
                        onSelect(index, profileMbtiDimensions[index].first),
                  ),
                  const SizedBox(height: 16),
                  _MbtiChoiceButton(
                    text: profileMbtiDimensions[index].second,
                    isSelected:
                        selectedValue.length > index &&
                        selectedValue[index] ==
                            profileMbtiDimensions[index].second,
                    onTap: () =>
                        onSelect(index, profileMbtiDimensions[index].second),
                  ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _MbtiChoiceButton extends StatelessWidget {
  final String text;
  final bool isSelected;
  final VoidCallback onTap;

  const _MbtiChoiceButton({
    required this.text,
    required this.isSelected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () {
        HapticFeedback.lightImpact();
        onTap();
      },
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        width: double.infinity,
        height: 70,
        decoration: BoxDecoration(
          color: isSelected ? Colors.white : _surface,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: isSelected
                ? _primary.withValues(alpha: 0.1)
                : Colors.white.withValues(alpha: 0.4),
          ),
          boxShadow: isSelected
              ? [
                  BoxShadow(
                    color: _primary.withValues(alpha: 0.15),
                    blurRadius: 20,
                    offset: const Offset(0, 8),
                  ),
                ]
              : [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.05),
                    blurRadius: 10,
                    offset: const Offset(0, 4),
                  ),
                ],
        ),
        child: Center(
          child: Text(
            text,
            style: TextStyle(
              fontSize: 24,
              fontWeight: FontWeight.bold,
              color: isSelected ? _primary : _textSub.withValues(alpha: 0.5),
            ),
          ),
        ),
      ),
    );
  }
}
