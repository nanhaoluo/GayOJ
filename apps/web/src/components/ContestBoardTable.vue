<script setup lang="ts">
import { computed } from 'vue';
import type { Contest, StandingProblemResult, StandingRow } from '@/services/types';

const props = defineProps<{
  contest: Contest;
  standings: StandingRow[];
}>();

const problemIds = computed(() => props.contest.problems.map((problem) => problem.id));
const isAcmBoard = computed(() => props.contest.rule === 'ACM');

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
      return `${problem.attempts} attempts`;
    }
    return '';
  }
  if (problem.attempts > 0) {
    return `${problem.attempts} / ${problem.max_score}`;
  }
  return '';
}
</script>

<template>
  <div class="table-panel contest-board-table">
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
</template>
