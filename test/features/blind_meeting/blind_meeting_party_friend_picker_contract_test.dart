import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  final pickerSource = File(
    'lib/features/blind_meeting/presentation/screens/'
    'blind_meeting_party_friend_picker_screen.dart',
  ).readAsStringSync();
  final partySource = File(
    'functions/src/blindMeeting/party.ts',
  ).readAsStringSync();
  final rulesSource = File('firestore.rules').readAsStringSync();

  test('팀원 초대 화면은 설레연 친구 목록을 선택기로 사용한다', () {
    expect(pickerSource, contains('FriendsListStreamBody('));
    expect(pickerSource, contains('mode: FriendsListStreamMode.picker'));
    expect(pickerSource, contains('...party.acceptedUserIds'));
    expect(pickerSource, contains('...party.pendingInviteeIds'));
    expect(pickerSource, contains('_repository.createPartyInvite('));
  });

  test('블라인드 팀원 선택은 카카오 친구 API에 의존하지 않는다', () {
    expect(pickerSource, isNot(contains('kakao_flutter_sdk')));
    expect(pickerSource, isNot(contains('getKakaoUserId')));
    expect(pickerSource, contains('_repository.currentUserId()'));
  });

  test('서버는 실제 설레연 친구 mirror를 확인한 뒤에만 초대한다', () {
    expect(partySource, contains('.collection("friends")'));
    expect(partySource, contains('if (!friendSnap.exists)'));
    expect(partySource, contains('if (!friendshipSnap.exists)'));
  });

  test('친구 mirror는 본인 읽기·서버 쓰기 전용이다', () {
    expect(rulesSource, contains('match /friends/{friendUid}'));
    expect(rulesSource, contains('allow get, list: if isVerifiedOwner'));
    expect(rulesSource, contains('allow create, update, delete: if false'));
  });
}
