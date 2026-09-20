/**
 * Judge path (/try): a shared guardian + parent account baked in at build time so judges never
 * sign up. All four variables must be present; otherwise /try explains how to get credentials.
 */
export interface JudgeConfig {
  email: string;
  password: string;
  parentEmail: string;
  parentPassword: string;
}

export function judgeConfig(): JudgeConfig | null {
  const env = import.meta.env;
  const email = (env.VITE_JUDGE_EMAIL ?? '').trim();
  const password = env.VITE_JUDGE_PASSWORD ?? '';
  const parentEmail = (env.VITE_JUDGE_PARENT_EMAIL ?? '').trim();
  const parentPassword = env.VITE_JUDGE_PARENT_PASSWORD ?? '';
  if (!email || !password || !parentEmail || !parentPassword) return null;
  return { email, password, parentEmail, parentPassword };
}

export const judgeConfigured = (): boolean => judgeConfig() !== null;

/**
 * The other judge circles, named after the configured one: judge@x → judge2@x, judge3@x
 * (judge1@x → judge2@x, judge3@x). Only the addresses; the password is in the submission form.
 */
export function siblingJudgeEmails(email: string): string[] {
  const at = email.indexOf('@');
  if (at <= 0) return [];
  const local = email.slice(0, at).replace(/\d+$/, '');
  const domain = email.slice(at);
  return [2, 3].map((n) => `${local}${n}${domain}`).filter((e) => e.toLowerCase() !== email.toLowerCase());
}
