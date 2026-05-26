<script setup lang="ts">
import { ChevronLeft, ChevronRight, MessageSquarePlus, Search, Send } from 'lucide-vue-next';
import { onMounted, reactive, ref } from 'vue';
import { apiRequest, formatDate } from '@/services/api';
import type { Discussion, DiscussionListResponse } from '@/services/types';

const discussions = ref<Discussion[]>([]);
const selected = ref<Discussion | null>(null);
const error = ref('');
const loading = ref(false);
const formOpen = ref(false);
const form = reactive({
  type: 'general',
  target_id: '',
  title: '',
  content: '',
});
const reply = ref('');
const filters = reactive({
  type: '',
  q: '',
  limit: 10,
  offset: 0,
});
const total = ref(0);

async function load() {
  loading.value = true;
  error.value = '';
  try {
    const params = new URLSearchParams({
      limit: String(filters.limit),
      offset: String(filters.offset),
    });
    if (filters.type) params.set('type', filters.type);
    if (filters.q.trim()) params.set('q', filters.q.trim());
    const payload = await apiRequest<DiscussionListResponse>(`/discussions?${params.toString()}`, { auth: false });
    discussions.value = payload.items;
    total.value = payload.total;
    selected.value = selected.value ? discussions.value.find((item) => item.id === selected.value?.id) ?? null : discussions.value[0] ?? null;
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载讨论失败。';
  } finally {
    loading.value = false;
  }
}

async function applyFilters() {
  filters.offset = 0;
  await load();
}

async function page(delta: number) {
  const next = filters.offset + delta * filters.limit;
  if (next < 0 || next >= total.value) return;
  filters.offset = next;
  await load();
}

async function createDiscussion() {
  error.value = '';
  try {
    await apiRequest<Discussion>('/discussions', {
      method: 'POST',
      body: JSON.stringify({
        ...form,
        target_id: form.target_id || null,
      }),
    });
    form.title = '';
    form.content = '';
    form.target_id = '';
    formOpen.value = false;
    await load();
  } catch (err) {
    error.value = err instanceof Error ? err.message : '发布失败，请先登录。';
  }
}

async function sendReply() {
  if (!selected.value || !reply.value.trim()) return;
  error.value = '';
  try {
    selected.value = await apiRequest<Discussion>(`/discussions/${selected.value.id}/replies`, {
      method: 'POST',
      body: JSON.stringify({ content: reply.value }),
    });
    reply.value = '';
    await load();
  } catch (err) {
    error.value = err instanceof Error ? err.message : '回复失败，请先登录。';
  }
}

onMounted(load);
</script>

<template>
  <div class="page-stack">
    <section class="page-heading">
      <div>
        <span class="eyebrow">Discuss</span>
        <h1>讨论区与题解</h1>
      </div>
      <button class="primary-action" @click="formOpen = !formOpen"><MessageSquarePlus :size="18" />发布</button>
    </section>

    <section class="toolbar-panel discussion-filter-panel">
      <form class="discussion-filter" @submit.prevent="applyFilters">
        <label>
          <span>类型</span>
          <select v-model="filters.type">
            <option value="">全部</option>
            <option value="general">综合讨论</option>
            <option value="problem">题目讨论</option>
            <option value="contest">比赛讨论</option>
            <option value="solution">题解</option>
          </select>
        </label>
        <label>
          <span>搜索</span>
          <input v-model="filters.q" placeholder="标题、作者、内容" />
        </label>
        <button class="secondary-action" type="submit"><Search :size="16" />搜索</button>
      </form>
      <div class="discussion-pager">
        <span>{{ total }} 条</span>
        <button class="icon-button" type="button" :disabled="filters.offset === 0" aria-label="上一页" @click="page(-1)">
          <ChevronLeft :size="17" />
        </button>
        <button class="icon-button" type="button" :disabled="filters.offset + filters.limit >= total" aria-label="下一页" @click="page(1)">
          <ChevronRight :size="17" />
        </button>
      </div>
    </section>

    <section v-if="formOpen" class="panel form-panel">
      <form class="submit-form" @submit.prevent="createDiscussion">
        <label>标题<input v-model="form.title" required placeholder="讨论标题" /></label>
        <label>
          类型
          <select v-model="form.type">
            <option value="general">综合讨论</option>
            <option value="problem">题目讨论</option>
            <option value="contest">比赛讨论</option>
            <option value="solution">题解</option>
          </select>
        </label>
        <label>关联对象<input v-model="form.target_id" placeholder="例如 P1001 或 C1001，可留空" /></label>
        <label>内容<textarea v-model="form.content" rows="5" required placeholder="支持 Markdown 风格文本"></textarea></label>
        <button class="primary-action full" type="submit"><Send :size="18" />提交</button>
      </form>
      <p v-if="error" class="form-error">{{ error }}</p>
    </section>

    <p v-if="error && !formOpen" class="form-error">{{ error }}</p>

    <section class="discuss-layout">
      <aside class="panel discuss-list">
        <p v-if="loading" class="empty-text">加载中。</p>
        <button
          v-for="item in discussions"
          :key="item.id"
          class="discussion-list-item"
          :class="{ active: selected?.id === item.id }"
          @click="selected = item"
        >
          <strong>{{ item.title }}</strong>
          <span>{{ item.author_name }} · {{ item.type }} · {{ formatDate(item.updated_at) }}</span>
        </button>
        <p v-if="!loading && discussions.length === 0" class="empty-text">暂无匹配讨论。</p>
      </aside>

      <article v-if="selected" class="panel discussion-detail">
        <div class="panel-head">
          <div>
            <h2>{{ selected.title }}</h2>
            <p>{{ selected.author_name }} · {{ selected.type }} · {{ selected.target_id || '未关联' }}</p>
          </div>
          <span class="difficulty">{{ selected.likes }} likes</span>
        </div>
        <p class="discussion-body">{{ selected.content }}</p>

        <h3>回复</h3>
        <div class="list-stack">
          <div v-for="item in selected.replies" :key="String(item.id)" class="reply-row">
            <strong>{{ item.author_name }}</strong>
            <p>{{ item.content }}</p>
            <span>{{ formatDate(String(item.created_at)) }}</span>
          </div>
          <p v-if="!selected.replies.length" class="empty-text">暂无回复。</p>
        </div>

        <form class="reply-form" @submit.prevent="sendReply">
          <input v-model="reply" placeholder="写一条回复" />
          <button class="primary-action" type="submit"><Send :size="17" />回复</button>
        </form>
      </article>
    </section>
  </div>
</template>
