// Types mirroring docs/API.md (v1). Runtime guards live in client.ts.

export type Lang = 'hi' | 'en';
export type Role = 'parent' | 'guardian1' | 'guardian2' | 'son';
export type JoinRole = 'parent' | 'guardian2' | 'son';
export type LadderState = 'ok' | 'watching' | 'escalated';

export interface Medicine {
  name: string;
  time: string;
}

export interface Neighbour {
  name?: string;
  phone?: string;
  address?: string;
}

export interface Profile {
  sub?: string;
  email?: string;
  name?: string;
  lang?: Lang;
  city?: string;
  state?: string;
  phone?: string;
  role?: Role;
  circleId?: string;
  checkinHourIST?: number;
  holidayMode?: boolean;
  neighbour?: Neighbour;
  codeWord?: string;
  medicines?: Medicine[];
  photoKey?: string;
  photoUrl?: string;
  pactAccepted?: boolean;
  ladderState?: LadderState;
  lastCheckin?: string;
  lastCheckinDate?: string;
  createdAt?: string;
  updatedAt?: string;
}

export interface CircleMember {
  sub: string;
  name?: string;
  role?: Role;
  phone?: string;
  joinedAt?: string;
  ladderState?: LadderState;
  lastCheckin?: string;
  lastCheckinDate?: string;
  lastCheckinSource?: string;
}

export interface Circle {
  circleId: string;
  name?: string;
  inviteCode?: string;
  members: CircleMember[];
}

export interface ProfileResponse {
  profile: Profile;
  circle: Circle | null;
}

export interface ProfileInput {
  name?: string;
  lang?: Lang;
  city?: string;
  state?: string;
  phone?: string;
  checkinHourIST?: number;
  holidayMode?: boolean;
  neighbour?: Neighbour;
  codeWord?: string;
  medicines?: Medicine[];
  photoKey?: string;
  pactAccepted?: boolean;
}

export interface CreateCircleResponse {
  circleId: string;
  inviteCode: string;
}

export interface JoinCircleResponse {
  circleId: string;
  role: Role;
}

export interface CheckinResponse {
  date: string;
  nextDeadline?: string;
}

export interface SosResponse {
  ladderExecutionArn?: string;
}

export type TaskKind =
  | 'guardian_call'
  | 'neighbour'
  | 'emergency'
  | 'sos'
  | 'confirm_fields'
  | 'call_1930'
  | 'ncrp_filed'
  | 'mrm'
  | 'puchho_family'
  | 'info';

export type TaskOutcome =
  | 'reached'
  | 'no_answer'
  | 'done'
  | 'later'
  | 'confirmed'
  | 'filed'
  | 'yes'
  | 'no';

export interface TaskContext {
  rung?: number;
  reason?: string;
  caseId?: string;
  lat?: number;
  lon?: number;
  accuracy?: number;
  mapsUrl?: string;
  neighbour?: Neighbour;
  address?: string;
  script?: string;
  scriptHi?: string;
  codeWordHint?: string;
  since?: string;
  [key: string]: unknown;
}

export interface Task {
  taskId: string;
  kind: TaskKind | string;
  text: string;
  textHi?: string;
  assigneeSub?: string;
  assigneeName?: string;
  createdAt: string;
  expiresAt?: string;
  status: 'open' | 'done' | 'expired';
  context: TaskContext;
  allowedOutcomes: string[];
}

export interface TasksResponse {
  tasks: Task[];
}

export interface Txn {
  utr: string;
  amount: number | null;
  payee: string;
  timestamp: string;
  app: string;
  /** Screenshot this transaction was read from (pairs the row with its preview). */
  objectKey?: string;
  /** 'UPI/IMPS' (12 digits) or 'NEFT/RTGS' (16-22 alphanumerics), set by the backend validator. */
  rail?: string;
  valid?: boolean;
  issues?: string[];
  /** True for rows the guardian typed in by hand. */
  manual?: boolean;
}

export interface CompleteTaskBody {
  outcome: string;
  txns?: Txn[];
  ackNo?: string;
  codeWord?: string;
}

export interface CompleteTaskResponse {
  taskId: string;
  status: string;
}

export interface UploadRequest {
  contentType: string;
  purpose: 'analyze' | 'case';
}

export interface UploadResponse {
  url: string;
  fields: Record<string, string>;
  objectKey: string;
}

export type AnalyzeRequest = { objectKey: string } | { text: string };

export interface AnalyzeResponse {
  reportId: string;
}

export type VerdictState = 'none' | 'watching' | 'likely';

export interface Verdict {
  state: VerdictState;
  scamType?: string;
  tactics?: string[];
  redFlags?: string[];
  sayHi?: string;
  sayEn?: string;
}

export interface Report {
  reportId: string;
  status: 'pending' | 'done' | 'error';
  verdict?: Verdict;
  modelId?: string;
  error?: string;
  createdAt?: string;
}

export interface CreateCaseRequest {
  objectKeys: string[];
  victimName: string;
  state: string;
  incidentDate?: string;
  narrativeHint?: string;
}

export interface CreateCaseResponse {
  caseId: string;
  executionArn?: string;
}

export type CaseStatus =
  | 'open'
  | 'awaiting_confirmation'
  | 'building'
  | 'awaiting_1930'
  | 'awaiting_ncrp'
  | 'mrm'
  | 'filed'
  | 'error';

/** Where a rule came from: "Source: outlet, date" rendered as a link. */
export interface RuleSource {
  outlet?: string;
  date?: string;
  url?: string;
}

export interface EzeroFir {
  state?: string;
  thresholdInr?: number | null;
  note?: string;
  sourceUrl?: string;
  source?: RuleSource;
  caveat?: string;
}

export interface MrmInfo {
  eligible?: boolean;
  firRequired?: boolean;
  checklist?: string[];
  portal?: string;
  source?: RuleSource;
  caveat?: string;
}

export interface NcrpInfo {
  portal?: string;
  source?: RuleSource;
  caveat?: string;
}

export interface CaseArtifacts {
  script1930?: string;
  ncrpNarrative?: string;
  ncrpNarrativeLength?: number;
  freezeLetter?: string;
  ezeroFir?: EzeroFir;
  mrm?: MrmInfo;
  ncrp?: NcrpInfo;
}

export interface Case {
  caseId: string;
  status: CaseStatus | string;
  state?: string;
  victimName?: string;
  incidentDate?: string;
  narrativeHint?: string;
  objectKeys?: string[];
  extracted?: { txns: Txn[] };
  confirmedTxns?: Txn[];
  artifacts?: CaseArtifacts;
  ackNo?: string;
  openTaskId?: string;
  error?: string;
  createdAt?: string;
  updatedAt?: string;
}

export interface CaseSummary {
  caseId: string;
  status: string;
  victimName?: string;
  createdAt?: string;
}

export interface CasesResponse {
  cases: CaseSummary[];
}

export type PuchhoKind = 'authority' | 'family';

export interface PuchhoAuthorityResponse {
  audioUrl?: string;
  textHi: string;
  textEn?: string;
}

export interface PuchhoFamilyResponse {
  taskId: string;
}

export interface PuchhoStatus {
  status: 'open' | 'done';
  outcome: 'yes' | 'no' | null;
  codeWordMatched: boolean | null;
}

export interface PushPublicKeyResponse {
  publicKey: string;
}

export interface DemoResetResponse {
  ok?: boolean;
  stoppedExecutions?: number;
  closedTasks?: number;
  clearedCheckin?: boolean;
}

export interface DemoConfig {
  demoTimeouts: boolean;
  rungTimeoutSeconds?: number;
  watchDeadlineSeconds?: number;
}

export interface ApiErrorBody {
  error: string;
  message?: string;
}
