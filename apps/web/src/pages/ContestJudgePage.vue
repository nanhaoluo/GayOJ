<script setup lang="ts">
import { ArrowLeft, RefreshCw } from 'lucide-vue-next';
import { onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import StatusBadge from '@/components/StatusBadge.vue';
import { apiRequest } from '@/services/api';
import type { JudgeMonitor } from '@/services/types';

const route = useRoute();
const router = useRouter();
const data = ref<JudgeMonitor | null>(null);
const error = ref('');

async function load() {
  error.value = '';
  try {
    data.value = await apiRequest<JudgeMonitor>('/judge/monitor');
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
        <h1>裁判组</h1>
        <p>{{ route.params.id || '全局监控' }}</p>
      </div>
      <p v-if="error" class="form-error">{{ error }}</p>
      <div v-if="data" class="list-stack">
        <div v-for="node in data.judge_nodes" :key="node.id" class="reply-row">
          <strong>{{ node.name }}</strong>
          <span>{{ node.languages.join(', ') }}</span>
          <StatusBadge :status="node.status" />
        </div>
      </div>
    </section>
  </div>
</template>
