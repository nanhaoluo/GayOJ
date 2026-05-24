<script setup lang="ts">
import { Check, Loader2, Send } from 'lucide-vue-next';
import { computed, onMounted, reactive, ref } from 'vue';
import { useRoute } from 'vue-router';
import ProblemStatementRenderer from '@/components/ProblemStatementRenderer.vue';
import ProblemTypeIcon from '@/components/ProblemTypeIcon.vue';
import StatusBadge from '@/components/StatusBadge.vue';
import { apiRequest, problemTypeLabel } from '@/services/api';
import type { CompilerLanguage, ProblemDetail, Submission } from '@/services/types';
import { authState } from '@/stores/auth';

const route = useRoute();
const problem = ref<ProblemDetail | null>(null);
const loading = ref(false);
const submitting = ref(false);
const error = ref('');
const result = ref<Submission | null>(null);
const language = ref('cpp');
const compilerLanguages = ref<CompilerLanguage[]>([]);
const sourceCode = ref(`#include <bits/stdc++.h>
using namespace std;

int main() {
    long long a, b;
    cin >> a >> b;
    cout << a + b << '\\n';
    return 0;
}
`);
const answers = reactive<Record<string, unknown>>({});

const isObjective = computed(() => problem.value && problem.value.type !== 'code');
const canParticipate = computed(() => authState.user?.role === 'student');

async function load() {
  loading.value = true;
  error.value = '';
  try {
    problem.value = await apiRequest<ProblemDetail>(`/problems/${route.params.id}`);
    compilerLanguages.value = [];
    if (problem.value.type === 'code') {
      try {
        compilerLanguages.value = await apiRequest<CompilerLanguage[]>('/judge/languages', { auth: false });
      } catch {
        compilerLanguages.value = [];
      }
      if (compilerLanguages.value.length && !compilerLanguages.value.some((item) => item.code === language.value)) {
        language.value = compilerLanguages.value[0].code;
      }
    }
    if (problem.value.type === 'single_choice') answers.choice = '';
    if (problem.value.type === 'multiple_choice') answers.choices = [];
    for (const blank of problem.value.blanks) answers[blank.key] = '';
  } catch (err) {
    error.value = err instanceof Error ? err.message : '题目加载失败';
  } finally {
    loading.value = false;
  }
}

function toggleChoice(key: string) {
  const choices = Array.isArray(answers.choices) ? [...answers.choices] : [];
  const index = choices.indexOf(key);
  if (index >= 0) choices.splice(index, 1);
  else choices.push(key);
  answers.choices = choices;
}

async function submit() {
  if (!problem.value) return;
  if (!canParticipate.value) {
    error.value = authState.user ? '只有选手账号可以参赛提交。' : '请先登录选手账号后再提交。';
    return;
  }
  submitting.value = true;
  error.value = '';
  try {
    if (problem.value.type === 'code') {
      result.value = await apiRequest<Submission>(`/problems/${problem.value.id}/submit-code`, {
        method: 'POST',
        body: JSON.stringify({ language: language.value, source_code: sourceCode.value }),
      });
    } else {
      result.value = await apiRequest<Submission>(`/problems/${problem.value.id}/submit-objective`, {
        method: 'POST',
        body: JSON.stringify({ answers }),
      });
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : '提交失败，请先登录';
  } finally {
    submitting.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div class="page-stack">
    <section v-if="problem" class="page-heading">
      <div>
        <span class="eyebrow">{{ problem.id }} / {{ problemTypeLabel(problem.type) }}</span>
        <h1>{{ problem.title }}</h1>
      </div>
      <div class="heading-meta">
        <ProblemTypeIcon :type="problem.type" />
        <span>{{ problem.difficulty }}</span>
        <span v-if="problem.time_limit_ms">{{ problem.time_limit_ms }} ms</span>
        <span v-if="problem.memory_limit_mb">{{ problem.memory_limit_mb }} MB</span>
      </div>
    </section>

    <p v-if="error" class="form-error">{{ error }}</p>

    <section v-if="problem" class="solve-layout">
      <article class="panel statement-panel">
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
            <h2>{{ isObjective ? '客观题作答' : '代码提交' }}</h2>
            <p>{{ isObjective ? '本题由规则引擎即时判分' : '提交进入在线评测队列，等待 worker 回写' }}</p>
          </div>
        </div>

        <p v-if="!canParticipate" class="empty-text">只有选手账号可以参赛提交。教练、裁判和管理员账号用于管理与裁判工作。</p>
        <form v-else class="submit-form" @submit.prevent="submit">
        <template v-if="problem.type === 'code'">
          <label>
            语言
            <select v-model="language">
              <option v-for="item in compilerLanguages" :key="item.code" :value="item.code">
                {{ item.display_name }} · {{ item.version }}
              </option>
            </select>
          </label>
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

          <button class="primary-action full" type="submit" :disabled="submitting">
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
