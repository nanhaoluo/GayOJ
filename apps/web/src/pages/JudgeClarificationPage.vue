<script setup lang="ts">
import { ArrowLeft, Eye, Globe2, MessageSquare, RefreshCw } from 'lucide-vue-next';
import { computed, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { apiRequest, formatDate } from '@/services/api';
import type { Clarification, Contest } from '@/services/types';

const route = useRoute();
const router = useRouter();
const contest = ref<Contest | null>(null);
const clarifications = ref<Clarification[]>([]);
const answerMap = ref<Record<string, string>>({});
const visibilityMap = ref<Record<string, 'private' | 'public' | 'broadcast'>>({});
const savingId = ref('');
const error = ref('');

const pending = computed(() => clarifications.value.filter((item) => !item.answer));
const replied = computed(() => clarifications.value.filter((item) => item.answer));

function applyVisibility(items: Clarification[]) {
  for (const item of items) {
    if (!visibilityMap.value[item.id]) {
      visibilityMap.value[item.id] = item.broadcast ? 'broadcast' : item.public ? 'public' : 'private';
    }
  }
}

async function load() {
  error.value = '';
  try {
    contest.value = await apiRequest<Contest>(`/contests/${route.params.id}`);
    clarifications.value = await apiRequest<Clarification[]>(`/judge/clar/${route.params.id}`);
    applyVisibility(clarifications.value);
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败';
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

function clarificationProblemLabel(item: Clarification): string {
  if (!item.problem_key && !item.problem_title) return '全局问题';
  return [item.problem_key, item.problem_title].filter(Boolean).join(' · ');
}

onMounted(load);
</script>

<template>
  <div class="pure-page">
    <header class="pure-toolbar">
      <button class="secondary-action" type="button" @click="router.back()"><ArrowLeft :size="16" />返回</button>
      <button class="secondary-action" type="button" @click="load"><RefreshCw :size="16" />刷新</button>
    </header>

    <section class="pure-content clarification-page judge-clar-page">
      <div class="pure-heading">
        <h1>{{ contest?.title || 'Clarification 审批' }}</h1>
        <p>仅展示当前比赛的 Clarification，回复后可选择私有、公开或广播。</p>
      </div>

      <section class="contest-monitor-summary judge-clar-summary">
        <article class="monitor-stat-card">
          <small>待处理</small>
          <strong>{{ pending.length }}</strong>
          <span>仍需裁判回复</span>
        </article>
        <article class="monitor-stat-card">
          <small>已处理</small>
          <strong>{{ replied.length }}</strong>
          <span>已完成回复</span>
        </article>
      </section>

      <p v-if="error" class="form-error">{{ error }}</p>

      <div class="list-stack clarification-list">
        <article v-for="item in clarifications" :key="item.id" class="clarification-card judge-clar-card">
          <div class="clarification-card-head">
            <div class="clarification-card-title">
              <strong>{{ clarificationProblemLabel(item) }}</strong>
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
              <span>{{ item.answer ? `${item.answered_by_name || '裁判'} · ${formatDate(item.answered_at)}` : '尚未回复' }}</span>
            </div>
            <p>{{ item.answer || '尚未回复' }}</p>
          </div>

          <form class="clarification-reply-form" @submit.prevent="submitAnswer(item)">
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
                <span>广播全场</span>
              </label>
              <button class="secondary-action" type="submit" :disabled="savingId === item.id">提交回复</button>
            </div>
          </form>
        </article>
        <p v-if="clarifications.length === 0" class="empty-text">当前比赛没有 Clarification 记录。</p>
      </div>
    </section>
  </div>
</template>
