<script setup lang="ts">
import { Activity, Server } from 'lucide-vue-next';
import { onMounted, ref } from 'vue';
import BaseModal from '@/components/BaseModal.vue';
import StatusBadge from '@/components/StatusBadge.vue';
import { apiRequest, formatDate } from '@/services/api';
import type { JudgeMonitor } from '@/services/types';

const data = ref<JudgeMonitor | null>(null);
const error = ref('');
const queueOpen = ref(false);

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
        <p v-if="data.queue.last_jobs.length === 0" class="empty-state">暂无代码评测队列任务。</p>
      </div>
    </BaseModal>
  </div>
</template>
