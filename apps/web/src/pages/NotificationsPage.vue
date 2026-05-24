<script setup lang="ts">
import { Bell, CheckCheck } from 'lucide-vue-next';
import { onMounted, ref } from 'vue';
import { apiRequest, formatDate } from '@/services/api';
import type { NotificationItem } from '@/services/types';

const notifications = ref<NotificationItem[]>([]);
const error = ref('');

async function load() {
  error.value = '';
  try {
    notifications.value = await apiRequest<NotificationItem[]>('/notifications');
  } catch (err) {
    error.value = err instanceof Error ? err.message : '请先登录后查看通知。';
  }
}

async function markRead(item: NotificationItem) {
  await apiRequest<NotificationItem>(`/notifications/${item.id}/read`, { method: 'PATCH' });
  await load();
}

onMounted(load);
</script>

<template>
  <div class="page-stack">
    <section class="page-heading">
      <div>
        <span class="eyebrow">Notifications</span>
        <h1>通知中心</h1>
      </div>
    </section>

    <p v-if="error" class="form-error">{{ error }}</p>

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
