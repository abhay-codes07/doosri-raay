/** NCRP acknowledgement number: 14 digits starting with 329 (API contract). */
export const ACK_RE = /^329\d{11}$/;
/** UPI/IMPS UTR: 12 digits. */
export const UTR_RE = /^\d{12}$/;
/** NEFT/RTGS reference: 16-22 alphanumerics. */
export const NEFT_RE = /^[A-Za-z0-9]{16,22}$/;
export const REF_MAX_LEN = 22;

export type Rail = 'UPI/IMPS' | 'NEFT/RTGS';

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
