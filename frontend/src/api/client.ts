import { fetchAuthSession } from 'aws-amplify/auth';
import type {
  AnalyzeRequest,
  AnalyzeResponse,
  ApiErrorBody,
  Case,
  CasesResponse,
  CheckinResponse,
  CompleteTaskBody,
  CompleteTaskResponse,
  CreateCaseRequest,
  CreateCaseResponse,
  CreateCircleResponse,
  DemoConfig,
  DemoResetResponse,
  JoinCircleResponse,
  JoinRole,
  Profile,
  ProfileInput,
  ProfileResponse,
  PuchhoAuthorityResponse,
  PuchhoFamilyResponse,
  PuchhoStatus,
  PushPublicKeyResponse,
  Report,
  SosResponse,
  TasksResponse,
  UploadRequest,
  UploadResponse,
} from './types';

export const API_URL: string = (import.meta.env.VITE_API_URL ?? '').replace(/\/+$/, '');

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

export type TokenProvider = () => Promise<string | null>;

/** Default token source: the Amplify session of the signed-in user. */
export const amplifyTokenProvider: TokenProvider = async () => {
  try {
    const session = await fetchAuthSession();
    return session.tokens?.idToken?.toString() ?? null;
  } catch {
    return null;
  }
};

const isRecord = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null;

function parseErrorBody(status: number, raw: string): ApiError {
  try {
    const parsed: unknown = JSON.parse(raw);
    if (isRecord(parsed) && typeof parsed.error === 'string') {
      const body = parsed as unknown as ApiErrorBody;
      return new ApiError(status, body.error, body.message ?? body.error);
    }
  } catch {
    /* not JSON */
  }
  return new ApiError(status, `http_${status}`, raw || `HTTP ${status}`);
}

export interface PollOpts {
  intervalMs?: number;
  maxMs?: number;
  signal?: AbortSignal;
  onTick?: (n: number) => void;
}

export interface ApiClient {
  request<T>(method: string, path: string, body?: unknown): Promise<T>;
  // onboarding
  getProfile(): Promise<ProfileResponse>;
  updateProfile(input: ProfileInput): Promise<{ profile: Profile }>;
  createCircle(): Promise<CreateCircleResponse>;
  joinCircle(inviteCode: string, role: JoinRole): Promise<JoinCircleResponse>;
  // check-in / ladder
  checkin(source?: 'tile' | 'sos'): Promise<CheckinResponse>;
  sos(loc: { lat: number; lon: number; accuracy: number }): Promise<SosResponse>;
  listTasks(): Promise<TasksResponse>;
  completeTask(taskId: string, body: CompleteTaskBody): Promise<CompleteTaskResponse>;
  // classifier
  requestUpload(req: UploadRequest): Promise<UploadResponse>;
  /** Presigned POST upload; resolves with the objectKey. */
  uploadFile(file: Blob, purpose: UploadRequest['purpose']): Promise<string>;
  analyze(req: AnalyzeRequest): Promise<AnalyzeResponse>;
  getReport(reportId: string): Promise<Report>;
  /** Poll GET /reports/{id} every 2 s for at most 30 s. */
  pollReport(reportId: string, opts?: PollOpts): Promise<Report>;
  // recovery
  createCase(req: CreateCaseRequest): Promise<CreateCaseResponse>;
  getCase(caseId: string): Promise<Case>;
  listCases(): Promise<CasesResponse>;
  // puchho
  puchhoAuthority(): Promise<PuchhoAuthorityResponse>;
  puchhoFamily(): Promise<PuchhoFamilyResponse>;
  getPuchho(taskId: string): Promise<PuchhoStatus>;
  pollPuchho(taskId: string, opts?: PollOpts): Promise<PuchhoStatus>;
  // push
  getPushPublicKey(): Promise<PushPublicKeyResponse>;
  pushSubscribe(sub: PushSubscriptionJSON): Promise<void>;
  // demo
  getDemoConfig(): Promise<DemoConfig>;
  /** Stops executions, closes tasks and clears today's check-in for the caller's circle. */
  demoReset(): Promise<DemoResetResponse>;
}

const sleep = (ms: number, signal?: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException('aborted', 'AbortError'));
      return;
    }
    const t = setTimeout(resolve, ms);
    signal?.addEventListener('abort', () => {
      clearTimeout(t);
      reject(new DOMException('aborted', 'AbortError'));
    });
  });

export function createApiClient(getToken: TokenProvider = amplifyTokenProvider): ApiClient {
  async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
    if (!API_URL) throw new ApiError(0, 'not_configured', 'VITE_API_URL is not set');
    const token = await getToken();
    if (!token) throw new ApiError(401, 'no_session', 'Not signed in');
    const headers: Record<string, string> = { Authorization: `Bearer ${token}` };
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    let res: Response;
    try {
      res = await fetch(`${API_URL}${path}`, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch (e) {
      throw new ApiError(0, 'network', e instanceof Error ? e.message : 'network error');
    }
    const raw = await res.text();
    if (!res.ok) throw parseErrorBody(res.status, raw);
    if (!raw) return {} as T;
    try {
      return JSON.parse(raw) as T;
    } catch {
      throw new ApiError(res.status, 'bad_json', 'Response was not JSON');
    }
  }

  const client: ApiClient = {
    request,
    getProfile: async () => {
      const r = await request<Partial<ProfileResponse>>('GET', '/profile');
      return { profile: isRecord(r.profile) ? (r.profile as Profile) : {}, circle: r.circle ?? null };
    },
    updateProfile: (input) => request('POST', '/profile', input),
    createCircle: () => request('POST', '/circles', {}),
    joinCircle: (inviteCode, role) =>
      request('POST', '/circles/join', { inviteCode: inviteCode.trim().toUpperCase(), role }),

    checkin: (source = 'tile') => request('POST', '/checkin', { source }),
    sos: (loc) => request('POST', '/sos', loc),
    listTasks: async () => {
      const r = await request<Partial<TasksResponse>>('GET', '/tasks');
      return { tasks: Array.isArray(r.tasks) ? r.tasks : [] };
    },
    completeTask: (taskId, body) => request('POST', `/tasks/${encodeURIComponent(taskId)}/complete`, body),

    requestUpload: (req) => request('POST', '/uploads', req),
    uploadFile: async (file, purpose) => {
      const contentType = file.type && file.type.startsWith('image/') ? file.type : 'image/png';
      const presigned = await client.requestUpload({ contentType, purpose });
      const fields = presigned.fields ?? {};
      const form = new FormData();
      Object.entries(fields).forEach(([k, v]) => form.append(k, v));
      if (!('Content-Type' in fields)) form.append('Content-Type', contentType);
      form.append('file', file);
      let res: Response;
      try {
        res = await fetch(presigned.url, { method: 'POST', body: form });
      } catch (e) {
        throw new ApiError(0, 'upload_network', e instanceof Error ? e.message : 'upload failed');
      }
      if (!res.ok) throw new ApiError(res.status, 'upload_failed', `Upload failed (${res.status})`);
      return presigned.objectKey;
    },
    analyze: (req) => request('POST', '/analyze', req),
    getReport: (reportId) => request('GET', `/reports/${encodeURIComponent(reportId)}`),
    pollReport: async (reportId, opts = {}) => {
      const interval = opts.intervalMs ?? 2000;
      const maxMs = opts.maxMs ?? 30000;
      const start = Date.now();
      let n = 0;
      for (;;) {
        const r = await client.getReport(reportId);
        if (r.status === 'done' || r.status === 'error') return r;
        n += 1;
        opts.onTick?.(n);
        if (Date.now() - start + interval > maxMs) {
          throw new ApiError(0, 'timeout', 'Report still pending after 30 s');
        }
        await sleep(interval, opts.signal);
      }
    },

    createCase: (req) => request('POST', '/cases', req),
    getCase: (caseId) => request('GET', `/cases/${encodeURIComponent(caseId)}`),
    listCases: async () => {
      const r = await request<unknown>('GET', '/cases');
      if (Array.isArray(r)) return { cases: r as CasesResponse['cases'] };
      if (isRecord(r) && Array.isArray(r.cases)) return { cases: r.cases as CasesResponse['cases'] };
      return { cases: [] };
    },

    puchhoAuthority: () => request('POST', '/puchho', { kind: 'authority' }),
    puchhoFamily: () => request('POST', '/puchho', { kind: 'family' }),
    getPuchho: (taskId) => request('GET', `/puchho/${encodeURIComponent(taskId)}`),
    pollPuchho: async (taskId, opts = {}) => {
      const interval = opts.intervalMs ?? 3000;
      const maxMs = opts.maxMs ?? 10 * 60 * 1000;
      const start = Date.now();
      let n = 0;
      for (;;) {
        const s = await client.getPuchho(taskId);
        if (s.status === 'done') return s;
        n += 1;
        opts.onTick?.(n);
        if (Date.now() - start + interval > maxMs) throw new ApiError(0, 'timeout', 'No answer yet');
        await sleep(interval, opts.signal);
      }
    },

    getPushPublicKey: () => request('GET', '/push/public-key'),
    pushSubscribe: async (sub) => {
      await request('POST', '/push/subscribe', sub);
    },
    getDemoConfig: () => request('GET', '/demo/config'),
    demoReset: () => request('POST', '/demo/reset', {}),
  };
  return client;
}

/** Shared default client (Amplify session). */
export const api: ApiClient = createApiClient();

export function isAbort(e: unknown): boolean {
  return e instanceof DOMException && e.name === 'AbortError';
}

export function describeError(e: unknown, lang: 'hi' | 'en' = 'hi'): string {
  if (e instanceof ApiError) {
    switch (e.code) {
      case 'quota_exceeded':
        return lang === 'hi' ? 'आज की सीमा पूरी हो गई। कल फिर कोशिश करें।' : 'Daily quota reached. Try again tomorrow.';
      case 'network':
      case 'upload_network':
        return lang === 'hi' ? 'नेटवर्क नहीं मिल रहा।' : 'No network right now.';
      case 'no_session':
        return lang === 'hi' ? 'कृपया फिर से साइन इन करें।' : 'Please sign in again.';
      case 'not_configured':
        return 'VITE_API_URL is not set (see frontend/.env.example).';
      case 'not_found':
        return lang === 'hi' ? 'यह नहीं मिला।' : 'Not found.';
      case 'role_taken':
        return lang === 'hi' ? 'इस परिवार में पहले से एक parent है।' : 'This circle already has a parent.';
      case 'invalid_txns':
        return lang === 'hi'
          ? 'कुछ लेन-देन की जानकारी सर्वर ने नहीं मानी — UTR, रकम, किसे भेजा और समय जाँचकर फिर पक्का करें।'
          : `The server rejected some rows; check UTR, amount, payee and time, then confirm again. (${e.message})`;
      default:
        return e.message || e.code;
    }
  }
  if (e instanceof Error) return e.message;
  return String(e);
}
