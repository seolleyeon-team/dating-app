# 미팅 아이스브레이킹 효과음

3:3 미팅 아이스브레이킹 룰렛의 폭탄 돌리기 게임에서 사용하는 효과음이다.

| 파일 | 길이 | 용도 |
|---|---|---|
| `bomb_tick_loop.wav` | 1.0초 | 째깍째깍 소리 (loop 재생) |
| `bomb_explosion.wav` | 1.3초 | 폭발음 (1회 재생) |

## 출처와 라이선스

외부에서 가져온 파일이 아니다. 두 파일 모두
`tools/generate_meeting_icebreaker_audio.js` 가 사인파·노이즈·엔벨로프를
직접 합성해 만든 **프로젝트 자체 제작 asset**이다.
따라서 제3자 라이선스 제약이 없다.

재생성:

```bash
node tools/generate_meeting_icebreaker_audio.js
```

생성기는 결정적(deterministic) 난수를 쓰므로 실행할 때마다 같은 파일이 나온다.

## 포맷

- WAV / PCM 16-bit / mono / 22050 Hz
- 모바일과 Flutter Web에서 추가 디코더 없이 재생된다
- 두 파일 합계 약 100KB
