<script setup lang="ts">
import { ArrowLeft, RefreshCw } from 'lucide-vue-next';
import { onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import StatusBadge from '@/components/StatusBadge.vue';
import { apiRequest, formatDate } from '@/services/api';
import type { Contest, StandingRow } from '@/services/types';

const route = useRoute();
const router = useRouter();
const contest = ref<Contest | null>(null);
const standings = ref<StandingRow[]>([]);
const error = ref('');

async function load() {
  error.value = '';
  try {
    contest.value = await apiRequest<Contest>(`/contests/${route.params.id}`, { auth: false });
    standings.value = await apiRequest<StandingRow[]>(`/contests/${route.params.id}/standings`, { auth: false });
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败';
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
        <h1>{{ contest?.title || '排行榜' }}</h1>
        <p v-if="contest">{{ formatDate(contest.start_at) }} - {{ formatDate(contest.end_at) }}</p>
      </div>
      <p v-if="error" class="form-error">{{ error }}</p>
      <div class="table-panel">
        <div class="table-row table-head standings-table">
          <span>#</span>
          <span>选手</span>
          <span>解题</span>
          <span>总分</span>
          <span>状态</span>
        </div>
        <div v-for="(row, index) in standings" :key="row.user_id" class="table-row standings-table">
          <strong>{{ index + 1 }}</strong>
          <span>{{ row.display_name }}</span>
          <span>{{ row.solved }}</span>
          <span>{{ row.score }}</span>
          <StatusBadge :status="contest?.status || 'running'" />
        </div>
      </div>
    </section>
  </div>
</template>
