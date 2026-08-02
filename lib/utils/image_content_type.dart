/// 이미지 업로드용 contentType 정규화.
///
/// 이전에는 업로드 화면이 `'image/$extension'` 을 그대로 넣어서 `.jpg` 파일이
/// `image/jpg` 가 됐다. 이건 표준 MIME 타입이 아니라서 Storage 규칙에서
/// allowlist 검사를 하면 걸러진다. 업로드 경로가 두 곳(온보딩·프로필 편집)이라
/// 같은 매핑을 한 곳에서만 관리한다.
library;

/// Storage 에 업로드를 허용하는 이미지 MIME 타입.
///
/// `image/svg+xml` 은 스크립트를 품을 수 있어 의도적으로 제외했다.
const Set<String> kAllowedImageContentTypes = {
  'image/jpeg',
  'image/png',
  'image/gif',
  'image/webp',
  'image/heic',
  'image/heif',
};

const String _kFallbackImageContentType = 'image/jpeg';

/// 파일 확장자를 표준 이미지 MIME 타입으로 바꾼다.
///
/// 알 수 없는 확장자는 `image/jpeg` 로 떨어뜨린다. image_picker 가 돌려주는
/// 값은 사실상 카메라·갤러리 이미지이고, 업로드 자체를 막는 것보다 표준
/// 타입으로 보내는 편이 낫다. 실제 바이트 검증은 서버측 과제로 남아 있다.
String imageContentTypeForExtension(String? extension) {
  final normalized = (extension ?? '').trim().toLowerCase().replaceAll('.', '');
  switch (normalized) {
    case 'jpg':
    case 'jpeg':
      return 'image/jpeg';
    case 'png':
      return 'image/png';
    case 'gif':
      return 'image/gif';
    case 'webp':
      return 'image/webp';
    case 'heic':
      return 'image/heic';
    case 'heif':
      return 'image/heif';
    default:
      return _kFallbackImageContentType;
  }
}

/// 파일 경로에서 확장자를 뽑아 MIME 타입으로 바꾼다.
String imageContentTypeForPath(String? path) {
  final value = path ?? '';
  final lastDot = value.lastIndexOf('.');
  if (lastDot < 0 || lastDot == value.length - 1) {
    return _kFallbackImageContentType;
  }
  return imageContentTypeForExtension(value.substring(lastDot + 1));
}
