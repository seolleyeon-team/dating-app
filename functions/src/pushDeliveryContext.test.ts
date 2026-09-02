import assert from "node:assert/strict";
import test from "node:test";
import { shouldSuppressPushForDevice } from "./shared/notify";

const NOW = 1_800_000_000_000;

function context(overrides: Record<string, unknown> = {}) {
  return {
    appState: "foreground",
    screen: "other",
    updatedAt: { toMillis: () => NOW },
    ...overrides,
  };
}

test("chat list suppresses only chat pushes on the active device", () => {
  assert.equal(
    shouldSuppressPushForDevice({
      notificationType: "chat",
      roomId: "room-a",
      deliveryContext: context({ screen: "chat_list" }),
      nowMs: NOW,
    }),
    true
  );
  assert.equal(
    shouldSuppressPushForDevice({
      notificationType: "community_comment",
      deliveryContext: context({ screen: "chat_list" }),
      nowMs: NOW,
    }),
    false
  );
});

test("only the currently-open chat room suppresses its own messages", () => {
  const roomContext = context({ screen: "chat_room", chatRoomId: "room-a" });
  assert.equal(
    shouldSuppressPushForDevice({
      notificationType: "chat",
      roomId: "room-a",
      deliveryContext: roomContext,
      nowMs: NOW,
    }),
    true
  );
  assert.equal(
    shouldSuppressPushForDevice({
      notificationType: "chat",
      roomId: "room-b",
      deliveryContext: roomContext,
      nowMs: NOW,
    }),
    false
  );
});

test("background and stale device context never suppress a push", () => {
  assert.equal(
    shouldSuppressPushForDevice({
      notificationType: "chat",
      roomId: "room-a",
      deliveryContext: context({ appState: "background", screen: "chat_list" }),
      nowMs: NOW,
    }),
    false
  );
  assert.equal(
    shouldSuppressPushForDevice({
      notificationType: "chat",
      roomId: "room-a",
      deliveryContext: context({
        screen: "chat_list",
        updatedAt: { toMillis: () => NOW - 90_001 },
      }),
      nowMs: NOW,
    }),
    false
  );
});
