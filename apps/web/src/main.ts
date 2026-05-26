import { createApp } from 'vue';
import { createRouter, createWebHistory } from 'vue-router';
import App from './App.vue';
import AdminPage from './pages/AdminPage.vue';
import CoachPage from './pages/CoachPage.vue';
import ContestsPage from './pages/ContestsPage.vue';
import ContestBalloonPage from './pages/ContestBalloonPage.vue';
import ContestClarificationPage from './pages/ContestClarificationPage.vue';
import ContestJudgePage from './pages/ContestJudgePage.vue';
import ContestPrintPage from './pages/ContestPrintPage.vue';
import ContestStandingsPage from './pages/ContestStandingsPage.vue';
import ContestSubmissionsPage from './pages/ContestSubmissionsPage.vue';
import DashboardPage from './pages/DashboardPage.vue';
import DiscussPage from './pages/DiscussPage.vue';
import JudgePage from './pages/JudgePage.vue';
import NotificationsPage from './pages/NotificationsPage.vue';
import ProblemDetailPage from './pages/ProblemDetailPage.vue';
import ProblemManagePage from './pages/ProblemManagePage.vue';
import ProblemSetsPage from './pages/ProblemSetsPage.vue';
import ProblemsPage from './pages/ProblemsPage.vue';
import ProfileSettingsPage from './pages/ProfileSettingsPage.vue';
import RankingsPage from './pages/RankingsPage.vue';
import SubmissionsPage from './pages/SubmissionsPage.vue';
import TagManagePage from './pages/TagManagePage.vue';
import './styles.css';

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: DashboardPage },
    { path: '/problems', component: ProblemsPage },
    { path: '/problems/:id', component: ProblemDetailPage },
    { path: '/problem-sets', component: ProblemSetsPage },
    { path: '/contests', component: ContestsPage },
    { path: '/contests/:id/standings', component: ContestStandingsPage, meta: { pure: true } },
    { path: '/contests/:id/submissions', component: ContestSubmissionsPage, meta: { pure: true } },
    { path: '/contests/:id/clar', component: ContestClarificationPage, meta: { pure: true } },
    { path: '/judge/monitor/:id', component: ContestJudgePage, meta: { pure: true } },
    { path: '/judge/balloons/:id', component: ContestBalloonPage, meta: { pure: true } },
    { path: '/contests/:id/print', component: ContestPrintPage, meta: { pure: true } },
    { path: '/submissions', component: SubmissionsPage },
    { path: '/rankings', component: RankingsPage },
    { path: '/discuss', component: DiscussPage },
    { path: '/notifications', component: NotificationsPage },
    { path: '/settings', component: ProfileSettingsPage },
    { path: '/coach', component: CoachPage },
    { path: '/judge', component: JudgePage },
    { path: '/admin', component: AdminPage },
    { path: '/admin/problems', component: ProblemManagePage },
    { path: '/admin/tags', component: TagManagePage },
  ],
});

createApp(App).use(router).mount('#app');
