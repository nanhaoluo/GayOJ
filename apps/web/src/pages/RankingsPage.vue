<script setup lang="ts">
import { Medal } from 'lucide-vue-next';
import { onMounted, ref } from 'vue';
import { apiRequest } from '@/services/api';

const rankings = ref<Array<Record<string, unknown>>>([]);

onMounted(async () => {
  rankings.value = await apiRequest<Array<Record<string, unknown>>>('/rankings', { auth: false });
});
</script>

<template>
  <div class="page-stack">
    <section class="page-heading">
      <div>
        <span class="eyebrow">Rankings</span>
        <h1>排行榜</h1>
      </div>
    </section>

    <section class="panel table-panel">
      <div class="table-row table-head">
        <span>#</span>
        <span>用户</span>
        <span>学校</span>
        <span>角色</span>
        <span>AC</span>
        <span>Rating</span>
      </div>
      <div v-for="(row, index) in rankings" :key="String(row.user_id)" class="table-row">
        <span class="rank-medal"><Medal :size="17" />{{ index + 1 }}</span>
        <strong>{{ row.display_name }}</strong>
        <span>{{ row.school }}</span>
        <span>{{ row.role }}</span>
        <span>{{ row.solved }}</span>
        <span>{{ row.rating }}</span>
      </div>
    </section>
  </div>
</template>
