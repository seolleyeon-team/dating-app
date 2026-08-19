/**
 * 블라인드 3:3 participant/application FSM — 전이 매트릭스 + Dart 파리티 +
 * status write bypass source-scan.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, it } from "node:test";

import {
  ALLOWED_APPLICATION_TRANSITIONS,
  ALLOWED_PARTICIPANT_TRANSITIONS,
  PARTICIPANT_STATUS_TO_APP,
  canTransitionApplication,
  canTransitionParticipant,
  type ParticipantStatus,
} from "../types";

const ALL_STATUSES = Object.keys(
  PARTICIPANT_STATUS_TO_APP
) as ParticipantStatus[];

describe("blind participant FSM matrix", () => {
  it("allows exactly the edges in the transition table", () => {
    for (const from of ALL_STATUSES) {
      for (const to of ALL_STATUSES) {
        const expected =
          from !== to &&
          (ALLOWED_PARTICIPANT_TRANSITIONS[from] ?? []).includes(to);
        assert.equal(
          canTransitionParticipant(from, to),
          expected,
          `participant ${from} -> ${to}`
        );
      }
    }
  });

  it("terminal states have no outgoing edges", () => {
    for (const terminal of [
      "replaced",
      "cancelled",
      "completed",
      "restricted",
    ] as ParticipantStatus[]) {
      assert.equal(ALLOWED_PARTICIPANT_TRANSITIONS[terminal].length, 0);
      for (const to of ALL_STATUSES) {
        assert.equal(canTransitionParticipant(terminal, to), false);
      }
    }
  });

  it("rejects the historically dangerous reverse edges", () => {
    assert.equal(canTransitionParticipant("cancelled", "confirmed"), false);
    assert.equal(canTransitionParticipant("cancelled", "replacement_pending"), false);
    assert.equal(canTransitionParticipant("replaced", "confirmed"), false);
    assert.equal(canTransitionParticipant("completed", "invited"), false);
    assert.equal(canTransitionParticipant("invited", "confirmed"), false);
  });
});

describe("blind application FSM matrix", () => {
  it("allows exactly the edges in the transition table", () => {
    for (const from of ALL_STATUSES) {
      for (const to of ALL_STATUSES) {
        const expected =
          from !== to &&
          (ALLOWED_APPLICATION_TRANSITIONS[from] ?? []).includes(to);
        assert.equal(
          canTransitionApplication(from, to),
          expected,
          `application ${from} -> ${to}`
        );
      }
    }
  });

  it("supports re-application from settled states", () => {
    for (const settled of [
      "cancelled",
      "completed",
      "no_show",
      "restricted",
    ] as ParticipantStatus[]) {
      assert.equal(canTransitionApplication(settled, "applied"), true);
      assert.equal(canTransitionApplication(settled, "confirmed"), false);
    }
  });

  it("participant-only states are unused on applications", () => {
    for (const participantOnly of [
      "cancel_requested",
      "replacement_pending",
      "replaced",
      "attended",
    ] as ParticipantStatus[]) {
      assert.equal(
        ALLOWED_APPLICATION_TRANSITIONS[participantOnly].length,
        0,
        `${participantOnly} must have no application edges`
      );
    }
  });
});

describe("Dart parity", () => {
  it("participant table matches blind_meeting_session.dart exactly", () => {
    const dartSource = readFileSync(
      resolve(
        __dirname,
        "../../../../lib/features/blind_meeting/domain/blind_meeting_session.dart"
      ),
      "utf8"
    );
    const tableStart = dartSource.indexOf("allowedParticipantTransitions = {");
    const tableEnd = dartSource.indexOf("};", tableStart);
    assert.ok(tableStart >= 0 && tableEnd > tableStart);
    const dartTable = dartSource.slice(tableStart, tableEnd);

    const appToServer = new Map<string, ParticipantStatus>();
    for (const [server, app] of Object.entries(PARTICIPANT_STATUS_TO_APP)) {
      appToServer.set(app, server as ParticipantStatus);
    }

    // Dart 표기: BlindMeetingParticipantStatus.<camel> — from: {...to들}
    const entryPattern =
      /BlindMeetingParticipantStatus\.(\w+):\s*(?:\{([^}]*)\}|<BlindMeetingParticipantStatus>\{\})/g;
    const dartEdges = new Map<ParticipantStatus, Set<ParticipantStatus>>();
    let match: RegExpExecArray | null;
    while ((match = entryPattern.exec(dartTable)) != null) {
      const from = appToServer.get(match[1]);
      assert.ok(from != null, `unknown dart status ${match[1]}`);
      const targets = new Set<ParticipantStatus>();
      const body = match[2] ?? "";
      const toPattern = /BlindMeetingParticipantStatus\.(\w+)/g;
      let toMatch: RegExpExecArray | null;
      while ((toMatch = toPattern.exec(body)) != null) {
        const to = appToServer.get(toMatch[1]);
        assert.ok(to != null, `unknown dart status ${toMatch[1]}`);
        targets.add(to);
      }
      dartEdges.set(from, targets);
    }

    assert.equal(dartEdges.size, ALL_STATUSES.length, "dart table entry count");
    for (const from of ALL_STATUSES) {
      const server = new Set(ALLOWED_PARTICIPANT_TRANSITIONS[from]);
      const dart = dartEdges.get(from) ?? new Set();
      assert.deepEqual(
        [...server].sort(),
        [...dart].sort(),
        `edges for ${from} must match Dart`
      );
    }
  });
});

describe("status write bypass scan", () => {
  function readCompiled(file: string): string {
    return readFileSync(resolve(__dirname, "..", file), "utf8");
  }

  function extractServerStatusLiterals(source: string): string[] {
    const literals: string[] = [];
    const pattern = /serverStatus:\s*["']([a-z_]+)["']/g;
    let match: RegExpExecArray | null;
    while ((match = pattern.exec(source)) != null) {
      literals.push(match[1]);
    }
    return literals.sort();
  }

  it("orchestrator raw serverStatus writes stay limited to the allowlisted tx paths", () => {
    // 허용: 미팅 생성(awaiting_acceptance), 참가자/신청서 최초 초대 클레임
    // (invited ×2), 대체 합류 tx(confirmed 참가자 + replaced 이탈자 +
    // confirmed 신청서). 이 목록이 늘어나면 FSM bypass다.
    const literals = extractServerStatusLiterals(readCompiled("orchestrator.js"));
    assert.deepEqual(literals, [
      "awaiting_acceptance",
      "confirmed",
      "confirmed",
      "invited",
      "invited",
      "replaced",
    ]);
  });

  it("scheduled/ops/callables/matching have no raw serverStatus writes", () => {
    for (const file of ["scheduled.js", "ops.js", "callables.js", "matching.js"]) {
      assert.deepEqual(
        extractServerStatusLiterals(readCompiled(file)),
        [],
        `${file} must not write serverStatus literals`
      );
    }
  });

  it("store keeps the FSM predicates wired into both choke points", () => {
    const store = readCompiled("store.js");
    assert.match(store, /canTransitionParticipant/);
    assert.match(store, /canTransitionApplication/);
    assert.match(store, /blind_participant_transition_rejected/);
    assert.match(store, /blind_application_transition_rejected/);
    assert.match(store, /blind_participant_status_unknown/);
    assert.match(store, /blind_application_status_unknown/);
  });
});
