<script setup lang="ts">
import { ClipboardList, Plus } from 'lucide-vue-next';
import { computed, onMounted, reactive, ref } from 'vue';
import { RouterLink } from 'vue-router';
import ProblemTypeIcon from '@/components/ProblemTypeIcon.vue';
import { apiRequest, formatDate } from '@/services/api';
import type { ProblemSet, ProblemSummary } from '@/services/types';

const sets = ref<ProblemSet[]>([]);
const problems = ref<ProblemSummary[]>([]);
const error = ref('');
const createOpen = ref(false);
const form = reactive({
  title: '',
  description: '',
  type: 'set',
  visibility: 'public',
  problem_ids: [] as string[],
});

const problemOptions = computed(() => problems.value.map((item) => `${item.id} ${item.title}`));

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
      <button class="primary-action" @click="createOpen = !createOpen"><Plus :size="18" />创建题单</button>
    </section>

    <section v-if="createOpen" class="panel form-panel">
      <div class="panel-head">
        <div>
          <h2>创建题单</h2>
          <p>支持公开题单、试卷和作业类型</p>
        </div>
      </div>
      <form class="submit-form" @submit.prevent="createSet">
        <label>标题<input v-model="form.title" required placeholder="例如：动态规划基础训练" /></label>
        <label>描述<textarea v-model="form.description" rows="3" placeholder="训练目标、适用对象和注意事项"></textarea></label>
        <div class="segmented wide">
          <button type="button" :class="{ active: form.type === 'set' }" @click="form.type = 'set'">题单</button>
          <button type="button" :class="{ active: form.type === 'exam' }" @click="form.type = 'exam'">试卷</button>
          <button type="button" :class="{ active: form.type === 'assignment' }" @click="form.type = 'assignment'">作业</button>
        </div>
        <div class="checkbox-grid">
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
      <p v-if="error" class="form-error">{{ error }}</p>
    </section>

    <section class="dashboard-grid">
      <article v-for="set in sets" :key="set.id" class="panel set-card">
        <div class="panel-head">
          <div>
            <h2>{{ set.title }}</h2>
            <p>{{ set.description || '暂无描述' }}</p>
          </div>
          <span class="difficulty">{{ set.type }}</span>
        </div>
        <div class="problem-short-list">
          <RouterLink v-for="problem in set.problems" :key="problem.id" :to="`/problems/${problem.id}`">
            <ProblemTypeIcon :type="problem.type" />
            <div>
              <strong>{{ problem.id }} · {{ problem.title }}</strong>
              <span>{{ problem.difficulty }} · {{ problem.tags.join(' / ') }}</span>
            </div>
          </RouterLink>
        </div>
        <div class="set-meta">
          <span>{{ set.problems.length }} 题</span>
          <span v-if="set.due_at">截止 {{ formatDate(set.due_at) }}</span>
          <span v-else>更新 {{ formatDate(set.updated_at) }}</span>
        </div>
      </article>
    </section>
  </div>
</template>
