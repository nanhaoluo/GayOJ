<script setup lang="ts">
import { RefreshCw, RotateCcw } from 'lucide-vue-next';
import { computed, onMounted, ref } from 'vue';
import StatusBadge from '@/components/StatusBadge.vue';
import { apiRequest, formatDate, problemTypeLabel } from '@/services/api';
import { authState } from '@/stores/auth';
import type { RejudgeBatchResponse, Submission } from '@/services/types';

const submissions = ref<Submission[]>([]);
const error = ref('');
const feedback = ref('');
const selectedIds = ref<string[]>([]);
const rejudging = ref(false);

const canManageRejudge = computed(() => Boolean(authState.user?.permissions.includes('submission:override')));
const selectableIds = computed(() => submissions.value.filter((item) => item.problem_type === 'code').map((item) => item.id));
const selectedRejudgeIds = computed(() => selectedIds.value.filter((id) => selectableIds.value.includes(id)));
const allSelected = computed(() => selectableIds.value.length > 0 && selectedRejudgeIds.value.length === selectableIds.value.length);

function canRejudge(item: Submission): boolean {
  return canManageRejudge.value && item.problem_type === 'code';
}

function replaceSubmission(updated: Submission) {
  const index = submissions.value.findIndex((item) => item.id === updated.id);
  if (index >= 0) {
    submissions.value[index] = updated;
  }
}

function toggleAll(event: Event) {
  const checked = (event.target as HTMLInputElement).checked;
  selectedIds.value = checked ? [...selectableIds.value] : [];
}

async function load() {
  error.value = '';
  feedback.value = '';
  try {
    submissions.value = await apiRequest<Submission[]>('/submissions');
    selectedIds.value = selectedIds.value.filter((id) => selectableIds.value.includes(id));
  } catch (err) {
    error.value = err instanceof Error ? err.message : '请先登录后查看提交。';
  }
}

async function rejudgeOne(item: Submission) {
  if (!canRejudge(item)) return;
  error.value = '';
  feedback.value = '';
  rejudging.value = true;
  try {
    const updated = await apiRequest<Submission>(`/judge/submissions/${item.id}/rejudge`, {
      method: 'POST',
      body: JSON.stringify({ reason: 'manual-web-rejudge' }),
    });
    replaceSubmission(updated);
    feedback.value = `${updated.id} 已重新进入在线评测队列。`;
  } catch (err) {
    error.value = err instanceof Error ? err.message : '重测请求失败。';
  } finally {
    rejudging.value = false;
  }
}

async function rejudgeSelected() {
  const ids = selectedRejudgeIds.value;
  if (!ids.length) return;
  error.value = '';
  feedback.value = '';
  rejudging.value = true;
  try {
    const result = await apiRequest<RejudgeBatchResponse>('/judge/submissions/rejudge', {
      method: 'POST',
      body: JSON.stringify({ submission_ids: ids, reason: 'manual-web-batch-rejudge' }),
    });
    result.requeued.forEach(replaceSubmission);
    selectedIds.value = [];
    feedback.value = `已重测 ${result.requeued_count} 条提交${result.skipped_count ? `，跳过 ${result.skipped_count} 条` : ''}。`;
  } catch (err) {
    error.value = err instanceof Error ? err.message : '批量重测请求失败。';
  } finally {
    rejudging.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div class="page-stack">
    <section class="page-heading">
      <div>
        <span class="eyebrow">Submissions</span>
        <h1>提交与作答记录</h1>
      </div>
      <button class="secondary-action" @click="load"><RefreshCw :size="17" />刷新</button>
    </section>

    <p v-if="error" class="form-error">{{ error }}</p>
    <p v-if="feedback" class="form-success">{{ feedback }}</p>
    <section v-if="canManageRejudge" class="submission-toolbar">
      <label class="select-cell">
        <input type="checkbox" :checked="allSelected" :disabled="!selectableIds.length || rejudging" @change="toggleAll" />
        <span>全选代码提交</span>
      </label>
      <button class="secondary-action" :disabled="!selectedRejudgeIds.length || rejudging" @click="rejudgeSelected">
        <RotateCcw :size="16" />批量重测
      </button>
    </section>
    <section class="panel table-panel">
      <div class="table-row table-head submissions-table" :class="{ 'with-actions': canManageRejudge }">
        <span v-if="canManageRejudge"></span>
        <span>编号</span>
        <span>题目</span>
        <span>题型</span>
        <span>状态</span>
        <span>分数</span>
        <span>时间</span>
        <span v-if="canManageRejudge">操作</span>
      </div>
      <div v-for="item in submissions" :key="item.id" class="table-row submissions-table" :class="{ 'with-actions': canManageRejudge }">
        <label v-if="canManageRejudge" class="select-cell" :title="canRejudge(item) ? '选择重测' : '只有代码提交可重测'">
          <input v-model="selectedIds" type="checkbox" :value="item.id" :disabled="!canRejudge(item) || rejudging" />
        </label>
        <strong>{{ item.id }}</strong>
        <span>{{ item.problem_title }}</span>
        <span>{{ problemTypeLabel(item.problem_type) }}</span>
        <StatusBadge :status="item.status" />
        <span>{{ item.score }}/{{ item.max_score }}</span>
        <span>{{ formatDate(item.created_at) }}</span>
        <span v-if="canManageRejudge" class="row-actions">
          <button class="icon-button" :disabled="!canRejudge(item) || rejudging" title="重新进入在线评测队列" @click="rejudgeOne(item)">
            <RotateCcw :size="16" />
          </button>
        </span>
      </div>
      <p v-if="!submissions.length && !error" class="empty-text">暂无提交。</p>
    </section>
  </div>
</template>
