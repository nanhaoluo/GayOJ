<script setup lang="ts">
import { CheckCircle2, ChevronLeft, ChevronRight, FileClock, KeyRound, Languages, RefreshCw, Save, Search, Server, ShieldCheck, UsersRound } from 'lucide-vue-next';
import { computed, onMounted, reactive, ref } from 'vue';
import StatusBadge from '@/components/StatusBadge.vue';
import { apiRequest, formatDate } from '@/services/api';
import type {
  AuditLog,
  AuditLogList,
  CompilerConfig,
  CompilerConfigUpdate,
  CompilerLanguage,
  JudgeNode,
  JudgeNodeStatus,
  PublicUser,
  RbacMatrix,
  Role,
  SystemConfig,
} from '@/services/types';

const users = ref<PublicUser[]>([]);
const nodes = ref<JudgeNode[]>([]);
const logs = ref<AuditLog[]>([]);
const rbac = ref<RbacMatrix | null>(null);
const logTotal = ref(0);
const logOffset = ref(0);
const logLimit = 20;
const error = ref('');
const actionError = ref('');
const notice = ref('');
const compilerNotice = ref('');
const compilerError = ref('');
const savingRoleUserId = ref('');
const updatingNodeId = ref('');
const savingCompilerCode = ref('');
const selectedCompilerCode = ref('');
const compilerConfigs = ref<CompilerConfig[]>([]);
const compilerLanguages = ref<CompilerLanguage[]>([]);
const config = reactive<SystemConfig>({
  site_name: 'gayoj',
  registration_enabled: true,
  default_language: 'cpp',
  judge_submit_rate_limit_per_minute: 10,
  objective_submit_rate_limit_per_minute: 30,
  password_min_length: 6,
  password_require_letter: true,
  password_require_digit: true,
  login_max_failed_attempts: 5,
  login_lockout_minutes: 15,
  maintenance_mode: false,
});
const compilerForm = reactive({
  display_name: '',
  version: '',
  source_extension: '',
  compile_command_text: '[]',
  run_command_text: '[]',
  enabled: true,
  sort_order: 0,
});
const pendingRoles = reactive<Record<string, Role>>({});
const auditFilters = reactive({
  action: '',
  actor_id: '',
  resource: '',
});

const roleLabels: Record<Role, string> = {
  student: '选手',
  coach: '教练',
  judge: '裁判',
  admin: '管理员',
};

const roleOptions = computed(() => rbac.value?.roles ?? []);
const activeAdminCount = computed(() => users.value.filter((user) => user.role === 'admin' && !user.disabled).length);
const enabledCompilerLanguages = computed(() => compilerConfigs.value.filter((item) => item.enabled));
const selectedCompiler = computed(() => compilerConfigs.value.find((item) => item.code === selectedCompilerCode.value) ?? null);

function roleLabel(role: Role): string {
  return roleLabels[role];
}

function isLastActiveAdmin(user: PublicUser): boolean {
  return user.role === 'admin' && !user.disabled && activeAdminCount.value <= 1;
}

function syncPendingRoles(userData: PublicUser[]) {
  const userIds = new Set(userData.map((user) => user.id));
  for (const user of userData) {
    pendingRoles[user.id] = user.role;
  }
  for (const userId of Object.keys(pendingRoles)) {
    if (!userIds.has(userId)) {
      delete pendingRoles[userId];
    }
  }
}

function syncCompilerForm(config: CompilerConfig) {
  selectedCompilerCode.value = config.code;
  compilerForm.display_name = config.display_name;
  compilerForm.version = config.version;
  compilerForm.source_extension = config.source_extension;
  compilerForm.compile_command_text = JSON.stringify(config.compile_command, null, 2);
  compilerForm.run_command_text = JSON.stringify(config.run_command, null, 2);
  compilerForm.enabled = config.enabled;
  compilerForm.sort_order = config.sort_order;
}

function loadCompilerDefaults() {
  if (selectedCompilerCode.value) {
    const selected = compilerConfigs.value.find((item) => item.code === selectedCompilerCode.value);
    if (selected) {
      syncCompilerForm(selected);
      return;
    }
  }
  const initial = compilerConfigs.value[0];
  if (initial) {
    syncCompilerForm(initial);
  }
}

function parseCompilerCommand(text: string): string[] {
  if (!text.trim()) return [];
  const parsed = JSON.parse(text);
  if (!Array.isArray(parsed)) {
    throw new Error('编译器命令必须是 JSON 数组。');
  }
  return parsed.map((item) => String(item).trim()).filter(Boolean);
}

function auditLogPath() {
  const params = new URLSearchParams({
    limit: String(logLimit),
    offset: String(logOffset.value),
  });
  for (const [key, value] of Object.entries(auditFilters)) {
    if (value.trim()) {
      params.set(key, value.trim());
    }
  }
  return `/admin/audit-logs?${params.toString()}`;
}

async function loadAuditLogs() {
  const data = await apiRequest<AuditLogList>(auditLogPath());
  logs.value = data.items;
  logTotal.value = data.total;
  logOffset.value = data.offset;
}

async function load() {
  try {
    error.value = '';
    actionError.value = '';
    compilerError.value = '';
    compilerNotice.value = '';
    const [userData, nodeData, logData, configData, rbacData, compilerData, languageData] = await Promise.all([
      apiRequest<PublicUser[]>('/admin/users'),
      apiRequest<JudgeNode[]>('/admin/judge-nodes'),
      apiRequest<AuditLogList>(auditLogPath()),
      apiRequest<SystemConfig>('/system/config'),
      apiRequest<RbacMatrix>('/admin/rbac/matrix'),
      apiRequest<CompilerConfig[]>('/admin/compiler-configs'),
      apiRequest<CompilerLanguage[]>('/judge/languages', { auth: false }).catch(() => []),
    ]);
    users.value = userData;
    syncPendingRoles(userData);
    nodes.value = nodeData;
    logs.value = logData.items;
    logTotal.value = logData.total;
    logOffset.value = logData.offset;
    rbac.value = rbacData;
    compilerConfigs.value = compilerData;
    compilerLanguages.value = languageData;
    Object.assign(config, configData);
    if (!selectedCompilerCode.value || !compilerConfigs.value.some((item) => item.code === selectedCompilerCode.value)) {
      loadCompilerDefaults();
    } else if (selectedCompiler.value) {
      syncCompilerForm(selectedCompiler.value);
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : '需要管理员权限。';
  }
}

async function toggleBan(user: PublicUser) {
  try {
    actionError.value = '';
    notice.value = '';
    await apiRequest<PublicUser>(`/admin/users/${user.id}/ban?disabled=${!user.disabled}`, { method: 'PATCH' });
    notice.value = `${user.display_name} 已${user.disabled ? '解封' : '封禁'}。`;
    await load();
  } catch (err) {
    actionError.value = err instanceof Error ? err.message : '用户状态更新失败。';
  }
}

async function assignRole(user: PublicUser) {
  const nextRole = pendingRoles[user.id];
  if (!nextRole || nextRole === user.role) return;
  try {
    actionError.value = '';
    notice.value = '';
    savingRoleUserId.value = user.id;
    const updated = await apiRequest<PublicUser>(`/admin/users/${user.id}/role`, {
      method: 'PATCH',
      body: JSON.stringify({ role: nextRole }),
    });
    notice.value = `${updated.display_name} 已更新为${roleLabel(updated.role)}。`;
    await load();
  } catch (err) {
    pendingRoles[user.id] = user.role;
    actionError.value = err instanceof Error ? err.message : '角色更新失败。';
  } finally {
    savingRoleUserId.value = '';
  }
}

async function saveConfig() {
  Object.assign(config, await apiRequest<SystemConfig>('/system/config', {
    method: 'PUT',
    body: JSON.stringify(config),
  }));
  await load();
}

async function saveCompilerConfig() {
  if (!selectedCompiler.value) return;
  try {
    compilerError.value = '';
    compilerNotice.value = '';
    savingCompilerCode.value = selectedCompiler.value.code;
    const payload: CompilerConfigUpdate = {
      display_name: compilerForm.display_name.trim(),
      version: compilerForm.version.trim(),
      source_extension: compilerForm.source_extension.trim(),
      compile_command: parseCompilerCommand(compilerForm.compile_command_text),
      run_command: parseCompilerCommand(compilerForm.run_command_text),
      enabled: compilerForm.enabled,
      sort_order: Number(compilerForm.sort_order || 0),
    };
    const updated = await apiRequest<CompilerConfig>(`/admin/compiler-configs/${selectedCompiler.value.code}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    });
    compilerNotice.value = `${updated.code} 编译器配置已保存。`;
    await load();
    selectedCompilerCode.value = updated.code;
  } catch (err) {
    compilerError.value = err instanceof Error ? err.message : '编译器配置更新失败。';
  } finally {
    savingCompilerCode.value = '';
  }
}

function selectCompilerConfig(config: CompilerConfig) {
  compilerError.value = '';
  compilerNotice.value = '';
  syncCompilerForm(config);
}

async function updateNodeStatus(node: JudgeNode, status: JudgeNodeStatus) {
  try {
    actionError.value = '';
    notice.value = '';
    updatingNodeId.value = node.id;
    const updated = await apiRequest<JudgeNode>(`/admin/judge-nodes/${node.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    });
    nodes.value = nodes.value.map((item) => (item.id === updated.id ? updated : item));
    notice.value = `${updated.name} 已切换为 ${updated.status}。`;
    await loadAuditLogs();
  } catch (err) {
    actionError.value = err instanceof Error ? err.message : '节点状态更新失败。';
  } finally {
    updatingNodeId.value = '';
  }
}

async function applyAuditFilters() {
  logOffset.value = 0;
  await loadAuditLogs();
}

async function pageAuditLogs(direction: -1 | 1) {
  logOffset.value = Math.max(0, logOffset.value + direction * logLimit);
  await loadAuditLogs();
}

onMounted(load);
</script>

<template>
  <div class="page-stack">
    <section class="page-heading">
      <div>
        <span class="eyebrow">Admin Console</span>
        <h1>管理端</h1>
      </div>
    </section>

    <p v-if="error" class="form-error">{{ error }}</p>
    <p v-if="actionError" class="form-error">{{ actionError }}</p>
    <p v-if="notice" class="form-success">{{ notice }}</p>

    <section v-if="!error" class="metric-grid">
      <article class="metric-panel">
        <UsersRound :size="20" />
        <span>用户</span>
        <strong>{{ users.length }}</strong>
      </article>
      <article class="metric-panel">
        <ShieldCheck :size="20" />
        <span>角色</span>
        <strong>{{ roleOptions.length }}</strong>
      </article>
      <article class="metric-panel">
        <Server :size="20" />
        <span>节点</span>
        <strong>{{ nodes.length }}</strong>
      </article>
      <article class="metric-panel">
        <FileClock :size="20" />
        <span>审计日志</span>
        <strong>{{ logTotal }}</strong>
      </article>
    </section>

    <section v-if="!error" class="dashboard-grid">
      <div class="panel">
        <div class="panel-head">
          <div>
            <h2>用户与角色</h2>
            <p>分配平台角色、封禁账号</p>
          </div>
        </div>
        <div class="list-stack">
          <div v-for="user in users" :key="user.id" class="role-user-row">
            <div class="user-identity">
              <strong>{{ user.display_name }}</strong>
              <span>{{ user.username }} · {{ user.school || '未填写学校' }}</span>
            </div>
            <select v-model="pendingRoles[user.id]" class="role-select" :aria-label="`调整 ${user.username} 角色`">
              <option v-for="role in roleOptions" :key="role.code" :value="role.code">
                {{ roleLabel(role.code) }}
              </option>
            </select>
            <span class="permission-count">{{ user.permissions.length }} 权限</span>
            <button
              class="secondary-action"
              type="button"
              :disabled="pendingRoles[user.id] === user.role || savingRoleUserId === user.id"
              @click="assignRole(user)"
            >
              <CheckCircle2 :size="16" />保存
            </button>
            <button class="secondary-action" type="button" :disabled="isLastActiveAdmin(user)" @click="toggleBan(user)">
              {{ user.disabled ? '解封' : '封禁' }}
            </button>
          </div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-head">
          <div>
            <h2>评测节点</h2>
            <p>在线、下线与负载</p>
          </div>
        </div>
        <div class="list-stack">
          <div v-for="node in nodes" :key="node.id" class="node-row">
            <div>
              <strong>{{ node.name }}</strong>
              <span>{{ node.languages.join(', ') || '未上报语言' }}</span>
              <span>{{ node.queue_depth }} queued · {{ Math.round(node.load * 100) }}% · {{ formatDate(node.last_heartbeat) }}</span>
            </div>
            <StatusBadge :status="node.status" />
            <div class="node-actions">
              <button
                class="secondary-action compact"
                type="button"
                :disabled="updatingNodeId === node.id || node.status === 'draining'"
                @click="updateNodeStatus(node, 'draining')"
              >
                下线中
              </button>
              <button
                class="secondary-action compact"
                type="button"
                :disabled="updatingNodeId === node.id || node.status === 'online'"
                @click="updateNodeStatus(node, 'online')"
              >
                恢复
              </button>
              <button
                class="secondary-action compact"
                type="button"
                :disabled="updatingNodeId === node.id || node.status === 'offline'"
                @click="updateNodeStatus(node, 'offline')"
              >
                离线
              </button>
            </div>
          </div>
          <p v-if="nodes.length === 0" class="empty-state">暂无评测节点心跳。</p>
        </div>
      </div>

      <div class="panel large-panel">
        <div class="panel-head">
          <div>
            <h2>角色权限矩阵</h2>
            <p>来自运行时 RBAC 权限码模型</p>
          </div>
          <KeyRound :size="20" />
        </div>
        <div v-if="rbac" class="role-matrix">
          <div class="role-matrix-row matrix-head">
            <span>权限</span>
            <span v-for="role in rbac.roles" :key="role.code">{{ roleLabel(role.code) }}</span>
          </div>
          <div v-for="permission in rbac.permissions" :key="permission.code" class="role-matrix-row">
            <span class="permission-cell">
              <strong>{{ permission.code }}</strong>
              <em>{{ permission.description }}</em>
            </span>
            <span
              v-for="role in rbac.roles"
              :key="`${role.code}-${permission.code}`"
              class="matrix-state"
              :class="{ allowed: rbac.matrix[role.code]?.[permission.code] }"
            >
              {{ rbac.matrix[role.code]?.[permission.code] ? '允许' : '-' }}
            </span>
          </div>
        </div>
      </div>

      <div class="panel large-panel">
        <div class="panel-head">
          <div>
            <h2>操作审计</h2>
            <p>敏感动作留痕</p>
          </div>
        </div>
        <form class="audit-filter" @submit.prevent="applyAuditFilters">
          <label>Action<input v-model="auditFilters.action" placeholder="system.config.update" /></label>
          <label>Actor<input v-model="auditFilters.actor_id" placeholder="u-admin" /></label>
          <label>Resource<input v-model="auditFilters.resource" placeholder="system:config" /></label>
          <button class="secondary-action" type="submit"><Search :size="16" />筛选</button>
        </form>
        <div class="audit-table">
          <div class="audit-row table-head">
            <span>动作</span>
            <span>资源</span>
            <span>操作者</span>
            <span>时间</span>
          </div>
          <div v-for="log in logs" :key="log.id" class="audit-row">
            <strong>{{ log.action }}</strong>
            <span>{{ log.resource }}</span>
            <span>{{ log.actor_id ?? 'system' }}</span>
            <span>{{ formatDate(log.created_at) }}</span>
          </div>
          <p v-if="logs.length === 0" class="empty-state">暂无匹配的审计日志。</p>
        </div>
        <div class="audit-pager">
          <span>{{ logTotal === 0 ? 0 : logOffset + 1 }}-{{ Math.min(logOffset + logs.length, logTotal) }} / {{ logTotal }}</span>
          <div>
            <button class="secondary-action" type="button" :disabled="logOffset === 0" @click="pageAuditLogs(-1)">
              <ChevronLeft :size="16" />上一页
            </button>
            <button class="secondary-action" type="button" :disabled="logOffset + logs.length >= logTotal" @click="pageAuditLogs(1)">
              下一页<ChevronRight :size="16" />
            </button>
          </div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-head">
          <div>
            <h2>系统配置</h2>
            <p>站点参数、账号安全和提交限流</p>
          </div>
        </div>
        <form class="submit-form" @submit.prevent="saveConfig">
          <label>站点名称<input v-model="config.site_name" /></label>
          <label>默认语言
            <select v-model="config.default_language">
              <option v-for="item in enabledCompilerLanguages" :key="item.code" :value="item.code">
                {{ item.display_name }} · {{ item.version }}
              </option>
            </select>
          </label>
          <label>代码提交限流/分钟<input v-model.number="config.judge_submit_rate_limit_per_minute" type="number" min="1" /></label>
          <label>客观题提交限流/分钟<input v-model.number="config.objective_submit_rate_limit_per_minute" type="number" min="1" /></label>
          <label>密码最小长度<input v-model.number="config.password_min_length" type="number" min="1" max="128" /></label>
          <label>失败锁定阈值<input v-model.number="config.login_max_failed_attempts" type="number" min="1" max="50" /></label>
          <label>锁定分钟数<input v-model.number="config.login_lockout_minutes" type="number" min="1" max="1440" /></label>
          <label class="choice-line">
            <input v-model="config.password_require_letter" type="checkbox" />
            <span>密码必须包含字母</span>
          </label>
          <label class="choice-line">
            <input v-model="config.password_require_digit" type="checkbox" />
            <span>密码必须包含数字</span>
          </label>
          <label class="choice-line">
            <input v-model="config.registration_enabled" type="checkbox" />
            <span>允许注册</span>
          </label>
          <label class="choice-line">
            <input v-model="config.maintenance_mode" type="checkbox" />
            <span>维护模式</span>
          </label>
          <button class="primary-action full" type="submit"><Save :size="17" />保存配置</button>
        </form>
      </div>

      <div class="panel large-panel">
        <div class="panel-head">
          <div>
            <h2>编译器配置</h2>
            <p>管理可用语言、版本与 worker 命令模板</p>
            <p>{{ compilerLanguages.length }} 个公开语言，{{ enabledCompilerLanguages.length }} 个启用</p>
          </div>
          <button class="secondary-action" type="button" @click="load">
            <RefreshCw :size="16" />刷新
          </button>
        </div>
        <p v-if="compilerError" class="form-error">{{ compilerError }}</p>
        <p v-if="compilerNotice" class="form-success">{{ compilerNotice }}</p>
        <div class="compiler-config-layout">
          <div class="compiler-config-list">
            <button
              v-for="configItem in compilerConfigs"
              :key="configItem.code"
              type="button"
              class="compiler-config-row"
              :class="{ active: selectedCompilerCode === configItem.code, muted: !configItem.enabled }"
              @click="selectCompilerConfig(configItem)"
            >
              <Languages :size="18" />
              <span>
                <strong>{{ configItem.display_name }}</strong>
                <em>{{ configItem.code }} · {{ configItem.version }} · {{ configItem.source_extension }}</em>
              </span>
              <StatusBadge :status="configItem.enabled ? 'online' : 'offline'" />
            </button>
          </div>

          <form v-if="selectedCompiler" class="submit-form compiler-config-form" @submit.prevent="saveCompilerConfig">
            <div class="form-grid two">
              <label>语言代码<input :value="selectedCompiler.code" disabled /></label>
              <label>排序<input v-model.number="compilerForm.sort_order" type="number" min="0" /></label>
            </div>
            <div class="form-grid two">
              <label>显示名称<input v-model="compilerForm.display_name" /></label>
              <label>版本<input v-model="compilerForm.version" /></label>
            </div>
            <div class="form-grid two">
              <label>源文件扩展名<input v-model="compilerForm.source_extension" /></label>
              <label class="choice-line">
                <input v-model="compilerForm.enabled" type="checkbox" />
                <span>启用在线评测</span>
              </label>
            </div>
            <label>
              编译命令
              <textarea
                v-model="compilerForm.compile_command_text"
                class="code-config-editor"
                rows="6"
                placeholder='["g++","-std=c++17","Main.cpp"]'
              />
            </label>
            <label>
              运行命令
              <textarea
                v-model="compilerForm.run_command_text"
                class="code-config-editor"
                rows="4"
                placeholder='["./Main"]'
              />
            </label>
            <button class="primary-action full" type="submit" :disabled="savingCompilerCode === selectedCompiler.code">
              <Loader2 v-if="savingCompilerCode === selectedCompiler.code" :size="17" class="spin" />
              <Save v-else :size="17" />
              保存编译器配置
            </button>
          </form>

          <div v-else class="empty-state">暂无编译器配置。</div>
        </div>
      </div>
    </section>
  </div>
</template>
