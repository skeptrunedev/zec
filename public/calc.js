// Zcash mining economics. Pure functions, shared by the page and the tests.

// Zcash targets 75s blocks since Blossom.
export const BLOCKS_PER_DAY = 86400 / 75;

// Block subsidy after the Nov 2024 halving is 1.5625 ZEC. 20% goes to the dev
// fund (8% ZCG output + 12% in-protocol lockbox), so the miner keeps 1.25 ZEC
// plus fees. Verified against live coinbase outputs on 2026-09-19.
export const MINER_REWARD_ZEC = 1.25;

// Post-Blossom halving interval is 1,680,000 blocks; the last one was 2,726,400.
export const NEXT_HALVING_HEIGHT = 4_406_400;

export const Z15_PRO = { name: "Antminer Z15 Pro", hashrateKsol: 840, powerW: 2780 };

// A "month" is 30 days everywhere: the Month row, and monthly rental.
export const DAYS_PER_MONTH = 30;

export const PERIODS = [
  { label: "Day", days: 1 },
  { label: "Week", days: 7 },
  { label: "Month", days: DAYS_PER_MONTH },
  { label: "Year", days: 365 },
];

export function estimate({
  hashrateSol,
  powerW,
  units = 1,
  electricityUsdKwh,
  poolFeePct = 0,
  priceUsd,
  networkSol,
  hardwareUsd = 0,
  rentalUsdPerMonth = 0,
  minerRewardZec = MINER_REWARD_ZEC,
}) {
  const share = (hashrateSol * units) / networkSol;
  const grossZecPerDay = share * BLOCKS_PER_DAY * minerRewardZec;
  const zecPerDay = grossZecPerDay * (1 - poolFeePct / 100);
  const revenuePerDay = zecPerDay * priceUsd;
  const poolFeePerDay = (grossZecPerDay - zecPerDay) * priceUsd;
  const kwhPerDay = (powerW * units * 24) / 1000;
  const powerCostPerDay = kwhPerDay * electricityUsdKwh;
  const rentalCostPerDay = (rentalUsdPerMonth / DAYS_PER_MONTH) * units;
  const profitPerDay = revenuePerDay - powerCostPerDay - rentalCostPerDay;
  const totalHardware = hardwareUsd * units;

  return {
    share,
    zecPerDay,
    revenuePerDay,
    poolFeePerDay,
    kwhPerDay,
    powerCostPerDay,
    rentalCostPerDay,
    profitPerDay,
    breakevenElectricity: kwhPerDay > 0 ? (revenuePerDay - rentalCostPerDay) / kwhPerDay : Infinity,
    breakevenPriceUsd: zecPerDay > 0 ? (powerCostPerDay + rentalCostPerDay) / zecPerDay : Infinity,
    paybackDays: totalHardware > 0 && profitPerDay > 0 ? totalHardware / profitPerDay : null,
    periods: PERIODS.map(({ label, days }) => ({
      label,
      zec: zecPerDay * days,
      grossRevenue: (revenuePerDay + poolFeePerDay) * days,
      poolFee: poolFeePerDay * days,
      revenue: revenuePerDay * days,
      power: powerCostPerDay * days,
      rental: rentalCostPerDay * days,
      profit: profitPerDay * days,
    })),
  };
}

export function blocksToHalving(height) {
  return Math.max(0, NEXT_HALVING_HEIGHT - height);
}

// What the same cash would do in an index fund. Mining cash in is the hardware
// up front plus each month's running costs; the stock side invests exactly those
// amounts on the same schedule (start of each month) at a fixed annual return.
// Mined ZEC is assumed sold at today's price as it comes in.
export function compareToStocks({ upfrontUsd, monthlyCostUsd, monthlyRevenueUsd, months, annualReturnPct }) {
  const monthlyRate = Math.pow(1 + annualReturnPct / 100, 1 / 12) - 1;
  const cashIn = upfrontUsd + monthlyCostUsd * months;

  let stockValue = upfrontUsd;
  for (let m = 0; m < months; m++) stockValue = (stockValue + monthlyCostUsd) * (1 + monthlyRate);

  const miningValue = monthlyRevenueUsd * months;
  return {
    cashIn,
    mining: { endValue: miningValue, gain: miningValue - cashIn },
    stocks: { endValue: stockValue, gain: stockValue - cashIn },
  };
}
