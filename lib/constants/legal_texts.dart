class LegalTextSection {
  final String title;
  final String content;

  const LegalTextSection({required this.title, required this.content});
}

class LegalTextDocument {
  final String id;
  final String title;
  final String summary;
  final List<LegalTextSection> sections;

  const LegalTextDocument({
    required this.id,
    required this.title,
    required this.summary,
    required this.sections,
  });
}

class LegalTexts {
  LegalTexts._();

  static const version = '2026-05-08';

  static const serviceTerms = LegalTextDocument(
    id: 'termsOfService',
    title: '서비스 이용약관',
    summary: '설레연 서비스 이용과 관련한 회사와 이용자의 권리, 의무 및 책임사항',
    sections: [
      LegalTextSection(
        title: '제1조 목적',
        content:
            '본 약관은 설레연이 제공하는 대학생 인증 기반 매칭 커뮤니티 서비스의 이용과 관련하여 회사와 이용자 간의 권리, 의무 및 책임사항을 규정함을 목적으로 합니다.',
      ),
      LegalTextSection(
        title: '제2조 서비스의 내용',
        content:
            '설레연은 대학생 인증을 기반으로 한 프로필 생성, 매칭, 채팅, 커뮤니티, 신고 및 차단 기능 등을 제공합니다. 회사는 서비스 개선, 안전성 강화, 운영 정책 변경에 따라 서비스의 일부 내용을 변경하거나 중단할 수 있습니다.',
      ),
      LegalTextSection(
        title: '제3조 회원가입 및 계정 관리',
        content:
            '이용자는 카카오 로그인 등 회사가 제공하는 인증 방식을 통해 회원가입할 수 있습니다. 이용자는 정확한 정보를 제공해야 하며, 타인의 정보를 도용하거나 허위 정보를 입력해서는 안 됩니다.',
      ),
      LegalTextSection(
        title: '제4조 이용자의 의무',
        content:
            '이용자는 다음 행위를 해서는 안 됩니다.\n- 타인의 개인정보를 도용하는 행위\n- 허위 프로필을 생성하는 행위\n- 욕설, 성희롱, 혐오 표현, 위협, 스토킹 등 타인에게 피해를 주는 행위\n- 불법 촬영물, 음란물, 폭력적 콘텐츠를 게시하거나 전송하는 행위\n- 서비스 운영을 방해하거나 시스템을 악용하는 행위\n- 기타 관련 법령 및 서비스 운영정책을 위반하는 행위',
      ),
      LegalTextSection(
        title: '제5조 신고 및 제재',
        content:
            '회사는 이용자의 신고, 차단, 운영 모니터링 결과에 따라 경고, 이용 제한, 계정 정지, 영구 탈퇴 등의 조치를 할 수 있습니다. 안전한 커뮤니티 운영을 위해 필요한 경우 관련 기록을 보관할 수 있습니다.',
      ),
      LegalTextSection(
        title: '제6조 서비스 이용 제한',
        content:
            '회사는 이용자가 본 약관 또는 운영정책을 위반한 경우 서비스 이용을 제한할 수 있습니다. 중대한 위반 행위가 확인되는 경우 사전 통지 없이 이용 제한 조치가 이루어질 수 있습니다.',
      ),
      LegalTextSection(
        title: '제7조 책임의 제한',
        content:
            '회사는 이용자 간의 실제 만남, 대화, 게시물, 외부 행위에 대해 직접적인 책임을 지지 않습니다. 다만 안전한 서비스 제공을 위해 신고 및 제재 시스템을 운영합니다.',
      ),
      LegalTextSection(
        title: '제8조 약관의 변경',
        content:
            '회사는 필요한 경우 관련 법령을 위반하지 않는 범위에서 본 약관을 변경할 수 있으며, 변경 시 앱 내 공지 또는 별도 방법으로 안내합니다.',
      ),
    ],
  );

  static const privacyPolicy = LegalTextDocument(
    id: 'privacyPolicy',
    title: '개인정보 처리방침',
    summary: '설레연이 수집하는 개인정보 항목, 이용 목적, 보유 기간 및 이용자 권리 안내',
    sections: [
      LegalTextSection(
        title: '개인정보 처리 원칙',
        content: '설레연은 이용자의 개인정보를 중요하게 생각하며, 관련 법령에 따라 개인정보를 안전하게 처리합니다.',
      ),
      LegalTextSection(
        title: '1. 수집하는 개인정보 항목',
        content:
            '설레연은 서비스 제공을 위해 다음 정보를 수집할 수 있습니다.\n- 카카오 로그인 정보\n- 이름\n- 전화번호\n- 학교 이메일 또는 학교 인증 정보\n- 프로필 정보\n- 성별, 나이, 학교, 관심사 등 이용자가 입력한 정보\n- 서비스 이용 기록, 접속 로그, 기기 정보\n- 신고, 차단, 제재 관련 기록',
      ),
      LegalTextSection(
        title: '2. 개인정보 수집 및 이용 목적',
        content:
            '수집한 개인정보는 다음 목적으로 이용됩니다.\n- 회원가입 및 본인 확인\n- 대학생 인증 및 실사용자 확인\n- 중복 가입 및 악성 사용자 재가입 방지\n- 매칭, 채팅, 커뮤니티 기능 제공\n- 신고, 차단, 제재 등 안전 관리\n- 서비스 품질 개선 및 부정 이용 방지\n- 고객 문의 대응 및 공지 전달',
      ),
      LegalTextSection(
        title: '3. 개인정보 보유 및 이용 기간',
        content:
            '개인정보는 회원 탈퇴 시까지 보관하며, 탈퇴 후에는 지체 없이 파기합니다. 단, 관계 법령에 따라 보관이 필요한 정보 또는 신고, 제재, 분쟁 대응에 필요한 정보는 일정 기간 보관될 수 있습니다.',
      ),
      LegalTextSection(
        title: '4. 개인정보의 제3자 제공',
        content:
            '설레연은 이용자의 개인정보를 원칙적으로 외부에 제공하지 않습니다. 다만 이용자의 동의가 있거나 법령에 따라 필요한 경우 예외적으로 제공될 수 있습니다.',
      ),
      LegalTextSection(
        title: '5. 개인정보 처리 위탁',
        content:
            '서비스 운영을 위해 Firebase, Google Cloud, Kakao 등 외부 플랫폼을 이용할 수 있으며, 이 과정에서 서비스 제공에 필요한 범위 내에서 개인정보가 처리될 수 있습니다.',
      ),
      LegalTextSection(
        title: '6. 이용자의 권리',
        content:
            '이용자는 언제든지 자신의 개인정보에 대한 열람, 수정, 삭제, 처리 정지를 요청할 수 있습니다. 회원 탈퇴를 통해 개인정보 삭제를 요청할 수 있습니다.',
      ),
      LegalTextSection(
        title: '7. 개인정보 보호를 위한 조치',
        content:
            '설레연은 개인정보의 안전한 처리를 위해 접근 권한 관리, 데이터 보안 설정, 신고 및 제재 시스템 운영 등 필요한 보호 조치를 수행합니다.',
      ),
      LegalTextSection(
        title: '8. 개인정보 관련 문의',
        content: '개인정보 관련 문의는 앱 내 문의 기능 또는 운영자 연락처를 통해 접수할 수 있습니다.',
      ),
    ],
  );

  static const kakaoNamePhoneConsent = LegalTextDocument(
    id: 'kakaoNamePhone',
    title: '이름 및 전화번호 수집·이용 동의',
    summary: '카카오 로그인 과정에서 제공받을 수 있는 이름과 전화번호의 이용 목적 안내',
    sections: [
      LegalTextSection(
        title: '이름 및 전화번호 수집·이용 동의',
        content:
            '설레연은 대학생 인증 기반 매칭 커뮤니티 서비스의 안전한 운영을 위해 카카오 로그인 과정에서 사용자의 이름 및 전화번호 정보를 제공받을 수 있습니다.',
      ),
      LegalTextSection(title: '1. 수집 항목', content: '- 이름\n- 카카오계정에 등록된 전화번호'),
      LegalTextSection(
        title: '2. 수집 및 이용 목적',
        content:
            '- 실사용자 확인 및 중복 가입 방지\n- 악성 사용자 재가입 방지\n- 신고, 차단, 제재 등 안전 관리 대응\n- 비상 상황 또는 이용자 보호가 필요한 경우의 본인 확인\n- 안전한 대학생 인증 기반 커뮤니티 환경 조성',
      ),
      LegalTextSection(
        title: '3. 보유 및 이용 기간',
        content:
            '- 회원 탈퇴 시까지 보관합니다.\n- 단, 관계 법령에 따라 보관이 필요한 경우 해당 법령에서 정한 기간 동안 보관할 수 있습니다.\n- 신고, 제재, 분쟁 대응 기록은 서비스 안전성 확보를 위해 내부 정책에 따라 일정 기간 보관될 수 있습니다.',
      ),
      LegalTextSection(
        title: '4. 동의를 거부할 권리 및 불이익',
        content:
            '- 사용자는 이름 및 전화번호 수집·이용에 대한 동의를 거부할 수 있습니다.\n- 다만 해당 정보는 안전한 서비스 운영 및 사용자 보호를 위한 필수 항목이므로, 동의하지 않을 경우 설레연 회원가입 및 서비스 이용이 제한될 수 있습니다.',
      ),
      LegalTextSection(
        title: '5. 동의 여부 저장',
        content: '사용자가 동의한 경우, 동의 여부와 동의 시각을 저장할 수 있습니다.',
      ),
    ],
  );

  static const documents = [serviceTerms, privacyPolicy, kakaoNamePhoneConsent];

  static LegalTextDocument? findById(String id) {
    for (final document in documents) {
      if (document.id == id) return document;
    }
    return null;
  }
}
