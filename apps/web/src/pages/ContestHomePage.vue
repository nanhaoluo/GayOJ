<script setup lang="ts">
import { ArrowRight, Bell, FileCode2, FileQuestion, KeyRound, MessageSquare, Printer, Radio, RefreshCw, Rows3, Trophy, UserPlus } from 'lucide-vue-next';
import { computed, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import ProblemTypeIcon from '@/components/ProblemTypeIcon.vue';
import StatusBadge from '@/components/StatusBadge.vue';
import { ApiError, apiRequest, formatDate, problemTypeLabel } from '@/services/api';
import type { Contest, ContestAccessResponse, ContestAnnouncement, ContestProblemDetail, ContestRegistrationResponse } from '@/services/types';
import { authState } from '@/stores/auth';

const route = useRoute();
const router = useRouter();
const contest = ref<Contest | null>(null);
const announcements = ref<ContestAnnouncement[]>([]);
const problems = ref<ContestProblemDetail[]>([]);
const error = ref('');
const notice = ref('');
const accessRequired = ref(false);
const accessCode = ref('');
const unlocking = ref(false);
const registering = ref(false);

const canUseContestTools = computed(() => Boolean(authState.user));
const canRegister = computed(() => {
  return Boolean(authState.user?.role === 'student' && contest.value && contest.value.access_unlocked && contest.value.participation_mode !== 'open' && !contest.value.self_registered);
});
const canOpenPrintDesk = computed(() => {
  const permissions = authState.user?.permissions ?? [];
  return permissions.includes('judge:monitor') || permissions.includes('contest:manage') || authState.user?.role === 'student';
});

function problemAttemptSummary(problem: ContestProblemDetail): string {
  return `${problem.accepted}/${problem.attempts || 0}`;
}

function allowedLanguageText(problem: ContestProblemDetail): string {
  if (problem.type !== 'code') return '';
  if (!problem.allowed_languages.length) return '不限语言';
  return problem.allowed_languages.join(', ');
}

function participationLabel(value: Contest['participation_mode']): string {
  const labels: Record<Contest['participation_mode'], string> = {
    open: '开放参赛',
    individual: '个人报名',
    team: '队伍报名',
  };
  return labels[value];
}

async function load() {
  error.value = '';
  notice.value = '';
  accessRequired.value = false;
  try {
    contest.value = await apiRequest<Contest>(`/contests/${route.params.id}`);
    announcements.value = await apiRequest<ContestAnnouncement[]>(`/contests/${route.params.id}/announcements`);
    try {
      problems.value = await apiRequest<ContestProblemDetail[]>(`/contests/${route.params.id}/problems`);
    } catch (err) {
      problems.value = [];
      if (!canRegister.value) {
        throw err;
      }
    }
  } catch (err) {
    if (err instanceof ApiError && err.status === 403) {
      accessRequired.value = true;
      contest.value = null;
      announcements.value = [];
      problems.value = [];
      error.value = '';
      return;
    }
    error.value = err instanceof Error ? err.message : '比赛加载失败';
  }
}

async function unlockContest() {
  unlocking.value = true;
  error.value = '';
  notice.value = '';
  try {
    await apiRequest<ContestAccessResponse>(`/contests/${route.params.id}/access`, {
      method: 'POST',
      body: JSON.stringify({ code: accessCode.value.trim() || undefined }),
    });
    accessCode.value = '';
    await load();
  } catch (err) {
    error.value = err instanceof Error ? err.message : '访问验证失败';
  } finally {
    unlocking.value = false;
  }
}

async function registerContest() {
  if (!contest.value) return;
  registering.value = true;
  error.value = '';
  notice.value = '';
  try {
    const result = await apiRequest<ContestRegistrationResponse>(`/contests/${contest.value.id}/register`, { method: 'POST' });
    contest.value = result.contest;
    notice.value = contest.value.participation_mode === 'team' ? '已完成队伍报名。' : '已完成个人报名。';
    announcements.value = await apiRequest<ContestAnnouncement[]>(`/contests/${route.params.id}/announcements`);
    problems.value = await apiRequest<ContestProblemDetail[]>(`/contests/${route.params.id}/problems`);
  } catch (err) {
    error.value = err instanceof Error ? err.message : '报名失败';
  } finally {
    registering.value = false;
  }
}

async function openProblem(problem: ContestProblemDetail) {
  await router.push(`/contests/${route.params.id}/p/${encodeURIComponent(problem.problem_key || problem.id)}`);
}

async function openStandings() {
  await router.push(`/contests/${route.params.id}/standings`);
}

async function openExternalBoard() {
  await router.push(`/contests/${route.params.id}/external-board`);
}

async function openLiveBoard() {
  await router.push(`/contests/${route.params.id}/live-board`);
}

async function openClarifications() {
  await router.push(`/contests/${route.params.id}/clar`);
}

async function openPrintDesk() {
  await router.push(`/contests/${route.params.id}/print`);
}

onMounted(load);
</script>

<template>
  <div class="page-stack">
    <section class="page-heading">
      <div>
        <span class="eyebrow">Contest</span>
        <h1>{{ contest?.title || '比赛详情' }}</h1>
        <p v-if="contest" class="contest-subtitle">
          {{ contest.rule }} · {{ formatDate(contest.start_at) }} - {{ formatDate(contest.end_at) }}
        </p>
      </div>
      <div class="heading-meta">
        <StatusBadge v-if="contest" :status="contest.freeze_active ? 'disabled' : contest.status" />
      </div>
    </section>

    <p v-if="error" class="form-error">{{ error }}</p>
    <p v-if="notice" class="form-success">{{ notice }}</p>

    <section v-if="accessRequired" class="panel contest-access-panel">
      <div class="contest-access-copy">
        <KeyRound :size="20" />
        <div>
          <h2>需要访问权限</h2>
          <p>请输入比赛口令或邀请码。</p>
        </div>
      </div>
      <form class="inline-form contest-access-form" @submit.prevent="unlockContest">
        <input v-model="accessCode" type="password" autocomplete="current-password" placeholder="访问凭据" />
        <button class="primary-action" type="submit" :disabled="unlocking">
          <RefreshCw v-if="unlocking" :size="16" class="spin" />
          <KeyRound v-else :size="16" />
          解锁
        </button>
      </form>
    </section>

    <section v-if="contest" class="contest-home-layout">
      <article class="panel contest-home-main">
        <div class="contest-home-toolbar">
          <div class="contest-home-toolbar-copy">
            <h2>比赛题目</h2>
            <p>按比赛顺序查看题面，提交代码或作答客观题。</p>
          </div>
          <div class="row-actions">
            <button v-if="canRegister" class="primary-action" type="button" :disabled="registering || contest.roster_locked" @click="registerContest">
              <UserPlus :size="16" />报名
            </button>
            <button class="secondary-action" type="button" @click="openStandings">
              <Trophy :size="16" />榜单
            </button>
            <button class="secondary-action" type="button" @click="openExternalBoard">
              <Rows3 :size="16" />外榜
            </button>
            <button class="secondary-action" type="button" @click="openLiveBoard">
              <Radio :size="16" />实时外榜
            </button>
            <button class="secondary-action" type="button" :disabled="!canUseContestTools" @click="openClarifications">
              <MessageSquare :size="16" />Clarification
            </button>
            <button class="secondary-action" type="button" :disabled="!canOpenPrintDesk" @click="openPrintDesk">
              <Printer :size="16" />打印台
            </button>
          </div>
        </div>

        <div class="contest-problem-list">
          <article v-for="problem in problems" :key="problem.id" class="contest-problem-card">
            <div class="contest-problem-card-main">
              <div class="contest-problem-badge">{{ problem.problem_key }}</div>
              <div class="contest-problem-copy">
                <div class="contest-problem-title">
                  <strong>{{ problem.title }}</strong>
                  <span>{{ problem.score }} 分</span>
                </div>
                <div class="contest-problem-meta">
                  <span><ProblemTypeIcon :type="problem.type" />{{ problemTypeLabel(problem.type) }}</span>
                  <span>{{ problem.difficulty }}</span>
                  <span>{{ problemAttemptSummary(problem) }}</span>
                  <span v-if="problem.type === 'code'">{{ allowedLanguageText(problem) }}</span>
                </div>
                <p class="contest-problem-tags">
                  <span v-for="tag in problem.tags" :key="tag">{{ tag }}</span>
                </p>
              </div>
            </div>
            <button class="secondary-action" type="button" @click="openProblem(problem)">
              <ArrowRight :size="16" />进入
            </button>
          </article>
          <p v-if="problems.length === 0" class="empty-text">当前比赛没有可见题目。</p>
        </div>
      </article>

      <aside class="panel contest-home-side">
        <section class="contest-announcement-panel">
          <div class="contest-side-head">
            <h2>比赛公告</h2>
            <span>{{ announcements.length }}</span>
          </div>
          <div class="contest-announcement-list">
            <article v-for="item in announcements" :key="item.id" class="contest-announcement-card">
              <div class="contest-announcement-title">
                <Bell :size="15" />
                <strong>{{ item.title }}</strong>
              </div>
              <p>{{ item.content }}</p>
              <small>{{ item.created_by_name }} · {{ formatDate(item.created_at) }}</small>
            </article>
            <p v-if="announcements.length === 0" class="empty-text">当前比赛暂无公告。</p>
          </div>
        </section>

        <section class="contest-home-info">
          <h2>比赛信息</h2>
          <div class="contest-home-facts">
            <div class="contest-home-fact">
              <small>赛制</small>
              <strong>{{ contest.rule }}</strong>
            </div>
            <div class="contest-home-fact">
              <small>题量</small>
              <strong>{{ problems.length }}</strong>
            </div>
            <div class="contest-home-fact">
              <small>状态</small>
              <strong>{{ contest.freeze_active ? '封榜中' : contest.status }}</strong>
            </div>
            <div class="contest-home-fact">
              <small>参赛</small>
              <strong>{{ participationLabel(contest.participation_mode) }}</strong>
            </div>
            <div class="contest-home-fact">
              <small>名单</small>
              <strong>{{ contest.participant_user_count }}</strong>
            </div>
          </div>
          <div class="contest-home-notes">
            <p><FileCode2 :size="16" />代码题统一进入在线评测队列。</p>
            <p><FileQuestion :size="16" />客观题在比赛内即时判分。</p>
            <p v-if="contest.participation_mode !== 'open'"><UserPlus :size="16" />{{ contest.self_registered ? '当前账号已在参赛名单内。' : '报名后才能查看题面、提交、提问和打印。' }}</p>
          </div>
        </section>
      </aside>
    </section>
  </div>
</template>
