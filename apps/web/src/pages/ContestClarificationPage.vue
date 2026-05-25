<script setup lang="ts">
import { ArrowLeft, RefreshCw, Send } from 'lucide-vue-next';
import { onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { apiRequest, formatDate } from '@/services/api';
import { authState } from '@/stores/auth';
import type { Clarification, Contest } from '@/services/types';

const route = useRoute();
const router = useRouter();
const contest = ref<Contest | null>(null);
const clarifications = ref<Clarification[]>([]);
const question = ref('');
const answerMap = ref<Record<string, string>>({});
const error = ref('');

async function load() {
  error.value = '';
  try {
    contest.value = await apiRequest<Contest>(`/contests/${route.params.id}`, { auth: false });
    clarifications.value = await apiRequest<Clarification[]>(`/contests/${route.params.id}/clarifications`);
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败';
  }
}

async function submitQuestion() {
  if (!question.value.trim()) return;
  try {
    await apiRequest(`/contests/${route.params.id}/clarifications`, {
      method: 'POST',
      body: JSON.stringify({ question: question.value }),
    });
    question.value = '';
    await load();
  } catch (err) {
    error.value = err instanceof Error ? err.message : '提交失败';
  }
}

async function submitAnswer(item: Clarification) {
  const answer = answerMap.value[item.id];
  if (!answer?.trim()) return;
  try {
    await apiRequest(`/clarifications/${item.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ answer, public: true }),
    });
    answerMap.value[item.id] = '';
    await load();
  } catch (err) {
    error.value = err instanceof Error ? err.message : '回复失败';
  }
}

onMounted(load);
</script>

<template>
  <div class="pure-page">
    <header class="pure-toolbar">
      <button class="secondary-action" type="button" @click="router.back()"><ArrowLeft :size="16" />返回</button>
      <button class="secondary-action" type="button" @click="load"><RefreshCw :size="16" />刷新</button>
    </header>
    <section class="pure-content">
      <div class="pure-heading">
        <h1>{{ contest?.title || 'Clarification' }}</h1>
      </div>
      <form v-if="authState.user?.role === 'student'" class="inline-form" @submit.prevent="submitQuestion">
        <input v-model="question" placeholder="提问" />
        <button class="primary-action" type="submit"><Send :size="16" />提交</button>
      </form>
      <p v-if="error" class="form-error">{{ error }}</p>
      <div class="list-stack">
        <div v-for="item in clarifications" :key="item.id" class="reply-row">
          <strong>{{ item.question }}</strong>
          <p>{{ item.answer || '等待回复' }}</p>
          <span>{{ formatDate(item.created_at) }}</span>
          <form v-if="authState.user?.permissions.includes('clarification:reply')" class="inline-form" @submit.prevent="submitAnswer(item)">
            <input v-model="answerMap[item.id]" placeholder="回复" />
            <button class="secondary-action" type="submit">回复</button>
          </form>
        </div>
      </div>
    </section>
  </div>
</template>
