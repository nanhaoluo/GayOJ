<script setup lang="ts">
import { ArrowLeft, RefreshCw } from 'lucide-vue-next';
import { onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import StatusBadge from '@/components/StatusBadge.vue';
import { apiRequest } from '@/services/api';
import type { ContestBalloon } from '@/services/types';

const route = useRoute();
const router = useRouter();
const data = ref<ContestBalloon[]>([]);
const error = ref('');

async function load() {
  error.value = '';
  try {
    data.value = await apiRequest<ContestBalloon[]>(`/contests/${route.params.id}/balloons`);
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
        <h1>气球台</h1>
      </div>
      <p v-if="error" class="form-error">{{ error }}</p>
      <div class="list-stack">
        <div v-for="item in data" :key="item.submission_id" class="reply-row">
          <strong>{{ item.display_name }} / {{ item.problem_title }}</strong>
          <StatusBadge :status="item.status" />
        </div>
      </div>
    </section>
  </div>
</template>
