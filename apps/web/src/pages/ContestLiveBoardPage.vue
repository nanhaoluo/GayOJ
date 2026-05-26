<script setup lang="ts">
import { ArrowLeft, Radio, RefreshCw } from 'lucide-vue-next';
import { onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import ContestBoardTable from '@/components/ContestBoardTable.vue';
import { apiRequest, formatDate } from '@/services/api';
import type { ContestBoardResponse } from '@/services/types';

const route = useRoute();
const router = useRouter();
const board = ref<ContestBoardResponse | null>(null);
const error = ref('');

async function load() {
  error.value = '';
  try {
    board.value = await apiRequest<ContestBoardResponse>(`/contests/${route.params.id}/live-board`, { auth: false });
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载实时外榜失败';
  }
}

onMounted(load);
</script>

<template>
  <div class="pure-page board-page">
    <header class="pure-toolbar">
      <button class="secondary-action" type="button" @click="router.back()"><ArrowLeft :size="16" />返回</button>
      <button class="secondary-action" type="button" @click="load"><RefreshCw :size="16" />刷新</button>
    </header>
    <section class="pure-content standings-content">
      <div class="pure-heading board-heading">
        <div>
          <h1>{{ board?.contest.title || '实时外榜' }}</h1>
          <p v-if="board">{{ board.contest.rule }} · {{ formatDate(board.contest.start_at) }} - {{ formatDate(board.contest.end_at) }}</p>
        </div>
        <span class="board-chip live"><Radio :size="15" />实时外榜</span>
      </div>
      <p v-if="board?.contest.freeze_active" class="freeze-banner">实时外榜仍遵守封榜规则，不展示冻结后的公开排名变化。</p>
      <p v-if="error" class="form-error">{{ error }}</p>
      <ContestBoardTable v-if="board" :contest="board.contest" :standings="board.standings" />
    </section>
  </div>
</template>
