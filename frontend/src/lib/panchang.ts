/**
 * Approximate ("anumanit") panchang: tithi and paksha from low-precision solar and lunar
 * ecliptic longitudes (Meeus, Astronomical Algorithms ch. 25 and 47, main periodic terms).
 * Accuracy is a few arc-minutes for the Moon, well within the 12° width of a tithi,
 * except close to a tithi boundary, hence the "approximate" label in the UI.
 */

const DEG = Math.PI / 180;
const norm = (d: number) => ((d % 360) + 360) % 360;
const sin = (d: number) => Math.sin(d * DEG);

/** Julian Day for a JS Date (UTC). */
export function julianDay(date: Date): number {
  return date.getTime() / 86400000 + 2440587.5;
}

/** Apparent-ish geocentric ecliptic longitude of the Sun, degrees. */
export function sunLongitude(jd: number): number {
  const T = (jd - 2451545.0) / 36525;
  const L0 = 280.46646 + 36000.76983 * T + 0.0003032 * T * T;
  const M = 357.52911 + 35999.05029 * T - 0.0001537 * T * T;
  const C =
    (1.914602 - 0.004817 * T - 0.000014 * T * T) * sin(M) +
    (0.019993 - 0.000101 * T) * sin(2 * M) +
    0.000289 * sin(3 * M);
  const trueLong = L0 + C;
  // nutation + aberration correction (small)
  const omega = 125.04 - 1934.136 * T;
  return norm(trueLong - 0.00569 - 0.00478 * sin(omega));
}

// Meeus table 47.A, leading terms: [D, M, M', F, coefficient (1e-6 deg)]
const MOON_TERMS: ReadonlyArray<readonly [number, number, number, number, number]> = [
  [0, 0, 1, 0, 6288774],
  [2, 0, -1, 0, 1274027],
  [2, 0, 0, 0, 658314],
  [0, 0, 2, 0, 213618],
  [0, 1, 0, 0, -185116],
  [0, 0, 0, 2, -114332],
  [2, 0, -2, 0, 58793],
  [2, -1, -1, 0, 57066],
  [2, 0, 1, 0, 53322],
  [2, -1, 0, 0, 45758],
  [0, 1, -1, 0, -40923],
  [1, 0, 0, 0, -34720],
  [0, 1, 1, 0, -30383],
  [2, 0, 0, -2, 15327],
  [0, 0, 1, 2, -12528],
  [0, 0, 1, -2, 10980],
  [4, 0, -1, 0, 10675],
  [0, 0, 3, 0, 10034],
  [4, 0, -2, 0, 8548],
  [2, 1, -1, 0, -7888],
  [2, 1, 0, 0, -6766],
  [1, 0, -1, 0, -5163],
  [1, 1, 0, 0, 4987],
  [2, -1, 1, 0, 4036],
  [2, 0, 2, 0, 3994],
  [4, 0, 0, 0, 3861],
  [2, 0, -3, 0, 3665],
  [0, 1, -2, 0, -2689],
  [2, 0, -1, 2, -2602],
  [2, -1, -2, 0, 2390],
  [1, 0, 1, 0, -2348],
  [2, -2, 0, 0, 2236],
  [0, 1, 2, 0, -2120],
  [0, 2, 0, 0, -2069],
  [2, -2, -1, 0, 2048],
  [2, 0, 1, -2, -1773],
  [2, 0, 0, 2, -1595],
  [4, -1, -1, 0, 1215],
  [0, 0, 2, 2, -1110],
  [3, 0, -1, 0, -892],
  [2, 1, 1, 0, -810],
  [4, -1, -2, 0, 759],
  [0, 2, -1, 0, -713],
  [2, 2, -1, 0, -700],
  [2, 1, -2, 0, 691],
  [2, -1, 0, -2, 596],
  [4, 0, 1, 0, 549],
  [0, 0, 4, 0, 537],
  [4, -1, 0, 0, 520],
  [1, 0, -2, 0, -487],
];

/** Geocentric ecliptic longitude of the Moon, degrees. */
export function moonLongitude(jd: number): number {
  const T = (jd - 2451545.0) / 36525;
  const T2 = T * T;
  const T3 = T2 * T;
  const T4 = T3 * T;
  const Lp = 218.3164477 + 481267.88123421 * T - 0.0015786 * T2 + T3 / 538841 - T4 / 65194000;
  const D = 297.8501921 + 445267.1114034 * T - 0.0018819 * T2 + T3 / 545868 - T4 / 113065000;
  const M = 357.5291092 + 35999.0502909 * T - 0.0001536 * T2 + T3 / 24490000;
  const Mp = 134.9633964 + 477198.8675055 * T + 0.0087414 * T2 + T3 / 69699 - T4 / 14712000;
  const F = 93.272095 + 483202.0175233 * T - 0.0036539 * T2 - T3 / 3526000 + T4 / 863310000;
  const E = 1 - 0.002516 * T - 0.0000074 * T2;
  const A1 = 119.75 + 131.849 * T;
  const A2 = 53.09 + 479264.29 * T;

  let sum = 0;
  for (const [d, m, mp, f, coef] of MOON_TERMS) {
    let c = coef;
    if (Math.abs(m) === 1) c *= E;
    else if (Math.abs(m) === 2) c *= E * E;
    sum += c * sin(d * D + m * M + mp * Mp + f * F);
  }
  sum += 3958 * sin(A1) + 1962 * sin(Lp - F) + 318 * sin(A2);
  return norm(Lp + sum / 1e6);
}

export type Paksha = 'shukla' | 'krishna';

export interface Tithi {
  /** 1..30 (1–15 Shukla, 16–30 Krishna). */
  index: number;
  /** 1..15 within the paksha. */
  number: number;
  paksha: Paksha;
  nameHi: string;
  nameEn: string;
  pakshaHi: string;
  pakshaEn: string;
  /** Fraction of the current tithi elapsed (0..1). */
  progress: number;
}

const TITHI_HI = [
  'प्रतिपदा',
  'द्वितीया',
  'तृतीया',
  'चतुर्थी',
  'पंचमी',
  'षष्ठी',
  'सप्तमी',
  'अष्टमी',
  'नवमी',
  'दशमी',
  'एकादशी',
  'द्वादशी',
  'त्रयोदशी',
  'चतुर्दशी',
];
const TITHI_EN = [
  'Pratipada',
  'Dwitiya',
  'Tritiya',
  'Chaturthi',
  'Panchami',
  'Shashthi',
  'Saptami',
  'Ashtami',
  'Navami',
  'Dashami',
  'Ekadashi',
  'Dwadashi',
  'Trayodashi',
  'Chaturdashi',
];

export function tithiAt(date: Date): Tithi {
  const jd = julianDay(date);
  const diff = norm(moonLongitude(jd) - sunLongitude(jd));
  const index = Math.floor(diff / 12) + 1; // 1..30
  const progress = (diff % 12) / 12;
  const paksha: Paksha = index <= 15 ? 'shukla' : 'krishna';
  const number = paksha === 'shukla' ? index : index - 15;
  let nameHi: string;
  let nameEn: string;
  if (number === 15) {
    nameHi = paksha === 'shukla' ? 'पूर्णिमा' : 'अमावस्या';
    nameEn = paksha === 'shukla' ? 'Purnima' : 'Amavasya';
  } else {
    nameHi = TITHI_HI[number - 1] ?? '';
    nameEn = TITHI_EN[number - 1] ?? '';
  }
  return {
    index,
    number,
    paksha,
    nameHi,
    nameEn,
    pakshaHi: paksha === 'shukla' ? 'शुक्ल पक्ष' : 'कृष्ण पक्ष',
    pakshaEn: paksha === 'shukla' ? 'Shukla Paksha' : 'Krishna Paksha',
    progress,
  };
}

/** Tithi prevailing at sunrise (approx 06:00 IST) of the given IST calendar date. */
export function tithiForIstDay(now: Date = new Date()): Tithi {
  const ist = new Date(now.getTime() + 5.5 * 3600 * 1000);
  const y = ist.getUTCFullYear();
  const m = ist.getUTCMonth();
  const d = ist.getUTCDate();
  // 06:00 IST == 00:30 UTC
  const sunrise = new Date(Date.UTC(y, m, d, 0, 30, 0));
  return tithiAt(sunrise);
}

/** Approximate Vikram Samvat year (new year at Chaitra, ~late March/April: +57 from April, else +56). */
export function vikramSamvat(now: Date = new Date()): number {
  const ist = new Date(now.getTime() + 5.5 * 3600 * 1000);
  const month = ist.getUTCMonth(); // 0 = Jan
  return ist.getUTCFullYear() + (month >= 3 ? 57 : 56);
}

/** Moon phase icon for the tithi index. */
export function moonEmoji(index: number): string {
  if (index === 30) return '🌑';
  if (index === 15) return '🌕';
  if (index < 8) return '🌒';
  if (index < 15) return '🌔';
  if (index < 23) return '🌖';
  return '🌘';
}
