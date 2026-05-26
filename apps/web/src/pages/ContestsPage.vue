<script setup lang="ts">
import { ClipboardList, Lock, LockOpen, MessageSquare, Trophy } from 'lucide-vue-next';
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import StatusBadge from '@/components/StatusBadge.vue';
import { apiRequest, formatDate } from '@/services/api';
import type { Contest } from '@/services/types';
import { authState } from '@/stores/auth';

const router = useRouter();
const contests = ref<Contest[]>([]);
const selected = ref('');
const actionError = ref('');

const canManageContests = computed(() => Boolean(authState.user?.permissions.includes('contest:manage')));

async function load() {
  contests.value = await apiRequest<Contest[]>('/contests');
  selected.value = contests.value[0]?.id ?? '';
}

async function openStandings(id: string) {
  await router.push(`/contests/${id}/standings`);
}

async function openClarifications(id: string) {
  await router.push(`/contests/${id}/clar`);
}

async function openSubmissions(id: string) {
  await router.push(`/contests/${id}/submissions`);
}

async function freezeContest(contest: Contest) {
  actionError.value = '';
  try {
    await apiRequest<Contest>(`/contests/${contest.id}/freeze`, {
      method: 'POST',
      body: JSON.stringify({ reason: 'manual freeze from contest list' }),
    });
    await load();
  } catch (err) {
    actionError.value = err instanceof Error ? err.message : '封榜失败';
  }
}

async function unfreezeContest(contest: Contest) {
  actionError.value = '';
  try {
    await apiRequest<Contest>(`/contests/${contest.id}/unfreeze`, {
      method: 'POST',
      body: JSON.stringify({ reason: 'manual unfreeze from contest list' }),
    });
    await load();
  } catch (err) {
    actionError.value = err instanceof Error ? err.message : '解封失败';
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
      <p v-if="actionError" class="form-error">{{ actionError }}</p>
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
        <div class="contest-status-stack">
          <StatusBadge :status="contest.freeze_active ? 'disabled' : contest.status" />
          <small v-if="contest.freeze_active">已封榜</small>
        </div>
        <div class="row-actions">
          <button
            v-if="canManageContests && !contest.freeze_active"
            class="secondary-action"
            type="button"
            @click="freezeContest(contest)"
          >
            <Lock :size="16" />封榜
          </button>
          <button
            v-if="canManageContests && contest.frozen"
            class="secondary-action"
            type="button"
            @click="unfreezeContest(contest)"
          >
            <LockOpen :size="16" />解封
          </button>
          <button class="secondary-action" type="button" @click="openStandings(contest.id)">
            <Trophy :size="16" />榜单
          </button>
          <button class="secondary-action" type="button" @click="openSubmissions(contest.id)">
            <ClipboardList :size="16" />提交
          </button>
          <button class="secondary-action" type="button" @click="openClarifications(contest.id)">
            <MessageSquare :size="16" />提问
          </button>
        </div>
      </div>
      <p v-if="contests.length === 0" class="empty-text">暂无比赛。</p>
    </section>
  </div>
</template>
