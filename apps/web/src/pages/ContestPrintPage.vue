<script setup lang="ts">
import { ArrowLeft, CheckCircle2, Printer, RefreshCw, XCircle } from 'lucide-vue-next';
import { computed, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { apiRequest, formatDate } from '@/services/api';
import type { ContestPrintJobSummary, ContestPrintResponse, ContestPrintStatus } from '@/services/types';
import { authState } from '@/stores/auth';

const route = useRoute();
const router = useRouter();
const data = ref<ContestPrintResponse | null>(null);
const jobs = ref<ContestPrintJobSummary[]>([]);
const error = ref('');
const submissionId = ref('');
const problemId = ref('');
const sourceCode = ref('');
const language = ref('');
const loading = ref(false);
const creating = ref(false);
const updating = ref('');

const canProcessPrint = computed(() => {
  const permissions = authState.user?.permissions ?? [];
  return permissions.includes('submission:read:all') || permissions.includes('contest:manage') || permissions.includes('judge:monitor');
});

async function loadJobs() {
  error.value = '';
  loading.value = true;
  try {
    jobs.value = await apiRequest<ContestPrintJobSummary[]>(`/contests/${route.params.id}/print`);
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败';
  } finally {
    loading.value = false;
  }
}

async function createPrintJob() {
  error.value = '';
  creating.value = true;
  try {
    data.value = await apiRequest<ContestPrintResponse>(`/contests/${route.params.id}/print`, {
      method: 'POST',
      body: JSON.stringify({
        submission_id: submissionId.value || undefined,
        problem_id: problemId.value || undefined,
        language: language.value || undefined,
        source_code: sourceCode.value || undefined,
      }),
    });
    await loadJobs();
  } catch (err) {
    error.value = err instanceof Error ? err.message : '打印请求失败';
  } finally {
    creating.value = false;
  }
}

async function openJob(job: ContestPrintJobSummary) {
  error.value = '';
  try {
    data.value = await apiRequest<ContestPrintResponse>(`/contests/${route.params.id}/print/${job.id}`);
  } catch (err) {
    error.value = err instanceof Error ? err.message : '读取打印单失败';
  }
}

async function updateJob(job: ContestPrintJobSummary, status: ContestPrintStatus) {
  updating.value = job.id;
  error.value = '';
  try {
    data.value = await apiRequest<ContestPrintResponse>(`/contests/${route.params.id}/print/${job.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    });
    await loadJobs();
  } catch (err) {
    error.value = err instanceof Error ? err.message : '更新打印单失败';
  } finally {
    updating.value = '';
  }
}

function printSource() {
  window.print();
}

onMounted(loadJobs);
</script>

<template>
  <div class="pure-page">
    <header class="pure-toolbar">
      <button class="secondary-action" type="button" @click="router.back()"><ArrowLeft :size="16" />返回</button>
      <button class="secondary-action" type="button" @click="loadJobs" :disabled="loading"><RefreshCw :size="16" />刷新</button>
      <button class="secondary-action" type="button" @click="createPrintJob" :disabled="creating"><Printer :size="16" />打印</button>
    </header>
    <section class="pure-content">
      <div class="pure-heading">
        <h1>打印台</h1>
        <p>打印单只来自已提交源码或本次请求源码。</p>
      </div>
      <form class="inline-form" @submit.prevent="createPrintJob">
        <input v-model="submissionId" placeholder="提交 ID" />
        <input v-model="problemId" placeholder="题目 ID（手工源码时必填）" />
        <input v-model="language" placeholder="语言" />
      </form>
      <textarea v-model="sourceCode" class="pure-textarea" placeholder="或输入本次请求要打印的源码"></textarea>
      <p v-if="error" class="form-error">{{ error }}</p>

      <div class="print-console">
        <section class="print-jobs">
          <div class="print-job-row" v-for="job in jobs" :key="job.id" :class="{ active: data?.id === job.id }">
            <button class="print-job-main" type="button" @click="openJob(job)">
              <strong>{{ job.problem_key || job.problem_id || '题目' }} · {{ job.user_display_name || job.user_id }}</strong>
              <span>{{ job.source_kind === 'submission' ? '提交源码' : '请求源码' }} · {{ job.language || '未知语言' }} · {{ job.line_count }} 行</span>
              <small>{{ job.status }} · {{ formatDate(job.requested_at) }}</small>
            </button>
            <div v-if="canProcessPrint" class="row-actions compact-actions">
              <button class="icon-action" type="button" :disabled="updating === job.id" @click="updateJob(job, 'printed')" title="标记已打印">
                <CheckCircle2 :size="16" />
              </button>
              <button class="icon-action" type="button" :disabled="updating === job.id" @click="updateJob(job, 'cancelled')" title="取消打印">
                <XCircle :size="16" />
              </button>
            </div>
          </div>
          <p v-if="jobs.length === 0" class="empty-text">当前比赛暂无打印单。</p>
        </section>

        <section class="print-preview-panel">
          <div class="monitor-panel-head">
            <div>
              <h2>{{ data ? `${data.problem_key || data.problem_id} · ${data.language || '源码'}` : '源码预览' }}</h2>
              <p v-if="data">{{ data.id }} · {{ data.status }} · {{ data.line_count }} 行</p>
            </div>
            <button v-if="data" class="secondary-action" type="button" @click="printSource"><Printer :size="16" />打印预览</button>
          </div>
          <pre v-if="data" class="print-preview">{{ data.source_code }}</pre>
          <p v-else class="empty-text">选择或创建打印单后显示源码。</p>
        </section>
      </div>
    </section>
  </div>
</template>
