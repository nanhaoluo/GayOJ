<script setup lang="ts">
import { ArrowLeft, CheckCircle2, Eye, Printer, RefreshCw, Send, XCircle } from 'lucide-vue-next';
import { computed, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { apiRequest, formatDate } from '@/services/api';
import type { ContestPrintJobSummary, ContestPrintResponse, ContestPrintStatus } from '@/services/types';
import { authState } from '@/stores/auth';

const route = useRoute();
const router = useRouter();
const printJobs = ref<ContestPrintJobSummary[]>([]);
const selectedJob = ref<ContestPrintResponse | null>(null);
const error = ref('');
const submissionId = ref('');
const problemId = ref('');
const language = ref('');
const sourceCode = ref('');
const loading = ref(false);
const submitting = ref(false);
const updatingId = ref('');
const dispatchingId = ref('');
const printerName = ref('');
const copies = ref(1);

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
    selectedJob.value = await apiRequest<ContestPrintResponse>(`/contests/${contestId()}/print`, {
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
    selectedJob.value = await apiRequest<ContestPrintResponse>(`/contests/${contestId()}/print/${job.id}`);
  } catch (err) {
    error.value = err instanceof Error ? err.message : '源码读取失败';
  }
}

async function updatePrintJob(job: ContestPrintJobSummary, status: ContestPrintStatus) {
  updatingId.value = job.id;
  error.value = '';
  try {
    selectedJob.value = await apiRequest<ContestPrintResponse>(`/contests/${contestId()}/print/${job.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    });
    await refreshJobs();
  } catch (err) {
    error.value = err instanceof Error ? err.message : '状态更新失败';
  } finally {
    updatingId.value = '';
  }
}

async function dispatchPrintJob(job: ContestPrintJobSummary) {
  dispatchingId.value = job.id;
  error.value = '';
  try {
    selectedJob.value = await apiRequest<ContestPrintResponse>(`/contests/${contestId()}/print/${job.id}/dispatch`, {
      method: 'POST',
      body: JSON.stringify({
        printer_name: printerName.value.trim() || undefined,
        copies: copies.value,
        note: 'sent to physical printer queue',
      }),
    });
    await refreshJobs();
  } catch (err) {
    error.value = err instanceof Error ? err.message : '发送打印队列失败';
  } finally {
    dispatchingId.value = '';
  }
}

function printPreview() {
  window.print();
}

function printProblemLabel(job: ContestPrintJobSummary | ContestPrintResponse): string {
  return [job.problem_key, job.problem_title].filter(Boolean).join(' · ') || job.problem_id || '比赛题目';
}

function printerStatusText(job: ContestPrintJobSummary | ContestPrintResponse): string {
  const labels: Record<string, string> = {
    not_sent: '未发送',
    queued: '已入物理队列',
    accepted: '打印机已接收',
    failed: '发送失败',
  };
  return labels[job.printer_status] ?? job.printer_status;
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
      <button v-if="selectedJob" class="secondary-action" type="button" @click="printPreview"><Printer :size="16" />打印预览</button>
    </header>

    <section class="pure-content print-desk">
      <div class="pure-heading">
        <h1>打印台</h1>
        <p>打印单只来自已提交源码或本次请求源码。</p>
      </div>

      <form class="print-request-panel" @submit.prevent="submitPrintJob">
        <div class="inline-form">
          <input v-model="submissionId" placeholder="提交 ID" />
          <input v-model="problemId" placeholder="比赛题号（手工源码时必填）" />
          <input v-model="language" placeholder="语言" />
        </div>
        <textarea v-model="sourceCode" class="pure-textarea" placeholder="或输入本次请求要打印的源码"></textarea>
        <div class="row-actions">
          <button class="secondary-action" type="submit" :disabled="submitting">
            <Printer :size="16" />提交打印申请
          </button>
        </div>
      </form>

      <section v-if="canProcessPrint" class="print-request-panel">
        <div class="inline-form">
          <input v-model="printerName" placeholder="打印机名称（默认）" />
          <input v-model.number="copies" type="number" min="1" max="10" placeholder="份数" />
        </div>
      </section>

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
                <strong>{{ printProblemLabel(item) }} · {{ item.user_display_name || item.user_id }}</strong>
                <span>{{ item.source_kind === 'submission' ? '已提交源码' : '本次请求源码' }} · {{ item.user_display_name || item.user_id }} · {{ item.line_count }} 行</span>
                <small>{{ item.language || '未知语言' }} · {{ printerStatusText(item) }} · {{ formatDate(item.requested_at) }}</small>
              </div>
              <div class="row-actions">
                <button class="secondary-action compact" type="button" @click="openPrintJob(item)">
                  <Eye :size="14" />打开
                </button>
                <button
                  v-if="canProcessPrint"
                  class="icon-action"
                  type="button"
                  :disabled="dispatchingId === item.id"
                  title="发送到物理打印机"
                  @click="dispatchPrintJob(item)"
                >
                  <Send :size="16" />
                </button>
                <button
                  v-if="canProcessPrint"
                  class="icon-action"
                  type="button"
                  :disabled="updatingId === item.id"
                  title="标记已打印"
                  @click="updatePrintJob(item, 'printed')"
                >
                  <CheckCircle2 :size="16" />
                </button>
                <button
                  v-if="canProcessPrint"
                  class="icon-action"
                  type="button"
                  :disabled="updatingId === item.id"
                  title="取消打印"
                  @click="updatePrintJob(item, 'cancelled')"
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
                <strong>{{ printProblemLabel(item) }} · {{ item.status }}</strong>
                <span>{{ item.user_display_name || item.user_id }} · {{ printerStatusText(item) }} · {{ formatDate(item.printed_at || item.requested_at) }}</span>
              </div>
              <button class="secondary-action compact" type="button" @click="openPrintJob(item)">
                <Eye :size="14" />打开
              </button>
            </div>
            <p v-if="!loading && completedJobs.length === 0" class="empty-text">暂无已处理打印记录。</p>
          </div>
        </article>
      </section>

      <section class="print-preview-panel">
        <div class="monitor-panel-head">
          <div>
            <h2>{{ selectedJob ? `${printProblemLabel(selectedJob)} · ${selectedJob.language || '源码'}` : '源码预览' }}</h2>
            <p v-if="selectedJob">
              {{ selectedJob.id }} · {{ selectedJob.source_kind === 'submission' ? '已提交源码' : '本次请求源码' }} · {{ selectedJob.status }} · {{ selectedJob.line_count }} 行
            </p>
            <p v-if="selectedJob">
              {{ printerStatusText(selectedJob) }} · {{ selectedJob.printer_name || '默认打印机' }} · {{ selectedJob.printer_job_id || '未分配队列号' }}
            </p>
            <p v-if="selectedJob?.printer_error" class="form-error">{{ selectedJob.printer_error }}</p>
            <p v-if="selectedJob?.printer_receipt" class="receipt-text">回执：{{ selectedJob.printer_receipt }}</p>
          </div>
          <button v-if="selectedJob" class="secondary-action" type="button" @click="printPreview">
            <Printer :size="16" />打印预览
          </button>
        </div>
        <pre v-if="selectedJob" class="print-preview">{{ selectedJob.source_code }}</pre>
        <p v-else class="empty-text">选择或创建打印单后显示源码。</p>
      </section>
    </section>
  </div>
</template>
