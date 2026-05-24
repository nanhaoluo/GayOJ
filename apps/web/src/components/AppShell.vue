<script setup lang="ts">
import {
  BarChart3,
  BookOpen,
  ClipboardList,
  Bell,
  Gauge,
  FilePenLine,
  LayoutDashboard,
  ListChecks,
  LogOut,
  Medal,
  Scale,
  Settings,
  Shield,
  Tags,
  Trophy,
  UserRound,
} from 'lucide-vue-next';
import { computed, onMounted, ref } from 'vue';
import { RouterLink, useRoute } from 'vue-router';
import { authState, login, logout, restoreSession } from '@/stores/auth';

const route = useRoute();
const username = ref('alice');
const password = ref('gayoj123');

const navItems = [
  { path: '/', label: '总览', icon: LayoutDashboard },
  { path: '/problems', label: '题库', icon: BookOpen },
  { path: '/problem-sets', label: '题单', icon: ListChecks },
  { path: '/contests', label: '比赛', icon: Trophy },
  { path: '/submissions', label: '提交', icon: ClipboardList },
  { path: '/rankings', label: '排行', icon: Medal },
  { path: '/discuss', label: '讨论', icon: Bell },
  { path: '/notifications', label: '通知', icon: Bell },
  { path: '/settings', label: '设置', icon: Settings },
  { path: '/coach', label: '教练端', icon: BarChart3 },
  { path: '/judge', label: '裁判端', icon: Scale },
  { path: '/admin', label: '管理端', icon: Shield },
  { path: '/admin/problems', label: '题目管理', icon: FilePenLine },
  { path: '/admin/tags', label: '知识点', icon: Tags },
];

const roleLabel = computed(() => {
  const map = { student: '选手', coach: '教练', judge: '裁判', admin: '管理员' };
  return authState.user ? map[authState.user.role] : '未登录';
});

function isActive(path: string): boolean {
  if (path === '/') return route.path === '/';
  if (path === '/admin') return route.path === '/admin';
  return route.path.startsWith(path);
}

async function quickLogin(name: string) {
  username.value = name;
  password.value = 'gayoj123';
  await login(username.value, password.value);
}

onMounted(() => {
  void restoreSession();
});
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <RouterLink class="brand" to="/">
        <div class="brand-mark">ct</div>
        <div>
          <strong>gayoj</strong>
          <span>算法训练平台</span>
        </div>
      </RouterLink>

      <nav class="nav-list" aria-label="主导航">
        <RouterLink
          v-for="item in navItems"
          :key="item.path"
          :to="item.path"
          class="nav-item"
          :class="{ active: isActive(item.path) }"
        >
          <component :is="item.icon" :size="18" />
          <span>{{ item.label }}</span>
        </RouterLink>
      </nav>
    </aside>

    <div class="workspace">
      <header class="topbar">
        <div class="topbar-title">
          <Gauge :size="20" />
          <span>Online Judge Workspace</span>
        </div>
        <div v-if="authState.user" class="user-pill">
          <UserRound :size="17" />
          <span>{{ authState.user.display_name }}</span>
          <em>{{ roleLabel }}</em>
          <button class="icon-button" aria-label="退出登录" @click="logout">
            <LogOut :size="17" />
          </button>
        </div>
      </header>

      <section v-if="!authState.user" class="login-strip">
        <div>
          <strong>登录工作台</strong>
          <span>演示账号密码均为 gayoj123</span>
        </div>
        <form class="login-form" @submit.prevent="login(username, password)">
          <input v-model="username" aria-label="用户名" placeholder="用户名" />
          <input v-model="password" aria-label="密码" type="password" placeholder="密码" />
          <button type="submit" :disabled="authState.loading">登录</button>
        </form>
        <div class="quick-logins">
          <button type="button" @click="quickLogin('alice')">选手</button>
          <button type="button" @click="quickLogin('coach')">教练</button>
          <button type="button" @click="quickLogin('judge')">裁判</button>
          <button type="button" @click="quickLogin('admin')">管理</button>
        </div>
        <p v-if="authState.error" class="form-error">{{ authState.error }}</p>
      </section>

      <main class="content">
        <slot />
      </main>
    </div>
  </div>
</template>
