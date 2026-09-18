/** NCRP acknowledgement number: 14 digits starting with 329 (API contract). */
export const ACK_RE = /^329\d{11}$/;
/** UPI/IMPS UTR: 12 digits. */
export const UTR_RE = /^\d{12}$/;

export const MAX_UPLOAD_BYTES = 5 * 1024 * 1024;

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
