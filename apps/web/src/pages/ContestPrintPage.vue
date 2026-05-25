<script setup lang="ts">
import { ArrowLeft, Printer } from 'lucide-vue-next';
import { ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { apiRequest } from '@/services/api';
import type { ContestPrintResponse } from '@/services/types';

const route = useRoute();
const router = useRouter();
const data = ref<ContestPrintResponse | null>(null);
const error = ref('');
const submissionId = ref('');
const problemId = ref('');
const sourceCode = ref('');

async function load() {
  error.value = '';
  try {
    data.value = await apiRequest<ContestPrintResponse>(`/contests/${route.params.id}/print`, {
      method: 'POST',
      body: JSON.stringify({
        submission_id: submissionId.value || undefined,
        problem_id: problemId.value || undefined,
        source_code: sourceCode.value || undefined,
      }),
    });
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败';
  }
}
</script>

<template>
  <div class="pure-page">
    <header class="pure-toolbar">
      <button class="secondary-action" type="button" @click="router.back()"><ArrowLeft :size="16" />返回</button>
      <button class="secondary-action" type="button" @click="load"><Printer :size="16" />打印</button>
    </header>
    <section class="pure-content">
      <div class="pure-heading">
        <h1>打印台</h1>
      </div>
      <form class="inline-form" @submit.prevent="load">
        <input v-model="submissionId" placeholder="提交 ID" />
        <input v-model="problemId" placeholder="题目 ID（手工源码时必填）" />
      </form>
      <textarea v-model="sourceCode" class="pure-textarea" placeholder="或输入本次请求要打印的源码"></textarea>
      <p v-if="error" class="form-error">{{ error }}</p>
      <pre v-if="data" class="print-preview">{{ data.source_code }}</pre>
    </section>
  </div>
</template>
