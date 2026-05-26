<script setup lang="ts">
import { computed } from 'vue';
import type { Contest, StandingProblemResult, StandingRow } from '@/services/types';

const props = defineProps<{
  contest: Contest;
  standings: StandingRow[];
}>();

const problemColumns = computed(() => {
  const summaries = new Map(props.contest.problems.map((problem) => [problem.id, problem]));
  const layout = props.contest.problem_layout.length
    ? props.contest.problem_layout
    : props.contest.problem_ids.map((problemId, index) => ({
      problem_id: problemId,
      problem_key: String(index + 1),
      display_title: null,
      score: null,
      allowed_languages: [],
    }));
  return layout
    .filter((item) => summaries.has(item.problem_id) || props.contest.problem_ids.includes(item.problem_id))
    .map((item) => ({
      id: item.problem_id,
      key: item.problem_key || item.problem_id,
      title: item.display_title || summaries.get(item.problem_id)?.title || item.problem_key || '比赛题目',
      score: item.score,
    }));
});
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
    <div class="table-row table-head standings-table standings-grid" :style="{ '--standing-problem-count': String(problemColumns.length) }">
      <span>#</span>
      <span>选手</span>
      <span>{{ isAcmBoard ? '通过' : '总分' }}</span>
      <span>{{ isAcmBoard ? '罚时' : '满分题' }}</span>
      <span>{{ isAcmBoard ? '首杀' : '提交' }}</span>
      <span v-for="problem in problemColumns" :key="problem.id" class="standing-problem-head" :title="problem.title">
        <strong>{{ problem.key }}</strong>
        <small>{{ problem.score !== null ? `${problem.score} 分` : problem.title }}</small>
      </span>
    </div>
    <div
      v-for="(row, index) in standings"
      :key="row.user_id"
      class="table-row standings-table standings-grid"
      :style="{ '--standing-problem-count': String(problemColumns.length) }"
    >
      <strong>{{ index + 1 }}</strong>
      <span class="standing-user">{{ row.display_name }}</span>
      <span>{{ isAcmBoard ? row.solved : row.score }}</span>
      <span>{{ isAcmBoard ? row.penalty : row.solved }}</span>
      <span>{{ isAcmBoard ? row.first_blood : totalAttempts(row) }}</span>
      <div
        v-for="problem in problemColumns"
        :key="`${row.user_id}-${problem.id}`"
        :class="problemCellClass(row.problems[problem.id])"
      >
        <strong>{{ problemCellText(row.problems[problem.id]) }}</strong>
        <small>{{ problemCellMeta(row.problems[problem.id]) }}</small>
      </div>
    </div>
  </div>
</template>
