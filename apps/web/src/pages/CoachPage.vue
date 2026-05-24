<script setup lang="ts">
import { ClipboardCheck, Plus, UsersRound } from 'lucide-vue-next';
import { onMounted, reactive, ref } from 'vue';
import { apiRequest } from '@/services/api';
import type { ProblemSet, Team } from '@/services/types';

const data = ref<Record<string, any> | null>(null);
const problemSets = ref<ProblemSet[]>([]);
const error = ref('');
const teamForm = reactive({ name: '', description: '' });
const assignmentForm = reactive({
  title: '',
  description: '',
  problem_set_id: '',
  team_id: '',
  due_at: '',
});

async function load() {
  try {
    const [analytics, sets] = await Promise.all([
      apiRequest('/coach/analytics'),
      apiRequest<ProblemSet[]>('/problem-sets', { auth: false }),
    ]);
    data.value = analytics as Record<string, any>;
    problemSets.value = sets;
    assignmentForm.problem_set_id ||= sets[0]?.id ?? '';
    assignmentForm.team_id ||= data.value.teams?.[0]?.id ?? '';
  } catch (err) {
    error.value = err instanceof Error ? err.message : '需要教练或管理员权限。';
  }
}

async function createTeam() {
  error.value = '';
  try {
    await apiRequest<Team>('/teams', {
      method: 'POST',
      body: JSON.stringify({ ...teamForm, member_ids: ['u-student'] }),
    });
    teamForm.name = '';
    teamForm.description = '';
    await load();
  } catch (err) {
    error.value = err instanceof Error ? err.message : '创建队伍失败。';
  }
}

async function createAssignment() {
  error.value = '';
  try {
    await apiRequest('/assignments', {
      method: 'POST',
      body: JSON.stringify({
        ...assignmentForm,
        team_id: assignmentForm.team_id || null,
        due_at: new Date(assignmentForm.due_at).toISOString(),
      }),
    });
    assignmentForm.title = '';
    assignmentForm.description = '';
    await load();
  } catch (err) {
    error.value = err instanceof Error ? err.message : '创建作业失败。';
  }
}

onMounted(load);
</script>

<template>
  <div class="page-stack">
    <section class="page-heading">
      <div>
        <span class="eyebrow">Coach Console</span>
        <h1>教练端</h1>
      </div>
    </section>

    <p v-if="error" class="form-error">{{ error }}</p>

    <template v-if="data">
      <section class="metric-grid">
        <article class="metric-panel">
          <UsersRound :size="20" />
          <span>学生规模</span>
          <strong>{{ data.class_size }}</strong>
        </article>
        <article class="metric-panel">
          <ClipboardCheck :size="20" />
          <span>活跃学生</span>
          <strong>{{ data.active_students }}</strong>
        </article>
      </section>

      <section class="dashboard-grid">
        <div class="panel">
          <div class="panel-head">
            <div>
              <h2>训练作业</h2>
              <p>截止时间与完成率</p>
            </div>
          </div>
          <div class="list-stack">
            <div v-for="item in data.assignments" :key="item.id" class="assignment-row">
              <strong>{{ item.title }}</strong>
              <span>{{ item.problem_set_title }} · {{ item.due_at }}</span>
              <div class="bar-track"><i :style="{ width: `${item.completion * 100}%` }"></i></div>
            </div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-head">
            <div>
              <h2>知识点掌握</h2>
              <p>由提交记录聚合</p>
            </div>
          </div>
          <div class="type-stat-list">
            <div v-for="item in data.tag_mastery" :key="item.tag" class="type-stat-row">
              <span>{{ item.tag }}</span>
              <div class="bar-track">
                <i :style="{ width: `${item.attempts ? (item.accepted / item.attempts) * 100 : 0}%` }"></i>
              </div>
              <strong>{{ item.accepted }}/{{ item.attempts }}</strong>
            </div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-head">
            <div>
              <h2>队伍管理</h2>
              <p>创建班级/队伍邀请码</p>
            </div>
          </div>
          <div class="list-stack">
            <div v-for="team in data.teams" :key="team.id" class="user-row">
              <strong>{{ team.name }}</strong>
              <span>{{ team.description }} · 邀请码 {{ team.invite_code }}</span>
              <b>{{ team.member_ids.length }} 人</b>
            </div>
          </div>
          <form class="submit-form" @submit.prevent="createTeam">
            <label>队伍名<input v-model="teamForm.name" required placeholder="新训练班" /></label>
            <label>描述<input v-model="teamForm.description" placeholder="队伍说明" /></label>
            <button class="secondary-action full" type="submit"><Plus :size="17" />创建队伍</button>
          </form>
        </div>

        <div class="panel">
          <div class="panel-head">
            <div>
              <h2>布置作业</h2>
              <p>基于题单发布训练任务</p>
            </div>
          </div>
          <form class="submit-form" @submit.prevent="createAssignment">
            <label>标题<input v-model="assignmentForm.title" required placeholder="作业标题" /></label>
            <label>题单<select v-model="assignmentForm.problem_set_id">
              <option v-for="set in problemSets" :key="set.id" :value="set.id">{{ set.title }}</option>
            </select></label>
            <label>队伍<select v-model="assignmentForm.team_id">
              <option value="">全部学生</option>
              <option v-for="team in data.teams" :key="team.id" :value="team.id">{{ team.name }}</option>
            </select></label>
            <label>截止时间<input v-model="assignmentForm.due_at" required type="datetime-local" /></label>
            <label>说明<textarea v-model="assignmentForm.description" rows="3"></textarea></label>
            <button class="primary-action full" type="submit"><Plus :size="17" />发布作业</button>
          </form>
        </div>
      </section>
    </template>
  </div>
</template>
