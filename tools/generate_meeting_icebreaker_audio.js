#!/usr/bin/env node
/**
 * 3:3 미팅 아이스브레이킹 룰렛 — 효과음 생성기
 * 경로: tools/generate_meeting_icebreaker_audio.js
 *
 * 폭탄 돌리기에 쓰는 두 개의 효과음을 코드로 합성한다.
 * 외부 asset을 가져오지 않으므로 라이선스가 명확하다(프로젝트 자체 제작).
 *
 * 실행:
 *   node tools/generate_meeting_icebreaker_audio.js
 *
 * 출력:
 *   assets/audio/bomb_tick_loop.wav   1.0초, 째깍-째깍 2회 (loop 재생용)
 *   assets/audio/bomb_explosion.wav   1.3초, 폭발음
 *
 * 포맷: WAV / PCM 16-bit / mono / 22050 Hz
 *  - 모바일·웹 모두 디코더가 내장되어 있고 파일도 작다.
 */

const fs = require("fs");
const path = require("path");

const SAMPLE_RATE = 22050;
const OUTPUT_DIR = path.join(__dirname, "..", "assets", "audio");

/** 결정적 난수 (실행할 때마다 같은 파일이 나오도록) */
function createRandom(seed) {
  let state = seed >>> 0;
  return function next() {
    // xorshift32
    state ^= state << 13;
    state >>>= 0;
    state ^= state >>> 17;
    state ^= state << 5;
    state >>>= 0;
    return state / 4294967296;
  };
}

function writeWav(filePath, samples) {
  const dataLength = samples.length * 2;
  const buffer = Buffer.alloc(44 + dataLength);

  buffer.write("RIFF", 0, "ascii");
  buffer.writeUInt32LE(36 + dataLength, 4);
  buffer.write("WAVE", 8, "ascii");
  buffer.write("fmt ", 12, "ascii");
  buffer.writeUInt32LE(16, 16); // fmt chunk size
  buffer.writeUInt16LE(1, 20); // PCM
  buffer.writeUInt16LE(1, 22); // mono
  buffer.writeUInt32LE(SAMPLE_RATE, 24);
  buffer.writeUInt32LE(SAMPLE_RATE * 2, 28); // byte rate
  buffer.writeUInt16LE(2, 32); // block align
  buffer.writeUInt16LE(16, 34); // bits per sample
  buffer.write("data", 36, "ascii");
  buffer.writeUInt32LE(dataLength, 40);

  for (let i = 0; i < samples.length; i++) {
    const clamped = Math.max(-1, Math.min(1, samples[i]));
    buffer.writeInt16LE(Math.round(clamped * 32767), 44 + i * 2);
  }

  fs.writeFileSync(filePath, buffer);
  return buffer.length;
}

/** 짧은 기계식 tick 하나를 [samples]의 [offsetSec] 위치에 더한다. */
function addTick(samples, offsetSec, frequency, gain, random) {
  const durationSec = 0.055;
  const start = Math.floor(offsetSec * SAMPLE_RATE);
  const count = Math.floor(durationSec * SAMPLE_RATE);

  for (let i = 0; i < count; i++) {
    const index = start + i;
    if (index >= samples.length) break;
    const t = i / SAMPLE_RATE;
    // 빠른 감쇠 = 딸깍하는 기계식 느낌
    const envelope = Math.exp(-t * 95);
    const body = Math.sin(2 * Math.PI * frequency * t);
    const overtone = 0.35 * Math.sin(2 * Math.PI * frequency * 2.6 * t);
    // 어택 순간의 아주 짧은 노이즈 transient
    const transient = i < 40 ? (random() * 2 - 1) * 0.5 * (1 - i / 40) : 0;
    samples[index] += gain * envelope * (body + overtone + transient) * 0.5;
  }
}

function buildTickLoop() {
  const random = createRandom(1234567);
  const totalSec = 1.0;
  const samples = new Float64Array(Math.floor(totalSec * SAMPLE_RATE));

  // 째깍 (높은 음) → 째깍 (낮은 음). 1초 loop이므로 이어 붙여도 자연스럽다.
  addTick(samples, 0.0, 1850, 0.85, random);
  addTick(samples, 0.5, 1420, 0.8, random);

  return samples;
}

function buildExplosion() {
  const random = createRandom(987654321);
  const totalSec = 1.3;
  const count = Math.floor(totalSec * SAMPLE_RATE);
  const samples = new Float64Array(count);

  // one-pole lowpass 상태
  let lowpass = 0;
  let lowpassSlow = 0;

  for (let i = 0; i < count; i++) {
    const t = i / SAMPLE_RATE;
    const noise = random() * 2 - 1;

    // 어택: 5ms 상승, 이후 지수 감쇠
    const attack = Math.min(1, t / 0.005);
    const decay = Math.exp(-t * 3.1);
    const envelope = attack * decay;

    // 밝은 파열음 (초반에만)
    lowpass += (noise - lowpass) * 0.45;
    const crack = lowpass * Math.exp(-t * 16);

    // 낮은 럼블 (오래 남는 부분)
    lowpassSlow += (noise - lowpassSlow) * 0.06;
    const rumble = lowpassSlow * 1.9;

    // 90Hz → 35Hz로 내려가는 저음 스윕
    const sweepFreq = 90 * Math.exp(-t * 1.6) + 35;
    const sweep = Math.sin(2 * Math.PI * sweepFreq * t) * Math.exp(-t * 2.4);

    let value = envelope * (crack * 0.85 + rumble * 0.9 + sweep * 0.55);

    // 부드러운 soft clip (귀에 거슬리는 디지털 클리핑 방지)
    value = Math.tanh(value * 1.4) * 0.82;
    samples[i] = value;
  }

  // 끝부분 20ms 페이드아웃 (클릭 노이즈 제거)
  const fade = Math.floor(0.02 * SAMPLE_RATE);
  for (let i = 0; i < fade; i++) {
    const index = count - fade + i;
    samples[index] *= 1 - i / fade;
  }

  return samples;
}

function main() {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });

  const tickPath = path.join(OUTPUT_DIR, "bomb_tick_loop.wav");
  const explosionPath = path.join(OUTPUT_DIR, "bomb_explosion.wav");

  const tickBytes = writeWav(tickPath, buildTickLoop());
  const explosionBytes = writeWav(explosionPath, buildExplosion());

  console.log(`generated ${tickPath} (${tickBytes} bytes)`);
  console.log(`generated ${explosionPath} (${explosionBytes} bytes)`);
}

main();
