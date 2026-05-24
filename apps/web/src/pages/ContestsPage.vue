<script setup lang="ts">
import { MessageSquare, Send, Trophy } from 'lucide-vue-next';
import { onMounted, ref } from 'vue';
import StatusBadge from '@/components/StatusBadge.vue';
import { apiRequest, formatDate } from '@/services/api';
import type { Clarification, Contest } from '@/services/types';

const contests = ref<Contest[]>([]);
const standings = ref<Array<Record<string, unknown>>>([]);
const clarifications = ref<Clarification[]>([]);
const selected = ref('');
const question = ref('');
const replyText = ref<Record<string, string>>({});
const error = ref('');

async function load() {
  contests.value = await apiRequest<Contest[]>('/contests', { auth: false });
  selected.value = contests.value[0]?.id ?? '';
  if (selected.value) await loadStandings(selected.value);
}

async function loadStandings(id: string) {
  selected.value = id;
  const [standingData, clarData] = await Promise.all([
    apiRequest<Array<Record<string, unknown>>>(`/contests/${id}/standings`, { auth: false }),
    apiRequest<Clarification[]>(`/contests/${id}/clarifications`, { auth: false }),
  ]);
  standings.value = standingData;
  clarifications.value = clarData;
}

async function submitClarification() {
  if (!selected.value || !question.value.trim()) return;
  error.value = '';
  try {
    await apiRequest<Clarification>(`/contests/${selected.value}/clarifications`, {
      method: 'POST',
      body: JSON.stringify({ question: question.value }),
    });
    question.value = '';
    await loadStandings(selected.value);
  } catch (err) {
    error.value = err instanceof Error ? err.message : '提交 Clarification 失败，请先登录。';
  }
}

async function replyClarification(item: Clarification) {
  const answer = replyText.value[item.id];
  if (!answer?.trim()) return;
  error.value = '';
  try {
    await apiRequest<Clarification>(`/clarifications/${item.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ answer, public: true }),
    });
    replyText.value[item.id] = '';
    await loadStandings(selected.value);
  } catch (err) {
    error.value = err instanceof Error ? err.message : '回复失败，需要裁判或管理员权限。';
  }
}

onMounted(load);
</script>

<template>
  <div class="page-stack">
    <section class="page-heading">
      <div>
        <span class="eyebrow">Contest</span>
        <h1>比赛系统</h1>
      </div>
    </section>

    <section class="dashboard-grid">
      <article v-for="contest in contests" :key="contest.id" class="panel contest-card">
        <div class="contest-title">
          <Trophy :size="20" />
          <div>
            <h2>{{ contest.title }}</h2>
            <p>{{ contest.rule }} · {{ formatDate(contest.start_at) }} - {{ formatDate(contest.end_at) }}</p>
          </div>
        </div>
        <StatusBadge :status="contest.status" />
        <div class="tag-line">
          <span v-for="problem in contest.problems" :key="problem.id">{{ problem.id }}</span>
        </div>
        <button class="secondary-action full" @click="loadStandings(contest.id)">查看榜单</button>
      </article>
    </section>

    <section class="panel table-panel">
      <div class="panel-head">
        <div>
          <h2>实时排行榜</h2>
          <p>{{ selected || '未选择比赛' }}</p>
        </div>
      </div>
      <div class="table-row table-head">
        <span>#</span>
        <span>用户</span>
        <span>解题</span>
        <span>总分</span>
      </div>
      <div v-for="(row, index) in standings" :key="String(row.user_id)" class="table-row">
        <strong>{{ index + 1 }}</strong>
        <span>{{ row.display_name }}</span>
        <span>{{ row.solved }}</span>
        <span>{{ row.score }}</span>
      </div>
      <p v-if="!standings.length" class="empty-text">暂无榜单数据。</p>
    </section>

    <section class="panel">
      <div class="panel-head">
        <div>
          <h2>Clarification</h2>
          <p>选手提问，裁判回复后可广播</p>
        </div>
      </div>
      <form class="reply-form" @submit.prevent="submitClarification">
        <input v-model="question" placeholder="向裁判提问" />
        <button class="primary-action" type="submit"><Send :size="17" />提交</button>
      </form>
      <p v-if="error" class="form-error">{{ error }}</p>
      <div class="list-stack">
        <div v-for="item in clarifications" :key="item.id" class="reply-row">
          <strong><MessageSquare :size="16" /> {{ item.question }}</strong>
          <p>{{ item.answer || '等待裁判回复' }}</p>
          <span>{{ formatDate(item.created_at) }} · {{ item.public ? '已广播' : '私有' }}</span>
          <form class="reply-form" @submit.prevent="replyClarification(item)">
            <input v-model="replyText[item.id]" placeholder="裁判回复内容" />
            <button class="secondary-action" type="submit">回复</button>
          </form>
        </div>
        <p v-if="!clarifications.length" class="empty-text">暂无 Clarification。</p>
      </div>
    </section>
  </div>
</template>
