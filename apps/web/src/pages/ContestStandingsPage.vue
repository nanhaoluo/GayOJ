<script setup lang="ts">
import { ArrowLeft, RefreshCw } from 'lucide-vue-next';
import { computed, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import ContestBoardTable from '@/components/ContestBoardTable.vue';
import { apiRequest, formatDate } from '@/services/api';
import type { Contest, StandingRow } from '@/services/types';
import { authState } from '@/stores/auth';

const route = useRoute();
const router = useRouter();
const contest = ref<Contest | null>(null);
const standings = ref<StandingRow[]>([]);
const error = ref('');

const canViewFullBoard = computed(() =>
  Boolean(
    authState.user?.permissions.includes('contest:manage')
      || authState.user?.permissions.includes('judge:monitor')
      || authState.user?.permissions.includes('clarification:read:all'),
  ),
);

const freezeNotice = computed(() => {
  if (!contest.value?.freeze_active) return '';
  if (canViewFullBoard.value) {
    return '当前比赛处于封榜阶段，你看到的是裁判完整榜单。';
  }
  return '当前榜单已封榜，仅展示冻结前的提交结果。';
});

async function load() {
  error.value = '';
  try {
    contest.value = await apiRequest<Contest>(`/contests/${route.params.id}`);
    standings.value = await apiRequest<StandingRow[]>(`/contests/${route.params.id}/standings`);
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载排行榜失败';
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
    <section class="pure-content standings-content">
      <div class="pure-heading">
        <h1>{{ contest?.title || '比赛榜单' }}</h1>
        <p v-if="contest">
          {{ contest.rule }} · {{ formatDate(contest.start_at) }} - {{ formatDate(contest.end_at) }}
        </p>
      </div>
      <p v-if="freezeNotice" class="freeze-banner">{{ freezeNotice }}</p>
      <p v-if="error" class="form-error">{{ error }}</p>
      <ContestBoardTable v-if="contest" :contest="contest" :standings="standings" />
    </section>
  </div>
</template>
