<script setup lang="ts">
import { ArrowLeft, Eye, Globe2, MessageSquare, RefreshCw, Send } from 'lucide-vue-next';
import { computed, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { apiRequest, formatDate } from '@/services/api';
import { authState } from '@/stores/auth';
import type { Clarification, Contest } from '@/services/types';

const route = useRoute();
const router = useRouter();
const contest = ref<Contest | null>(null);
const clarifications = ref<Clarification[]>([]);
const question = ref('');
const problemId = ref('');
const answerMap = ref<Record<string, string>>({});
const visibilityMap = ref<Record<string, 'private' | 'public' | 'broadcast'>>({});
const savingId = ref('');
const error = ref('');

const canReply = computed(() => authState.user?.permissions.includes('clarification:reply') ?? false);
const canAsk = computed(() => authState.user?.role === 'student');

function clarificationTitle(item: Clarification): string {
  if (!item.problem_id) return '全局问题';
  return `${item.problem_key || item.problem_id} · ${item.problem_title || '比赛题目'}`;
}

async function load() {
  error.value = '';
  try {
    contest.value = await apiRequest<Contest>(`/contests/${route.params.id}`);
    clarifications.value = await apiRequest<Clarification[]>(`/contests/${route.params.id}/clarifications`);
    for (const item of clarifications.value) {
      if (!visibilityMap.value[item.id]) {
        visibilityMap.value[item.id] = item.broadcast ? 'broadcast' : item.public ? 'public' : 'private';
      }
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败';
  }
}

async function submitQuestion() {
  const trimmedQuestion = question.value.trim();
  if (!trimmedQuestion) return;
  try {
    await apiRequest(`/contests/${route.params.id}/clarifications`, {
      method: 'POST',
      body: JSON.stringify({
        question: trimmedQuestion,
        problem_id: problemId.value.trim() || undefined,
      }),
    });
    question.value = '';
    problemId.value = '';
    await load();
  } catch (err) {
    error.value = err instanceof Error ? err.message : '提交失败';
  }
}

async function submitAnswer(item: Clarification) {
  const answer = answerMap.value[item.id]?.trim();
  if (!answer) return;
  savingId.value = item.id;
  error.value = '';
  const mode = visibilityMap.value[item.id] ?? 'private';
  try {
    await apiRequest(`/clarifications/${item.id}`, {
      method: 'PATCH',
      body: JSON.stringify({
        answer,
        public: mode !== 'private',
        broadcast: mode === 'broadcast',
      }),
    });
    answerMap.value[item.id] = '';
    await load();
  } catch (err) {
    error.value = err instanceof Error ? err.message : '回复失败';
  } finally {
    savingId.value = '';
  }
}

function clarificationScope(item: Clarification): string {
  if (item.broadcast) return '已广播';
  if (item.public) return '公开';
  return '私有';
}

function clarificationAudience(item: Clarification): string {
  if (item.broadcast) return '所有选手可见';
  if (item.public) return '公开展示';
  if (item.answer) return '仅提问者可见';
  return '等待裁判处理';
}

onMounted(load);
</script>

<template>
  <div class="pure-page">
    <header class="pure-toolbar">
      <button class="secondary-action" type="button" @click="router.back()"><ArrowLeft :size="16" />返回</button>
      <button class="secondary-action" type="button" @click="load"><RefreshCw :size="16" />刷新</button>
    </header>
    <section class="pure-content clarification-page">
      <div class="pure-heading">
        <h1>{{ contest?.title || 'Clarification' }}</h1>
        <p>{{ canReply ? '裁判审批与广播面板' : '提问与查看回复' }}</p>
      </div>

      <form v-if="canAsk" class="clarification-ask" @submit.prevent="submitQuestion">
        <div class="clarification-ask-row">
          <input v-model="problemId" placeholder="比赛题号（可选）" />
          <button class="primary-action" type="submit"><Send :size="16" />提交问题</button>
        </div>
        <textarea
          v-model="question"
          class="pure-textarea clarification-textarea"
          placeholder="输入 Clarification 内容"
        ></textarea>
      </form>

      <p v-if="error" class="form-error">{{ error }}</p>

      <div class="list-stack clarification-list">
        <article v-for="item in clarifications" :key="item.id" class="clarification-card">
          <div class="clarification-card-head">
            <div class="clarification-card-title">
              <strong>{{ clarificationTitle(item) }}</strong>
              <span>{{ item.user_display_name || '匿名选手' }}</span>
            </div>
            <div class="clarification-meta">
              <span class="clarification-chip">{{ clarificationScope(item) }}</span>
              <span>{{ formatDate(item.created_at) }}</span>
            </div>
          </div>

          <p class="clarification-question">{{ item.question }}</p>

          <div class="clarification-answer">
            <div class="clarification-answer-head">
              <strong>{{ item.answer ? '裁判回复' : '待处理' }}</strong>
              <span>{{ clarificationAudience(item) }}</span>
            </div>
            <p>{{ item.answer || '尚未回复' }}</p>
            <small v-if="item.answered_at">
              {{ item.answered_by_name || '裁判' }} · {{ formatDate(item.answered_at) }}
            </small>
          </div>

          <form
            v-if="canReply"
            class="clarification-reply-form"
            @submit.prevent="submitAnswer(item)"
          >
            <textarea
              v-model="answerMap[item.id]"
              class="pure-textarea clarification-textarea"
              placeholder="输入裁判回复"
            ></textarea>
            <div class="clarification-actions">
              <label class="clarification-mode">
                <Eye :size="16" />
                <input v-model="visibilityMap[item.id]" type="radio" value="private" />
                <span>私有回复</span>
              </label>
              <label class="clarification-mode">
                <MessageSquare :size="16" />
                <input v-model="visibilityMap[item.id]" type="radio" value="public" />
                <span>公开回复</span>
              </label>
              <label class="clarification-mode">
                <Globe2 :size="16" />
                <input v-model="visibilityMap[item.id]" type="radio" value="broadcast" />
                <span>广播给所有选手</span>
              </label>
              <button class="secondary-action" type="submit" :disabled="savingId === item.id">提交回复</button>
            </div>
          </form>
        </article>
      </div>
    </section>
  </div>
</template>
