// 후속 선택 제출: 서버가 값으로 돌려준 거절({ok:false, code})을 성공으로 넘기지 않는다.

import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/blind_meeting/data/blind_meeting_repository.dart';

void main() {
  test('ok:true 응답은 거절이 아니다', () {
    expect(
      BlindMeetingFollowUpRejectedException.fromResponse({'ok': true}),
      isNull,
    );
  });

  test('서버 거절 코드는 각각 사용자 문구로 바뀐다', () {
    final messages = <String, String>{
      for (final code in ['not_open', 'window_closed', 'already_submitted'])
        code: BlindMeetingFollowUpRejectedException.fromResponse({
          'ok': false,
          'code': code,
        })!.message,
    };

    expect(messages['not_open'], contains('아직'));
    expect(messages['window_closed'], contains('끝났'));
    expect(messages['already_submitted'], contains('이미'));
    expect(messages.values.toSet(), hasLength(3));
  });

  test('형태를 알 수 없는 응답도 성공으로 보지 않는다', () {
    final rejected = BlindMeetingFollowUpRejectedException.fromResponse(
      const {},
    );

    expect(rejected, isNotNull);
    expect('$rejected', rejected!.message);
    expect(rejected.message, isNotEmpty);
  });
}
