<script setup lang="ts">
import { ArrowLeft, RefreshCw } from 'lucide-vue-next';
import { computed, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { apiRequest, formatDate } from '@/services/api';
import type { Contest, StandingProblemResult, StandingRow } from '@/services/types';

const route = useRoute();
const router = useRouter();
const contest = ref<Contest | null>(null);
const standings = ref<StandingRow[]>([]);
const error = ref('');

const problemIds = computed(() => contest.value?.problems.map((problem) => problem.id) ?? []);
const isAcmBoard = computed(() => contest.value?.rule === 'ACM');

function totalAttempts(row: StandingRow): number {
  return Object.values(row.problems).reduce((sum, problem) => sum + problem.attempts, 0);
}

function problemCellClass(problem: StandingProblemResult | undefined): string {
  if (!problem) return 'standing-problem-cell';
  if (isAcmBoard.value) {
    if (problem.accepted_at) {
      return problem.first_blood ? 'standing-problem-cell accepted first-blood' : 'standing-problem-cell accepted';
    }
    if (problem.attempts > 0) {
      return 'standing-problem-cell attempted';
    }
    return 'standing-problem-cell';
  }
  if (problem.score >= problem.max_score && problem.max_score > 0) {
    return 'standing-problem-cell accepted';
  }
  if (problem.score > 0 || problem.attempts > 0) {
    return 'standing-problem-cell attempted';
  }
  return 'standing-problem-cell';
}

function problemCellText(problem: StandingProblemResult | undefined): string {
  if (!problem) return '-';
  if (isAcmBoard.value) {
    if (problem.accepted_at) {
      const wrongAttempts = Math.max(problem.attempts, 0);
      return wrongAttempts > 0 ? `+${wrongAttempts}` : '+';
    }
    if (problem.attempts > 0) {
      return `-${problem.attempts}`;
    }
    return '-';
  }
  if (problem.attempts === 0 && problem.score === 0) {
    return '-';
  }
  return `${problem.score}`;
}

function problemCellMeta(problem: StandingProblemResult | undefined): string {
  if (!problem) return '';
  if (isAcmBoard.value) {
    if (problem.accepted_at) {
      return `${problem.penalty_minutes} min${problem.first_blood ? ' / FB' : ''}`;
    }
    if (problem.attempts > 0) {
      return `${problem.attempts} 次尝试`;
    }
    return '';
  }
  if (problem.attempts > 0) {
    return `${problem.attempts} 次 / ${problem.max_score}`;
  }
  return '';
}

async function load() {
  error.value = '';
  try {
    contest.value = await apiRequest<Contest>(`/contests/${route.params.id}`);
    standings.value = await apiRequest<StandingRow[]>(`/contests/${route.params.id}/standings`);
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
    <section class="pure-content standings-content">
      <div class="pure-heading">
        <h1>{{ contest?.title || '比赛榜单' }}</h1>
        <p v-if="contest">
          {{ contest.rule }} · {{ formatDate(contest.start_at) }} - {{ formatDate(contest.end_at) }}
        </p>
      </div>
      <p v-if="error" class="form-error">{{ error }}</p>
      <div class="table-panel">
        <div class="table-row table-head standings-table standings-grid">
          <span>#</span>
          <span>选手</span>
          <span>{{ isAcmBoard ? '通过' : '总分' }}</span>
          <span>{{ isAcmBoard ? '罚时' : '满分题' }}</span>
          <span>{{ isAcmBoard ? '首杀' : '提交' }}</span>
          <span v-for="problemId in problemIds" :key="problemId">{{ problemId }}</span>
        </div>
        <div
          v-for="(row, index) in standings"
          :key="row.user_id"
          class="table-row standings-table standings-grid"
          :style="{ '--standing-problem-count': String(problemIds.length) }"
        >
          <strong>{{ index + 1 }}</strong>
          <span class="standing-user">{{ row.display_name }}</span>
          <span>{{ isAcmBoard ? row.solved : row.score }}</span>
          <span>{{ isAcmBoard ? row.penalty : row.solved }}</span>
          <span>{{ isAcmBoard ? row.first_blood : totalAttempts(row) }}</span>
          <div
            v-for="problemId in problemIds"
            :key="`${row.user_id}-${problemId}`"
            :class="problemCellClass(row.problems[problemId])"
          >
            <strong>{{ problemCellText(row.problems[problemId]) }}</strong>
            <small>{{ problemCellMeta(row.problems[problemId]) }}</small>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>
