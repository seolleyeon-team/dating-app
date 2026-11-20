import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/shared/utils/error_text.dart';

void main() {
  test('StateError 는 Bad state 접두어 없이 문구만 남긴다', () {
    expect(userFacingErrorText(StateError('로그인이 필요해요.')), '로그인이 필요해요.');
  });

  test('Exception 은 Exception 접두어 없이 문구만 남긴다', () {
    expect(userFacingErrorText(Exception('요청을 처리하지 못했어요.')), '요청을 처리하지 못했어요.');
  });

  test('문자열화된 StateError 도 접두어를 뗀다', () {
    expect(userFacingErrorText('Bad state: 다시 시도해주세요.'), '다시 시도해주세요.');
  });

  test('접두어는 맨 앞에 있을 때만 뗀다', () {
    expect(
      userFacingErrorText('서버 응답: Exception: 내부 오류'),
      '서버 응답: Exception: 내부 오류',
    );
  });
}
