/// Profile choices and limits shared by onboarding and Profile Edit.
///
/// The stored values in this file are part of the onboarding data contract.
/// Keep the values stable when changing a label; existing Firestore documents
/// contain the values, not the display labels.
class ProfileOption {
  final String value;
  final String label;

  const ProfileOption(this.value, this.label);
}

class MbtiDimension {
  final String first;
  final String second;

  const MbtiDimension(this.first, this.second);
}

const int profileHeightMin = 140;
const int profileHeightMax = 200;
const int profileAgeMin = 18;
const int profileAgeMax = 30;
const double profileAgeSliderMin = 18.0;
const double profileAgeSliderMax = 30.0;
const int maxProfileInterests = 10;
const int maxProfileKeywords = 8;
const int maxProfileQaAnswerLength = 100;
const int maxSelfIntroductionLength = 300;

const List<ProfileOption> profileRelationshipOptions = <ProfileOption>[
  ProfileOption('serious', '진지한 연애를 원해요'),
  ProfileOption('friend', '가볍게 알아가고 싶어요'),
  ProfileOption('open', '상관없어요'),
];

const List<ProfileOption> profileDrinkingOptions = <ProfileOption>[
  ProfileOption('none', '전혀 안 함'),
  ProfileOption('sometimes', '가끔'),
  ProfileOption('weekly1_2', '주 1-2회'),
  ProfileOption('often', '자주 즐김'),
];

const List<ProfileOption> profileSmokingOptions = <ProfileOption>[
  ProfileOption('nonSmoker', '비흡연'),
  ProfileOption('smoker', '흡연'),
  ProfileOption('quitting', '금연 중'),
];

const List<ProfileOption> profileExerciseOptions = <ProfileOption>[
  ProfileOption('mania', '운동 매니아'),
  ProfileOption('daily', '매일 함'),
  ProfileOption('sometimes', '가끔 함'),
  ProfileOption('breathingOnly', '숨쉬기만 함'),
];

const List<ProfileOption> profileReligionOptions = <ProfileOption>[
  ProfileOption('none', '무교'),
  ProfileOption('christianity', '기독교'),
  ProfileOption('catholic', '천주교'),
  ProfileOption('buddhism', '불교'),
  ProfileOption('other', '기타'),
];

const List<MbtiDimension> profileMbtiDimensions = <MbtiDimension>[
  MbtiDimension('E', 'I'),
  MbtiDimension('N', 'S'),
  MbtiDimension('F', 'T'),
  MbtiDimension('J', 'P'),
];

/// Keywords used for both the user's profile and ideal-type personality.
const List<String> profileKeywordOptions = <String>[
  '자신감 있는',
  '아담한',
  '듬직한',
  '잘 웃는',
  '자유분방한',
  '욕 안하는',
  '목소리 좋은',
  '또라이 같은',
  '먼저 말걸어주는',
  '옷 잘입는',
  '활발한',
  '조용한',
  '애교가 많은',
  '어른스러운',
  '열정적인',
  '차분한',
  '예의 바른',
  '재치있는',
  '진지한',
];

const List<String> profileQuestionPrompts = <String>[
  '주말에 보통 뭐 해요?',
  '가장 좋아하는 음식은?',
  '나의 힐링 포인트는?',
  '기억에 남는 여행지는?',
  '내 이상형에 가까운 사람은?',
];
