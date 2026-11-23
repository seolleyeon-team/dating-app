/**
 * NEW-24 — the declared account-state policy of every HTTPS endpoint exported
 * from index.ts (callables and onRequest handlers).
 *
 * callableAccountStatePolicy.test.ts loads the real exports and fails when an
 * endpoint has no entry here, when an entry names an export that no longer
 * exists, and (for the gates implemented in index.ts) when the declared gate
 * is not in the source. A new callable therefore cannot ship without a
 * decision about suspended / banned / withdrawn / inactive accounts.
 *
 * This module is documentation that a test executes; no runtime code reads it.
 */

export type CallableAccountGate =
  /** resolveAuthedAppUser: own users doc, active state, student-verified. */
  | "app_user"
  /** resolveReviewCapableAppUser: the Play review account, else app_user. */
  | "review_capable"
  /** Active state required; student verification deliberately not required. */
  | "account_state"
  /** The module's own resolver refuses withdrawn / login-disabled accounts. */
  | "module_gate"
  /** resolvePlayReviewUser: fixed review uid + claims + review document. */
  | "play_review"
  /** Operator / admin custom claim (and admin/{uid} where the module has one). */
  | "operator"
  /** Owner-lifecycle action that must stay available in every state. */
  | "owner_lifecycle"
  /** No account-state gate by design; `reason` says why. */
  | "exempt"
  /**
   * Should be gated but the handler lives in a module outside this change's
   * ownership. Listed so the gap is explicit; remove the entry's `pending`
   * kind when the module calls assertActiveAccountState.
   */
  | "pending";

export type CallableAccountStatePolicy = {
  gate: CallableAccountGate;
  reason: string;
};

const appUser = (reason: string): CallableAccountStatePolicy => ({
  gate: "app_user",
  reason,
});
const reviewCapable = (reason: string): CallableAccountStatePolicy => ({
  gate: "review_capable",
  reason,
});
const operator = (reason: string): CallableAccountStatePolicy => ({
  gate: "operator",
  reason,
});

const AVATAR = "avatar / onboarding photo feature of a verified account";
const SEASON = "season meeting action of a verified participant";
const INVITE = "friend / event-team invitation of a verified account";
const SUPPORT_CONSOLE =
  "operations claim + admin/{uid}.active; an operator is not an app account";
const MODERATION_CONSOLE =
  "operations claim + admin/{uid}.active; requireOperations additionally " +
  "refuses an operator whose users/{uid} is suspended, banned or withdrawn " +
  "(NEW-25)";

export const CALLABLE_ACCOUNT_STATE_POLICY: Readonly<
  Record<string, CallableAccountStatePolicy>
> = {
  // ---- hearts / chat -------------------------------------------------------
  grantPurchasedHearts: reviewCapable("purchase credit to the caller's account"),
  spendHearts: appUser("retired debit endpoint; still authenticates first"),
  unlockDirectChat: reviewCapable("opens a paid 1:1 chat"),
  purchaseRecommendationRefresh: reviewCapable("paid recommendation refresh"),
  sendChatText: reviewCapable("writes a chat message"),
  getChatRealProfilePhoto: appUser("reads a chat partner's real photo"),
  updateProfileVisibility: appUser("changes the caller's recommendation visibility"),

  // ---- invitations / teams -------------------------------------------------
  createFriendInvite: appUser(INVITE),
  previewInviteToken: appUser(INVITE),
  acceptFriendInvite: appUser(INVITE),
  createEventTeamShareInvite: appUser(INVITE),
  redeemEventTeamShareInvite: appUser(INVITE),
  ensureEventTeamSetup: appUser(INVITE),
  createEventTeamInvite: appUser(INVITE),
  respondEventTeamInvite: appUser(INVITE),
  spinSeasonMeetingRoulette: appUser(SEASON),
  createTeamMeetingRequest: appUser(SEASON),
  respondTeamMeetingRequest: appUser(SEASON),
  createSeasonMeetingDepositIntent: appUser(SEASON),
  cancelSeasonMeeting: appUser(SEASON),
  reportSeasonMeetingNoShow: appUser(SEASON),
  claimSeasonMeetingReplacementSeat: appUser(SEASON),
  refundSeasonMeetingDeposit: appUser(SEASON),

  // ---- avatar / media ------------------------------------------------------
  uploadOnboardingPhoto: appUser(AVATAR),
  beginAvatarGenerationFromOnboardingPhotos: appUser(AVATAR),
  replaceAvatarGeneration: appUser(AVATAR),
  getCurrentAvatarGenerationStatus: appUser(AVATAR),
  prewarmAvatarWorker: appUser(AVATAR),
  retryCurrentAvatarGeneration: appUser(AVATAR),
  getAvatarJobCandidates: appUser(AVATAR),
  approveAvatarCandidate: appUser(AVATAR),
  cleanupAvatarMedia: {
    gate: "owner_lifecycle",
    reason:
      "reason=account_deletion is authorized by request.auth.uid alone " +
      "(accountDeletionAuthorization.ts): every identity, including a " +
      "suspended or half-deleted one, must be able to finish deleting " +
      "itself. reason=consent_withdrawal goes through resolveAuthedAppUser.",
  },

  // ---- community / reports -------------------------------------------------
  reportAndBlockUser: reviewCapable("files a report and blocks"),
  createCommunityPost: reviewCapable("writes Bamboo content"),
  createCommunityComment: reviewCapable("writes Bamboo content"),
  deleteCommunityPost: reviewCapable("deletes the caller's Bamboo content"),
  deleteCommunityComment: reviewCapable("deletes the caller's Bamboo content"),
  reportBambooContent: reviewCapable("files a Bamboo report"),
  submitInquiry: appUser(
    "support case of a verified, active account. A suspended account cannot " +
      "file one in-app today (Firebase Auth is disabled as well); an in-app " +
      "appeal path would be a product decision"
  ),
  submitIssueReport: appUser("same as submitInquiry"),

  // ---- operators -----------------------------------------------------------
  listSupportUsers: operator(SUPPORT_CONSOLE),
  openSupportChat: operator(SUPPORT_CONSOLE),
  getCommunityModerationAccess: operator(MODERATION_CONSOLE),
  listCommunityModerationReports: operator(MODERATION_CONSOLE),
  setCommunityReportReviewing: operator(MODERATION_CONSOLE),
  decideCommunityReport: operator(MODERATION_CONSOLE),
  restoreCommunityAccount: operator(MODERATION_CONSOLE),
  blindMeetingOps: operator("admin / blindMeetingOps custom claim"),
  backfillVerifiedPhoneHashIndex: operator("admin custom claim"),
  purgeLegacyKakaoPhoneHashes: operator("admin custom claim"),

  // ---- sign-in, verification recovery, consent -----------------------------
  createFirebaseCustomToken: {
    gate: "exempt",
    reason:
      "legacy pre-auth sign-in bridge (Kakao token -> custom token). It " +
      "grants no access by itself: a moderated account has Firebase Auth " +
      "disabled, and every later callable re-reads the state. A half-deleted " +
      "legacy account must still be able to sign in to finish its deletion.",
  },
  sendPrimaryStudentEmailLink: {
    gate: "exempt",
    reason:
      "pre-auth by design (App Check only); the account is resolved and its " +
      "state checked at completion",
  },
  completePrimaryStudentEmailAuth: {
    gate: "account_state",
    reason:
      "sign-in completion: the rejoin guard refuses a restricted account " +
      "inside the transaction and never creates a fresh one to bypass it",
  },
  sendStudentVerificationEmail: {
    gate: "account_state",
    reason: "legacy verification recovery: unverified allowed, restricted refused",
  },
  completeStudentEmailLink: {
    gate: "account_state",
    reason:
      "legacy verification completion: emailLinkCompletion.ts asserts the " +
      "account state inside the transaction that marks it verified",
  },
  recordTermsAcceptance: {
    gate: "account_state",
    reason: "re-consent must not require student verification",
  },
  verifyAdultIdentityAfterLogin: {
    gate: "account_state",
    reason:
      "runs before student/adult eligibility exists; refuses restricted " +
      "accounts and the review partition (adultIdentityOwnership.ts)",
  },

  // ---- Kakao friend exclusion ----------------------------------------------
  linkKakaoFriendIdentity: {
    gate: "account_state",
    reason: "state asserted inside the link transaction",
  },
  syncContactBlocks: {
    gate: "account_state",
    reason: "own account document required and active (eligibility: AUD-05)",
  },
  syncKakaoTalkFriendBlocks: {
    gate: "account_state",
    reason: "legacy sync; state asserted on the resolved caller document",
  },
  beginKakaoFriendRecommendationPrivacySync: {
    gate: "exempt",
    reason:
      "legacy fail-closed step that can only CLOSE the caller's own " +
      "recommendation gate (recommendationPrivacyReady:false); it never " +
      "opens anything and old binaries call it without a Firebase session",
  },
  createKakaoFriendPairsOnce: {
    gate: "account_state",
    reason:
      "kakaoFriendPairs.ts asserts the account state in its lease transaction",
  },
  setKakaoFriendAvoidanceEnabled: {
    gate: "account_state",
    reason:
      "kakaoFriendPairs.ts asserts the account state in the CAS-lock " +
      "transaction of executeSetKakaoFriendAvoidanceEnabled",
  },

  // ---- meetings ------------------------------------------------------------
  blindMeetingAction: {
    gate: "module_gate",
    reason:
      "blindMeeting/store.ts requireVerifiedUser refuses isWithdrawn / " +
      "loginDisabled, which every state writer sets; it should move to the " +
      "shared classifier",
  },
  meetingIcebreakerAction: {
    gate: "account_state",
    reason:
      "meetingIcebreaker/functions.ts: requireActiveAccount before any action; " +
      "membership is checked per action afterwards",
  },
  submitSafetyStamp: {
    gate: "account_state",
    reason:
      "safetyStamp.ts: requireActiveAccount before the room membership check",
  },
  submitSafetyStampFollowUp: {
    gate: "account_state",
    reason:
      "same as submitSafetyStamp",
  },

  // ---- Play review ---------------------------------------------------------
  playReviewSignIn: {
    gate: "exempt",
    reason:
      "pre-auth review sign-in: secret credentials, rate limit, fixed review " +
      "uid and review document shape; the session it mints is gated below",
  },
  preparePlayReviewSession: {
    gate: "play_review",
    reason: "review-partition only",
  },
  getPlayReviewFeed: { gate: "play_review", reason: "review-partition only" },
  purchasePlayReviewRecommendationRefresh: {
    gate: "play_review",
    reason: "review-partition only",
  },

  // ---- HTTP (not callables) ------------------------------------------------
  appStoreServerNotifications: {
    gate: "exempt",
    reason:
      "server-to-server App Store notification authenticated by Apple's " +
      "signed payload; it acts for no caller",
  },
};
