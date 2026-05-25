<script setup lang="ts">
import { Activity, MessageSquare, Server, Trophy } from 'lucide-vue-next';
import { onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import BaseModal from '@/components/BaseModal.vue';
import StatusBadge from '@/components/StatusBadge.vue';
import { apiRequest, formatDate } from '@/services/api';
import type { JudgeMonitor } from '@/services/types';

const router = useRouter();
const data = ref<JudgeMonitor | null>(null);
const error = ref('');
const queueOpen = ref(false);

async function load() {
  error.value = '';
  try {
    data.value = await apiRequest<JudgeMonitor>('/judge/monitor');
  } catch (err) {
    error.value = err instanceof Error ? err.message : '需要裁判或管理员权限。';
  }
}

async function openMonitor(contestId: string) {
  await router.push(`/judge/monitor/${contestId}`);
}

async function openClarifications(contestId: string) {
  await router.push(`/judge/clar/${contestId}`);
}

async function openBalloons(contestId: string) {
  await router.push(`/judge/balloons/${contestId}`);
}

onMounted(load);
</script>

<template>
  <div class="page-stack">
    <section class="page-heading">
      <div>
        <span class="eyebrow">Judge Console</span>
        <h1>裁判台</h1>
      </div>
      <button class="secondary-action" type="button" @click="queueOpen = true">
        <Activity :size="16" />队列任务
      </button>
    </section>

    <p v-if="error" class="form-error">{{ error }}</p>

    <template v-if="data">
      <section class="summary-strip">
        <span>{{ data.queue_depth }} 队列深度</span>
        <span>{{ data.queue.pending }} 待调度</span>
        <span>{{ data.queue.leased }} 执行中</span>
        <span>{{ data.judge_nodes.length }} 节点</span>
      </section>

      <section class="dashboard-grid">
        <div class="panel large-panel">
          <div class="panel-head">
            <div>
              <h2>比赛工作台</h2>
              <p>直接进入比赛监控、Clarification 审批和气球台。</p>
            </div>
          </div>
          <div class="list-stack">
            <div v-for="contest in data.contests" :key="contest.id" class="judge-contest-row">
              <div class="judge-contest-main">
                <strong>{{ contest.title }}</strong>
                <span>{{ contest.rule }} · {{ contest.status }} · {{ formatDate(contest.start_at) }} - {{ formatDate(contest.end_at) }}</span>
              </div>
              <StatusBadge :status="contest.freeze_active ? 'disabled' : contest.status" />
              <div class="row-actions">
                <button class="secondary-action compact" type="button" @click="openMonitor(contest.id)">
                  <Server :size="14" />监控
                </button>
                <button class="secondary-action compact" type="button" @click="openClarifications(contest.id)">
                  <MessageSquare :size="14" />Clar
                </button>
                <button class="secondary-action compact" type="button" @click="openBalloons(contest.id)">
                  <Trophy :size="14" />气球
                </button>
              </div>
            </div>
            <p v-if="data.contests.length === 0" class="empty-text">当前没有比赛可供监控。</p>
          </div>
        </div>

        <div class="panel">
          <div class="panel-head">
            <div>
              <h2>节点状态</h2>
              <p>沙箱节点心跳与负载</p>
            </div>
          </div>
          <div class="list-stack">
            <div v-for="node in data.judge_nodes" :key="node.id" class="node-row">
              <div>
                <strong>{{ node.name }}</strong>
                <span>{{ node.languages.join(', ') || '未上报语言' }} · {{ formatDate(node.last_heartbeat) }}</span>
              </div>
              <StatusBadge :status="node.status" />
              <b>{{ node.queue_depth }} / {{ Math.round(node.load * 100) }}%</b>
            </div>
            <p v-if="data.judge_nodes.length === 0" class="empty-text">暂无评测节点心跳。</p>
          </div>
        </div>
      </section>
    </template>

    <BaseModal
      :open="queueOpen"
      title="队列任务"
      :description="data ? `${data.queue.backend} · ${data.queue.topic}` : ''"
      size="lg"
      @close="queueOpen = false"
    >
      <div v-if="data" class="submission-feed">
        <div v-for="job in data.queue.last_jobs" :key="job.id" class="submission-row">
          <span>{{ job.problem_id }} · {{ job.language }}</span>
          <StatusBadge :status="job.status" />
          <strong>{{ job.assigned_node_id ?? '待分配' }}</strong>
        </div>
        <p v-if="data.queue.last_jobs.length === 0" class="empty-text">暂无代码评测队列任务。</p>
      </div>
    </BaseModal>
  </div>
</template>
