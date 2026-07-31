import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/utils/image_content_type.dart';

void main() {
  group('imageContentTypeForExtension', () {
    test('jpg 를 표준 image/jpeg 로 정규화한다', () {
      // 이전 온보딩 업로드 코드는 'image/$extension' 을 그대로 넣어서
      // .jpg 파일이면 'image/jpg' 가 됐다. 표준 MIME 이 아니라서
      // Storage 규칙의 allowlist 검사를 통과하지 못한다.
      expect(imageContentTypeForExtension('jpg'), 'image/jpeg');
      expect(imageContentTypeForExtension('jpeg'), 'image/jpeg');
      expect(imageContentTypeForExtension('JPG'), 'image/jpeg');
    });

    test('나머지 지원 확장자를 매핑한다', () {
      expect(imageContentTypeForExtension('png'), 'image/png');
      expect(imageContentTypeForExtension('gif'), 'image/gif');
      expect(imageContentTypeForExtension('webp'), 'image/webp');
      expect(imageContentTypeForExtension('heic'), 'image/heic');
      expect(imageContentTypeForExtension('heif'), 'image/heif');
    });

    test('앞에 붙은 점과 공백을 무시한다', () {
      expect(imageContentTypeForExtension('.png'), 'image/png');
      expect(imageContentTypeForExtension('  webp '), 'image/webp');
    });

    test('알 수 없는 값과 null 은 image/jpeg 로 떨어진다', () {
      expect(imageContentTypeForExtension('exe'), 'image/jpeg');
      expect(imageContentTypeForExtension(''), 'image/jpeg');
      expect(imageContentTypeForExtension(null), 'image/jpeg');
    });

    test('svg 를 image/svg+xml 로 만들지 않는다', () {
      // SVG 는 스크립트를 품을 수 있어서 Storage 규칙에서 거부한다.
      // 정규화 단계에서도 svg 로 승격시키지 않는다.
      expect(imageContentTypeForExtension('svg'), isNot('image/svg+xml'));
      expect(kAllowedImageContentTypes, isNot(contains('image/svg+xml')));
    });

    test('허용 목록의 모든 값이 정규화 결과로 나올 수 있다', () {
      final produced = <String>{
        imageContentTypeForExtension('jpg'),
        imageContentTypeForExtension('png'),
        imageContentTypeForExtension('gif'),
        imageContentTypeForExtension('webp'),
        imageContentTypeForExtension('heic'),
        imageContentTypeForExtension('heif'),
      };
      expect(produced, equals(kAllowedImageContentTypes));
    });
  });

  group('imageContentTypeForPath', () {
    test('경로 마지막 확장자를 사용한다', () {
      expect(imageContentTypeForPath('/tmp/1700000000_slot0.png'), 'image/png');
      expect(
        imageContentTypeForPath(r'C:\Users\a\photo.archive.webp'),
        'image/webp',
      );
    });

    test('확장자가 없으면 image/jpeg 로 떨어진다', () {
      expect(imageContentTypeForPath('/tmp/photo'), 'image/jpeg');
      expect(imageContentTypeForPath('/tmp/photo.'), 'image/jpeg');
      expect(imageContentTypeForPath(null), 'image/jpeg');
    });
  });
}
