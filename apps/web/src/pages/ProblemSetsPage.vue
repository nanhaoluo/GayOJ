<script setup lang="ts">
import { ClipboardList, Eye, Plus } from 'lucide-vue-next';
import { onMounted, reactive, ref } from 'vue';
import { RouterLink } from 'vue-router';
import BaseModal from '@/components/BaseModal.vue';
import ProblemTypeIcon from '@/components/ProblemTypeIcon.vue';
import { apiRequest, formatDate } from '@/services/api';
import type { ProblemSet, ProblemSummary } from '@/services/types';

const sets = ref<ProblemSet[]>([]);
const problems = ref<ProblemSummary[]>([]);
const error = ref('');
const createOpen = ref(false);
const detailOpen = ref(false);
const selectedSet = ref<ProblemSet | null>(null);
const form = reactive({
  title: '',
  description: '',
  type: 'set',
  visibility: 'public',
  problem_ids: [] as string[],
});

async function load() {
  const [setData, problemData] = await Promise.all([
    apiRequest<ProblemSet[]>('/problem-sets', { auth: false }),
    apiRequest<ProblemSummary[]>('/problems', { auth: false }),
  ]);
  sets.value = setData;
  problems.value = problemData;
}

function toggleProblem(problemId: string) {
  const index = form.problem_ids.indexOf(problemId);
  if (index >= 0) form.problem_ids.splice(index, 1);
  else form.problem_ids.push(problemId);
}

function openSetDetail(set: ProblemSet) {
  selectedSet.value = set;
  detailOpen.value = true;
}

async function createSet() {
  error.value = '';
  try {
    await apiRequest<ProblemSet>('/problem-sets', {
      method: 'POST',
      body: JSON.stringify(form),
    });
    form.title = '';
    form.description = '';
    form.problem_ids = [];
    createOpen.value = false;
    await load();
  } catch (err) {
    error.value = err instanceof Error ? err.message : '创建题单失败，需要教练、裁判或管理员权限。';
  }
}

onMounted(load);
</script>

<template>
  <div class="page-stack">
    <section class="page-heading">
      <div>
        <span class="eyebrow">Problem Sets</span>
        <h1>题单与试卷</h1>
      </div>
      <button class="primary-action" type="button" @click="createOpen = true"><Plus :size="18" />创建题单</button>
    </section>

    <p v-if="error" class="form-error">{{ error }}</p>

    <section class="panel set-list-panel">
      <div class="set-table-row set-table-head">
        <span>名称</span>
        <span>类型</span>
        <span>题量</span>
        <span>更新</span>
        <span>操作</span>
      </div>
      <div v-for="set in sets" :key="set.id" class="set-table-row">
        <div>
          <strong>{{ set.title }}</strong>
          <span>{{ set.description || '暂无描述' }}</span>
        </div>
        <span class="difficulty">{{ set.type }}</span>
        <span>{{ set.problems.length }} 题</span>
        <span v-if="set.due_at">截止 {{ formatDate(set.due_at) }}</span>
        <span v-else>{{ formatDate(set.updated_at) }}</span>
        <button class="secondary-action" type="button" @click="openSetDetail(set)">
          <Eye :size="16" />查看
        </button>
      </div>
      <p v-if="sets.length === 0" class="empty-text">暂无题单。</p>
    </section>

    <BaseModal
      :open="createOpen"
      title="创建题单"
      description="填写基本信息后再选择题目"
      size="lg"
      @close="createOpen = false"
    >
      <form class="submit-form" @submit.prevent="createSet">
        <label>标题<input v-model="form.title" required placeholder="例如：动态规划基础训练" /></label>
        <label>描述<textarea v-model="form.description" rows="3" placeholder="训练目标、适用对象和注意事项"></textarea></label>
        <div class="segmented wide">
          <button type="button" :class="{ active: form.type === 'set' }" @click="form.type = 'set'">题单</button>
          <button type="button" :class="{ active: form.type === 'exam' }" @click="form.type = 'exam'">试卷</button>
          <button type="button" :class="{ active: form.type === 'assignment' }" @click="form.type = 'assignment'">作业</button>
        </div>
        <div class="checkbox-grid modal-choice-grid">
          <label v-for="problem in problems" :key="problem.id" class="choice-line">
            <input
              type="checkbox"
              :checked="form.problem_ids.includes(problem.id)"
              @change="toggleProblem(problem.id)"
            />
            <span>{{ problem.id }} · {{ problem.title }}</span>
          </label>
        </div>
        <button class="primary-action full" type="submit"><ClipboardList :size="18" />保存</button>
      </form>
    </BaseModal>

    <BaseModal
      :open="detailOpen"
      :title="selectedSet?.title || '题单详情'"
      :description="selectedSet ? `${selectedSet.type} · ${selectedSet.problems.length} 题` : ''"
      size="lg"
      @close="detailOpen = false"
    >
      <section v-if="selectedSet" class="set-detail-view">
        <div class="set-meta">
          <span>{{ selectedSet.problems.length }} 题</span>
          <span v-if="selectedSet.due_at">截止 {{ formatDate(selectedSet.due_at) }}</span>
          <span v-else>更新 {{ formatDate(selectedSet.updated_at) }}</span>
        </div>
        <p>{{ selectedSet.description || '暂无描述' }}</p>
        <div class="problem-short-list">
          <RouterLink v-for="problem in selectedSet.problems" :key="problem.id" :to="`/problems/${problem.id}`">
            <ProblemTypeIcon :type="problem.type" />
            <div>
              <strong>{{ problem.id }} · {{ problem.title }}</strong>
              <span>{{ problem.difficulty }} · {{ problem.tags.join(' / ') }}</span>
            </div>
          </RouterLink>
        </div>
      </section>
    </BaseModal>
  </div>
</template>
