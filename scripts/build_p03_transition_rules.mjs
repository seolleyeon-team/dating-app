/**
 * P0-3 Phase 0B — 마이그레이션 동안만 배포하는 과도기 Firestore 규칙을 만든다.
 *
 * 최종 규칙(firestore.rules)은 public 대나무숲 글/댓글을 로그인 사용자 누구나 읽게
 * 한다. 그런데 마이그레이션 전 문서에는 아직 authorId 가 있고, 규칙은 읽기 응답의
 * 필드를 가릴 수 없다. 그래서 규칙 배포(2단계) 부터 마이그레이션(4단계) 이 끝날
 * 때까지는 "작성자 식별 필드가 하나라도 있는 문서는 읽을 수 없다" 는 조건을 붙인다.
 *
 * 목록(list) 은 아예 닫는다: 쿼리에 대한 규칙 평가는 저장된 문서가 아니라 쿼리
 * 제약만 보므로 `resource.data.keys()` 조건은 목록에서 빈 조건처럼 통과한다
 * (에뮬레이터에서 필터 없는 목록이 authorId 문서를 돌려준 것을 확인). 그 사이
 * 대나무숲 피드는 열리지 않는다 — 신원 노출보다 짧은 이용 제한이 낫다. 신원 노출보다 짧은 이용 제한이
 * 낫다는 결정이다. 마이그레이션 verify 가 0 이 되면 최종 firestore.rules 를 다시
 * 배포해 목록을 연다.
 *
 * 생성물: firestore.p03-transition.rules (커밋된다). rules_tests 가 이 스크립트의
 * 출력과 커밋된 파일이 같은지 확인한다 — 최종 규칙과 어긋난 과도기 규칙이 배포되지
 * 않게 하기 위해서다.
 *
 *   node scripts/build_p03_transition_rules.mjs          # 파일 갱신
 *   node scripts/build_p03_transition_rules.mjs --check  # 다르면 exit 1
 */
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "..");
export const FINAL_RULES = resolve(root, "firestore.rules");
export const TRANSITION_RULES = resolve(root, "firestore.p03-transition.rules");

const GATE = "noPublicBambooIdentity()";

const HELPER = `
    // P0-3 TRANSITION ONLY (scripts/build_p03_transition_rules.mjs). A Bamboo
    // document that still carries an author-identifying field is unreadable
    // until the historical migration removes it (get only). Bamboo list
    // queries are closed while this ruleset is live: for a query the Rules
    // engine sees only the query constraints, so this predicate cannot
    // protect a list.
    function noPublicBambooIdentity() {
      return !resource.data.keys().hasAny([
        'authorId', 'authorUid', 'ownerUid', 'userId', 'uid', 'actorId',
        'actorName', 'nickname', 'authorName', 'authorNickname',
        'authorProfileUrl', 'profileId'
      ]);
    }
`;

/** 최종 규칙 → 과도기 규칙. 대나무숲 public 문서의 읽기 4곳에만 조건을 붙인다. */
export function buildTransitionRules(finalSource) {
  // Leading "\n" anchors each rule to its own indentation: the 6-space post
  // rule is otherwise a substring of the 8-space comment rule.
  const reads = [
    "\n      allow get, list: if isSignedIn() && !isPlayReviewSession();\n",
    "\n        allow get, list: if isSignedIn() && !isPlayReviewSession();\n",
    "\n      allow get, list: if isPlayReviewSession();\n",
    "\n        allow get, list: if isPlayReviewSession();\n",
  ];
  const bambooStart = finalSource.indexOf("    match /bamboo_posts/{postId} {");
  const mappingStart = finalSource.indexOf("    match /bamboo_post_authors/{postId} {");
  const reviewStart = finalSource.indexOf("    match /playReviewBambooPosts/{postId} {");
  const reviewEnd = finalSource.indexOf("    match /playReviewBambooPostAuthors/{postId} {");
  if ([bambooStart, mappingStart, reviewStart, reviewEnd].some((i) => i < 0)) {
    throw new Error("final rules layout changed: Bamboo blocks not found");
  }
  const gate = (block, prodOrReview) => {
    const [postRead, commentRead] = prodOrReview === "prod" ? reads.slice(0, 2) : reads.slice(2, 4);
    if (block.split(postRead).length !== 2 || block.split(commentRead).length !== 2) {
      throw new Error(`final rules layout changed: ${prodOrReview} read rules not found exactly once`);
    }
    // get: evaluated against the stored document, so the identity gate holds.
    // list: Rules evaluate a query against its constraints, not the stored
    // documents — `resource.data.keys()` then sees only the filters and the
    // gate passes vacuously (emulator-proven: an unfiltered list returned
    // authorId-bearing documents). Lists are therefore closed outright.
    const split = (read, indent) =>
      read
        .replace("allow get, list:", "allow get:")
        .replace(";\n", ` &&\n${indent}  ${GATE};\n${indent}allow list: if false;\n`);
    return block
      .replace(postRead, split(postRead, "      "))
      .replace(commentRead, split(commentRead, "        "));
  };
  const prod = gate(finalSource.slice(bambooStart, mappingStart), "prod");
  const review = gate(finalSource.slice(reviewStart, reviewEnd), "review");
  const out =
    finalSource.slice(0, bambooStart) + prod +
    finalSource.slice(mappingStart, reviewStart) + review +
    finalSource.slice(reviewEnd);
  const anchor = "    function bambooCommentCounterUpdateOk() {";
  if (out.split(anchor).length !== 2) throw new Error("helper anchor not found");
  return out.replace(anchor, `${HELPER.replace(/^\n/, "")}\n${anchor}`);
}

const invokedDirectly = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (invokedDirectly) {
  const built = buildTransitionRules(readFileSync(FINAL_RULES, "utf8"));
  if (process.argv.includes("--check")) {
    const current = readFileSync(TRANSITION_RULES, "utf8");
    if (current !== built) {
      console.error("firestore.p03-transition.rules is stale; run node scripts/build_p03_transition_rules.mjs");
      process.exitCode = 1;
    }
  } else {
    writeFileSync(TRANSITION_RULES, built, "utf8");
    console.log("wrote", TRANSITION_RULES);
  }
}
