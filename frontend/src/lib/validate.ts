/** NCRP acknowledgement number: 14 digits (API contract). */
export const ACK_RE = /^\d{14}$/;
export const ACK_LEN = 14;
/** Most NCRP acknowledgement numbers start with 329; anything else gets a non-blocking warning. */
export const ACK_EXPECTED_PREFIX = '329';

export function ackNeedsWarning(ack: string): boolean {
  const a = ack.trim();
  return a.length > 0 && !a.startsWith(ACK_EXPECTED_PREFIX);
}
/** UPI/IMPS UTR: 12 digits. */
export const UTR_RE = /^\d{12}$/;
/** NEFT/RTGS reference: 16-22 alphanumerics. */
export const NEFT_RE = /^[A-Za-z0-9]{16,22}$/;
export const REF_MAX_LEN = 22;

export type Rail = 'UPI/IMPS' | 'NEFT/RTGS';

/** Server rule (rules.py): amount 1..1e8. */
export const AMOUNT_MIN = 1;
export const AMOUNT_MAX = 100_000_000;

export type TxnIssue = 'utr_invalid' | 'amount_invalid' | 'payee_missing' | 'timestamp_missing';

/** Parse a typed amount ("₹ 50,000.00" → 50000); null when not numeric. */
export function parseAmount(text: string): number | null {
  const cleaned = text.replace(/[^\d.]/g, '');
  if (!cleaned) return null;
  const n = Number(cleaned);
  return Number.isFinite(n) ? n : null;
}

/**
 * Mirror of the server's validate_txn: reference on a known rail, numeric amount within range,
 * non-empty payee, parseable timestamp (here: an ISO string produced from the datetime input).
 */
export function txnIssues(row: { utr: string; amountText: string; payee: string; timestampIso: string }): TxnIssue[] {
  const issues: TxnIssue[] = [];
  if (!classifyReference(row.utr).valid) issues.push('utr_invalid');
  const amount = parseAmount(row.amountText);
  if (amount === null || amount < AMOUNT_MIN || amount > AMOUNT_MAX) issues.push('amount_invalid');
  if (!row.payee.trim()) issues.push('payee_missing');
  if (!row.timestampIso || Number.isNaN(new Date(row.timestampIso).getTime())) issues.push('timestamp_missing');
  return issues;
}

/** Classify a transaction reference: 12 digits → UPI/IMPS, 16-22 alphanumerics → NEFT/RTGS. */
export function classifyReference(raw: string): { valid: boolean; rail: Rail | null } {
  const ref = raw.trim();
  if (UTR_RE.test(ref)) return { valid: true, rail: 'UPI/IMPS' };
  if (NEFT_RE.test(ref)) return { valid: true, rail: 'NEFT/RTGS' };
  return { valid: false, rail: null };
}

/** Presigned POST content-length-range upper bound (backend). */
export const MAX_UPLOAD_BYTES = 3_500_000;
export const MAX_UPLOAD_LABEL = '3.5 MB';
/** Screenshots per recovery case. */
export const MAX_CASE_SCREENSHOTS = 5;

export function formatBytes(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)} MB`;
  if (n >= 1000) return `${Math.round(n / 1000)} kB`;
  return `${n} B`;
}

export function isImageFile(f: File): boolean {
  return f.type.startsWith('image/');
}

/** Downscale an image file to a small JPEG data URL for local previews (keeps localStorage small). */
export function fileToPreview(file: File, maxSide = 480): Promise<string> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      try {
        const scale = Math.min(1, maxSide / Math.max(img.width, img.height));
        const canvas = document.createElement('canvas');
        canvas.width = Math.max(1, Math.round(img.width * scale));
        canvas.height = Math.max(1, Math.round(img.height * scale));
        const ctx = canvas.getContext('2d');
        if (!ctx) throw new Error('canvas');
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        resolve(canvas.toDataURL('image/jpeg', 0.7));
      } catch (e) {
        reject(e instanceof Error ? e : new Error(String(e)));
      } finally {
        URL.revokeObjectURL(url);
      }
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error('image decode failed'));
    };
    img.src = url;
  });
}
