/**
 * A tiny "something is in flight" counter for the top progress bar. Polls and one-off requests
 * call begin()/end(); the bar subscribes. No React here so hooks and plain helpers can share it.
 */
let active = 0;
const listeners = new Set<(n: number) => void>();

export function beginActivity(): () => void {
  active += 1;
  listeners.forEach((l) => l(active));
  let ended = false;
  return () => {
    if (ended) return;
    ended = true;
    active = Math.max(0, active - 1);
    listeners.forEach((l) => l(active));
  };
}

export function subscribeActivity(l: (n: number) => void): () => void {
  listeners.add(l);
  l(active);
  return () => {
    listeners.delete(l);
  };
}

/** Wrap a promise-returning function so the bar shows while it runs. */
export async function withActivity<T>(fn: () => Promise<T>): Promise<T> {
  const end = beginActivity();
  try {
    return await fn();
  } finally {
    end();
  }
}
