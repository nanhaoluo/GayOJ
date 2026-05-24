<script setup lang="ts">
import { MessageSquare, Send, Trophy } from 'lucide-vue-next';
import { computed, onMounted, ref } from 'vue';
import BaseModal from '@/components/BaseModal.vue';
import StatusBadge from '@/components/StatusBadge.vue';
import { apiRequest, formatDate } from '@/services/api';
import type { Clarification, Contest } from '@/services/types';
import { authState } from '@/stores/auth';

const contests = ref<Contest[]>([]);
const standings = ref<Array<Record<string, unknown>>>([]);
const clarifications = ref<Clarification[]>([]);
const selected = ref('');
const question = ref('');
const replyText = ref<Record<string, string>>({});
const error = ref('');
const standingsOpen = ref(false);
const clarificationOpen = ref(false);

const canAskClarification = computed(() => authState.user?.role === 'student');

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

async function openStandings(id: string) {
  await loadStandings(id);
  standingsOpen.value = true;
}

async function openClarifications(id: string) {
  await loadStandings(id);
  clarificationOpen.value = true;
}

async function submitClarification() {
  if (!selected.value || !question.value.trim()) return;
  if (!canAskClarification.value) {
    error.value = authState.user ? '只有选手账号可以发起比赛提问。' : '请先登录选手账号后再提问。';
    return;
  }
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
      <button class="secondary-action" type="button" :disabled="!selected" @click="openClarifications(selected)">
        <MessageSquare :size="16" />Clarification
      </button>
    </section>

    <section class="panel set-list-panel">
      <div class="set-table-row set-table-head">
        <span>比赛</span>
        <span>赛制</span>
        <span>题量</span>
        <span>状态</span>
        <span>操作</span>
      </div>
      <div v-for="contest in contests" :key="contest.id" class="set-table-row">
        <div>
          <strong>{{ contest.title }}</strong>
          <span>{{ formatDate(contest.start_at) }} - {{ formatDate(contest.end_at) }}</span>
        </div>
        <span>{{ contest.rule }}</span>
        <span>{{ contest.problems.length }} 题</span>
        <StatusBadge :status="contest.status" />
        <div class="row-actions">
          <button class="secondary-action" type="button" @click="openStandings(contest.id)">
            <Trophy :size="16" />榜单
          </button>
          <button class="secondary-action" type="button" @click="openClarifications(contest.id)">
            <MessageSquare :size="16" />提问
          </button>
        </div>
      </div>
      <p v-if="contests.length === 0" class="empty-text">暂无比赛。</p>
    </section>

    <BaseModal
      :open="standingsOpen"
      title="实时排行榜"
      :description="selected || '未选择比赛'"
      size="lg"
      @close="standingsOpen = false"
    >
      <section class="table-panel">
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
    </BaseModal>

    <BaseModal
      :open="clarificationOpen"
      title="Clarification"
      description="选手提问，裁判回复后可广播"
      size="lg"
      @close="clarificationOpen = false"
    >
      <p v-if="!canAskClarification" class="empty-text">只有选手账号可以发起比赛提问；裁判和管理员可在下方回复。</p>
      <form v-else class="reply-form" @submit.prevent="submitClarification">
        <input v-model="question" placeholder="向裁判提问" />
        <button class="primary-action" type="submit"><Send :size="17" />提交</button>
      </form>
      <p v-if="error" class="form-error">{{ error }}</p>
      <div class="list-stack" style="margin-top:12px">
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
    </BaseModal>
  </div>
</template>
