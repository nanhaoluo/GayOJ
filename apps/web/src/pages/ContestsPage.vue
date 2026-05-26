<script setup lang="ts">
import {
  ArrowRight,
  ClipboardList,
  FilePenLine,
  Lock,
  LockOpen,
  MessageSquare,
  Plus,
  RefreshCw,
  RotateCcw,
  Save,
  Users,
  Trophy,
} from 'lucide-vue-next';
import { computed, onMounted, reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import BaseModal from '@/components/BaseModal.vue';
import ProblemTypeIcon from '@/components/ProblemTypeIcon.vue';
import StatusBadge from '@/components/StatusBadge.vue';
import { apiRequest, formatDate } from '@/services/api';
import type {
  CompilerLanguage,
  Contest,
  ContestFormPayload,
  ContestProblemLayoutItem,
  ContestRejudgeResponse,
  ProblemAdminDetail,
  Team,
} from '@/services/types';
import { authState } from '@/stores/auth';

type ContestRule = ContestFormPayload['rule'];

const router = useRouter();
const contests = ref<Contest[]>([]);
const problems = ref<ProblemAdminDetail[]>([]);
const compilerLanguages = ref<CompilerLanguage[]>([]);
const teams = ref<Team[]>([]);
const selected = ref('');
const actionError = ref('');
const notice = ref('');
const rejudgingContestId = ref('');
const loading = ref(false);
const editorOpen = ref(false);
const saving = ref(false);
const editingContestId = ref('');
const problemFilter = ref('');

const contestForm = reactive<ContestFormPayload>({
  title: '',
  rule: 'ACM',
  start_at: '',
  end_at: '',
  problem_ids: [],
  problem_layout: [],
  visibility: 'public',
  participation_mode: 'open',
  registered_user_ids: [],
  registered_team_ids: [],
});

const canManageContests = computed(() => Boolean(authState.user?.permissions.includes('contest:manage')));
const canTriggerContestRejudge = computed(() => {
  const permissions = authState.user?.permissions ?? [];
  return permissions.includes('submission:override') && (permissions.includes('judge:monitor') || permissions.includes('contest:manage'));
});
const manageableProblems = computed(() => {
  const query = problemFilter.value.trim().toLowerCase();
  const items = problems.value;
  if (!query) return items;
  return items.filter((problem) => `${problem.id} ${problem.title} ${problem.tags.join(' ')}`.toLowerCase().includes(query));
});
const selectedProblemSet = computed(() => new Set(contestForm.problem_ids));
const isEditing = computed(() => Boolean(editingContestId.value));

const ruleOptions: ContestRule[] = ['ACM', 'OI', 'IOI', 'CF'];
const visibilityOptions: Array<ContestFormPayload['visibility']> = ['public', 'private'];
const participationOptions: Array<ContestFormPayload['participation_mode']> = ['open', 'individual', 'team'];
const userRosterText = computed({
  get: () => contestForm.registered_user_ids.join(','),
  set: (value: string) => {
    contestForm.registered_user_ids = value
      .replace(/，/g, ',')
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean);
  },
});

function participationLabel(value: ContestFormPayload['participation_mode']): string {
  const labels: Record<ContestFormPayload['participation_mode'], string> = {
    open: '开放参赛',
    individual: '个人报名',
    team: '队伍报名',
  };
  return labels[value];
}

function defaultLayoutItem(problemId: string, index: number): ContestProblemLayoutItem {
  return {
    problem_id: problemId,
    problem_key: String.fromCharCode('A'.charCodeAt(0) + index),
    allowed_languages: [],
  };
}

function normalizeDateTimeInput(value: string | null | undefined): string {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, '0');
  const day = `${date.getDate()}`.padStart(2, '0');
  const hour = `${date.getHours()}`.padStart(2, '0');
  const minute = `${date.getMinutes()}`.padStart(2, '0');
  return `${year}-${month}-${day}T${hour}:${minute}`;
}

function normalizeLayout(problemIds: string[], layout: ContestProblemLayoutItem[]): ContestProblemLayoutItem[] {
  const byProblemId = new Map(layout.map((item) => [item.problem_id, item]));
  return problemIds.map((problemId, index) => {
    const existing = byProblemId.get(problemId);
    return {
      problem_id: problemId,
      problem_key: existing?.problem_key || defaultLayoutItem(problemId, index).problem_key,
      allowed_languages: existing?.allowed_languages ? [...existing.allowed_languages] : [],
    };
  });
}

function resetForm() {
  editingContestId.value = '';
  contestForm.title = '';
  contestForm.rule = 'ACM';
  contestForm.start_at = '';
  contestForm.end_at = '';
  contestForm.problem_ids = [];
  contestForm.problem_layout = [];
  contestForm.visibility = 'public';
  contestForm.participation_mode = 'open';
  contestForm.registered_user_ids = [];
  contestForm.registered_team_ids = [];
  problemFilter.value = '';
}

function openCreateContest() {
  resetForm();
  editorOpen.value = true;
}

function openEditContest(contest: Contest) {
  editingContestId.value = contest.id;
  contestForm.title = contest.title;
  contestForm.rule = contest.rule;
  contestForm.start_at = normalizeDateTimeInput(contest.start_at);
  contestForm.end_at = normalizeDateTimeInput(contest.end_at);
  contestForm.problem_ids = [...contest.problem_ids];
  contestForm.problem_layout = normalizeLayout(contest.problem_ids, contest.problem_layout);
  contestForm.visibility = contest.visibility;
  contestForm.participation_mode = contest.participation_mode;
  contestForm.registered_user_ids = [...contest.registered_user_ids];
  contestForm.registered_team_ids = [...contest.registered_team_ids];
  problemFilter.value = '';
  editorOpen.value = true;
}

function contestEnded(contest: Contest): boolean {
  return new Date(contest.end_at).getTime() <= Date.now();
}

function canRejudgeContest(contest: Contest): boolean {
  return canTriggerContestRejudge.value && contestEnded(contest);
}

function rejudgeMeta(contest: Contest): string {
  return contest.rejudge_at ? `最近重测 ${formatDate(contest.rejudge_at)}` : '';
}

function rosterMeta(contest: Contest): string {
  if (contest.participation_mode === 'open') return '开放';
  const count = contest.participation_mode === 'team' ? contest.registered_team_count : contest.registered_user_count;
  return `${participationLabel(contest.participation_mode)} · ${count}${contest.participation_mode === 'team' ? ' 队' : ' 人'}${contest.roster_locked ? ' · 已锁定' : ''}`;
}

function problemTitle(problemId: string): string {
  return problems.value.find((problem) => problem.id === problemId)?.title || problemId;
}

function toggleProblem(problem: ProblemAdminDetail) {
  const exists = selectedProblemSet.value.has(problem.id);
  if (exists) {
    contestForm.problem_ids = contestForm.problem_ids.filter((id) => id !== problem.id);
  } else {
    contestForm.problem_ids = [...contestForm.problem_ids, problem.id];
  }
  contestForm.problem_layout = normalizeLayout(contestForm.problem_ids, contestForm.problem_layout);
}

function moveProblem(problemId: string, direction: -1 | 1) {
  const index = contestForm.problem_ids.indexOf(problemId);
  const nextIndex = index + direction;
  if (index < 0 || nextIndex < 0 || nextIndex >= contestForm.problem_ids.length) return;
  const ids = [...contestForm.problem_ids];
  const [item] = ids.splice(index, 1);
  ids.splice(nextIndex, 0, item);
  contestForm.problem_ids = ids;
  contestForm.problem_layout = normalizeLayout(contestForm.problem_ids, contestForm.problem_layout);
}

function updateProblemKey(problemId: string, value: string) {
  contestForm.problem_layout = contestForm.problem_layout.map((item) =>
    item.problem_id === problemId ? { ...item, problem_key: value.trim().toUpperCase() } : item,
  );
}

function toggleAllowedLanguage(problemId: string, language: CompilerLanguage['code']) {
  contestForm.problem_layout = contestForm.problem_layout.map((item) => {
    if (item.problem_id !== problemId) return item;
    const exists = item.allowed_languages.includes(language);
    return {
      ...item,
      allowed_languages: exists ? item.allowed_languages.filter((entry) => entry !== language) : [...item.allowed_languages, language],
    };
  });
}

function buildPayload(): ContestFormPayload {
  return {
    title: contestForm.title.trim(),
    rule: contestForm.rule,
    start_at: new Date(contestForm.start_at).toISOString(),
    end_at: new Date(contestForm.end_at).toISOString(),
    problem_ids: [...contestForm.problem_ids],
    problem_layout: normalizeLayout(contestForm.problem_ids, contestForm.problem_layout).map((item) => ({
      problem_id: item.problem_id,
      problem_key: item.problem_key.trim().toUpperCase(),
      allowed_languages: [...item.allowed_languages],
    })),
    visibility: contestForm.visibility,
    participation_mode: contestForm.participation_mode,
    registered_user_ids: contestForm.participation_mode === 'individual' ? [...contestForm.registered_user_ids] : [],
    registered_team_ids: contestForm.participation_mode === 'team' ? [...contestForm.registered_team_ids] : [],
  };
}

async function load() {
  loading.value = true;
  actionError.value = '';
  try {
    const [contestData, problemData, languageData, teamData] = await Promise.all([
      apiRequest<Contest[]>('/contests'),
      canManageContests.value ? apiRequest<ProblemAdminDetail[]>('/admin/problems') : Promise.resolve([]),
      apiRequest<CompilerLanguage[]>('/judge/languages', { auth: false }).catch(() => []),
      canManageContests.value ? apiRequest<Team[]>('/teams') : Promise.resolve([]),
    ]);
    contests.value = contestData;
    problems.value = problemData;
    compilerLanguages.value = languageData;
    teams.value = teamData;
    selected.value = contestData[0]?.id ?? '';
  } catch (err) {
    actionError.value = err instanceof Error ? err.message : '比赛列表加载失败';
  } finally {
    loading.value = false;
  }
}

async function setRosterLock(contest: Contest, locked: boolean) {
  actionError.value = '';
  notice.value = '';
  try {
    await apiRequest(`/contests/${contest.id}/roster/lock`, {
      method: 'POST',
      body: JSON.stringify({ locked }),
    });
    notice.value = `${contest.title} 名单已${locked ? '锁定' : '解锁'}。`;
    await load();
  } catch (err) {
    actionError.value = err instanceof Error ? err.message : '名单锁定失败';
  }
}

async function saveContest() {
  saving.value = true;
  actionError.value = '';
  notice.value = '';
  try {
    const payload = buildPayload();
    const path = isEditing.value ? `/contests/${editingContestId.value}` : '/contests';
    const method = isEditing.value ? 'PUT' : 'POST';
    const saved = await apiRequest<Contest>(path, {
      method,
      body: JSON.stringify(payload),
    });
    notice.value = `${saved.title} 已${isEditing.value ? '更新' : '创建'}。`;
    editorOpen.value = false;
    await load();
    selected.value = saved.id;
  } catch (err) {
    actionError.value = err instanceof Error ? err.message : '比赛保存失败';
  } finally {
    saving.value = false;
  }
}

async function openStandings(id: string) {
  await router.push(`/contests/${id}/standings`);
}

async function openContest(id: string) {
  await router.push(`/contests/${id}`);
}

async function openSubmissions(id: string) {
  await router.push(`/contests/${id}/submissions`);
}

async function openClarifications(id: string) {
  await router.push(`/contests/${id}/clar`);
}

async function freezeContest(contest: Contest) {
  actionError.value = '';
  notice.value = '';
  try {
    await apiRequest<Contest>(`/contests/${contest.id}/freeze`, {
      method: 'POST',
      body: JSON.stringify({ reason: 'manual freeze from contest list' }),
    });
    await load();
  } catch (err) {
    actionError.value = err instanceof Error ? err.message : '封榜失败';
  }
}

async function unfreezeContest(contest: Contest) {
  actionError.value = '';
  notice.value = '';
  try {
    await apiRequest<Contest>(`/contests/${contest.id}/unfreeze`, {
      method: 'POST',
      body: JSON.stringify({ reason: 'manual unfreeze from contest list' }),
    });
    await load();
  } catch (err) {
    actionError.value = err instanceof Error ? err.message : '解封失败';
  }
}

async function rejudgeContest(contest: Contest) {
  if (!canRejudgeContest(contest)) return;
  actionError.value = '';
  notice.value = '';
  rejudgingContestId.value = contest.id;
  try {
    const result = await apiRequest<ContestRejudgeResponse>(`/contests/${contest.id}/rejudge`, {
      method: 'POST',
      body: JSON.stringify({ reason: 'manual contest rejudge from contest list' }),
    });
    notice.value = `比赛 ${contest.title} 已重测 ${result.requeued_count} 条代码提交${result.skipped_count ? `，跳过 ${result.skipped_count} 条` : ''}。`;
    await load();
  } catch (err) {
    actionError.value = err instanceof Error ? err.message : '赛后重测失败';
  } finally {
    rejudgingContestId.value = '';
  }
}

onMounted(load);
</script>

<template>
  <div class="page-stack">
    <section class="page-heading">
      <div>
        <span class="eyebrow">Contest</span>
        <h1>比赛系统</h1>
      </div>
      <div class="row-actions">
        <button class="secondary-action" type="button" :disabled="!selected" @click="openClarifications(selected)">
          <MessageSquare :size="16" />Clarification
        </button>
        <button v-if="canManageContests" class="primary-action" type="button" @click="openCreateContest">
          <Plus :size="16" />新建比赛
        </button>
      </div>
    </section>

    <section class="panel set-list-panel">
      <p v-if="actionError" class="form-error">{{ actionError }}</p>
      <p v-if="notice" class="form-success">{{ notice }}</p>
      <div class="set-table-row set-table-head contest-manage-table">
        <span>比赛</span>
        <span>赛制</span>
        <span>参赛</span>
        <span>状态</span>
        <span>操作</span>
      </div>
      <div v-for="contest in contests" :key="contest.id" class="set-table-row contest-manage-table">
        <div>
          <strong>{{ contest.title }}</strong>
          <span>{{ formatDate(contest.start_at) }} - {{ formatDate(contest.end_at) }}</span>
        </div>
        <span>{{ contest.rule }}</span>
        <span>{{ rosterMeta(contest) }}</span>
        <div class="contest-status-stack">
          <StatusBadge :status="contest.freeze_active ? 'disabled' : contest.status" />
          <small v-if="contest.freeze_active">{{ contest.frozen ? '手动封榜' : '自动封榜' }}</small>
          <small v-if="rejudgeMeta(contest)">{{ rejudgeMeta(contest) }}</small>
        </div>
        <div class="row-actions">
          <button v-if="canManageContests" class="secondary-action" type="button" @click="openEditContest(contest)">
            <FilePenLine :size="16" />编辑
          </button>
          <button
            v-if="canManageContests && contest.participation_mode !== 'open'"
            class="secondary-action"
            type="button"
            @click="setRosterLock(contest, !contest.roster_locked)"
          >
            <Users :size="16" />{{ contest.roster_locked ? '解锁名单' : '锁定名单' }}
          </button>
          <button
            v-if="canManageContests && !contest.freeze_active"
            class="secondary-action"
            type="button"
            @click="freezeContest(contest)"
          >
            <Lock :size="16" />封榜
          </button>
          <button
            v-if="canManageContests && contest.freeze_active"
            class="secondary-action"
            type="button"
            @click="unfreezeContest(contest)"
          >
            <LockOpen :size="16" />解封
          </button>
          <button class="secondary-action" type="button" @click="openStandings(contest.id)">
            <Trophy :size="16" />榜单
          </button>
          <button class="secondary-action" type="button" @click="openContest(contest.id)">
            <ArrowRight :size="16" />进入比赛
          </button>
          <button class="secondary-action" type="button" @click="openSubmissions(contest.id)">
            <ClipboardList :size="16" />提交
          </button>
          <button class="secondary-action" type="button" @click="openClarifications(contest.id)">
            <MessageSquare :size="16" />提问
          </button>
          <button
            v-if="canRejudgeContest(contest)"
            class="secondary-action"
            type="button"
            :disabled="rejudgingContestId === contest.id"
            @click="rejudgeContest(contest)"
          >
            <RotateCcw :size="16" />赛后重测
          </button>
        </div>
      </div>
      <p v-if="loading" class="empty-text"><RefreshCw :size="16" class="spin" /> 正在加载比赛。</p>
      <p v-else-if="contests.length === 0" class="empty-text">暂无比赛。</p>
    </section>

    <BaseModal
      :open="editorOpen"
      :title="isEditing ? '编辑比赛' : '新建比赛'"
      :description="isEditing ? editingContestId : '配置题目、赛制、时间与可见性'"
      size="xl"
      @close="editorOpen = false"
    >
      <form class="submit-form problem-form contest-form" @submit.prevent="saveContest">
        <div class="form-grid two">
          <label>比赛标题<input v-model="contestForm.title" required /></label>
          <label>
            赛制
            <select v-model="contestForm.rule">
              <option v-for="rule in ruleOptions" :key="rule" :value="rule">{{ rule }}</option>
            </select>
          </label>
        </div>

        <div class="form-grid two">
          <label>开始时间<input v-model="contestForm.start_at" type="datetime-local" required /></label>
          <label>结束时间<input v-model="contestForm.end_at" type="datetime-local" required /></label>
        </div>

        <div class="form-grid two">
          <label>
            可见性
            <select v-model="contestForm.visibility">
              <option v-for="visibility in visibilityOptions" :key="visibility" :value="visibility">
                {{ visibility === 'public' ? '公开赛' : '私有赛' }}
              </option>
            </select>
          </label>
          <label>
            参赛方式
            <select v-model="contestForm.participation_mode">
              <option v-for="mode in participationOptions" :key="mode" :value="mode">{{ participationLabel(mode) }}</option>
            </select>
          </label>
        </div>

        <div class="form-grid two">
          <label>题目搜索<input v-model="problemFilter" placeholder="P1001 / 标签 / 标题" /></label>
          <label v-if="contestForm.participation_mode === 'individual'">
            个人名单
            <input v-model="userRosterText" placeholder="u-student,u-xxx" />
          </label>
          <label v-else-if="contestForm.participation_mode === 'team'">
            队伍名单
            <select v-model="contestForm.registered_team_ids" multiple size="4">
              <option v-for="team in teams" :key="team.id" :value="team.id">{{ team.name }} · {{ team.id }}</option>
            </select>
          </label>
          <label v-else>
            名单策略
            <input value="开放赛无需维护名单" disabled />
          </label>
        </div>

        <div class="contest-editor-layout">
          <section class="field-block">
            <div class="field-head">
              <strong>候选题目</strong>
              <span>{{ contestForm.problem_ids.length }} / {{ problems.length }}</span>
            </div>
            <div class="contest-problem-picker">
              <button
                v-for="problem in manageableProblems"
                :key="problem.id"
                type="button"
                class="contest-problem-picker-row"
                :class="{ active: selectedProblemSet.has(problem.id) }"
                @click="toggleProblem(problem)"
              >
                <ProblemTypeIcon :type="problem.type" />
                <span>
                  <strong>{{ problem.id }} · {{ problem.title }}</strong>
                  <em>{{ problem.type }} · {{ problem.difficulty }} · {{ problem.visible ? '公开题库' : '仅管理可见' }}</em>
                </span>
              </button>
              <p v-if="!manageableProblems.length" class="empty-text">暂无可用题目。</p>
            </div>
          </section>

          <section class="field-block">
            <div class="field-head">
              <strong>比赛编排</strong>
              <span>{{ contestForm.problem_layout.length }} 题</span>
            </div>
            <div class="contest-layout-list">
              <div v-for="(item, index) in contestForm.problem_layout" :key="item.problem_id" class="contest-layout-row">
                <div class="contest-layout-row-main">
                  <strong>{{ item.problem_id }} · {{ problemTitle(item.problem_id) }}</strong>
                  <span>第 {{ index + 1 }} 题</span>
                </div>
                <label>
                  题号
                  <input
                    :value="item.problem_key"
                    maxlength="16"
                    @input="updateProblemKey(item.problem_id, ($event.target as HTMLInputElement).value)"
                  />
                </label>
                <div class="contest-layout-actions">
                  <button class="secondary-action compact" type="button" :disabled="index === 0" @click="moveProblem(item.problem_id, -1)">
                    上移
                  </button>
                  <button
                    class="secondary-action compact"
                    type="button"
                    :disabled="index === contestForm.problem_layout.length - 1"
                    @click="moveProblem(item.problem_id, 1)"
                  >
                    下移
                  </button>
                </div>
                <div class="contest-layout-language-grid">
                  <label
                    v-for="language in compilerLanguages"
                    :key="`${item.problem_id}-${language.code}`"
                    class="tag-filter-option"
                  >
                    <input
                      type="checkbox"
                      :checked="item.allowed_languages.includes(language.code)"
                      @change="toggleAllowedLanguage(item.problem_id, language.code)"
                    />
                    <span>{{ language.code }}</span>
                  </label>
                </div>
              </div>
              <p v-if="!contestForm.problem_layout.length" class="empty-text">先从左侧选择题目，再配置题号和语言限制。</p>
            </div>
          </section>
        </div>

        <button class="primary-action full" type="submit" :disabled="saving || !contestForm.problem_ids.length">
          <Save v-if="!saving" :size="16" />
          <RefreshCw v-else :size="16" class="spin" />
          {{ isEditing ? '保存比赛' : '创建比赛' }}
        </button>
      </form>
    </BaseModal>
  </div>
</template>
