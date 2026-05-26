<script setup lang="ts">
import { ArrowLeft, Check, Loader2, Send } from 'lucide-vue-next';
import { computed, onMounted, reactive, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import ProblemStatementRenderer from '@/components/ProblemStatementRenderer.vue';
import ProblemTypeIcon from '@/components/ProblemTypeIcon.vue';
import StatusBadge from '@/components/StatusBadge.vue';
import { apiRequest, formatDate, problemTypeLabel } from '@/services/api';
import type { CompilerLanguage, Contest, ContestProblemDetail, Submission } from '@/services/types';
import { authState } from '@/stores/auth';

const route = useRoute();
const router = useRouter();
const contest = ref<Contest | null>(null);
const problem = ref<ContestProblemDetail | null>(null);
const problems = ref<ContestProblemDetail[]>([]);
const compilerLanguages = ref<CompilerLanguage[]>([]);
const loading = ref(false);
const submitting = ref(false);
const error = ref('');
const result = ref<Submission | null>(null);
const language = ref('cpp');
const sourceCode = ref(`#include <bits/stdc++.h>
using namespace std;

int main() {
    return 0;
}
`);
const answers = reactive<Record<string, unknown>>({});

const isObjective = computed(() => problem.value && problem.value.type !== 'code');
const canParticipate = computed(() => authState.user?.role === 'student');
const contestProblemKey = computed(() => problem.value?.problem_key ?? '');
const visibleCompilerLanguages = computed(() => {
  if (!problem.value?.allowed_languages.length) return compilerLanguages.value;
  const allowed = new Set(problem.value.allowed_languages);
  return compilerLanguages.value.filter((item) => allowed.has(item.code));
});
const allowedLanguageText = computed(() => {
  if (!problem.value || problem.value.type !== 'code') return '';
  if (!problem.value.allowed_languages.length) return '不限语言';
  return problem.value.allowed_languages.join(', ');
});

function toggleChoice(key: string) {
  const choices = Array.isArray(answers.choices) ? [...answers.choices] : [];
  const index = choices.indexOf(key);
  if (index >= 0) choices.splice(index, 1);
  else choices.push(key);
  answers.choices = choices;
}

function resetAnswers(detail: ContestProblemDetail) {
  Object.keys(answers).forEach((key) => delete answers[key]);
  if (detail.type === 'single_choice') answers.choice = '';
  if (detail.type === 'multiple_choice') answers.choices = [];
  for (const blank of detail.blanks) answers[blank.key] = '';
}

async function load() {
  loading.value = true;
  error.value = '';
  result.value = null;
  try {
    contest.value = await apiRequest<Contest>(`/contests/${route.params.id}`);
    problems.value = await apiRequest<ContestProblemDetail[]>(`/contests/${route.params.id}/problems`);
    const problemRef = String(route.params.problemId || '').toUpperCase();
    problem.value = problems.value.find((item) => item.id === route.params.problemId || item.problem_key.toUpperCase() === problemRef) ?? null;
    if (!problem.value) {
      throw new Error('Problem not found');
    }
    resetAnswers(problem.value);
    compilerLanguages.value = [];
    if (problem.value.type === 'code') {
      try {
        compilerLanguages.value = await apiRequest<CompilerLanguage[]>('/judge/languages', { auth: false });
      } catch {
        compilerLanguages.value = [];
      }
      if (visibleCompilerLanguages.value.length && !visibleCompilerLanguages.value.some((item) => item.code === language.value)) {
        language.value = visibleCompilerLanguages.value[0].code;
      }
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : '比赛题目加载失败';
  } finally {
    loading.value = false;
  }
}

async function submit() {
  if (!problem.value || !contest.value) return;
  if (!canParticipate.value) {
    error.value = authState.user ? '只有选手账号可以提交比赛题目。' : '请先登录选手账号后再提交。';
    return;
  }
  submitting.value = true;
  error.value = '';
  try {
    result.value = await apiRequest<Submission>(`/contests/${contest.value.id}/submit`, {
      method: 'POST',
      body: JSON.stringify(
        problem.value.type === 'code'
          ? { problem_id: problem.value.problem_key, language: language.value, source_code: sourceCode.value }
          : { problem_id: problem.value.problem_key, answers },
      ),
    });
  } catch (err) {
    error.value = err instanceof Error ? err.message : '比赛提交失败';
  } finally {
    submitting.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div class="page-stack">
    <section v-if="contest && problem" class="page-heading">
      <div>
        <span class="eyebrow">Contest {{ contestProblemKey }} / {{ problemTypeLabel(problem.type) }}</span>
        <h1>{{ problem.title }}</h1>
        <p class="contest-subtitle">
          {{ contest.title }} · {{ formatDate(contest.start_at) }} - {{ formatDate(contest.end_at) }}
        </p>
      </div>
      <div class="heading-meta">
        <ProblemTypeIcon :type="problem.type" />
        <span>{{ problem.difficulty }}</span>
        <span v-if="problem.time_limit_ms">{{ problem.time_limit_ms }} ms</span>
        <span v-if="problem.memory_limit_mb">{{ problem.memory_limit_mb }} MB</span>
      </div>
    </section>

    <p v-if="error" class="form-error">{{ error }}</p>

    <section v-if="contest && problem" class="solve-layout">
      <article class="panel statement-panel">
        <div class="contest-problem-header">
          <button class="secondary-action" type="button" @click="router.push(`/contests/${contest.id}`)">
            <ArrowLeft :size="16" />返回比赛
          </button>
          <StatusBadge :status="contest.freeze_active ? 'disabled' : contest.status" />
        </div>

        <h2>题面</h2>
        <ProblemStatementRenderer :source="problem.statement" aria-label="题面" />

        <template v-if="problem.input_format">
          <h3>输入格式</h3>
          <ProblemStatementRenderer :source="problem.input_format" compact aria-label="输入格式" />
        </template>

        <template v-if="problem.output_format">
          <h3>输出格式</h3>
          <ProblemStatementRenderer :source="problem.output_format" compact aria-label="输出格式" />
        </template>

        <template v-if="problem.samples.length">
          <h3>样例</h3>
          <div class="sample-grid">
            <div v-for="(sample, index) in problem.samples" :key="index" class="sample-box">
              <span>Input</span>
              <pre>{{ sample.input }}</pre>
              <span>Output</span>
              <pre>{{ sample.output }}</pre>
            </div>
          </div>
        </template>

        <div class="tag-line">
          <span v-for="tag in problem.tags" :key="tag">{{ tag }}</span>
        </div>
      </article>

      <aside class="panel submit-panel">
        <div class="panel-head">
          <div>
            <h2>{{ isObjective ? '比赛作答' : '比赛提交' }}</h2>
            <p>{{ isObjective ? '客观题比赛内即时判分。' : '代码题会进入比赛在线评测队列。' }}</p>
          </div>
        </div>

        <p v-if="!canParticipate" class="empty-text">只有选手账号可以提交比赛题目。</p>
        <form v-else class="submit-form" @submit.prevent="submit">
          <template v-if="problem.type === 'code'">
            <label>
              语言
              <select v-model="language">
                <option v-for="item in visibleCompilerLanguages" :key="item.code" :value="item.code">
                  {{ item.display_name }} · {{ item.version }}
                </option>
              </select>
            </label>
            <p class="form-hint">允许语言：{{ allowedLanguageText }}</p>
            <p v-if="!visibleCompilerLanguages.length" class="form-error">当前没有可用语言，无法提交代码。</p>
            <label>
              源码
              <textarea v-model="sourceCode" class="code-editor" spellcheck="false"></textarea>
            </label>
          </template>

          <template v-if="problem.type === 'blank'">
            <label v-for="blank in problem.blanks" :key="blank.key">
              {{ blank.label }}
              <input v-model="answers[blank.key]" placeholder="填写答案" />
            </label>
          </template>

          <template v-if="problem.type === 'single_choice'">
            <label v-for="option in problem.options" :key="option.key" class="choice-line">
              <input v-model="answers.choice" type="radio" :value="option.key" />
              <span class="choice-option-content">
                <strong>{{ option.key }}.</strong>
                <ProblemStatementRenderer :source="option.text" compact :aria-label="`选项 ${option.key}`" />
              </span>
            </label>
          </template>

          <template v-if="problem.type === 'multiple_choice'">
            <label v-for="option in problem.options" :key="option.key" class="choice-line">
              <input
                type="checkbox"
                :checked="Array.isArray(answers.choices) && answers.choices.includes(option.key)"
                @change="toggleChoice(option.key)"
              />
              <span class="choice-option-content">
                <strong>{{ option.key }}.</strong>
                <ProblemStatementRenderer :source="option.text" compact :aria-label="`选项 ${option.key}`" />
              </span>
            </label>
          </template>

          <button class="primary-action full" type="submit" :disabled="submitting || loading || (problem.type === 'code' && !visibleCompilerLanguages.length)">
            <Loader2 v-if="submitting" :size="18" class="spin" />
            <Send v-else :size="18" />
            提交
          </button>
        </form>

        <div v-if="result" class="result-panel">
          <div class="result-head">
            <Check :size="18" />
            <strong>{{ result.id }}</strong>
            <StatusBadge :status="result.status" />
          </div>
          <p>{{ result.message }}</p>
          <strong>{{ result.score }} / {{ result.max_score }}</strong>
        </div>
      </aside>
    </section>
  </div>
</template>
