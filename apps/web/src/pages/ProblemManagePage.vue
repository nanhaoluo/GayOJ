<script setup lang="ts">
import { Download, Eye, EyeOff, History, Loader2, Plus, RefreshCw, RotateCcw, Save, Search, Trash2, Upload } from 'lucide-vue-next';
import { computed, onMounted, reactive, ref } from 'vue';
import ProblemTypeIcon from '@/components/ProblemTypeIcon.vue';
import { API_BASE, apiRequest, formatDate, getStoredAuthToken, problemTypeLabel } from '@/services/api';
import type {
  ProblemAdminDetail,
  ProblemExportResponse,
  ProblemFormPayload,
  ProblemImportConflictStrategy,
  ProblemImportResponse,
  ProblemPackageFormat,
  ProblemTestData,
  ProblemType,
  ProblemVersion,
  TagTreeNode,
} from '@/services/types';

type Difficulty = ProblemFormPayload['difficulty'];

interface BlankRow {
  key: string;
  label: string;
  score: number;
  answersText: string;
}

interface FlatTag {
  tag: TagTreeNode;
  depth: number;
}

const problems = ref<ProblemAdminDetail[]>([]);
const tagTree = ref<TagTreeNode[]>([]);
const versions = ref<ProblemVersion[]>([]);
const selectedId = ref('');
const mode = ref<'create' | 'edit'>('create');
const loading = ref(false);
const versionLoading = ref(false);
const versionRestoringId = ref('');
const saving = ref(false);
const error = ref('');
const notice = ref('');
const search = ref('');
const ioFormat = ref<ProblemPackageFormat>('hydro');
const importStrategy = ref<ProblemImportConflictStrategy>('create_new');
const importContent = ref('');
const importResult = ref<ProblemImportResponse | null>(null);
const exporting = ref(false);
const importing = ref(false);
const uploadingTestData = ref(false);
const testDataFile = ref<File | null>(null);
const testDataInput = ref<HTMLInputElement | null>(null);

const form = reactive({
  title: '',
  type: 'code' as ProblemType,
  difficulty: '基础' as Difficulty,
  tagsText: '',
  statement: '',
  input_format: '',
  output_format: '',
  samples: [{ input: '', output: '' }],
  options: [
    { key: 'A', text: '' },
    { key: 'B', text: '' },
    { key: 'C', text: '' },
    { key: 'D', text: '' },
  ],
  blankRows: [{ key: 'answer', label: '答案', score: 100, answersText: '' }] as BlankRow[],
  time_limit_ms: 1000 as number | null,
  memory_limit_mb: 128 as number | null,
  visible: true,
  case_sensitive: false,
  trim_space: true,
  singleAnswer: 'A',
  multipleAnswers: ['A'] as string[],
  objectiveScore: 100,
  codeJudgeConfigText: '{\n  "mode": "standard"\n}',
});

const typeOptions: Array<{ value: ProblemType; label: string }> = [
  { value: 'code', label: '代码题' },
  { value: 'blank', label: '填空题' },
  { value: 'single_choice', label: '单选题' },
  { value: 'multiple_choice', label: '多选题' },
];

const difficultyOptions: Difficulty[] = ['入门', '基础', '提高', '困难'];
const packageFormats: Array<{ value: ProblemPackageFormat; label: string }> = [
  { value: 'hydro', label: 'Hydro JSON' },
  { value: 'qdu', label: 'QDU JSON' },
  { value: 'fps', label: 'FPS XML' },
];
const importStrategies: Array<{ value: ProblemImportConflictStrategy; label: string }> = [
  { value: 'create_new', label: '新建副本' },
  { value: 'overwrite', label: '覆盖同号' },
  { value: 'skip', label: '跳过同号' },
];

function flattenTags(items: TagTreeNode[], depth = 0): FlatTag[] {
  return items.flatMap((tag) => [{ tag, depth }, ...flattenTags(tag.children, depth + 1)]);
}

const flatTags = computed(() => flattenTags(tagTree.value));
const filteredProblems = computed(() => {
  const query = search.value.trim().toLowerCase();
  if (!query) return problems.value;
  return problems.value.filter((problem) =>
    `${problem.id} ${problem.title} ${problem.tags.join(' ')}`.toLowerCase().includes(query),
  );
});
const selectedProblem = computed(() => problems.value.find((problem) => problem.id === selectedId.value) ?? null);
const selectedTestData = computed(() => selectedProblem.value?.test_data ?? null);

function normalizeRows<T extends Record<string, unknown>>(rows: T[], fallback: T): T[] {
  return rows.length ? rows.map((row) => ({ ...row })) : [{ ...fallback }];
}

function resetForm() {
  mode.value = 'create';
  selectedId.value = '';
  form.title = '';
  form.type = 'code';
  form.difficulty = '基础';
  form.tagsText = '';
  form.statement = '';
  form.input_format = '';
  form.output_format = '';
  form.samples = [{ input: '', output: '' }];
  form.options = [
    { key: 'A', text: '' },
    { key: 'B', text: '' },
    { key: 'C', text: '' },
    { key: 'D', text: '' },
  ];
  form.blankRows = [{ key: 'answer', label: '答案', score: 100, answersText: '' }];
  form.time_limit_ms = 1000;
  form.memory_limit_mb = 128;
  form.visible = true;
  form.case_sensitive = false;
  form.trim_space = true;
  form.singleAnswer = 'A';
  form.multipleAnswers = ['A'];
  form.objectiveScore = 100;
  form.codeJudgeConfigText = '{\n  "mode": "standard"\n}';
  notice.value = '';
  error.value = '';
  versions.value = [];
  testDataFile.value = null;
  if (testDataInput.value) testDataInput.value.value = '';
}

function setType(type: ProblemType) {
  form.type = type;
  if (type === 'code') {
    form.time_limit_ms = form.time_limit_ms ?? 1000;
    form.memory_limit_mb = form.memory_limit_mb ?? 128;
  }
  if (type === 'blank' && form.blankRows.length === 0) {
    form.blankRows = [{ key: 'answer', label: '答案', score: 100, answersText: '' }];
  }
  if ((type === 'single_choice' || type === 'multiple_choice') && form.options.length < 2) {
    form.options = [
      { key: 'A', text: '' },
      { key: 'B', text: '' },
    ];
  }
}

function editProblem(problem: ProblemAdminDetail) {
  mode.value = 'edit';
  selectedId.value = problem.id;
  form.title = problem.title;
  form.type = problem.type;
  form.difficulty = problem.difficulty as Difficulty;
  form.tagsText = problem.tags.join(', ');
  form.statement = problem.statement;
  form.input_format = problem.input_format;
  form.output_format = problem.output_format;
  form.samples = normalizeRows(problem.samples, { input: '', output: '' });
  form.options = normalizeRows(problem.options, { key: 'A', text: '' });
  form.time_limit_ms = problem.time_limit_ms;
  form.memory_limit_mb = problem.memory_limit_mb;
  form.visible = problem.visible;
  form.codeJudgeConfigText = JSON.stringify(problem.judge_config ?? {}, null, 2);

  const judgeConfig = problem.judge_config ?? {};
  form.case_sensitive = Boolean(judgeConfig.case_sensitive);
  form.trim_space = judgeConfig.trim_space !== false;
  form.objectiveScore = Number(judgeConfig.score ?? 100);
  form.singleAnswer = String(judgeConfig.answer ?? form.options[0]?.key ?? 'A');
  form.multipleAnswers = Array.isArray(judgeConfig.answer) ? judgeConfig.answer.map(String) : [];

  const answers = judgeConfig.answers && typeof judgeConfig.answers === 'object' ? judgeConfig.answers as Record<string, unknown> : {};
  const scores = judgeConfig.scores && typeof judgeConfig.scores === 'object' ? judgeConfig.scores as Record<string, unknown> : {};
  form.blankRows = normalizeRows(
    problem.blanks.map((blank) => {
      const key = String(blank.key);
      const answerValue = answers[key];
      return {
        key,
        label: blank.label,
        score: Number(scores[key] ?? blank.score ?? 100),
        answersText: Array.isArray(answerValue) ? answerValue.join('\n') : '',
      };
    }),
    { key: 'answer', label: '答案', score: 100, answersText: '' },
  );
  notice.value = '';
  error.value = '';
  testDataFile.value = null;
  if (testDataInput.value) testDataInput.value.value = '';
  void loadProblemVersions(problem.id);
}

function versionActionLabel(action: ProblemVersion['action']): string {
  const labels: Record<ProblemVersion['action'], string> = {
    update: '编辑前',
    delete: '下线前',
    restore: '回滚前',
  };
  return labels[action] ?? action;
}

function tagsFromText(): string[] {
  return form.tagsText
    .replaceAll('，', ',')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}

function setTags(tags: string[]) {
  form.tagsText = tags.join(', ');
}

function toggleTagChoice(name: string) {
  const current = tagsFromText();
  const index = current.indexOf(name);
  if (index >= 0) current.splice(index, 1);
  else current.push(name);
  setTags(current);
}

function cleanSamples(): Array<{ input: string; output: string }> {
  return form.samples
    .map((sample) => ({ input: sample.input.trim(), output: sample.output.trim() }))
    .filter((sample) => sample.input || sample.output);
}

function cleanOptions(): Array<{ key: string; text: string }> {
  return form.options
    .map((option) => ({ key: option.key.trim(), text: option.text.trim() }))
    .filter((option) => option.key && option.text);
}

function buildPayload(): ProblemFormPayload {
  const payload: ProblemFormPayload = {
    title: form.title.trim(),
    type: form.type,
    difficulty: form.difficulty,
    tags: tagsFromText(),
    statement: form.statement.trim(),
    input_format: form.type === 'code' ? form.input_format.trim() : '',
    output_format: form.type === 'code' ? form.output_format.trim() : '',
    samples: form.type === 'code' ? cleanSamples() : [],
    options: [],
    blanks: [],
    time_limit_ms: form.type === 'code' ? form.time_limit_ms : null,
    memory_limit_mb: form.type === 'code' ? form.memory_limit_mb : null,
    visible: form.visible,
    judge_config: {},
  };

  if (form.type === 'code') {
    try {
      payload.judge_config = form.codeJudgeConfigText.trim() ? JSON.parse(form.codeJudgeConfigText) : {};
    } catch {
      throw new Error('代码题在线评测配置不是有效 JSON。');
    }
    return payload;
  }

  if (form.type === 'blank') {
    const answers: Record<string, string[]> = {};
    const scores: Record<string, number> = {};
    payload.blanks = form.blankRows
      .map((blank) => ({
        key: blank.key.trim(),
        label: blank.label.trim(),
        score: Number(blank.score || 0),
      }))
      .filter((blank) => blank.key && blank.label);
    for (const blank of form.blankRows) {
      const key = blank.key.trim();
      if (!key) continue;
      answers[key] = blank.answersText
        .split('\n')
        .map((answer) => answer.trim())
        .filter(Boolean);
      scores[key] = Number(blank.score || 0);
    }
    payload.judge_config = {
      case_sensitive: form.case_sensitive,
      trim_space: form.trim_space,
      answers,
      scores,
    };
    return payload;
  }

  payload.options = cleanOptions();
  payload.judge_config = {
    answer: form.type === 'single_choice' ? form.singleAnswer : form.multipleAnswers,
    score: Number(form.objectiveScore || 0),
  };
  return payload;
}

function addSample() {
  form.samples.push({ input: '', output: '' });
}

function removeSample(index: number) {
  form.samples.splice(index, 1);
  if (form.samples.length === 0) addSample();
}

function addOption() {
  const nextKey = String.fromCharCode(65 + form.options.length);
  form.options.push({ key: nextKey, text: '' });
}

function removeOption(index: number) {
  const key = form.options[index]?.key;
  form.options.splice(index, 1);
  form.multipleAnswers = form.multipleAnswers.filter((answer) => answer !== key);
  if (form.singleAnswer === key) {
    form.singleAnswer = form.options[0]?.key ?? '';
  }
}

function addBlank() {
  form.blankRows.push({ key: `blank_${form.blankRows.length + 1}`, label: '答案', score: 100, answersText: '' });
}

function removeBlank(index: number) {
  form.blankRows.splice(index, 1);
  if (form.blankRows.length === 0) addBlank();
}

function toggleMultipleAnswer(key: string) {
  const index = form.multipleAnswers.indexOf(key);
  if (index >= 0) form.multipleAnswers.splice(index, 1);
  else form.multipleAnswers.push(key);
}

function importActionLabel(action: string): string {
  const labels: Record<string, string> = {
    created: '新建',
    updated: '覆盖',
    skipped: '跳过',
  };
  return labels[action] ?? action;
}

function downloadTextFile(filename: string, contentType: string, content: string) {
  const blob = new Blob([content], { type: `${contentType};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function formatBytes(value: number | null | undefined): string {
  const size = Number(value ?? 0);
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function selectTestDataFile(event: Event) {
  const input = event.target as HTMLInputElement;
  testDataFile.value = input.files?.[0] ?? null;
}

async function uploadProblemTestData() {
  if (!selectedProblem.value || !testDataFile.value) return;
  uploadingTestData.value = true;
  error.value = '';
  notice.value = '';
  try {
    const formData = new FormData();
    formData.append('file', testDataFile.value);
    const uploaded = await apiRequest<ProblemTestData>(`/admin/problems/${selectedProblem.value.id}/testdata`, {
      method: 'POST',
      body: formData,
    });
    notice.value = `${selectedProblem.value.id} 测试数据已上传：${uploaded.case_count} 组。`;
    testDataFile.value = null;
    if (testDataInput.value) testDataInput.value.value = '';
    await loadProblems();
  } catch (err) {
    error.value = err instanceof Error ? err.message : '测试数据上传失败。';
  } finally {
    uploadingTestData.value = false;
  }
}

async function downloadProblemTestData(problem: ProblemAdminDetail) {
  error.value = '';
  try {
    const headers = new Headers();
    const token = getStoredAuthToken();
    if (token) headers.set('Authorization', `Bearer ${token}`);
    const response = await fetch(`${API_BASE}/admin/problems/${problem.id}/testdata/download`, { headers });
    if (!response.ok) {
      const text = await response.text();
      let message = response.statusText;
      try {
        message = JSON.parse(text)?.detail ?? message;
      } catch {
        if (text) message = text;
      }
      throw new Error(message);
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${problem.id}-testdata.zip`;
    link.click();
    URL.revokeObjectURL(url);
  } catch (err) {
    error.value = err instanceof Error ? err.message : '测试数据下载失败。';
  }
}

async function exportProblems(scope: 'all' | 'selected') {
  exporting.value = true;
  error.value = '';
  notice.value = '';
  try {
    const params = new URLSearchParams({ format: ioFormat.value });
    if (scope === 'selected' && selectedProblem.value) {
      params.set('ids', selectedProblem.value.id);
    }
    const exported = await apiRequest<ProblemExportResponse>(`/admin/problems/export?${params.toString()}`);
    downloadTextFile(exported.filename, exported.content_type, exported.content);
    notice.value = `已导出 ${exported.problem_count} 题。`;
  } catch (err) {
    error.value = err instanceof Error ? err.message : '题目导出失败。';
  } finally {
    exporting.value = false;
  }
}

async function importProblems(dryRun = false) {
  importing.value = true;
  error.value = '';
  notice.value = '';
  importResult.value = null;
  try {
    const result = await apiRequest<ProblemImportResponse>('/admin/problems/import', {
      method: 'POST',
      body: JSON.stringify({
        format: ioFormat.value,
        content: importContent.value,
        conflict_strategy: importStrategy.value,
        dry_run: dryRun,
      }),
    });
    importResult.value = result;
    notice.value = dryRun
      ? `预检完成：${result.imported} 题可导入，${result.skipped} 题跳过。`
      : `已导入 ${result.imported} 题，跳过 ${result.skipped} 题。`;
    if (!dryRun) await loadProblems();
  } catch (err) {
    error.value = err instanceof Error ? err.message : '题目导入失败，批量写入已回滚。';
  } finally {
    importing.value = false;
  }
}

async function loadProblems() {
  loading.value = true;
  error.value = '';
  try {
    problems.value = await apiRequest<ProblemAdminDetail[]>('/admin/problems');
    if (selectedId.value) {
      const selected = problems.value.find((problem) => problem.id === selectedId.value);
      if (selected) editProblem(selected);
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : '题目管理数据加载失败。';
  } finally {
    loading.value = false;
  }
}

async function loadTags() {
  try {
    tagTree.value = await apiRequest<TagTreeNode[]>('/tags', { auth: false });
  } catch {
    tagTree.value = [];
  }
}

async function loadProblemVersions(problemId: string) {
  versionLoading.value = true;
  try {
    versions.value = await apiRequest<ProblemVersion[]>(`/admin/problems/${problemId}/versions`);
  } catch (err) {
    error.value = err instanceof Error ? err.message : '版本历史加载失败。';
    versions.value = [];
  } finally {
    versionLoading.value = false;
  }
}

async function saveProblem() {
  saving.value = true;
  error.value = '';
  notice.value = '';
  try {
    const payload = buildPayload();
    const path = mode.value === 'edit' && selectedId.value ? `/admin/problems/${selectedId.value}` : '/admin/problems';
    const method = mode.value === 'edit' && selectedId.value ? 'PUT' : 'POST';
    const saved = await apiRequest<ProblemAdminDetail>(path, {
      method,
      body: JSON.stringify(payload),
    });
    notice.value = `${saved.id} 已保存。`;
    selectedId.value = saved.id;
    mode.value = 'edit';
    await loadProblems();
  } catch (err) {
    error.value = err instanceof Error ? err.message : '题目保存失败。';
  } finally {
    saving.value = false;
  }
}

async function restoreVersion(version: ProblemVersion) {
  if (!selectedProblem.value) return;
  if (!window.confirm(`确认回滚到 V${version.version} · ${version.snapshot.title}？`)) return;
  versionRestoringId.value = version.id;
  error.value = '';
  notice.value = '';
  try {
    const restored = await apiRequest<ProblemAdminDetail>(
      `/admin/problems/${version.problem_id}/versions/${version.id}/restore`,
      { method: 'POST' },
    );
    notice.value = `${restored.id} 已回滚到 V${version.version}。`;
    selectedId.value = restored.id;
    await loadProblems();
  } catch (err) {
    error.value = err instanceof Error ? err.message : '题目回滚失败。';
  } finally {
    versionRestoringId.value = '';
  }
}

async function deleteProblem(problem: ProblemAdminDetail) {
  if (!window.confirm(`确认下线 ${problem.id} · ${problem.title}？`)) return;
  error.value = '';
  notice.value = '';
  const deleted = await apiRequest<ProblemAdminDetail>(`/admin/problems/${problem.id}`, { method: 'DELETE' });
  notice.value = `${deleted.id} 已下线。`;
  await loadProblems();
}

onMounted(() => {
  void loadTags();
  void loadProblems();
});
</script>

<template>
  <div class="page-stack">
    <section class="page-heading">
      <div>
        <span class="eyebrow">Problem Management</span>
        <h1>题目管理</h1>
      </div>
      <button class="secondary-action" type="button" @click="loadProblems">
        <RefreshCw :size="16" />刷新
      </button>
    </section>

    <p v-if="error" class="form-error">{{ error }}</p>
    <p v-if="notice" class="form-success">{{ notice }}</p>

    <section class="problem-editor-grid">
      <aside class="panel problem-manager-list">
        <div class="panel-head">
          <div>
            <h2>题库条目</h2>
            <p>{{ problems.length }} 题</p>
          </div>
          <button class="secondary-action" type="button" @click="resetForm">
            <Plus :size="16" />新建
          </button>
        </div>
        <label class="search-box compact-search">
          <Search :size="17" />
          <input v-model="search" placeholder="搜索题号、标题或标签" />
        </label>
        <div class="problem-manage-list">
          <button
            v-for="problem in filteredProblems"
            :key="problem.id"
            class="problem-manage-row"
            :class="{ active: selectedId === problem.id, muted: !problem.visible }"
            type="button"
            @click="editProblem(problem)"
          >
            <ProblemTypeIcon :type="problem.type" />
            <span>
              <strong>{{ problem.id }} · {{ problem.title }}</strong>
              <em>{{ problemTypeLabel(problem.type) }} · {{ problem.difficulty }} · {{ problem.tags.join(' / ') || '未分类' }}</em>
            </span>
            <Eye v-if="problem.visible" :size="16" />
            <EyeOff v-else :size="16" />
          </button>
          <p v-if="loading" class="empty-state"><Loader2 :size="16" class="spin" /> 正在加载</p>
          <p v-if="!loading && filteredProblems.length === 0" class="empty-state">暂无匹配题目。</p>
        </div>
      </aside>

      <section class="panel problem-form-panel">
        <div class="panel-head">
          <div>
            <h2>{{ mode === 'edit' ? '编辑题目' : '新建题目' }}</h2>
            <p>{{ selectedId || '未分配题号' }}</p>
          </div>
          <div class="inline-actions">
            <button class="secondary-action" type="button" @click="resetForm">
              <Plus :size="16" />清空
            </button>
            <button
              v-if="mode === 'edit' && selectedProblem"
              class="secondary-action danger-action"
              type="button"
              @click="deleteProblem(selectedProblem)"
            >
              <Trash2 :size="16" />下线
            </button>
          </div>
        </div>

        <div class="problem-io-block">
          <div class="field-head">
            <strong>导入导出</strong>
            <div class="inline-actions">
              <button class="secondary-action" type="button" :disabled="exporting" @click="exportProblems('all')">
                <Loader2 v-if="exporting" :size="15" class="spin" />
                <Download v-else :size="15" />
                全部
              </button>
              <button
                class="secondary-action"
                type="button"
                :disabled="exporting || !selectedProblem"
                @click="exportProblems('selected')"
              >
                <Download :size="15" />
                当前
              </button>
            </div>
          </div>
          <div class="problem-io-grid">
            <label>格式
              <select v-model="ioFormat">
                <option v-for="item in packageFormats" :key="item.value" :value="item.value">{{ item.label }}</option>
              </select>
            </label>
            <label>冲突
              <select v-model="importStrategy">
                <option v-for="item in importStrategies" :key="item.value" :value="item.value">{{ item.label }}</option>
              </select>
            </label>
          </div>
          <label class="problem-io-textarea">
            内容
            <textarea v-model="importContent" rows="5" />
          </label>
          <div class="inline-actions">
            <button class="secondary-action" type="button" :disabled="importing || !importContent.trim()" @click="importProblems(true)">
              <Loader2 v-if="importing" :size="15" class="spin" />
              <Search v-else :size="15" />
              预检
            </button>
            <button class="primary-action" type="button" :disabled="importing || !importContent.trim()" @click="importProblems(false)">
              <Loader2 v-if="importing" :size="15" class="spin" />
              <Upload v-else :size="15" />
              导入
            </button>
          </div>
          <div v-if="importResult" class="import-result-list">
            <div v-for="item in importResult.items" :key="`${item.action}-${item.source_id}-${item.target_id}`">
              <strong>{{ importActionLabel(item.action) }}</strong>
              <span>{{ item.source_id || '-' }} → {{ item.target_id || '-' }} · {{ item.title }}</span>
            </div>
          </div>
        </div>

        <div v-if="mode === 'edit' && selectedProblem" class="version-history-block">
          <div class="field-head">
            <strong><History :size="16" />版本历史</strong>
            <button class="secondary-action" type="button" @click="loadProblemVersions(selectedProblem.id)">
              <RefreshCw :size="15" />刷新
            </button>
          </div>
          <div class="version-history-list">
            <div v-for="version in versions" :key="version.id" class="version-history-row">
              <div>
                <strong>V{{ version.version }} · {{ version.snapshot.title }}</strong>
                <span>
                  {{ versionActionLabel(version.action) }} · {{ problemTypeLabel(version.snapshot.type) }} ·
                  {{ formatDate(version.saved_at) }}
                </span>
              </div>
              <button
                class="secondary-action"
                type="button"
                :disabled="versionRestoringId === version.id"
                @click="restoreVersion(version)"
              >
                <Loader2 v-if="versionRestoringId === version.id" :size="15" class="spin" />
                <RotateCcw v-else :size="15" />
                回滚
              </button>
            </div>
            <p v-if="versionLoading" class="empty-state"><Loader2 :size="16" class="spin" /> 正在加载版本</p>
            <p v-if="!versionLoading && versions.length === 0" class="empty-state">尚无历史版本。</p>
          </div>
        </div>

        <form class="submit-form problem-form" @submit.prevent="saveProblem">
          <div class="form-grid two">
            <label>标题<input v-model="form.title" required /></label>
            <label>难度
              <select v-model="form.difficulty">
                <option v-for="difficulty in difficultyOptions" :key="difficulty" :value="difficulty">{{ difficulty }}</option>
              </select>
            </label>
          </div>

          <div class="type-switch" role="group" aria-label="题型">
            <button
              v-for="item in typeOptions"
              :key="item.value"
              type="button"
              :class="{ active: form.type === item.value }"
              @click="setType(item.value)"
            >
              {{ item.label }}
            </button>
          </div>

          <div class="field-block tag-picker-block">
            <div class="field-head">
              <strong>标签与知识点</strong>
              <span>{{ tagsFromText().length }} 个</span>
            </div>
            <label>标签<input v-model="form.tagsText" placeholder="图论, 二分, 安全" /></label>
            <div class="tag-choice-grid">
              <label
                v-for="item in flatTags"
                :key="item.tag.id"
                class="tag-filter-option"
                :style="{ paddingLeft: `${10 + item.depth * 18}px` }"
              >
                <input
                  type="checkbox"
                  :checked="tagsFromText().includes(item.tag.name)"
                  @change="toggleTagChoice(item.tag.name)"
                />
                <span>{{ item.tag.name }}</span>
              </label>
            </div>
          </div>
          <label>题面<textarea v-model="form.statement" required rows="6" /></label>

          <label class="choice-line">
            <input v-model="form.visible" type="checkbox" />
            <span>公开显示</span>
          </label>

          <template v-if="form.type === 'code'">
            <div class="form-grid two">
              <label>时间限制 ms<input v-model.number="form.time_limit_ms" type="number" min="1" /></label>
              <label>内存限制 MB<input v-model.number="form.memory_limit_mb" type="number" min="1" /></label>
            </div>
            <div class="form-grid two">
              <label>输入格式<textarea v-model="form.input_format" rows="4" /></label>
              <label>输出格式<textarea v-model="form.output_format" rows="4" /></label>
            </div>
            <div class="field-block">
              <div class="field-head">
                <strong>样例</strong>
                <button class="secondary-action" type="button" @click="addSample"><Plus :size="15" />添加</button>
              </div>
              <div v-for="(sample, index) in form.samples" :key="index" class="sample-editor-row">
                <label>输入<textarea v-model="sample.input" rows="3" /></label>
                <label>输出<textarea v-model="sample.output" rows="3" /></label>
                <button class="icon-button danger-icon" type="button" aria-label="删除样例" @click="removeSample(index)">
                  <Trash2 :size="16" />
                </button>
              </div>
            </div>
            <div v-if="mode === 'edit' && selectedProblem" class="field-block testdata-block">
              <div class="field-head">
                <strong>测试数据 ZIP</strong>
                <button
                  class="secondary-action"
                  type="button"
                  :disabled="!selectedTestData"
                  @click="downloadProblemTestData(selectedProblem)"
                >
                  <Download :size="15" />下载
                </button>
              </div>
              <div class="testdata-actions">
                <label class="file-picker">
                  <Upload :size="16" />
                  <span>{{ testDataFile?.name || '选择 ZIP' }}</span>
                  <input ref="testDataInput" type="file" accept=".zip,application/zip" @change="selectTestDataFile" />
                </label>
                <button class="primary-action" type="button" :disabled="uploadingTestData || !testDataFile" @click="uploadProblemTestData">
                  <Loader2 v-if="uploadingTestData" :size="16" class="spin" />
                  <Upload v-else :size="16" />
                  上传
                </button>
              </div>
              <div v-if="selectedTestData" class="testdata-meta">
                <span>{{ selectedTestData.filename }}</span>
                <span>{{ selectedTestData.case_count }} 组</span>
                <span>{{ formatBytes(selectedTestData.size_bytes) }}</span>
                <span>{{ formatDate(selectedTestData.uploaded_at) }}</span>
              </div>
              <p v-else class="empty-state">未上传测试数据。</p>
            </div>
            <label>在线评测配置 JSON<textarea v-model="form.codeJudgeConfigText" class="code-config-editor" rows="6" /></label>
          </template>

          <template v-if="form.type === 'blank'">
            <div class="form-grid two">
              <label class="choice-line">
                <input v-model="form.case_sensitive" type="checkbox" />
                <span>区分大小写</span>
              </label>
              <label class="choice-line">
                <input v-model="form.trim_space" type="checkbox" />
                <span>忽略空白</span>
              </label>
            </div>
            <div class="field-block">
              <div class="field-head">
                <strong>填空项</strong>
                <button class="secondary-action" type="button" @click="addBlank"><Plus :size="15" />添加</button>
              </div>
              <div v-for="(blank, index) in form.blankRows" :key="index" class="blank-editor-row">
                <label>Key<input v-model="blank.key" /></label>
                <label>标签<input v-model="blank.label" /></label>
                <label>分值<input v-model.number="blank.score" type="number" min="1" /></label>
                <label>答案<textarea v-model="blank.answersText" rows="3" /></label>
                <button class="icon-button danger-icon" type="button" aria-label="删除填空项" @click="removeBlank(index)">
                  <Trash2 :size="16" />
                </button>
              </div>
            </div>
          </template>

          <template v-if="form.type === 'single_choice' || form.type === 'multiple_choice'">
            <div class="form-grid two">
              <label>分值<input v-model.number="form.objectiveScore" type="number" min="1" /></label>
            </div>
            <div class="field-block">
              <div class="field-head">
                <strong>选项</strong>
                <button class="secondary-action" type="button" @click="addOption"><Plus :size="15" />添加</button>
              </div>
              <div v-for="(option, index) in form.options" :key="index" class="option-editor-row">
                <input v-model="option.key" class="option-key-input" aria-label="选项 Key" />
                <input v-model="option.text" aria-label="选项内容" placeholder="选项内容" />
                <label v-if="form.type === 'single_choice'" class="choice-line compact-choice">
                  <input v-model="form.singleAnswer" type="radio" :value="option.key" />
                  <span>答案</span>
                </label>
                <label v-else class="choice-line compact-choice">
                  <input
                    type="checkbox"
                    :checked="form.multipleAnswers.includes(option.key)"
                    @change="toggleMultipleAnswer(option.key)"
                  />
                  <span>答案</span>
                </label>
                <button class="icon-button danger-icon" type="button" aria-label="删除选项" @click="removeOption(index)">
                  <Trash2 :size="16" />
                </button>
              </div>
            </div>
          </template>

          <button class="primary-action full" type="submit" :disabled="saving">
            <Loader2 v-if="saving" :size="17" class="spin" />
            <Save v-else :size="17" />
            保存题目
          </button>
        </form>
      </section>
    </section>
  </div>
</template>
