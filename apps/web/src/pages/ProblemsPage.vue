<script setup lang="ts">
import { Search, X } from 'lucide-vue-next';
import { computed, onMounted, ref, watch } from 'vue';
import { RouterLink } from 'vue-router';
import BaseModal from '@/components/BaseModal.vue';
import ProblemTypeIcon from '@/components/ProblemTypeIcon.vue';
import { apiRequest, problemTypeLabel } from '@/services/api';
import type { ProblemSummary, TagTreeNode } from '@/services/types';

interface FlatTag {
  tag: TagTreeNode;
  depth: number;
}

const problems = ref<ProblemSummary[]>([]);
const tagTree = ref<TagTreeNode[]>([]);
const selectedTags = ref<string[]>([]);
const q = ref('');
const type = ref('');
const loading = ref(false);
const error = ref('');
const filtersOpen = ref(false);

function flattenTags(items: TagTreeNode[], depth = 0): FlatTag[] {
  return items.flatMap((tag) => [{ tag, depth }, ...flattenTags(tag.children, depth + 1)]);
}

const flatTags = computed(() => flattenTags(tagTree.value));

function toggleTag(name: string) {
  const index = selectedTags.value.indexOf(name);
  if (index >= 0) selectedTags.value.splice(index, 1);
  else selectedTags.value.push(name);
}

function clearFilters() {
  q.value = '';
  type.value = '';
  selectedTags.value = [];
}

function problemQueryPath(): string {
  const params = new URLSearchParams();
  if (q.value.trim()) params.set('q', q.value.trim());
  if (type.value) params.set('type', type.value);
  for (const tag of selectedTags.value) params.append('tag', tag);
  const query = params.toString();
  return query ? `/problems?${query}` : '/problems';
}

async function load() {
  loading.value = true;
  error.value = '';
  try {
    problems.value = await apiRequest<ProblemSummary[]>(problemQueryPath(), { auth: false });
  } catch (err) {
    error.value = err instanceof Error ? err.message : '题库加载失败。';
  } finally {
    loading.value = false;
  }
}

async function loadTags() {
  tagTree.value = await apiRequest<TagTreeNode[]>('/tags', { auth: false });
}

watch([q, type, () => selectedTags.value.join('|')], () => {
  void load();
});

onMounted(() => {
  void loadTags();
  void load();
});
</script>

<template>
  <div class="page-stack">
    <section class="page-heading">
      <div>
        <span class="eyebrow">Problem Bank</span>
        <h1>题库</h1>
      </div>
      <button class="secondary-action" type="button" @click="filtersOpen = true">
        <Search :size="16" />知识点
      </button>
    </section>

    <section class="toolbar-panel">
      <label class="search-box">
        <Search :size="18" />
        <input v-model="q" placeholder="搜索题号、标题或标签" />
      </label>
      <div class="segmented">
        <button :class="{ active: type === '' }" @click="type = ''">全部</button>
        <button :class="{ active: type === 'code' }" @click="type = 'code'">代码</button>
        <button :class="{ active: type === 'blank' }" @click="type = 'blank'">填空</button>
        <button :class="{ active: type === 'single_choice' }" @click="type = 'single_choice'">单选</button>
        <button :class="{ active: type === 'multiple_choice' }" @click="type = 'multiple_choice'">多选</button>
      </div>
    </section>

    <section v-if="selectedTags.length" class="summary-strip">
      <span>已选 {{ selectedTags.length }} 个知识点</span>
      <button class="text-link" type="button" @click="clearFilters">
        <X :size="15" />清除
      </button>
    </section>

    <p v-if="error" class="form-error">{{ error }}</p>

    <section class="problem-table panel">
      <RouterLink v-for="problem in problems" :key="problem.id" :to="`/problems/${problem.id}`" class="problem-row">
        <ProblemTypeIcon :type="problem.type" />
        <div class="problem-main">
          <strong>{{ problem.id }} · {{ problem.title }}</strong>
          <span>{{ problem.tags.join(' / ') || '未分类' }}</span>
        </div>
        <span class="difficulty">{{ problem.difficulty }}</span>
        <span>{{ problemTypeLabel(problem.type) }}</span>
        <span>{{ problem.accepted }}/{{ problem.attempts }}</span>
      </RouterLink>
      <p v-if="!problems.length && !loading" class="empty-text">没有匹配的题目。</p>
    </section>

    <BaseModal
      :open="filtersOpen"
      title="知识点筛选"
      :description="selectedTags.length ? `已选 ${selectedTags.length} 个标签` : '全部标签'"
      size="lg"
      @close="filtersOpen = false"
    >
      <div class="modal-action-row">
        <button v-if="q || type || selectedTags.length" class="secondary-action" type="button" @click="clearFilters">
          <X :size="16" />清除
        </button>
      </div>
      <div class="tag-filter-grid">
        <label
          v-for="item in flatTags"
          :key="item.tag.id"
          class="tag-filter-option"
          :style="{ paddingLeft: `${10 + item.depth * 18}px` }"
        >
          <input
            type="checkbox"
            :checked="selectedTags.includes(item.tag.name)"
            @change="toggleTag(item.tag.name)"
          />
          <span>{{ item.tag.name }}</span>
        </label>
      </div>
    </BaseModal>
  </div>
</template>
