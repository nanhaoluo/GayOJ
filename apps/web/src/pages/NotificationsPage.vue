<script setup lang="ts">
import { Bell, CheckCheck, RefreshCw, Radio } from 'lucide-vue-next';
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { apiRequest, apiStreamUrl, formatDate, getStoredAuthToken } from '@/services/api';
import { authState } from '@/stores/auth';
import type { NotificationItem, NotificationStreamEvent } from '@/services/types';

const notifications = ref<NotificationItem[]>([]);
const error = ref('');
const streamStatus = ref<'idle' | 'connecting' | 'live' | 'fallback'>('idle');
const streamMessage = ref('未连接');
const unreadCount = ref(0);
let source: EventSource | null = null;
let reconnectTimer: number | undefined;
let fallbackTimer: number | undefined;

const streamText = computed(() => {
  const labels = {
    idle: '未连接',
    connecting: '连接中',
    live: '实时推送',
    fallback: '轮询回退',
  };
  return labels[streamStatus.value];
});

function clearTimers() {
  if (reconnectTimer) window.clearTimeout(reconnectTimer);
  if (fallbackTimer) window.clearInterval(fallbackTimer);
  reconnectTimer = undefined;
  fallbackTimer = undefined;
}

function closeStream() {
  if (source) source.close();
  source = null;
}

async function load() {
  error.value = '';
  try {
    notifications.value = await apiRequest<NotificationItem[]>('/notifications');
    unreadCount.value = notifications.value.filter((item) => !item.is_read).length;
  } catch (err) {
    error.value = err instanceof Error ? err.message : '请先登录后查看通知。';
  }
}

async function markRead(item: NotificationItem) {
  await apiRequest<NotificationItem>(`/notifications/${item.id}/read`, { method: 'PATCH' });
  await load();
}

function scheduleFallback() {
  streamStatus.value = 'fallback';
  streamMessage.value = '实时连接断开，已切换为定时刷新。';
  if (!fallbackTimer) {
    fallbackTimer = window.setInterval(() => {
      void load();
    }, 12000);
  }
  if (!reconnectTimer) {
    reconnectTimer = window.setTimeout(() => {
      reconnectTimer = undefined;
      connectStream();
    }, 5000);
  }
}

function connectStream() {
  clearTimers();
  closeStream();
  if (!authState.user || !getStoredAuthToken()) {
    streamStatus.value = 'idle';
    streamMessage.value = '登录后接收通知推送。';
    return;
  }
  streamStatus.value = 'connecting';
  streamMessage.value = '正在连接通知推送。';
  source = new EventSource(apiStreamUrl('/notifications/stream'));
  source.onopen = () => {
    streamStatus.value = 'live';
    streamMessage.value = '通知会自动更新。';
  };
  source.onmessage = (event) => {
    const payload = JSON.parse(event.data) as NotificationStreamEvent;
    unreadCount.value = payload.unread_count;
    if (payload.event !== 'heartbeat') void load();
  };
  source.addEventListener('snapshot', (event) => {
    const payload = JSON.parse((event as MessageEvent).data) as NotificationStreamEvent;
    unreadCount.value = payload.unread_count;
    void load();
  });
  source.addEventListener('update', (event) => {
    const payload = JSON.parse((event as MessageEvent).data) as NotificationStreamEvent;
    unreadCount.value = payload.unread_count;
    void load();
  });
  source.onerror = () => {
    closeStream();
    scheduleFallback();
  };
}

onMounted(() => {
  void load();
  connectStream();
});

onBeforeUnmount(() => {
  clearTimers();
  closeStream();
});

watch(
  () => authState.user?.id,
  () => {
    void load();
    connectStream();
  },
);
</script>

<template>
  <div class="page-stack">
    <section class="page-heading">
      <div>
        <span class="eyebrow">Notifications</span>
        <h1>通知中心</h1>
      </div>
      <button class="secondary-action" type="button" @click="load">
        <RefreshCw :size="17" />刷新
      </button>
    </section>

    <p v-if="error" class="form-error">{{ error }}</p>

    <section class="notification-status-panel" :class="`stream-${streamStatus}`">
      <div>
        <Radio :size="17" />
        <span>{{ streamText }}</span>
        <b>{{ unreadCount }} 条未读</b>
      </div>
      <p>{{ streamMessage }}</p>
    </section>

    <section class="panel notification-list">
      <div v-for="item in notifications" :key="item.id" class="notification-row" :class="{ unread: !item.is_read }">
        <Bell :size="18" />
        <div>
          <strong>{{ item.title }}</strong>
          <p>{{ item.content }}</p>
          <span>{{ item.type }} · {{ formatDate(item.created_at) }}</span>
        </div>
        <button v-if="!item.is_read" class="secondary-action" @click="markRead(item)">
          <CheckCheck :size="17" />
          已读
        </button>
      </div>
      <p v-if="!notifications.length && !error" class="empty-text">暂无通知。</p>
    </section>
  </div>
</template>
