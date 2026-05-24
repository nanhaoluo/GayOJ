<script setup lang="ts">
import { Activity, Server } from 'lucide-vue-next';
import { onMounted, ref } from 'vue';
import StatusBadge from '@/components/StatusBadge.vue';
import { apiRequest, formatDate } from '@/services/api';
import type { JudgeMonitor } from '@/services/types';

const data = ref<JudgeMonitor | null>(null);
const error = ref('');

onMounted(async () => {
  try {
    data.value = await apiRequest('/judge/monitor');
  } catch (err) {
    error.value = err instanceof Error ? err.message : '需要裁判或管理员权限。';
  }
});
</script>

<template>
  <div class="page-stack">
    <section class="page-heading">
      <div>
        <span class="eyebrow">Judge Console</span>
        <h1>裁判端</h1>
      </div>
    </section>

    <p v-if="error" class="form-error">{{ error }}</p>

    <template v-if="data">
      <section class="metric-grid">
        <article class="metric-panel">
          <Activity :size="20" />
          <span>队列深度</span>
          <strong>{{ data.queue_depth }}</strong>
        </article>
        <article class="metric-panel">
          <Activity :size="20" />
          <span>待调度</span>
          <strong>{{ data.queue.pending }}</strong>
        </article>
        <article class="metric-panel">
          <Activity :size="20" />
          <span>执行中</span>
          <strong>{{ data.queue.leased }}</strong>
        </article>
        <article class="metric-panel">
          <Server :size="20" />
          <span>评测节点</span>
          <strong>{{ data.judge_nodes.length }}</strong>
        </article>
      </section>

      <section class="dashboard-grid">
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
            <p v-if="data.judge_nodes.length === 0" class="empty-state">暂无评测节点心跳。</p>
          </div>
        </div>

        <div class="panel">
          <div class="panel-head">
            <div>
              <h2>队列任务</h2>
              <p>{{ data.queue.backend }} · {{ data.queue.topic }}</p>
            </div>
          </div>
          <div class="submission-feed">
            <div v-for="job in data.queue.last_jobs" :key="job.id" class="submission-row">
              <span>{{ job.problem_id }} · {{ job.language }}</span>
              <StatusBadge :status="job.status" />
              <strong>{{ job.assigned_node_id ?? '待分配' }}</strong>
            </div>
            <p v-if="data.queue.last_jobs.length === 0" class="empty-state">暂无代码评测队列任务。</p>
          </div>
        </div>

        <div class="panel">
          <div class="panel-head">
            <div>
              <h2>提交流</h2>
              <p>最近 10 条提交</p>
            </div>
          </div>
          <div class="submission-feed">
            <div v-for="item in data.last_submissions" :key="item.id" class="submission-row">
              <span>{{ item.problem_title }}</span>
              <StatusBadge :status="item.status" />
              <strong>{{ item.score }}/{{ item.max_score }}</strong>
            </div>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>
