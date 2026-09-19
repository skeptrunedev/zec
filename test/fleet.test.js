import { test } from "node:test";
import assert from "node:assert/strict";
import { classifyWorker, fleetHealth, STATUS } from "../public/fleet.js";

const worker = (name, avg, offline = false) => ({
  name,
  averageSolPerSec: avg,
  currentSolPerSec: avg,
  offline,
  lastBeat: 0,
});

test("workers are judged on their average against the minimum", () => {
  assert.equal(classifyWorker(worker("a", 820e3), 815e3), STATUS.OK);
  assert.equal(classifyWorker(worker("a", 700e3), 815e3), STATUS.LOW);
  assert.equal(classifyWorker(worker("a", 900e3, true), 815e3), STATUS.OFFLINE);
});

test("fleet health counts statuses, missing machines, and share of expected", () => {
  const account = {
    averageSolPerSec: 2_360e3,
    workers: [worker("ok", 840e3), worker("low", 700e3), worker("off", 820e3, true)],
  };
  const h = fleetHealth(account, { expectedMachines: 5, perMachineSolPerSec: 840e3, minSolPerSec: 815e3 });
  assert.deepEqual([h.ok, h.low, h.offline, h.missing], [1, 1, 1, 2]);
  assert.equal(h.expectedSolPerSec, 4_200e3);
  assert.ok(Math.abs(h.pctOfExpected - 2_360 / 4_200) < 1e-12);
  // Problems sort first: offline, then low.
  assert.deepEqual(h.workers.map((w) => w.name), ["off", "low", "ok"]);
});
