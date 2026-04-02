import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:url_launcher/url_launcher.dart';

/// 카카오맵 / 네이버지도: **설치되어 있으면** 커스텀 스킴으로 앱 실행,
/// **아니면** 카카오맵·네이버지도 **웹**(브라우저)으로 연다.
///
/// 웹(Flutter Web)에서는 처음부터 HTTPS만 사용한다.
class PromiseMapLaunch {
  PromiseMapLaunch._();

  static const _naverCallerAppName = 'seolleyeon';

  /// `kakaomap://`, `nmap://` — 모바일 앱만.
  static Future<bool> _launchCustomScheme(Uri uri) async {
    if (kIsWeb) return false;
    try {
      final ok = await launchUrl(
        uri,
        mode: LaunchMode.externalNonBrowserApplication,
      );
      if (ok) return true;
    } catch (_) {
      // 미설치 등
    }
    try {
      return await launchUrl(uri, mode: LaunchMode.externalApplication);
    } catch (_) {
      return false;
    }
  }

  /// 공식 웹 지도(브라우저). 앱 미설치 시 폴백용.
  static Future<bool> _launchWebOnly(Uri uri) async {
    try {
      return await launchUrl(uri, mode: LaunchMode.externalApplication);
    } catch (_) {
      return false;
    }
  }

  /// 카카오 장소 ID가 있으면 앱에서 상세, 없으면 검색·핀. 실패 시 카카오맵 웹 검색.
  static Future<bool> openKakaoMap({
    required double lat,
    required double lng,
    required String name,
    String? kakaoPlaceId,
  }) async {
    final pCenter = '$lat,$lng';

    if (!kIsWeb && kakaoPlaceId != null && kakaoPlaceId.trim().isNotEmpty) {
      final id = kakaoPlaceId.trim();
      final appPlace = Uri(
        scheme: 'kakaomap',
        host: 'place',
        queryParameters: {'id': id},
      );
      if (await _launchCustomScheme(appPlace)) return true;
    }

    if (!kIsWeb) {
      final appSearch = Uri(
        scheme: 'kakaomap',
        host: 'search',
        queryParameters: {'q': name, 'p': pCenter},
      );
      if (await _launchCustomScheme(appSearch)) return true;

      final appLook = Uri(
        scheme: 'kakaomap',
        host: 'look',
        queryParameters: {'p': pCenter},
      );
      if (await _launchCustomScheme(appLook)) return true;
    }

    return _launchWebOnly(Uri.https('map.kakao.com', '/', {'q': name}));
  }

  /// 네이버: 앱 스킴 시도 후 네이버지도 웹.
  static Future<bool> openNaverMap({
    required double lat,
    required double lng,
    required String name,
    String? naverPlaceId,
  }) async {
    final encodedName = Uri.encodeComponent(name);

    if (!kIsWeb) {
      final appSearch = Uri(
        scheme: 'nmap',
        host: 'search',
        queryParameters: {
          'query': name,
          'appname': _naverCallerAppName,
        },
      );
      if (await _launchCustomScheme(appSearch)) return true;

      final appPlace = Uri(
        scheme: 'nmap',
        host: 'place',
        queryParameters: {
          'lat': lat.toString(),
          'lng': lng.toString(),
          'name': name,
          'appname': _naverCallerAppName,
        },
      );
      if (await _launchCustomScheme(appPlace)) return true;
    }

    if (naverPlaceId != null && naverPlaceId.trim().isNotEmpty) {
      final webPlace = Uri.parse(
        'https://map.naver.com/p/entry/place/${naverPlaceId.trim()}',
      );
      if (await _launchWebOnly(webPlace)) return true;
    }

    return _launchWebOnly(
      Uri.parse('https://map.naver.com/v5/search/$encodedName'),
    );
  }
}
