"""Canonical prompt contract for the Azure avatar generation path."""

AVATAR_GENERAL_PROMPT_V0_TEMP = """레퍼런스 정면 사진의 인물과 얼굴 특징과 인상을 최대한 동일하게 유지한 2D 아바타를 생성한다.

스타일은 깔끔한 Live2D 애니메이션 텍스처 스타일로, 자연스러운 애니메이션풍 얼굴 비율, 선명하고 정돈된 라인, 부드러운 셀 셰이딩과 은은한 입체감, 매끈한 피부 표현을 사용한다. 과도한 미화나 눈 확대, 얼굴형 변형은 하지 않는다.

헤어스타일, 머리색, 눈·코·입 형태, 얼굴형, 피부톤, 의상과 전체적인 인상을 레퍼런스와 충실하게 유지한다.

정면·눈높이 시점, 가슴 위까지 보이는 중앙 구도, 자연스러운 무표정, 단색 밝은 아이보리 배경.

표정 시트, 분리 파츠, 텍스트, 장식, 소품은 넣지 않고 완성된 아바타 1명만 출력한다."""
AVATAR_GENERAL_PROMPT_VERSION = "avatar_general_prompt_v1"

__all__ = [
    "AVATAR_GENERAL_PROMPT_V0_TEMP",
    "AVATAR_GENERAL_PROMPT_VERSION",
]
