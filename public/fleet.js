// Pool-side fleet health. Pure functions over the /api/pool/:address payload,
// shared by the monitor page and the tests.

export const STATUS = { OFFLINE: "offline", LOW: "low", OK: "ok" };

// Judge each worker on its longer pool-side average: short windows swing a lot
// with share luck, so a single low reading isn't a problem.
export function classifyWorker(worker, minSolPerSec) {
  if (worker.offline) return STATUS.OFFLINE;
  if (worker.averageSolPerSec < minSolPerSec) return STATUS.LOW;
  return STATUS.OK;
}

const ORDER = { [STATUS.OFFLINE]: 0, [STATUS.LOW]: 1, [STATUS.OK]: 2 };

export function fleetHealth(account, { expectedMachines, perMachineSolPerSec, minSolPerSec }) {
  const workers = account.workers
    .map((w) => ({
      ...w,
      status: classifyWorker(w, minSolPerSec),
      pctOfSpec: w.averageSolPerSec / perMachineSolPerSec,
    }))
    .sort((a, b) => ORDER[a.status] - ORDER[b.status] || a.pctOfSpec - b.pctOfSpec);

  const count = (status) => workers.filter((w) => w.status === status).length;
  const expectedSolPerSec = expectedMachines * perMachineSolPerSec;

  return {
    workers,
    ok: count(STATUS.OK),
    low: count(STATUS.LOW),
    offline: count(STATUS.OFFLINE),
    // Machines you're paying for that have never shown up at the pool.
    missing: Math.max(0, expectedMachines - workers.length),
    expectedSolPerSec,
    pctOfExpected: expectedSolPerSec > 0 ? account.averageSolPerSec / expectedSolPerSec : 0,
  };
}
