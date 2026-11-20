/// 예외를 사용자에게 보여 줄 문구로 바꾼다.
///
/// Dart 는 `Exception('문구')` 를 `Exception: 문구` 로, `StateError('문구')` 를
/// `Bad state: 문구` 로 문자열화한다. 화면마다 `replaceFirst('StateError: ', '')`
/// 로 접두어를 떼려 했지만 그 접두어는 실제로 붙지 않아서 `Bad state: …` 가
/// 그대로 노출됐다. 접두어 처리는 여기 한 곳에서만 한다.
String userFacingErrorText(Object error) {
  if (error is StateError) return error.message;
  final text = error.toString();
  for (final prefix in const ['Exception: ', 'Bad state: ']) {
    if (text.startsWith(prefix)) return text.substring(prefix.length);
  }
  return text;
}
