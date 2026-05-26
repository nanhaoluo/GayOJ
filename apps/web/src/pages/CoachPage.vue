<script setup lang="ts">
import { Activity, BarChart3, ClipboardCheck, Filter, Plus, ShieldCheck, UsersRound } from 'lucide-vue-next';
import { computed, onMounted, reactive, ref } from 'vue';
import BaseModal from '@/components/BaseModal.vue';
import { apiRequest, formatDate, problemTypeLabel } from '@/services/api';
import type {
  ActivityHeatmapCell,
  AssignmentAnalytics,
  AssignmentProgressState,
  CoachAnalyticsResponse,
  CoachSimilarityFinding,
  CoachSimilarityResponse,
  ProblemSet,
  StudentAbilityProfile,
  TagMastery,
  Team,
} from '@/services/types';

const data = ref<CoachAnalyticsResponse | null>(null);
const similarity = ref<CoachSimilarityResponse | null>(null);
const problemSets = ref<ProblemSet[]>([]);
const error = ref('');
const similarityError = ref('');
const assignmentOpen = ref(false);
const teamForm = reactive({ name: '', description: '' });
const assignmentForm = reactive({
  title: '',
  description: '',
  problem_set_id: '',
  team_id: '',
  due_at: '',
});
const similarityFilters = reactive({
  problem_id: '',
  contest_id: '',
  threshold: 82,
});

const stateText: Record<AssignmentProgressState, string> = {
  not_started: '未开始',
  in_progress: '进行中',
  overdue: '逾期',
  completed: '完成',
};

const visibleProfiles = computed(() => data.value?.student_profiles.slice(0, 6) ?? []);
const topTags = computed(() => data.value?.tag_mastery.slice(0, 8) ?? []);
const activityCells = computed(() => data.value?.activity_heatmap.slice(-21) ?? []);
const heatmapMax = computed(() => Math.max(1, ...activityCells.value.map((item) => item.attempts)));
const similarityFindings = computed(() => similarity.value?.findings ?? []);

function percent(value: number): string {
  return `${Math.round(Math.max(0, Math.min(1, value)) * 100)}%`;
}

function heatmapLevel(item: ActivityHeatmapCell): number {
  return Math.min(4, Math.ceil((item.attempts / heatmapMax.value) * 4));
}

function latestTag(profile: StudentAbilityProfile): string {
  return profile.tag_mastery[0]?.tag ?? '暂无标签';
}

function stateCount(item: AssignmentAnalytics, state: AssignmentProgressState): number {
  return item.state_counts[state] ?? 0;
}

function studentTeams(item: CoachSimilarityFinding, side: 'a' | 'b'): string {
  const student = side === 'a' ? item.student_a : item.student_b;
  return student.team_names.length ? student.team_names.join('、') : student.school || '未分组';
}

function similarityMeta(item: CoachSimilarityFinding): string {
  const contest = item.contest_title ? `${item.contest_title} · ` : '';
  return `${contest}${item.language.toUpperCase()} · 共享 ${item.shared_token_count} 个 token`;
}

function similarityQuery(): string {
  const params = new URLSearchParams({
    threshold: String(similarityFilters.threshold / 100),
    limit: '50',
  });
  if (similarityFilters.problem_id) params.set('problem_id', similarityFilters.problem_id);
  if (similarityFilters.contest_id) params.set('contest_id', similarityFilters.contest_id);
  return params.toString();
}

async function loadSimilarity() {
  similarityError.value = '';
  try {
    similarity.value = await apiRequest<CoachSimilarityResponse>(`/coach/similarity?${similarityQuery()}`);
  } catch (err) {
    similarityError.value = err instanceof Error ? err.message : '加载相似提交失败。';
  }
}

async function load() {
  try {
    const [analytics, sets, similarityData] = await Promise.all([
      apiRequest<CoachAnalyticsResponse>('/coach/analytics'),
      apiRequest<ProblemSet[]>('/problem-sets', { auth: false }),
      apiRequest<CoachSimilarityResponse>(`/coach/similarity?${similarityQuery()}`),
    ]);
    data.value = analytics;
    problemSets.value = sets;
    similarity.value = similarityData;
    assignmentForm.problem_set_id ||= sets[0]?.id ?? '';
    assignmentForm.team_id ||= analytics.teams[0]?.id ?? '';
  } catch (err) {
    error.value = err instanceof Error ? err.message : '需要教练或管理员权限。';
  }
}

async function createTeam() {
  error.value = '';
  try {
    await apiRequest<Team>('/teams', {
      method: 'POST',
      body: JSON.stringify({ ...teamForm, member_ids: ['u-student'] }),
    });
    teamForm.name = '';
    teamForm.description = '';
    await load();
  } catch (err) {
    error.value = err instanceof Error ? err.message : '创建队伍失败。';
  }
}

async function createAssignment() {
  error.value = '';
  try {
    await apiRequest('/assignments', {
      method: 'POST',
      body: JSON.stringify({
        ...assignmentForm,
        team_id: assignmentForm.team_id || null,
        due_at: new Date(assignmentForm.due_at).toISOString(),
      }),
    });
    assignmentForm.title = '';
    assignmentForm.description = '';
    assignmentOpen.value = false;
    await load();
  } catch (err) {
    error.value = err instanceof Error ? err.message : '创建作业失败。';
  }
}

onMounted(load);
</script>

<template>
  <div class="page-stack coach-workbench">
    <section class="page-heading">
      <div>
        <span class="eyebrow">Coach Console</span>
        <h1>教练端</h1>
      </div>
      <button class="primary-action" type="button" @click="assignmentOpen = true">
        <Plus :size="18" />布置作业
      </button>
    </section>

    <p v-if="error" class="form-error">{{ error }}</p>

    <template v-if="data">
      <section class="summary-strip">
        <span><UsersRound :size="15" />{{ data.class_size }} 名学生</span>
        <span><Activity :size="15" />{{ data.active_students }} 名活跃</span>
        <span><ClipboardCheck :size="15" />{{ data.assignments.length }} 个作业</span>
        <span><BarChart3 :size="15" />{{ data.tag_mastery.length }} 个标签</span>
        <span><ShieldCheck :size="15" />{{ similarity?.findings.length ?? 0 }} 组相似</span>
      </section>

      <section class="dashboard-grid coach-dashboard-grid">
        <div class="panel large-panel">
          <div class="panel-head">
            <div>
              <h2>训练作业</h2>
              <p>截止时间、完成率和单人状态</p>
            </div>
          </div>
          <div class="list-stack">
            <div v-for="item in data.assignments" :key="item.id" class="assignment-card">
              <div class="assignment-card-main">
                <div>
                  <strong>{{ item.title }}</strong>
                  <span>{{ item.problem_set_title }} · 截止 {{ formatDate(item.due_at) }}</span>
                </div>
                <b class="status-pill" :class="`state-${item.status}`">{{ stateText[item.status] }}</b>
              </div>
              <div class="bar-track">
                <i :style="{ width: percent(item.completion) }"></i>
              </div>
              <div class="assignment-state-grid">
                <span>完成 {{ item.completed_count }}/{{ item.student_count }}</span>
                <span>未开始 {{ stateCount(item, 'not_started') }}</span>
                <span>进行中 {{ stateCount(item, 'in_progress') }}</span>
                <span>逾期 {{ stateCount(item, 'overdue') }}</span>
              </div>
            </div>
            <p v-if="data.assignments.length === 0" class="empty-state">暂无作业。</p>
          </div>
        </div>

        <div class="panel">
          <div class="panel-head">
            <div>
              <h2>队伍管理</h2>
              <p>当前教练负责的班级和邀请码</p>
            </div>
          </div>
          <div class="list-stack">
            <div v-for="team in data.teams" :key="team.id" class="user-row">
              <strong>{{ team.name }}</strong>
              <span>{{ team.description || '暂无描述' }} · 邀请码 {{ team.invite_code }}</span>
              <b>{{ team.member_ids.length }} 人</b>
            </div>
            <p v-if="data.teams.length === 0" class="empty-state">暂无队伍。</p>
          </div>
          <form class="submit-form compact-form" @submit.prevent="createTeam">
            <label>队伍名<input v-model="teamForm.name" required placeholder="新训练班" /></label>
            <label>描述<input v-model="teamForm.description" placeholder="队伍说明" /></label>
            <button class="secondary-action full" type="submit"><Plus :size="17" />创建队伍</button>
          </form>
        </div>
      </section>

      <section class="dashboard-grid coach-dashboard-grid">
        <div class="panel large-panel">
          <div class="panel-head">
            <div>
              <h2>学生能力画像</h2>
              <p>按提交记录聚合，不展示源码或标准答案</p>
            </div>
          </div>
          <div class="profile-list">
            <article v-for="profile in visibleProfiles" :key="profile.user_id" class="student-profile-card">
              <div class="student-profile-head">
                <div>
                  <strong>{{ profile.display_name }}</strong>
                  <span>{{ profile.school }} · {{ latestTag(profile) }}</span>
                </div>
                <b>{{ percent(profile.accuracy) }}</b>
              </div>
              <div class="profile-metrics">
                <span>{{ profile.solved }} 已解</span>
                <span>{{ profile.accepted }}/{{ profile.attempts }} 通过</span>
                <span>{{ formatDate(profile.last_submission_at) }}</span>
              </div>
              <div class="mini-heatmap">
                <i
                  v-for="cell in profile.heatmap.slice(-14)"
                  :key="cell.date"
                  :class="`heat-${Math.min(4, cell.attempts)}`"
                  :title="`${cell.date} · ${cell.attempts} 次提交`"
                ></i>
              </div>
            </article>
            <p v-if="visibleProfiles.length === 0" class="empty-state">暂无学生画像数据。</p>
          </div>
        </div>

        <div class="panel">
          <div class="panel-head">
            <div>
              <h2>活跃热力</h2>
              <p>最近提交密度</p>
            </div>
          </div>
          <div class="heatmap-grid">
            <i
              v-for="cell in activityCells"
              :key="cell.date"
              :class="`heat-${heatmapLevel(cell)}`"
              :title="`${cell.date} · ${cell.attempts} 次提交 · ${cell.active_students} 人`"
            ></i>
          </div>
          <div class="type-stat-list mastery-list">
            <div v-for="item in data.type_mastery" :key="item.problem_type" class="type-stat-row">
              <span>{{ problemTypeLabel(item.problem_type) }}</span>
              <div class="bar-track"><i :style="{ width: percent(item.accuracy) }"></i></div>
              <strong>{{ item.solved }}</strong>
            </div>
          </div>
        </div>
      </section>

      <section class="panel">
        <div class="panel-head coach-similarity-head">
          <div>
            <h2>防抄袭辅助</h2>
            <p>仅展示相似提交元数据，源码与标准答案不在此处展示</p>
          </div>
          <form class="similarity-filter" @submit.prevent="loadSimilarity">
            <label>
              <span>题目</span>
              <select v-model="similarityFilters.problem_id">
                <option value="">全部题目</option>
                <option v-for="problem in similarity?.problems" :key="problem.id" :value="problem.id">
                  {{ problem.title }}（{{ problem.count }}）
                </option>
              </select>
            </label>
            <label>
              <span>比赛</span>
              <select v-model="similarityFilters.contest_id">
                <option value="">全部来源</option>
                <option v-for="contest in similarity?.contests" :key="contest.id" :value="contest.id">
                  {{ contest.title }}（{{ contest.count }}）
                </option>
              </select>
            </label>
            <label>
              <span>阈值 {{ similarityFilters.threshold }}%</span>
              <input v-model.number="similarityFilters.threshold" min="50" max="100" step="1" type="range" />
            </label>
            <button class="secondary-action" type="submit"><Filter :size="16" />筛选</button>
          </form>
        </div>
        <p v-if="similarityError" class="form-error">{{ similarityError }}</p>
        <div v-if="similarity" class="similarity-summary">
          <span>{{ similarity.scanned_submission_count }} 条代码提交</span>
          <span>{{ similarity.candidate_pair_count }} 组候选对比</span>
          <span>生成 {{ formatDate(similarity.generated_at) }}</span>
        </div>
        <div class="similarity-list">
          <article v-for="item in similarityFindings" :key="`${item.submission_a_id}-${item.submission_b_id}`" class="similarity-card">
            <div class="similarity-score">
              <strong>{{ percent(item.similarity) }}</strong>
              <span>相似度</span>
            </div>
            <div class="similarity-main">
              <div class="similarity-title">
                <strong>{{ item.problem_title }}</strong>
                <span>{{ similarityMeta(item) }}</span>
              </div>
              <div class="similarity-pair">
                <span>{{ item.student_a.display_name }} · {{ studentTeams(item, 'a') }}</span>
                <span>{{ item.student_b.display_name }} · {{ studentTeams(item, 'b') }}</span>
              </div>
              <div class="similarity-meta-row">
                <span>{{ item.submission_a_id }} · {{ formatDate(item.submitted_at_a) }}</span>
                <span>{{ item.submission_b_id }} · {{ formatDate(item.submitted_at_b) }}</span>
              </div>
            </div>
            <b class="status-pill">需复核</b>
          </article>
          <p v-if="similarityFindings.length === 0" class="empty-state">暂无达到阈值的相似提交。</p>
        </div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <div>
            <h2>标签掌握度</h2>
            <p>按负责学生提交聚合，显示通过率和覆盖学生数</p>
          </div>
        </div>
        <div class="tag-mastery-grid">
          <article v-for="item in topTags" :key="item.tag" class="tag-mastery-card">
            <strong>{{ item.tag }}</strong>
            <span>{{ item.accepted }}/{{ item.attempts }} 通过 · {{ item.student_count }} 人</span>
            <div class="bar-track"><i :style="{ width: percent(item.accuracy) }"></i></div>
          </article>
          <p v-if="topTags.length === 0" class="empty-state">暂无标签掌握数据。</p>
        </div>
      </section>
    </template>

    <BaseModal :open="assignmentOpen" title="布置作业" description="基于题单发布训练任务" size="md" @close="assignmentOpen = false">
      <form class="submit-form" @submit.prevent="createAssignment">
        <label>标题<input v-model="assignmentForm.title" required placeholder="作业标题" /></label>
        <label>题单<select v-model="assignmentForm.problem_set_id">
          <option v-for="set in problemSets" :key="set.id" :value="set.id">{{ set.title }}</option>
        </select></label>
        <label>队伍<select v-model="assignmentForm.team_id">
          <option value="">全部负责学生</option>
          <option v-for="team in data?.teams" :key="team.id" :value="team.id">{{ team.name }}</option>
        </select></label>
        <label>截止时间<input v-model="assignmentForm.due_at" required type="datetime-local" /></label>
        <label>说明<textarea v-model="assignmentForm.description" rows="3"></textarea></label>
        <button class="primary-action full" type="submit"><Plus :size="17" />发布作业</button>
      </form>
    </BaseModal>
  </div>
</template>
