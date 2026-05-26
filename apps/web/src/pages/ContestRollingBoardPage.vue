<script setup lang="ts">
import { ArrowLeft, Eye, EyeOff, RefreshCw } from 'lucide-vue-next';
import { computed, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import ContestBoardTable from '@/components/ContestBoardTable.vue';
import { apiRequest, formatDate } from '@/services/api';
import type { ContestRollingResponse } from '@/services/types';

const route = useRoute();
const router = useRouter();
const board = ref<ContestRollingResponse | null>(null);
const error = ref('');

const deltaCount = computed(() => {
  if (!board.value) return 0;
  const publicRank = new Map(board.value.public_standings.map((row, index) => [row.user_id, index]));
  return board.value.final_standings.filter((row, index) => publicRank.get(row.user_id) !== index).length;
});

async function load() {
  error.value = '';
  try {
    board.value = await apiRequest<ContestRollingResponse>(`/contests/${route.params.id}/rolling-board`);
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载滚榜失败';
  }
}

onMounted(load);
</script>

<template>
  <div class="pure-page board-page rolling-page">
    <header class="pure-toolbar">
      <button class="secondary-action" type="button" @click="router.back()"><ArrowLeft :size="16" />返回</button>
      <button class="secondary-action" type="button" @click="load"><RefreshCw :size="16" />刷新</button>
    </header>
    <section class="pure-content standings-content">
      <div class="pure-heading board-heading">
        <div>
          <h1>{{ board?.contest.title || '比赛滚榜' }}</h1>
          <p v-if="board">{{ board.contest.rule }} · {{ formatDate(board.contest.start_at) }} - {{ formatDate(board.contest.end_at) }}</p>
        </div>
        <span class="board-chip rolling">滚榜</span>
      </div>
      <p v-if="error" class="form-error">{{ error }}</p>
      <section v-if="board" class="rolling-summary">
        <article class="rolling-stat">
          <small>封榜前公开名次</small>
          <strong>{{ board.public_standings.length }}</strong>
        </article>
        <article class="rolling-stat">
          <small>最终完整名次</small>
          <strong>{{ board.final_standings.length }}</strong>
        </article>
        <article class="rolling-stat">
          <small>名次变化选手</small>
          <strong>{{ deltaCount }}</strong>
        </article>
      </section>
      <section v-if="board" class="rolling-grid">
        <article class="rolling-panel">
          <div class="rolling-panel-head">
            <h2><EyeOff :size="16" />封榜视图</h2>
          </div>
          <ContestBoardTable :contest="board.contest" :standings="board.public_standings" />
        </article>
        <article class="rolling-panel">
          <div class="rolling-panel-head">
            <h2><Eye :size="16" />最终视图</h2>
          </div>
          <ContestBoardTable :contest="board.contest" :standings="board.final_standings" />
        </article>
      </section>
    </section>
  </div>
</template>
