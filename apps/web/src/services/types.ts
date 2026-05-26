export type Role = 'student' | 'coach' | 'judge' | 'admin';
export type ProblemType = 'code' | 'blank' | 'single_choice' | 'multiple_choice';
export type ProblemPackageFormat = 'fps' | 'qdu' | 'hydro';
export type ProblemImportConflictStrategy = 'create_new' | 'overwrite' | 'skip';
export type JudgeNodeStatus = 'online' | 'offline' | 'draining';
export type JudgeQueueJobStatus = 'pending' | 'leased' | 'completed' | 'failed';
export type JudgeQueueBackend = 'json' | 'redis' | 'kafka';
export type CompilerLanguageCode = 'c' | 'cpp' | 'java' | 'python';
export type OfflineAnswerVisibility = 'full' | 'none';
export type OfflineSyncMode = 'allow' | 'disabled';

export interface OfflinePolicy {
  ttl_hours: number | null;
  answer_visibility: OfflineAnswerVisibility;
  sync_mode: OfflineSyncMode;
}

export interface PublicUser {
  id: string;
  username: string;
  display_name: string;
  role: Role;
  permissions: string[];
  school: string;
  rating: number;
  solved: number;
  disabled: boolean;
}

export interface UserProfile extends PublicUser {
  email: string;
}

export interface UserProfileUpdate {
  display_name?: string;
  school?: string;
  email?: string;
}

export interface PasswordChangeRequest {
  current_password: string;
  new_password: string;
}

export interface PermissionInfo {
  code: string;
  description: string;
  category: string;
}

export interface RolePermissionInfo {
  code: Role;
  name: string;
  description: string;
  permissions: string[];
}

export interface RbacMatrix {
  roles: RolePermissionInfo[];
  permissions: PermissionInfo[];
  matrix: Record<string, Record<string, boolean>>;
}

export interface CompilerLanguage {
  code: CompilerLanguageCode;
  display_name: string;
  version: string;
  source_extension: string;
}

export interface CompilerConfig extends CompilerLanguage {
  compile_command: string[];
  run_command: string[];
  enabled: boolean;
  sort_order: number;
  updated_at: string;
}

export interface CompilerConfigUpdate {
  display_name?: string;
  version?: string;
  source_extension?: string;
  compile_command?: string[];
  run_command?: string[];
  enabled?: boolean;
  sort_order?: number;
}

export interface Tag {
  id: string;
  name: string;
  slug: string;
  parent_id: string | null;
  sort_order: number;
  created_at: string;
}

export interface TagTreeNode extends Tag {
  children: TagTreeNode[];
}

export interface TagFormPayload {
  name: string;
  parent_id: string | null;
  sort_order: number;
}

export interface ProblemSummary {
  id: string;
  title: string;
  type: ProblemType;
  difficulty: string;
  tags: string[];
  accepted: number;
  attempts: number;
}

export interface ProblemDetail extends ProblemSummary {
  statement: string;
  input_format: string;
  output_format: string;
  samples: Array<{ input: string; output: string }>;
  options: Array<{ key: string; text: string }>;
  blanks: Array<{ key: string; label: string; score: number }>;
  time_limit_ms: number | null;
  memory_limit_mb: number | null;
  author_id: string;
  created_at: string;
  judge_config?: Record<string, unknown> | null;
}

export interface ProblemTestData {
  problem_id: string;
  filename: string;
  object_key: string;
  storage_backend: string;
  bucket: string;
  archive_format: 'zip';
  size_bytes: number;
  sha256: string;
  file_count: number;
  input_files: number;
  output_files: number;
  case_count: number;
  case_names: string[];
  uploaded_by: string;
  uploaded_at: string;
}

export interface ProblemAdminDetail extends ProblemDetail {
  visible: boolean;
  offline_enabled: boolean;
  offline_policy: OfflinePolicy;
  judge_config: Record<string, unknown>;
  test_data: ProblemTestData | null;
}

export interface ProblemVersionSnapshot {
  id: string;
  title: string;
  type: ProblemType;
  difficulty: '入门' | '基础' | '提高' | '困难';
  tags: string[];
  statement: string;
  input_format: string;
  output_format: string;
  samples: Array<{ input: string; output: string }>;
  options: Array<{ key: string; text: string }>;
  blanks: Array<{ key: string; label: string; score: number }>;
  time_limit_ms: number | null;
  memory_limit_mb: number | null;
  author_id: string;
  visible: boolean;
  offline_enabled: boolean;
  offline_policy: OfflinePolicy;
  judge_config: Record<string, unknown>;
  created_at: string;
}

export interface ProblemVersion {
  id: string;
  problem_id: string;
  version: number;
  saved_by: string;
  action: 'update' | 'delete' | 'restore';
  saved_at: string;
  snapshot: ProblemVersionSnapshot;
}

export interface ProblemExportResponse {
  format: ProblemPackageFormat;
  filename: string;
  content_type: string;
  content: string;
  problem_count: number;
  problem_ids: string[];
}

export interface ProblemImportRequest {
  format: ProblemPackageFormat;
  content: string;
  conflict_strategy: ProblemImportConflictStrategy;
  dry_run?: boolean;
}

export interface ProblemImportItem {
  source_id: string | null;
  target_id: string | null;
  title: string;
  type: ProblemType;
  action: 'created' | 'updated' | 'skipped';
}

export interface ProblemImportResponse {
  format: ProblemPackageFormat;
  dry_run: boolean;
  rollback_on_error: boolean;
  imported: number;
  created: number;
  updated: number;
  skipped: number;
  items: ProblemImportItem[];
}

export interface ProblemFormPayload {
  title: string;
  type: ProblemType;
  difficulty: '入门' | '基础' | '提高' | '困难';
  tags: string[];
  statement: string;
  input_format: string;
  output_format: string;
  samples: Array<{ input: string; output: string }>;
  options: Array<{ key: string; text: string }>;
  blanks: Array<{ key: string; label: string; score: number }>;
  time_limit_ms: number | null;
  memory_limit_mb: number | null;
  visible: boolean;
  offline_enabled: boolean;
  offline_policy: OfflinePolicy;
  judge_config: Record<string, unknown>;
}

export interface Submission {
  id: string;
  user_id: string;
  problem_id: string;
  problem_title: string;
  problem_type: ProblemType;
  contest_id: string | null;
  language: string | null;
  source_code: string | null;
  queue_job_id: string | null;
  queued_at: string | null;
  offline_result_key: string | null;
  answers: Record<string, unknown> | null;
  status: string;
  score: number;
  max_score: number;
  details: Array<Record<string, unknown>>;
  message: string;
  created_at: string;
  judged_at: string | null;
}

export interface RejudgeSkipped {
  submission_id: string;
  reason: string;
}

export interface RejudgeBatchResponse {
  requeued: Submission[];
  skipped: RejudgeSkipped[];
  requeued_count: number;
  skipped_count: number;
}

export interface Contest {
  id: string;
  title: string;
  rule: string;
  start_at: string;
  end_at: string;
  status: string;
  visibility: 'public' | 'private';
  frozen: boolean;
  freeze_disabled: boolean;
  frozen_at: string | null;
  frozen_by: string | null;
  freeze_reason: string;
  freeze_active: boolean;
  freeze_effective_at: string | null;
  rejudge_at: string | null;
  rejudge_by: string | null;
  rejudge_reason: string;
  problems: ProblemSummary[];
}

export interface ContestProblemView {
  problem_id: string;
  problem_key: string;
  title: string;
  type: ProblemType;
  allowed_languages: CompilerLanguageCode[];
}

export interface ContestSubmissionView extends Submission {
  problem_key: string;
  team_id: string | null;
  team_name: string | null;
  can_view_source: boolean;
}

export interface ContestTeamSubmissionSummary {
  team_id: string;
  team_name: string;
  member_ids: string[];
  submission_count: number;
  accepted_count: number;
  latest_submission_at: string | null;
  latest_status: string | null;
}

export interface ContestSubmissionStatusResponse {
  contest_id: string;
  contest_title: string;
  rule: string;
  now: string;
  can_submit: boolean;
  status: 'scheduled' | 'running' | 'ended';
  can_view_all: boolean;
  show_team_view: boolean;
  problems: ContestProblemView[];
  submissions: ContestSubmissionView[];
  teams: ContestTeamSubmissionSummary[];
}

export interface StandingProblemResult {
  score: number;
  max_score: number;
  status: string;
  attempts: number;
  accepted_at: string | null;
  penalty_minutes: number;
  first_blood: boolean;
}

export interface StandingRow {
  user_id: string;
  display_name: string;
  solved: number;
  score: number;
  penalty: number;
  first_blood: number;
  problems: Record<string, StandingProblemResult>;
}

export interface JudgeNode {
  id: string;
  name: string;
  status: JudgeNodeStatus;
  languages: string[];
  queue_depth: number;
  load: number;
  last_heartbeat: string;
}

export interface JudgeQueueJob {
  id: string;
  submission_id: string;
  problem_id: string;
  user_id: string;
  contest_id: string | null;
  language: string;
  source_ref: string;
  source_sha256: string;
  limits: Record<string, number | null>;
  testdata_ref: string | null;
  priority: number;
  status: JudgeQueueJobStatus;
  backend: JudgeQueueBackend;
  assigned_node_id: string | null;
  attempts: number;
  last_error: string;
  created_at: string;
  leased_at: string | null;
  completed_at: string | null;
}

export interface JudgeQueueSummary {
  backend: JudgeQueueBackend;
  topic: string;
  depth: number;
  pending: number;
  leased: number;
  last_jobs: JudgeQueueJob[];
}

export interface JudgeMonitor {
  queue_depth: number;
  queue: JudgeQueueSummary;
  last_submissions: Submission[];
  judge_nodes: JudgeNode[];
  clarifications: Clarification[];
  contests: Contest[];
  frozen_contests: Contest[];
  balloons: ContestBalloon[];
}

export interface AuditLog {
  id: string;
  actor_id: string | null;
  action: string;
  resource: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface AuditLogList {
  items: AuditLog[];
  total: number;
  limit: number;
  offset: number;
}

export interface ProblemSet {
  id: string;
  title: string;
  description: string;
  type: 'set' | 'exam' | 'assignment';
  visibility: 'public' | 'private';
  problem_ids: string[];
  problems: ProblemSummary[];
  owner_id: string;
  duration_minutes: number | null;
  due_at: string | null;
  offline_enabled: boolean;
  offline_policy: OfflinePolicy;
  created_at: string;
  updated_at: string;
}

export interface Discussion {
  id: string;
  type: 'general' | 'problem' | 'contest' | 'solution';
  target_id: string | null;
  title: string;
  content: string;
  author_id: string;
  author_name: string;
  pinned: boolean;
  likes: number;
  replies: Array<Record<string, unknown>>;
  created_at: string;
  updated_at: string;
}

export interface NotificationItem {
  id: string;
  user_id: string;
  title: string;
  content: string;
  type: 'judge' | 'contest' | 'reply' | 'system' | 'assignment';
  is_read: boolean;
  created_at: string;
}

export interface Clarification {
  id: string;
  contest_id: string;
  user_id: string;
  question: string;
  answer: string | null;
  public: boolean;
  created_at: string;
}

export interface ContestPrintResponse {
  contest_id: string;
  submission_id: string | null;
  problem_id: string | null;
  language: string | null;
  source_kind: 'submission' | 'request';
  source_code: string;
  line_count: number;
}

export interface ContestBalloon {
  contest_id: string;
  submission_id: string;
  user_id: string;
  display_name: string;
  problem_id: string;
  problem_title: string;
  status: string;
  score: number;
  max_score: number;
  judged_at: string | null;
  released: boolean;
}

export interface Team {
  id: string;
  name: string;
  description: string;
  invite_code: string;
  owner_id: string;
  member_ids: string[];
  created_at: string;
}

export interface SystemConfig {
  site_name: string;
  registration_enabled: boolean;
  default_language: string;
  judge_submit_rate_limit_per_minute: number;
  objective_submit_rate_limit_per_minute: number;
  password_min_length: number;
  password_require_letter: boolean;
  password_require_digit: boolean;
  login_max_failed_attempts: number;
  login_lockout_minutes: number;
  maintenance_mode: boolean;
  [key: string]: unknown;
}

export type SystemConfigUpdate = Partial<SystemConfig>;
