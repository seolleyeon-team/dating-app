import 'package:flutter/widgets.dart';

/// Arranges six profile-photo slots in a compact mosaic.
///
/// The first slot spans a 2x2 area, slots 1 and 2 sit to its right, and the
/// remaining three slots form the bottom row.
class ProfilePhotoMosaic extends StatelessWidget {
  const ProfilePhotoMosaic({
    super.key,
    required this.itemBuilder,
    this.gap = 8,
    this.featuredBadge,
  });

  final IndexedWidgetBuilder itemBuilder;
  final double gap;
  final Widget? featuredBadge;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final cellSize = (constraints.maxWidth - (gap * 2)) / 3;
        final featuredSize = (cellSize * 2) + gap;

        Widget slot(int index, double size) {
          return SizedBox.square(
            dimension: size,
            child: index == 0 && featuredBadge != null
                ? Stack(
                    fit: StackFit.expand,
                    children: [
                      itemBuilder(context, index),
                      Positioned(
                        top: 8,
                        left: 8,
                        child: IgnorePointer(child: featuredBadge!),
                      ),
                    ],
                  )
                : itemBuilder(context, index),
          );
        }

        return SizedBox(
          height: constraints.maxWidth,
          child: Column(
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  slot(0, featuredSize),
                  SizedBox(width: gap),
                  Column(
                    children: [
                      slot(1, cellSize),
                      SizedBox(height: gap),
                      slot(2, cellSize),
                    ],
                  ),
                ],
              ),
              SizedBox(height: gap),
              Row(
                children: [
                  slot(3, cellSize),
                  SizedBox(width: gap),
                  slot(4, cellSize),
                  SizedBox(width: gap),
                  slot(5, cellSize),
                ],
              ),
            ],
          ),
        );
      },
    );
  }
}
