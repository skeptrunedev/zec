import { test } from "node:test";
import assert from "node:assert/strict";
import { estimate, blocksToHalving, BLOCKS_PER_DAY, Z15_PRO } from "../public/calc.js";

const base = {
  hashrateSol: Z15_PRO.hashrateKsol * 1e3,
  powerW: Z15_PRO.powerW,
  electricityUsdKwh: 0.1,
  priceUsd: 1500,
  networkSol: 27e9,
};

test("75s blocks give 1152 blocks per day", () => {
  assert.equal(BLOCKS_PER_DAY, 1152);
});

test("Z15 Pro daily yield matches hand math", () => {
  const r = estimate(base);
  // 840e3 / 27e9 * 1152 * 1.25
  assert.ok(Math.abs(r.zecPerDay - 0.0448) < 1e-9);
  assert.ok(Math.abs(r.revenuePerDay - 67.2) < 1e-6);
  // 2.78 kW * 24 h * $0.10
  assert.ok(Math.abs(r.powerCostPerDay - 6.672) < 1e-9);
  assert.ok(Math.abs(r.profitPerDay - 60.528) < 1e-6);
});

test("pool fee and units scale linearly", () => {
  const one = estimate({ ...base, poolFeePct: 2 });
  const ten = estimate({ ...base, poolFeePct: 2, units: 10 });
  assert.ok(Math.abs(one.zecPerDay - 0.0448 * 0.98) < 1e-9);
  assert.ok(Math.abs(ten.profitPerDay - one.profitPerDay * 10) < 1e-6);
});

test("break-even points zero out profit", () => {
  const r = estimate(base);
  assert.ok(Math.abs(estimate({ ...base, electricityUsdKwh: r.breakevenElectricity }).profitPerDay) < 1e-9);
  assert.ok(Math.abs(estimate({ ...base, priceUsd: r.breakevenPriceUsd }).profitPerDay) < 1e-9);
});

test("payback only when profitable and hardware cost given", () => {
  assert.equal(estimate(base).paybackDays, null);
  assert.ok(Math.abs(estimate({ ...base, hardwareUsd: 6052.8 }).paybackDays - 100) < 1e-6);
  assert.equal(estimate({ ...base, hardwareUsd: 5000, electricityUsdKwh: 5 }).paybackDays, null);
});

test("halving countdown", () => {
  assert.equal(blocksToHalving(4_406_000), 400);
  assert.equal(blocksToHalving(5_000_000), 0);
});

test("rental cost comes out of profit and moves break-evens", () => {
  const r = estimate({ ...base, units: 2, rentalUsdPerDay: 10 });
  assert.ok(Math.abs(r.rentalCostPerDay - 20) < 1e-9);
  assert.ok(Math.abs(r.profitPerDay - (60.528 * 2 - 20)) < 1e-6);
  assert.ok(Math.abs(estimate({ ...base, units: 2, rentalUsdPerDay: 10, electricityUsdKwh: r.breakevenElectricity }).profitPerDay) < 1e-9);
  assert.ok(Math.abs(estimate({ ...base, units: 2, rentalUsdPerDay: 10, priceUsd: r.breakevenPriceUsd }).profitPerDay) < 1e-9);
});
