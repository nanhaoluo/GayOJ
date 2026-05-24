<script setup lang="ts">
import { Activity, ArrowRight, BookOpen, Clock, Server, Trophy } from 'lucide-vue-next';
import { computed, onMounted, ref } from 'vue';
import { RouterLink } from 'vue-router';
import ProblemTypeIcon from '@/components/ProblemTypeIcon.vue';
import StatusBadge from '@/components/StatusBadge.vue';
import { apiRequest, formatDate, problemTypeLabel } from '@/services/api';
import type { Contest, ProblemSummary, Submission } from '@/services/types';

const problems = ref<ProblemSummary[]>([]);
const contests = ref<Contest[]>([]);
const submissions = ref<Submission[]>([]);
const rankings = ref<Array<Record<string, unknown>>>([]);
const loading = ref(true);

const acceptedRate = computed(() => {
  const attempts = problems.value.reduce((sum, item) => sum + item.attempts, 0);
  const accepted = problems.value.reduce((sum, item) => sum + item.accepted, 0);
  return attempts ? Math.round((accepted / attempts) * 100) : 0;
});

const typeStats = computed(() => {
  const counts: Record<string, number> = {};
  for (const problem of problems.value) counts[problem.type] = (counts[problem.type] ?? 0) + 1;
  return Object.entries(counts).map(([type, count]) => ({ type, count }));
});

async function load() {
  loading.value = true;
  try {
    const [problemData, contestData, rankingData] = await Promise.all([
      apiRequest<ProblemSummary[]>('/problems', { auth: false }),
      apiRequest<Contest[]>('/contests', { auth: false }),
      apiRequest<Array<Record<string, unknown>>>('/rankings', { auth: false }),
    ]);
    problems.value = problemData;
    contests.value = contestData;
    rankings.value = rankingData;
    try {
      submissions.value = await apiRequest<Submission[]>('/submissions');
    } catch {
      submissions.value = [];
    }
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div class="page-stack">
    <section class="page-heading">
      <div>
        <span class="eyebrow">gayoj / Workspace</span>
        <h1>训练、比赛、评测与管理总览</h1>
      </div>
      <RouterLink class="primary-action" to="/problems">
        <BookOpen :size="18" />
        进入题库
      </RouterLink>
    </section>

    <section class="metric-grid" aria-label="系统指标">
      <article class="metric-panel">
        <BookOpen :size="20" />
        <span>公开题目</span>
        <strong>{{ problems.length }}</strong>
      </article>
      <article class="metric-panel">
        <Trophy :size="20" />
        <span>运行比赛</span>
        <strong>{{ contests.filter((item) => item.status === 'running').length }}</strong>
      </article>
      <article class="metric-panel">
        <Activity :size="20" />
        <span>通过率</span>
        <strong>{{ acceptedRate }}%</strong>
      </article>
      <article class="metric-panel">
        <Server :size="20" />
        <span>评测模式</span>
        <strong>Online</strong>
      </article>
    </section>

    <section class="dashboard-grid">
      <div class="panel large-panel">
        <div class="panel-head">
          <div>
            <h2>题型分布</h2>
            <p>覆盖代码题、填空题、单选题和多选题</p>
          </div>
          <RouterLink to="/problems" class="text-link">查看全部 <ArrowRight :size="15" /></RouterLink>
        </div>
        <div class="type-stat-list">
          <div v-for="item in typeStats" :key="item.type" class="type-stat-row">
            <span>{{ problemTypeLabel(item.type) }}</span>
            <div class="bar-track">
              <i :style="{ width: `${(item.count / Math.max(problems.length, 1)) * 100}%` }"></i>
            </div>
            <strong>{{ item.count }}</strong>
          </div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-head">
          <div>
            <h2>最近比赛</h2>
            <p>多赛制入口</p>
          </div>
        </div>
        <div class="list-stack">
          <RouterLink v-for="contest in contests" :key="contest.id" to="/contests" class="contest-row">
            <div>
              <strong>{{ contest.title }}</strong>
              <span>{{ contest.rule }} · {{ formatDate(contest.end_at) }}</span>
            </div>
            <StatusBadge :status="contest.status" />
          </RouterLink>
        </div>
      </div>

      <div class="panel">
        <div class="panel-head">
          <div>
            <h2>推荐训练</h2>
            <p>按题型快速进入</p>
          </div>
        </div>
        <div class="problem-short-list">
          <RouterLink v-for="problem in problems.slice(0, 4)" :key="problem.id" :to="`/problems/${problem.id}`">
            <ProblemTypeIcon :type="problem.type" />
            <div>
              <strong>{{ problem.id }} · {{ problem.title }}</strong>
              <span>{{ problem.difficulty }} · {{ problemTypeLabel(problem.type) }}</span>
            </div>
          </RouterLink>
        </div>
      </div>

      <div class="panel large-panel">
        <div class="panel-head">
          <div>
            <h2>提交动态</h2>
            <p>登录后显示个人提交，裁判和管理员可查看全局</p>
          </div>
          <RouterLink to="/submissions" class="text-link">提交列表 <ArrowRight :size="15" /></RouterLink>
        </div>
        <div v-if="submissions.length" class="submission-feed">
          <div v-for="item in submissions.slice(0, 5)" :key="item.id" class="submission-row">
            <Clock :size="16" />
            <span>{{ item.problem_title }}</span>
            <StatusBadge :status="item.status" />
            <strong>{{ item.score }}/{{ item.max_score }}</strong>
          </div>
        </div>
        <p v-else class="empty-text">暂无可显示提交。</p>
      </div>

      <div class="panel">
        <div class="panel-head">
          <div>
            <h2>排行榜</h2>
            <p>训练解题数与 Rating</p>
          </div>
        </div>
        <div class="rank-list">
          <div v-for="(row, index) in rankings.slice(0, 5)" :key="String(row.user_id)" class="rank-row">
            <b>{{ index + 1 }}</b>
            <span>{{ row.display_name }}</span>
            <strong>{{ row.solved }} AC</strong>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>
