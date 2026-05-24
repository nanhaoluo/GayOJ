<script setup lang="ts">
import { BadgeCheck, KeyRound, Mail, Save, School, UserRoundCog } from 'lucide-vue-next';
import { computed, onMounted, reactive, ref } from 'vue';
import { apiRequest } from '@/services/api';
import type { PasswordChangeRequest, PublicUser, UserProfile, UserProfileUpdate } from '@/services/types';
import { setCurrentUser } from '@/stores/auth';

const defaultStudentSchool = 'GayOJ University (GOJU)';
const profile = ref<UserProfile | null>(null);
const loading = ref(true);
const saving = ref(false);
const changingPassword = ref(false);
const error = ref('');
const saved = ref('');
const passwordError = ref('');
const passwordSaved = ref('');
const form = reactive({
  display_name: '',
  school: '',
  email: '',
});
const passwordForm = reactive({
  current_password: '',
  new_password: '',
  confirm_password: '',
});

const roleLabel = computed(() => {
  const map = { student: '选手', coach: '教练', judge: '裁判', admin: '管理员' };
  return profile.value ? map[profile.value.role] : '-';
});
const isStudent = computed(() => profile.value?.role === 'student');

const initials = computed(() => {
  const name = profile.value?.display_name || profile.value?.username || 'ct';
  return name.slice(0, 2).toUpperCase();
});

async function loadProfile() {
  loading.value = true;
  error.value = '';
  saved.value = '';
  try {
    const data = await apiRequest<UserProfile>('/users/me/profile');
    profile.value = data;
    form.display_name = data.display_name;
    form.school = data.school;
    form.email = data.email;
  } catch (err) {
    error.value = err instanceof Error ? err.message : '请先登录后再打开个人设置。';
  } finally {
    loading.value = false;
  }
}

async function saveProfile() {
  saving.value = true;
  error.value = '';
  saved.value = '';
  const update: UserProfileUpdate = {
    display_name: form.display_name,
    school: form.school,
    email: form.email,
  };
  try {
    const data = await apiRequest<UserProfile>('/users/me/profile', {
      method: 'PATCH',
      body: JSON.stringify(update),
    });
    profile.value = data;
    setCurrentUser(data);
    saved.value = '资料已更新';
  } catch (err) {
    error.value = err instanceof Error ? err.message : '保存失败';
  } finally {
    saving.value = false;
  }
}

async function changePassword() {
  passwordError.value = '';
  passwordSaved.value = '';
  if (passwordForm.new_password !== passwordForm.confirm_password) {
    passwordError.value = '两次输入的新密码不一致';
    return;
  }
  changingPassword.value = true;
  const payload: PasswordChangeRequest = {
    current_password: passwordForm.current_password,
    new_password: passwordForm.new_password,
  };
  try {
    const data = await apiRequest<PublicUser>('/users/me/password', {
      method: 'PUT',
      body: JSON.stringify(payload),
    });
    setCurrentUser(data);
    passwordForm.current_password = '';
    passwordForm.new_password = '';
    passwordForm.confirm_password = '';
    passwordSaved.value = '密码已更新';
  } catch (err) {
    passwordError.value = err instanceof Error ? err.message : '密码更新失败';
  } finally {
    changingPassword.value = false;
  }
}

onMounted(loadProfile);
</script>

<template>
  <div class="page-stack">
    <section class="page-heading">
      <div>
        <span class="eyebrow">Account</span>
        <h1>个人设置</h1>
      </div>
    </section>

    <p v-if="error" class="form-error">{{ error }}</p>
    <p v-if="saved" class="result-panel">{{ saved }}</p>

    <section v-if="profile && !loading" class="profile-layout">
      <article class="panel profile-summary">
        <div class="profile-avatar">{{ initials }}</div>
        <div>
          <h2>{{ profile.display_name }}</h2>
          <p>{{ profile.username }} · {{ roleLabel }}</p>
        </div>
        <div class="profile-stat-grid">
          <div>
            <span>Rating</span>
            <strong>{{ profile.rating }}</strong>
          </div>
          <div>
            <span>Accepted</span>
            <strong>{{ profile.solved }}</strong>
          </div>
        </div>
        <div class="profile-meta-list">
          <span><BadgeCheck :size="16" />{{ profile.permissions.length }} permissions</span>
          <span><School :size="16" />{{ profile.school || (isStudent ? defaultStudentSchool : '未填写学校/组织') }}</span>
          <span><Mail :size="16" />{{ profile.email || '未填写邮箱' }}</span>
        </div>
      </article>

      <article class="panel form-panel">
        <div class="panel-head">
          <div>
            <h2>资料</h2>
            <p>{{ isStudent ? '选手默认挂靠 GOJU，可自行更改学校' : '展示名称、组织和联系邮箱' }}</p>
          </div>
          <UserRoundCog :size="20" />
        </div>
        <form class="submit-form" @submit.prevent="saveProfile">
          <label>展示名称<input v-model="form.display_name" required maxlength="80" /></label>
          <label>
            {{ isStudent ? '学校' : '组织' }}
            <input v-model="form.school" :placeholder="isStudent ? defaultStudentSchool : '未填写组织'" maxlength="120" />
          </label>
          <label>邮箱<input v-model="form.email" type="email" maxlength="254" /></label>
          <button class="primary-action full" type="submit" :disabled="saving">
            <Save :size="17" />
            {{ saving ? '保存中' : '保存' }}
          </button>
        </form>
      </article>

      <article class="panel form-panel">
        <div class="panel-head">
          <div>
            <h2>密码</h2>
            <p>按当前密码策略更新登录密码</p>
          </div>
          <KeyRound :size="20" />
        </div>
        <p v-if="passwordError" class="form-error">{{ passwordError }}</p>
        <p v-if="passwordSaved" class="form-success">{{ passwordSaved }}</p>
        <form class="submit-form" @submit.prevent="changePassword">
          <label>当前密码<input v-model="passwordForm.current_password" type="password" required maxlength="256" /></label>
          <label>新密码<input v-model="passwordForm.new_password" type="password" required maxlength="256" /></label>
          <label>确认新密码<input v-model="passwordForm.confirm_password" type="password" required maxlength="256" /></label>
          <button class="primary-action full" type="submit" :disabled="changingPassword">
            <Save :size="17" />
            {{ changingPassword ? '更新中' : '更新密码' }}
          </button>
        </form>
      </article>
    </section>

    <section v-else-if="loading" class="panel">
      <p class="empty-text">加载中...</p>
    </section>
  </div>
</template>
