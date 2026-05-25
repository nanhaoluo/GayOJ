<script setup lang="ts">
import { Lock, LockOpen, MessageSquare, RotateCcw, Trophy } from 'lucide-vue-next';
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import StatusBadge from '@/components/StatusBadge.vue';
import { apiRequest, formatDate } from '@/services/api';
import type { Contest, ContestRejudgeResponse } from '@/services/types';
import { authState } from '@/stores/auth';

const router = useRouter();
const contests = ref<Contest[]>([]);
const selected = ref('');
const actionError = ref('');
const notice = ref('');
const rejudgingContestId = ref('');

const canManageContests = computed(() => Boolean(authState.user?.permissions.includes('contest:manage')));
const canTriggerContestRejudge = computed(() => {
  const permissions = authState.user?.permissions ?? [];
  return permissions.includes('submission:override') && (permissions.includes('judge:monitor') || permissions.includes('contest:manage'));
});

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

function contestEnded(contest: Contest): boolean {
  return new Date(contest.end_at).getTime() <= Date.now();
}

function canRejudgeContest(contest: Contest): boolean {
  return canTriggerContestRejudge.value && contestEnded(contest);
}

function rejudgeMeta(contest: Contest): string {
  return contest.rejudge_at ? `最近重测 ${formatDate(contest.rejudge_at)}` : '';
}

async function freezeContest(contest: Contest) {
  actionError.value = '';
  notice.value = '';
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
  notice.value = '';
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

async function rejudgeContest(contest: Contest) {
  if (!canRejudgeContest(contest)) return;
  actionError.value = '';
  notice.value = '';
  rejudgingContestId.value = contest.id;
  try {
    const result = await apiRequest<ContestRejudgeResponse>(`/contests/${contest.id}/rejudge`, {
      method: 'POST',
      body: JSON.stringify({ reason: 'manual contest rejudge from contest list' }),
    });
    notice.value = `比赛 ${contest.title} 已重测 ${result.requeued_count} 条代码提交${result.skipped_count ? `，跳过 ${result.skipped_count} 条` : ''}。`;
    await load();
  } catch (err) {
    actionError.value = err instanceof Error ? err.message : '赛后重测失败';
  } finally {
    rejudgingContestId.value = '';
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
      <p v-if="notice" class="form-success">{{ notice }}</p>
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
          <small v-if="rejudgeMeta(contest)">{{ rejudgeMeta(contest) }}</small>
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
          <button class="secondary-action" type="button" @click="openClarifications(contest.id)">
            <MessageSquare :size="16" />提问
          </button>
          <button
            v-if="canRejudgeContest(contest)"
            class="secondary-action"
            type="button"
            :disabled="rejudgingContestId === contest.id"
            @click="rejudgeContest(contest)"
          >
            <RotateCcw :size="16" />赛后重测
          </button>
        </div>
      </div>
      <p v-if="contests.length === 0" class="empty-text">暂无比赛。</p>
    </section>
  </div>
</template>
