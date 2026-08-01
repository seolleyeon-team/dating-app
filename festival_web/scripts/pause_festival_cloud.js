const fs = require('fs');
const os = require('os');
const path = require('path');

const projectId = 'seolleyeon-festival';
const location = 'asia-northeast3';
const cloudSchedulerApi = 'https://cloudscheduler.googleapis.com/v1';
const targetJobFragments = [
  'festivalEventScheduleTick',
  'festivalRevealCompletePushTick',
  'generateFestivalDailyRecommendations',
];

function readFirebaseAccessToken() {
  const configPath = path.join(
    os.homedir(),
    '.config',
    'configstore',
    'firebase-tools.json',
  );
  const cfg = JSON.parse(fs.readFileSync(configPath, 'utf8'));
  const candidates = [
    cfg,
    ...Object.values(cfg.user || {}),
    ...Object.values(cfg.users || {}),
  ];
  for (const candidate of candidates) {
    const token =
      candidate?.tokens?.access_token ||
      candidate?.access_token ||
      candidate?.token;
    if (token) return token;
  }
  throw new Error('Firebase CLI access token을 찾지 못했습니다.');
}

async function requestJson(url, token, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
  });
  const text = await response.text();
  let body = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}: ${text}`);
  }
  return body;
}

async function main() {
  const token = readFirebaseAccessToken();
  const schedulerBase =
    `${cloudSchedulerApi}/projects/${projectId}` + `/locations/${location}/jobs`;

  const jobsResponse = await requestJson(schedulerBase, token);
  const jobs = jobsResponse.jobs || [];
  const targets = jobs.filter((job) =>
    targetJobFragments.some((fragment) => job.name.includes(fragment)),
  );

  if (targets.length === 0) {
    console.log('No matching Cloud Scheduler jobs found.');
  }

  for (const job of targets) {
    if (job.state === 'PAUSED') {
      console.log(`already paused: ${job.name}`);
      continue;
    }
    await requestJson(`${cloudSchedulerApi}/${job.name}:pause`, token, {
      method: 'POST',
      body: '{}',
    });
    console.log(`paused: ${job.name}`);
  }

  const firestoreUrl =
    `https://firestore.googleapis.com/v1/projects/${projectId}` +
    `/databases/(default)/documents/festivalSettings/schedule` +
    `?updateMask.fieldPaths=enabled&updateMask.fieldPaths=disabledAt`;
  const now = new Date().toISOString();
  await requestJson(firestoreUrl, token, {
    method: 'PATCH',
    body: JSON.stringify({
      fields: {
        enabled: { booleanValue: false },
        disabledAt: { timestampValue: now },
      },
    }),
  });
  console.log(`festivalSettings/schedule enabled=false at ${now}`);
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
