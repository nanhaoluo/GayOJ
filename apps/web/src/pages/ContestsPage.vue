<script setup lang="ts">
import { MessageSquare, Trophy } from 'lucide-vue-next';
import { onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import StatusBadge from '@/components/StatusBadge.vue';
import { apiRequest, formatDate } from '@/services/api';
import type { Contest } from '@/services/types';

const router = useRouter();
const contests = ref<Contest[]>([]);
const selected = ref('');

async function load() {
  contests.value = await apiRequest<Contest[]>('/contests', { auth: false });
  selected.value = contests.value[0]?.id ?? '';
}

async function openStandings(id: string) {
  await router.push(`/contests/${id}/standings`);
}

async function openClarifications(id: string) {
  await router.push(`/contests/${id}/clar`);
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
        <StatusBadge :status="contest.frozen ? 'disabled' : contest.status" />
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
  </div>
</template>
