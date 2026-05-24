<script setup lang="ts">
import { GitBranch, Loader2, Plus, RefreshCw, Save, Tags, Trash2 } from 'lucide-vue-next';
import { computed, onMounted, reactive, ref } from 'vue';
import { apiRequest } from '@/services/api';
import type { Tag, TagFormPayload, TagTreeNode } from '@/services/types';

interface FlatTag {
  tag: TagTreeNode;
  depth: number;
}

const tags = ref<Tag[]>([]);
const tree = ref<TagTreeNode[]>([]);
const selectedId = ref('');
const loading = ref(false);
const saving = ref(false);
const deletingId = ref('');
const error = ref('');
const notice = ref('');

const form = reactive({
  name: '',
  parent_id: '',
  sort_order: 0,
});

function flattenTags(items: TagTreeNode[], depth = 0): FlatTag[] {
  return items.flatMap((tag) => [{ tag, depth }, ...flattenTags(tag.children, depth + 1)]);
}

const flatTree = computed(() => flattenTags(tree.value));
const mode = computed(() => (selectedId.value ? 'edit' : 'create'));
const selectedTag = computed(() => tags.value.find((tag) => tag.id === selectedId.value) ?? null);
const parentOptions = computed(() => tags.value.filter((tag) => tag.id !== selectedId.value));

function resetForm() {
  selectedId.value = '';
  form.name = '';
  form.parent_id = '';
  form.sort_order = 0;
  error.value = '';
  notice.value = '';
}

function editTag(tag: Tag) {
  selectedId.value = tag.id;
  form.name = tag.name;
  form.parent_id = tag.parent_id ?? '';
  form.sort_order = tag.sort_order;
  error.value = '';
  notice.value = '';
}

function payload(): TagFormPayload {
  return {
    name: form.name.trim(),
    parent_id: form.parent_id || null,
    sort_order: Number(form.sort_order || 0),
  };
}

async function loadTags() {
  loading.value = true;
  error.value = '';
  try {
    const [flat, nested] = await Promise.all([
      apiRequest<Tag[]>('/admin/tags'),
      apiRequest<TagTreeNode[]>('/tags', { auth: false }),
    ]);
    tags.value = flat;
    tree.value = nested;
    if (selectedId.value) {
      const selected = flat.find((tag) => tag.id === selectedId.value);
      if (selected) editTag(selected);
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : '标签数据加载失败。';
  } finally {
    loading.value = false;
  }
}

async function saveTag() {
  saving.value = true;
  error.value = '';
  notice.value = '';
  try {
    const path = mode.value === 'edit' ? `/admin/tags/${selectedId.value}` : '/admin/tags';
    const method = mode.value === 'edit' ? 'PUT' : 'POST';
    const saved = await apiRequest<Tag>(path, {
      method,
      body: JSON.stringify(payload()),
    });
    selectedId.value = saved.id;
    notice.value = `${saved.name} 已保存。`;
    await loadTags();
  } catch (err) {
    error.value = err instanceof Error ? err.message : '标签保存失败。';
  } finally {
    saving.value = false;
  }
}

async function deleteTag(tag: Tag) {
  if (!window.confirm(`确认删除 ${tag.name}？`)) return;
  deletingId.value = tag.id;
  error.value = '';
  notice.value = '';
  try {
    const deleted = await apiRequest<Tag>(`/admin/tags/${tag.id}`, { method: 'DELETE' });
    notice.value = `${deleted.name} 已删除。`;
    resetForm();
    await loadTags();
  } catch (err) {
    error.value = err instanceof Error ? err.message : '标签删除失败。';
  } finally {
    deletingId.value = '';
  }
}

onMounted(loadTags);
</script>

<template>
  <div class="page-stack">
    <section class="page-heading">
      <div>
        <span class="eyebrow">Knowledge Tags</span>
        <h1>知识点管理</h1>
      </div>
      <button class="secondary-action" type="button" @click="loadTags">
        <RefreshCw :size="16" />刷新
      </button>
    </section>

    <p v-if="error" class="form-error">{{ error }}</p>
    <p v-if="notice" class="form-success">{{ notice }}</p>

    <section class="tag-manager-layout">
      <aside class="panel tag-tree-panel">
        <div class="panel-head">
          <div>
            <h2>标签树</h2>
            <p>{{ tags.length }} 个知识点</p>
          </div>
          <button class="secondary-action" type="button" @click="resetForm">
            <Plus :size="16" />新建
          </button>
        </div>

        <div class="tag-tree-list">
          <button
            v-for="item in flatTree"
            :key="item.tag.id"
            class="tag-tree-row"
            :class="{ active: selectedId === item.tag.id }"
            type="button"
            :style="{ paddingLeft: `${12 + item.depth * 18}px` }"
            @click="editTag(item.tag)"
          >
            <GitBranch :size="16" />
            <span>
              <strong>{{ item.tag.name }}</strong>
              <em>{{ item.tag.slug }}</em>
            </span>
          </button>
          <p v-if="loading" class="empty-state"><Loader2 :size="16" class="spin" /> 正在加载</p>
          <p v-if="!loading && flatTree.length === 0" class="empty-state">暂无标签。</p>
        </div>
      </aside>

      <section class="panel form-panel">
        <div class="panel-head">
          <div>
            <h2>{{ mode === 'edit' ? '编辑知识点' : '新建知识点' }}</h2>
            <p>{{ selectedId || '未分配编号' }}</p>
          </div>
          <Tags :size="22" />
        </div>

        <form class="submit-form" @submit.prevent="saveTag">
          <label>名称<input v-model="form.name" required maxlength="64" /></label>
          <label>父级
            <select v-model="form.parent_id">
              <option value="">无父级</option>
              <option v-for="tag in parentOptions" :key="tag.id" :value="tag.id">{{ tag.name }}</option>
            </select>
          </label>
          <label>排序<input v-model.number="form.sort_order" type="number" /></label>

          <div class="inline-actions">
            <button class="primary-action" type="submit" :disabled="saving">
              <Loader2 v-if="saving" :size="17" class="spin" />
              <Save v-else :size="17" />
              保存
            </button>
            <button class="secondary-action" type="button" @click="resetForm">
              <Plus :size="16" />清空
            </button>
            <button
              v-if="selectedTag"
              class="secondary-action danger-action"
              type="button"
              :disabled="deletingId === selectedId"
              @click="deleteTag(selectedTag)"
            >
              <Loader2 v-if="deletingId === selectedId" :size="16" class="spin" />
              <Trash2 v-else :size="16" />
              删除
            </button>
          </div>
        </form>
      </section>
    </section>
  </div>
</template>
