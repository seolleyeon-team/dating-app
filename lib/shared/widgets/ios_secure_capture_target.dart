import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

class IosSecureCaptureTarget extends StatefulWidget {
  const IosSecureCaptureTarget({
    super.key,
    required this.child,
    required this.id,
    this.borderRadius = 0,
  });

  final Widget child;
  final String id;
  final double borderRadius;

  @override
  State<IosSecureCaptureTarget> createState() => _IosSecureCaptureTargetState();
}

class _IosSecureCaptureTargetState extends State<IosSecureCaptureTarget>
    with WidgetsBindingObserver {
  static const MethodChannel _channel = MethodChannel(
    'com.yonsei.dating/screen_security',
  );

  final GlobalKey _targetKey = GlobalKey();
  bool get _enabled =>
      !kIsWeb && defaultTargetPlatform == TargetPlatform.iOS;

  @override
  void initState() {
    super.initState();
    if (_enabled) {
      WidgetsBinding.instance.addObserver(this);
      WidgetsBinding.instance.addPostFrameCallback((_) => _syncRect());
    }
  }

  @override
  void didUpdateWidget(covariant IosSecureCaptureTarget oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (_enabled) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _syncRect());
    }
  }

  @override
  void didChangeMetrics() {
    super.didChangeMetrics();
    if (_enabled) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _syncRect());
    }
  }

  Future<void> _syncRect() async {
    if (!mounted || !_enabled) return;
    final context = _targetKey.currentContext;
    if (context == null) return;
    final renderObject = context.findRenderObject();
    if (renderObject is! RenderBox || !renderObject.hasSize) return;

    final offset = renderObject.localToGlobal(Offset.zero);
    final size = renderObject.size;
    if (size.width <= 0 || size.height <= 0) return;
    if (!offset.dx.isFinite || !offset.dy.isFinite) return;
    if (!size.width.isFinite || !size.height.isFinite) return;

    try {
      await _channel.invokeMethod<void>('registerSecureZone', {
        'id': widget.id,
        'x': offset.dx,
        'y': offset.dy,
        'width': size.width,
        'height': size.height,
        'borderRadius': widget.borderRadius,
      });
    } catch (_) {}
  }

  @override
  void dispose() {
    if (_enabled) {
      WidgetsBinding.instance.removeObserver(this);
      _channel.invokeMethod<void>('unregisterSecureZone', {'id': widget.id});
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (!_enabled) {
      return widget.child;
    }

    WidgetsBinding.instance.addPostFrameCallback((_) => _syncRect());
    return KeyedSubtree(
      key: _targetKey,
      child: widget.child,
    );
  }
}
