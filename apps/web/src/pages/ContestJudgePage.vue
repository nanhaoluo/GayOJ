<script setup lang="ts">
import { ArrowLeft, Bell, RefreshCw, Send } from 'lucide-vue-next';
import { computed, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import StatusBadge from '@/components/StatusBadge.vue';
import { apiRequest, formatDate, problemTypeLabel } from '@/services/api';
import type { ContestJudgeMonitor } from '@/services/types';
import { authState } from '@/stores/auth';

const route = useRoute();
const router = useRouter();
const data = ref<ContestJudgeMonitor | null>(null);
const error = ref('');
const announcementTitle = ref('');
const announcementContent = ref('');
const publishing = ref(false);

const pendingClarifications = computed(() => data.value?.clarifications.filter((item) => !item.answer) ?? []);
const repliedClarifications = computed(() => data.value?.clarifications.filter((item) => item.answer) ?? []);
const pendingBalloons = computed(() => data.value?.balloons.filter((item) => !item.released) ?? []);
const canPublishAnnouncements = computed(() => {
  const permissions = authState.user?.permissions ?? [];
  return permissions.includes('contest:manage') || permissions.includes('judge:monitor');
});

function clarificationTitle(item: ContestJudgeMonitor['clarifications'][number]): string {
  if (!item.problem_id) return '全局问题';
  return `${item.problem_key || item.problem_id} · ${item.problem_title || '比赛题目'}`;
}

function balloonProblemTitle(item: ContestJudgeMonitor['balloons'][number]): string {
  return `${item.problem_key || item.problem_id} · ${item.problem_title}`;
}

async function load() {
  error.value = '';
  try {
    data.value = await apiRequest<ContestJudgeMonitor>(`/judge/monitor/${route.params.id}`);
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败';
  }
}

async function publishAnnouncement() {
  const title = announcementTitle.value.trim();
  const content = announcementContent.value.trim();
  if (!title || !content) return;
  publishing.value = true;
  error.value = '';
  try {
    await apiRequest(`/contests/${route.params.id}/announcements`, {
      method: 'POST',
      body: JSON.stringify({ title, content }),
    });
    announcementTitle.value = '';
    announcementContent.value = '';
    await load();
  } catch (err) {
    error.value = err instanceof Error ? err.message : '公告发布失败';
  } finally {
    publishing.value = false;
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

    <section class="pure-content contest-monitor-page">
      <div class="pure-heading">
        <h1>{{ data?.contest.title || '比赛裁判工作台' }}</h1>
        <p v-if="data">
          {{ data.contest.rule }} · {{ data.contest.status }} · {{ formatDate(data.contest.start_at) }} - {{ formatDate(data.contest.end_at) }}
        </p>
      </div>

      <p v-if="error" class="form-error">{{ error }}</p>

      <template v-if="data">
        <section class="contest-monitor-summary contest-monitor-summary-wide">
          <article class="monitor-stat-card">
            <small>队列深度</small>
            <strong>{{ data.queue_depth }}</strong>
            <span>{{ data.queue.pending }} 待调度 / {{ data.queue.leased }} 执行中</span>
          </article>
          <article class="monitor-stat-card">
            <small>比赛提交</small>
            <strong>{{ data.last_submissions.length }}</strong>
            <span>最近 10 条比赛内提交</span>
          </article>
          <article class="monitor-stat-card">
            <small>Clarification</small>
            <strong>{{ pendingClarifications.length }}</strong>
            <span>{{ repliedClarifications.length }} 条已处理</span>
          </article>
          <article class="monitor-stat-card">
            <small>公告</small>
            <strong>{{ data.announcements.length }}</strong>
            <span>面向当前比赛范围发布</span>
          </article>
          <article class="monitor-stat-card">
            <small>气球</small>
            <strong>{{ pendingBalloons.length }}</strong>
            <span>{{ data.balloons.length }} 条比赛记录</span>
          </article>
          <article class="monitor-stat-card">
            <small>打印单</small>
            <strong>{{ data.print_jobs.filter((item) => item.status === 'pending').length }}</strong>
            <span>{{ data.print_jobs.length }} 条打印请求</span>
          </article>
        </section>

        <section class="contest-monitor-grid">
          <article class="monitor-panel">
            <div class="monitor-panel-head">
              <div>
                <h2>比赛公告</h2>
                <p>公告遵守比赛可见性与资源归属边界。</p>
              </div>
            </div>
            <form v-if="canPublishAnnouncements" class="announcement-form" @submit.prevent="publishAnnouncement">
              <input v-model="announcementTitle" type="text" placeholder="公告标题" maxlength="120" />
              <textarea
                v-model="announcementContent"
                class="pure-textarea announcement-textarea"
                placeholder="公告内容"
                maxlength="4000"
              ></textarea>
              <div class="row-actions">
                <button class="secondary-action" type="submit" :disabled="publishing">
                  <Send :size="16" />发布公告
                </button>
              </div>
            </form>
            <div class="monitor-list">
              <div v-for="item in data.announcements" :key="item.id" class="monitor-list-row">
                <div class="monitor-feed-main">
                  <strong>{{ item.title }}</strong>
                  <span>{{ item.created_by_name }} · {{ formatDate(item.created_at) }}</span>
                  <p>{{ item.content }}</p>
                </div>
                <Bell :size="16" />
              </div>
              <p v-if="data.announcements.length === 0" class="empty-text">当前比赛暂无公告。</p>
            </div>
          </article>

          <article class="monitor-panel">
            <div class="monitor-panel-head">
              <div>
                <h2>实时提交流</h2>
                <p>只展示当前比赛的提交记录。</p>
              </div>
            </div>
            <div class="monitor-feed">
              <div v-for="item in data.last_submissions" :key="item.id" class="monitor-feed-row">
                <div class="monitor-feed-main">
                  <strong>{{ item.problem_title }}</strong>
                  <span>{{ problemTypeLabel(item.problem_type) }} · {{ item.language || '客观题' }} · {{ formatDate(item.created_at) }}</span>
                </div>
                <StatusBadge :status="item.status" />
                <strong>{{ item.score }}/{{ item.max_score }}</strong>
              </div>
              <p v-if="data.last_submissions.length === 0" class="empty-text">当前比赛还没有提交记录。</p>
            </div>
          </article>

          <article class="monitor-panel">
            <div class="monitor-panel-head">
              <div>
                <h2>Clarification</h2>
                <p>未处理问题优先显示。</p>
              </div>
            </div>
            <div class="monitor-list">
              <div v-for="item in data.clarifications" :key="item.id" class="monitor-list-row">
                <div class="monitor-feed-main">
                  <strong>{{ clarificationTitle(item) }}</strong>
                  <span>{{ item.user_display_name || '匿名选手' }} · {{ formatDate(item.created_at) }}</span>
                  <p>{{ item.question }}</p>
                </div>
                <StatusBadge :status="item.answer ? 'completed' : 'pending'" />
              </div>
              <p v-if="data.clarifications.length === 0" class="empty-text">当前比赛没有 Clarification 记录。</p>
            </div>
          </article>

          <article class="monitor-panel">
            <div class="monitor-panel-head">
              <div>
                <h2>评测队列</h2>
                <p>{{ data.queue.backend }} · {{ data.queue.topic }}</p>
              </div>
            </div>
            <div class="monitor-list">
              <div v-for="job in data.queue.last_jobs" :key="job.id" class="monitor-list-row compact">
                <div class="monitor-feed-main">
                  <strong>{{ job.problem_id }} · {{ job.language }}</strong>
                  <span>{{ job.submission_id }} · {{ formatDate(job.created_at) }}</span>
                </div>
                <StatusBadge :status="job.status" />
              </div>
              <p v-if="data.queue.last_jobs.length === 0" class="empty-text">当前比赛没有代码评测队列任务。</p>
            </div>
          </article>

          <article class="monitor-panel">
            <div class="monitor-panel-head">
              <div>
                <h2>气球记录</h2>
                <p>只统计当前比赛可发放气球的通过记录。</p>
              </div>
            </div>
            <div class="monitor-list">
              <div v-for="item in data.balloons" :key="item.submission_id" class="monitor-list-row compact">
                <div class="monitor-feed-main">
                  <strong>{{ item.display_name }} · {{ item.problem_key || item.problem_id }}</strong>
                  <span>{{ balloonProblemTitle(item) }} · {{ formatDate(item.judged_at) }}</span>
                </div>
                <StatusBadge :status="item.released ? 'completed' : 'pending'" />
              </div>
              <p v-if="data.balloons.length === 0" class="empty-text">当前比赛还没有气球记录。</p>
            </div>
          </article>

          <article class="monitor-panel">
            <div class="monitor-panel-head">
              <div>
                <h2>打印单</h2>
                <p>只展示当前比赛代码打印请求。</p>
              </div>
            </div>
            <div class="monitor-list">
              <div v-for="job in data.print_jobs" :key="job.id" class="monitor-list-row compact">
                <div class="monitor-feed-main">
                  <strong>{{ job.problem_key || job.problem_id }} · {{ job.user_display_name || job.user_id }}</strong>
                  <span>{{ job.source_kind === 'submission' ? '提交源码' : '请求源码' }} · {{ job.language || '未知语言' }} · {{ formatDate(job.requested_at) }}</span>
                </div>
                <StatusBadge :status="job.status" />
              </div>
              <p v-if="data.print_jobs.length === 0" class="empty-text">当前比赛还没有打印单。</p>
            </div>
          </article>
        </section>
      </template>
    </section>
  </div>
</template>
