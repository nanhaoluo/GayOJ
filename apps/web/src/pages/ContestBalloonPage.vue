<script setup lang="ts">
import { ArrowLeft, Gift, RefreshCw, Undo2 } from 'lucide-vue-next';
import { computed, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import StatusBadge from '@/components/StatusBadge.vue';
import { apiRequest, formatDate } from '@/services/api';
import type { ContestBalloon } from '@/services/types';

const route = useRoute();
const router = useRouter();
const data = ref<ContestBalloon[]>([]);
const error = ref('');
const updatingId = ref('');

const pending = computed(() => data.value.filter((item) => !item.released));
const released = computed(() => data.value.filter((item) => item.released));

function balloonProblemTitle(item: ContestBalloon): string {
  return `${item.problem_key || item.problem_id} · ${item.problem_title}`;
}

async function load() {
  error.value = '';
  try {
    data.value = await apiRequest<ContestBalloon[]>(`/contests/${route.params.id}/balloons`);
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败';
  }
}

async function setReleased(item: ContestBalloon, releasedState: boolean) {
  updatingId.value = item.submission_id;
  error.value = '';
  try {
    const updated = await apiRequest<ContestBalloon>(`/contests/${route.params.id}/balloons/${item.submission_id}`, {
      method: 'PATCH',
      body: JSON.stringify({
        submission_id: item.submission_id,
        released: releasedState,
      }),
    });
    data.value = data.value.map((current) => (current.submission_id === updated.submission_id ? updated : current));
  } catch (err) {
    error.value = err instanceof Error ? err.message : '更新失败';
  } finally {
    updatingId.value = '';
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
    <section class="pure-content balloon-page">
      <div class="pure-heading">
        <h1>气球台</h1>
        <p>仅展示 ACM 比赛首个通过的待发与已发记录</p>
      </div>

      <p v-if="error" class="form-error">{{ error }}</p>

      <section class="balloon-section">
        <div class="balloon-section-head">
          <h2>待发放</h2>
          <span>{{ pending.length }}</span>
        </div>
        <div v-if="pending.length" class="list-stack balloon-list">
          <article v-for="item in pending" :key="item.submission_id" class="balloon-card">
            <div class="balloon-card-main">
              <div class="balloon-card-title">
                <strong>{{ item.display_name }}</strong>
                <span>{{ balloonProblemTitle(item) }}</span>
              </div>
              <div class="balloon-card-meta">
                <StatusBadge :status="item.status" />
                <span v-if="item.first_ac" class="balloon-chip">First Blood</span>
                <span>{{ formatDate(item.judged_at) }}</span>
              </div>
            </div>
            <div class="balloon-card-actions">
              <button class="primary-action" type="button" :disabled="updatingId === item.submission_id" @click="setReleased(item, true)">
                <Gift :size="16" />发放
              </button>
            </div>
          </article>
        </div>
        <p v-else class="balloon-empty">当前没有待发放气球。</p>
      </section>

      <section class="balloon-section">
        <div class="balloon-section-head">
          <h2>已发放</h2>
          <span>{{ released.length }}</span>
        </div>
        <div v-if="released.length" class="list-stack balloon-list">
          <article v-for="item in released" :key="item.submission_id" class="balloon-card released">
            <div class="balloon-card-main">
              <div class="balloon-card-title">
                <strong>{{ item.display_name }}</strong>
                <span>{{ balloonProblemTitle(item) }}</span>
              </div>
              <div class="balloon-card-meta">
                <StatusBadge status="completed" />
                <span v-if="item.first_ac" class="balloon-chip">First Blood</span>
                <span>{{ formatDate(item.released_at || item.judged_at) }}</span>
              </div>
            </div>
            <div class="balloon-card-actions">
              <button class="secondary-action" type="button" :disabled="updatingId === item.submission_id" @click="setReleased(item, false)">
                <Undo2 :size="16" />撤销
              </button>
            </div>
          </article>
        </div>
        <p v-else class="balloon-empty">当前还没有已发放记录。</p>
      </section>
    </section>
  </div>
</template>
