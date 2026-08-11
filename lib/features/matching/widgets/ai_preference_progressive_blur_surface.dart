import 'dart:ui' as ui;

import 'package:flutter/cupertino.dart';

/// Full-viewport AI preference image surface.
///
/// Every image layer uses the same [ImageProvider], `BoxFit.cover`, alignment,
/// and viewport geometry. Only the blur masks differ, which prevents the
/// cropped/duplicated-wallpaper artifact caused by separately fitted layers.
class AiPreferenceProgressiveBlurSurface extends StatelessWidget {
  const AiPreferenceProgressiveBlurSurface({
    super.key,
    required this.image,
    this.dragOffset = Offset.zero,
    this.rotationAngle = 0,
    this.errorBuilder,
    this.onFirstFrame,
  });

  final ImageProvider image;
  final Offset dragOffset;
  final double rotationAngle;
  final WidgetBuilder? errorBuilder;
  final VoidCallback? onFirstFrame;

  @override
  Widget build(BuildContext context) {
    return RepaintBoundary(
      child: Transform.translate(
        offset: dragOffset,
        child: Transform.rotate(
          angle: rotationAngle,
          child: Stack(
            key: const Key('ai_preference_visual_stack'),
            fit: StackFit.expand,
            children: [
              KeyedSubtree(
                key: const Key('ai_preference_sharp_base'),
                child: _coverImage(reportFirstFrame: true),
              ),
              _blurLayer(
                key: const Key('ai_preference_top_blur_mild'),
                sigma: 5,
                stops: const [0, 0.10, 0.24, 0.34],
                opacities: const [0.62, 0.36, 0.08, 0],
              ),
              _blurLayer(
                key: const Key('ai_preference_top_blur_medium'),
                sigma: 11,
                stops: const [0, 0.06, 0.16, 0.26],
                opacities: const [0.72, 0.54, 0.16, 0],
              ),
              _blurLayer(
                key: const Key('ai_preference_top_blur_strong'),
                sigma: 18,
                stops: const [0, 0.04, 0.10, 0.18],
                opacities: const [0.86, 0.58, 0.14, 0],
              ),
              _blurLayer(
                key: const Key('ai_preference_bottom_blur_mild'),
                sigma: 5,
                stops: const [0.56, 0.64, 0.78, 1],
                opacities: const [0, 0.08, 0.32, 0.66],
              ),
              _blurLayer(
                key: const Key('ai_preference_bottom_blur_medium'),
                sigma: 12,
                stops: const [0.68, 0.76, 0.88, 1],
                opacities: const [0, 0.10, 0.50, 0.84],
              ),
              _blurLayer(
                key: const Key('ai_preference_bottom_blur_strong'),
                sigma: 24,
                stops: const [0.82, 0.90, 0.96, 1],
                opacities: const [0, 0.14, 0.60, 0.96],
              ),
              const Positioned.fill(
                key: Key('ai_preference_top_dark_gradient'),
                child: IgnorePointer(
                  child: DecoratedBox(
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        begin: Alignment.topCenter,
                        end: Alignment.bottomCenter,
                        colors: [Color(0x47000000), Color(0x00000000)],
                        stops: [0, 0.27],
                      ),
                    ),
                  ),
                ),
              ),
              const Positioned.fill(
                key: Key('ai_preference_bottom_dark_gradient'),
                child: IgnorePointer(
                  child: DecoratedBox(
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        begin: Alignment.topCenter,
                        end: Alignment.bottomCenter,
                        colors: [
                          Color(0x00000000),
                          Color(0x14000000),
                          Color(0x4D000000),
                          Color(0x99000000),
                          Color(0xDB000000),
                        ],
                        stops: [0.58, 0.72, 0.83, 0.92, 1],
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _blurLayer({
    required Key key,
    required double sigma,
    required List<double> stops,
    required List<double> opacities,
  }) {
    return Positioned.fill(
      key: key,
      child: ShaderMask(
        blendMode: BlendMode.dstIn,
        shaderCallback: (bounds) {
          return LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            stops: stops,
            colors: [
              for (final opacity in opacities)
                Color.fromRGBO(255, 255, 255, opacity),
            ],
          ).createShader(bounds);
        },
        child: ImageFiltered(
          imageFilter: ui.ImageFilter.blur(sigmaX: sigma, sigmaY: sigma),
          child: _coverImage(),
        ),
      ),
    );
  }

  Widget _coverImage({bool reportFirstFrame = false}) {
    return Image(
      image: image,
      fit: BoxFit.cover,
      alignment: Alignment.center,
      gaplessPlayback: true,
      filterQuality: FilterQuality.medium,
      frameBuilder: reportFirstFrame && onFirstFrame != null
          ? (context, child, frame, wasSynchronouslyLoaded) {
              if (frame != null || wasSynchronouslyLoaded) {
                WidgetsBinding.instance.addPostFrameCallback((_) {
                  onFirstFrame?.call();
                });
              }
              return child;
            }
          : null,
      errorBuilder: errorBuilder == null
          ? null
          : (context, error, stackTrace) => errorBuilder!(context),
    );
  }
}
