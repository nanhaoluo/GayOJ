<script setup lang="ts">
import { ArrowLeft, CheckCircle2, Eye, Printer, RefreshCw, XCircle } from 'lucide-vue-next';
import { computed, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { apiRequest, formatDate } from '@/services/api';
import type { ContestPrintJobSummary, ContestPrintResponse, ContestPrintStatus } from '@/services/types';
import { authState } from '@/stores/auth';

const route = useRoute();
const router = useRouter();
const printJobs = ref<ContestPrintJobSummary[]>([]);
const data = ref<ContestPrintResponse | null>(null);
const error = ref('');
const submissionId = ref('');
const problemId = ref('');
const sourceCode = ref('');
const language = ref('');
const loading = ref(false);
const submitting = ref(false);
const updatingId = ref('');

const canProcessPrint = computed(() => {
  const permissions = authState.user?.permissions ?? [];
  return permissions.includes('submission:read:all') || permissions.includes('contest:manage') || permissions.includes('judge:monitor');
});
const pendingJobs = computed(() => printJobs.value.filter((item) => item.status === 'pending'));
const completedJobs = computed(() => printJobs.value.filter((item) => item.status !== 'pending'));

function contestId(): string {
  return String(route.params.id || '');
}

async function refreshJobs() {
  error.value = '';
  loading.value = true;
  try {
    printJobs.value = await apiRequest<ContestPrintJobSummary[]>(`/contests/${contestId()}/print`);
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败';
  } finally {
    loading.value = false;
  }
}

async function submitPrintJob() {
  error.value = '';
  submitting.value = true;
  try {
    data.value = await apiRequest<ContestPrintResponse>(`/contests/${contestId()}/print`, {
      method: 'POST',
      body: JSON.stringify({
        submission_id: submissionId.value.trim() || undefined,
        problem_id: problemId.value.trim() || undefined,
        language: language.value.trim() || undefined,
        source_code: sourceCode.value || undefined,
      }),
    });
    submissionId.value = '';
    problemId.value = '';
    language.value = '';
    sourceCode.value = '';
    await refreshJobs();
  } catch (err) {
    error.value = err instanceof Error ? err.message : '打印申请失败';
  } finally {
    submitting.value = false;
  }
}

async function openPrintJob(job: ContestPrintJobSummary) {
  error.value = '';
  try {
    data.value = await apiRequest<ContestPrintResponse>(`/contests/${contestId()}/print/${job.id}`);
  } catch (err) {
    error.value = err instanceof Error ? err.message : '源码读取失败';
  }
}

async function updateJob(job: ContestPrintJobSummary, nextStatus: ContestPrintStatus) {
  updatingId.value = job.id;
  error.value = '';
  try {
    data.value = await apiRequest<ContestPrintResponse>(`/contests/${contestId()}/print/${job.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ status: nextStatus }),
    });
    await refreshJobs();
  } catch (err) {
    error.value = err instanceof Error ? err.message : '状态更新失败';
  } finally {
    updatingId.value = '';
  }
}

function printSource() {
  window.print();
}

onMounted(() => {
  void refreshJobs();
});
</script>

<template>
  <div class="pure-page">
    <header class="pure-toolbar">
      <button class="secondary-action" type="button" @click="router.back()"><ArrowLeft :size="16" />返回</button>
      <button class="secondary-action" type="button" :disabled="loading" @click="refreshJobs"><RefreshCw :size="16" />刷新</button>
      <button v-if="data" class="secondary-action" type="button" @click="printSource"><Printer :size="16" />打印预览</button>
    </header>

    <section class="pure-content print-desk">
      <div class="pure-heading">
        <h1>打印台</h1>
        <p>打印单只来自已提交源码或本次请求源码。</p>
      </div>

      <form class="print-request-panel" @submit.prevent="submitPrintJob">
        <div class="inline-form">
          <input v-model="submissionId" placeholder="提交 ID" />
          <input v-model="problemId" placeholder="题目 ID 或比赛题号" />
          <input v-model="language" placeholder="语言" />
        </div>
        <textarea v-model="sourceCode" class="pure-textarea" placeholder="或输入本次请求要打印的源码"></textarea>
        <div class="row-actions">
          <button class="secondary-action" type="submit" :disabled="submitting">
            <Printer :size="16" />提交打印申请
          </button>
        </div>
      </form>

      <p v-if="error" class="form-error">{{ error }}</p>

      <section class="print-desk-layout">
        <article class="monitor-panel">
          <div class="monitor-panel-head">
            <div>
              <h2>待处理</h2>
              <p>{{ pendingJobs.length }} 条等待打印</p>
            </div>
          </div>
          <div class="monitor-list">
            <div v-for="item in pendingJobs" :key="item.id" class="monitor-list-row print-job-row">
              <div class="monitor-feed-main">
                <strong>{{ item.problem_key || item.problem_id }} · {{ item.problem_title || item.id }}</strong>
                <span>{{ item.user_display_name || item.user_id }} · {{ item.language || '未知语言' }} · {{ item.line_count }} 行 · {{ formatDate(item.requested_at) }}</span>
              </div>
              <div class="row-actions">
                <button class="secondary-action compact" type="button" @click="openPrintJob(item)">
                  <Eye :size="14" />打开
                </button>
                <button
                  v-if="canProcessPrint"
                  class="icon-action"
                  type="button"
                  :disabled="updatingId === item.id"
                  title="标记已打印"
                  @click="updateJob(item, 'printed')"
                >
                  <CheckCircle2 :size="16" />
                </button>
                <button
                  v-if="canProcessPrint"
                  class="icon-action"
                  type="button"
                  :disabled="updatingId === item.id"
                  title="取消打印"
                  @click="updateJob(item, 'cancelled')"
                >
                  <XCircle :size="16" />
                </button>
              </div>
            </div>
            <p v-if="!loading && pendingJobs.length === 0" class="empty-text">当前没有待打印申请。</p>
          </div>
        </article>

        <article class="monitor-panel">
          <div class="monitor-panel-head">
            <div>
              <h2>已处理</h2>
              <p>{{ completedJobs.length }} 条历史记录</p>
            </div>
          </div>
          <div class="monitor-list">
            <div v-for="item in completedJobs" :key="item.id" class="monitor-list-row print-job-row compact">
              <div class="monitor-feed-main">
                <strong>{{ item.problem_key || item.problem_id }} · {{ item.status }}</strong>
                <span>{{ item.user_display_name || item.user_id }} · {{ formatDate(item.printed_at || item.requested_at) }}</span>
              </div>
              <button class="secondary-action compact" type="button" @click="openPrintJob(item)">
                <Eye :size="14" />打开
              </button>
            </div>
            <p v-if="!loading && completedJobs.length === 0" class="empty-text">暂无已处理打印记录。</p>
          </div>
        </article>
      </section>

      <section v-if="data" class="print-preview-panel">
        <div class="print-job-meta">
          <strong>{{ data.problem_key || data.problem_id }} · {{ data.problem_title || '打印任务' }}</strong>
          <span>{{ data.source_kind === 'submission' ? '已提交源码' : '本次请求源码' }} · {{ data.line_count }} 行 · {{ data.status }}</span>
        </div>
        <pre class="print-preview">{{ data.source_code }}</pre>
      </section>
    </section>
  </div>
</template>
