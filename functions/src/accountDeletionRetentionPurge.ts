/**
 * Scheduled retention purge for deleted-author chat messages and empty event teams.
 */

import { type Firestore } from "firebase-admin/firestore";
import * as logger from "firebase-functions/logger";
import { onSchedule } from "firebase-functions/v2/scheduler";

import { purgeExpiredDeletedAuthorMessages } from "./accountDeletionChatLifecycle";
import { purgeEmptyEventTeams } from "./accountDeletionEventTeamCleanup";

export function createAccountDeletionRetentionPurgeSchedule(
  firestore: Firestore
) {
  return onSchedule(
    {
      schedule: "30 4 * * *",
      timeZone: "Asia/Seoul",
      region: "asia-northeast3",
      cpu: "gcf_gen1",
      concurrency: 1,
      maxInstances: 1,
    },
    async () => {
      const [messages, teams] = await Promise.all([
        purgeExpiredDeletedAuthorMessages(firestore, { limit: 300 }),
        purgeEmptyEventTeams(firestore, { limit: 100 }),
      ]);
      logger.info("accountDeletionRetentionPurge completed", {
        messages,
        teams,
      });
    }
  );
}
