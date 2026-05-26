<script setup lang="ts">
import { ArrowLeft, Eye, EyeOff, RefreshCw } from 'lucide-vue-next';
import { computed, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import StatusBadge from '@/components/StatusBadge.vue';
import { apiRequest, formatDate, problemTypeLabel } from '@/services/api';
import type { ContestSubmissionStatusResponse, ContestSubmissionView, ContestTeamSubmissionSummary } from '@/services/types';

const route = useRoute();
const router = useRouter();
const payload = ref<ContestSubmissionStatusResponse | null>(null);
const error = ref('');
const selectedSubmissionId = ref('');

const submissions = computed(() => payload.value?.submissions ?? []);
const teams = computed(() => payload.value?.teams ?? []);
const selectedSubmission = computed<ContestSubmissionView | null>(
  () => submissions.value.find((item) => item.id === selectedSubmissionId.value) ?? submissions.value[0] ?? null,
);
const selectedTeam = computed<ContestTeamSubmissionSummary | null>(
  () => teams.value.find((item) => item.team_id === selectedSubmission.value?.team_id) ?? null,
);

function summaryText(): string {
  if (!payload.value) return '';
  if (payload.value.status === 'scheduled') return '比赛未开始，提交入口关闭。';
  if (payload.value.status === 'ended') return '比赛已结束，仅保留状态查看。';
  if (!payload.value.can_submit) return '当前账号不可提交，仅查看比赛提交状态。';
  return '比赛进行中，代码题进入在线评测队列，客观题即时判分。';
}

function allowedLanguageText(problemId: string): string {
  const problem = payload.value?.problems.find((item) => item.problem_id === problemId);
  if (!problem || !problem.allowed_languages.length) return '不限语言';
  return problem.allowed_languages.join(', ');
}

async function load() {
  error.value = '';
  try {
    payload.value = await apiRequest<ContestSubmissionStatusResponse>(`/contests/${route.params.id}/submissions`);
    if (!selectedSubmissionId.value || !submissions.value.some((item) => item.id === selectedSubmissionId.value)) {
      selectedSubmissionId.value = submissions.value[0]?.id ?? '';
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败';
  }
}

onMounted(load);
</script>

<template>
  <div class="pure-page">
    <header class="pure-toolbar">
      <button class="secondary-action" type="button" @click="router.back()"><ArrowLeft :size="16" />返回</button>
      <button class="secondary-action" type="button" @click="load"><RefreshCw :size="16" />刷新</button>
    </header>

    <section class="pure-content contest-submissions-content">
      <div class="pure-heading">
        <h1>{{ payload?.contest_title || '比赛提交' }}</h1>
        <p v-if="payload">{{ payload.rule }} · {{ formatDate(payload.now) }}</p>
      </div>

      <div v-if="payload" class="summary-strip">
        <span><StatusBadge :status="payload.status" /> <strong>{{ payload.status === 'running' ? '比赛中' : payload.status === 'scheduled' ? '未开始' : '已结束' }}</strong></span>
        <span>{{ summaryText() }}</span>
        <span>提交 {{ submissions.length }}</span>
        <span v-if="payload.show_team_view">队伍 {{ teams.length }}</span>
      </div>

      <p v-if="error" class="form-error">{{ error }}</p>

      <div class="contest-submissions-layout">
        <section class="panel table-panel">
          <div class="panel-head">
            <div>
              <h2>提交列表</h2>
              <p>{{ payload?.can_view_all ? '裁判/管理员视图' : '个人比赛提交' }}</p>
            </div>
          </div>
          <div class="table-row table-head contest-submission-table">
            <span>题号</span>
            <span>题目</span>
            <span>类型</span>
            <span>状态</span>
            <span>分数</span>
            <span>语言</span>
            <span>时间</span>
          </div>
          <button
            v-for="item in submissions"
            :key="item.id"
            class="table-row contest-submission-table contest-submission-row"
            :class="{ active: item.id === selectedSubmissionId }"
            type="button"
            @click="selectedSubmissionId = item.id"
          >
            <strong>{{ item.problem_key }}</strong>
            <span>{{ item.problem_title }}</span>
            <span>{{ problemTypeLabel(item.problem_type) }}</span>
            <span><StatusBadge :status="item.status" /></span>
            <span>{{ item.score }}/{{ item.max_score }}</span>
            <span>{{ item.language || allowedLanguageText(item.problem_id) }}</span>
            <span>{{ formatDate(item.created_at) }}</span>
          </button>
          <p v-if="!submissions.length && !error" class="empty-text">暂无比赛提交。</p>
        </section>

        <section class="panel contest-submission-detail-panel">
          <div class="panel-head">
            <div>
              <h2>状态详情</h2>
              <p v-if="selectedSubmission">提交 {{ selectedSubmission.id }}</p>
            </div>
          </div>
          <div v-if="selectedSubmission" class="contest-submission-detail">
            <div class="contest-detail-grid">
              <span>题号</span><strong>{{ selectedSubmission.problem_key }}</strong>
              <span>题目</span><strong>{{ selectedSubmission.problem_title }}</strong>
              <span>状态</span><strong><StatusBadge :status="selectedSubmission.status" /></strong>
              <span>分数</span><strong>{{ selectedSubmission.score }}/{{ selectedSubmission.max_score }}</strong>
              <span>语言</span><strong>{{ selectedSubmission.language || allowedLanguageText(selectedSubmission.problem_id) }}</strong>
              <span>提交时间</span><strong>{{ formatDate(selectedSubmission.created_at) }}</strong>
              <span>队伍</span><strong>{{ selectedSubmission.team_name || '-' }}</strong>
            </div>

            <div v-if="selectedTeam" class="contest-team-card">
              <h3>{{ selectedTeam.team_name }}</h3>
              <p>成员 {{ selectedTeam.member_ids.join(', ') }}</p>
              <p>提交 {{ selectedTeam.submission_count }} · 通过 {{ selectedTeam.accepted_count }}</p>
            </div>

            <div class="contest-source-block">
              <div class="contest-source-head">
                <h3>源码 / 作答</h3>
                <span v-if="selectedSubmission.can_view_source"><Eye :size="15" />可见</span>
                <span v-else><EyeOff :size="15" />不可见</span>
              </div>
              <pre v-if="selectedSubmission.source_code" class="print-preview">{{ selectedSubmission.source_code }}</pre>
              <pre v-else-if="selectedSubmission.answers" class="print-preview">{{ JSON.stringify(selectedSubmission.answers, null, 2) }}</pre>
              <p v-else class="empty-text">当前视图不展示源码。</p>
            </div>
          </div>
          <p v-else class="empty-text">请选择一条提交查看状态。</p>
        </section>
      </div>
    </section>
  </div>
</template>
