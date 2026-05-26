import { createApp } from 'vue';
import { createRouter, createWebHistory } from 'vue-router';
import App from './App.vue';
import AdminPage from './pages/AdminPage.vue';
import CoachPage from './pages/CoachPage.vue';
import ContestsPage from './pages/ContestsPage.vue';
import ContestBalloonPage from './pages/ContestBalloonPage.vue';
import ContestClarificationPage from './pages/ContestClarificationPage.vue';
import ContestExternalBoardPage from './pages/ContestExternalBoardPage.vue';
import ContestHomePage from './pages/ContestHomePage.vue';
import ContestJudgePage from './pages/ContestJudgePage.vue';
import ContestLiveBoardPage from './pages/ContestLiveBoardPage.vue';
import ContestProblemPage from './pages/ContestProblemPage.vue';
import ContestPrintPage from './pages/ContestPrintPage.vue';
import ContestRollingBoardPage from './pages/ContestRollingBoardPage.vue';
import ContestStandingsPage from './pages/ContestStandingsPage.vue';
import DashboardPage from './pages/DashboardPage.vue';
import DiscussPage from './pages/DiscussPage.vue';
import JudgePage from './pages/JudgePage.vue';
import JudgeClarificationPage from './pages/JudgeClarificationPage.vue';
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
    { path: '/contests/:id', component: ContestHomePage },
    { path: '/contests/:id/p/:problemId', component: ContestProblemPage },
    { path: '/contests/:id/standings', component: ContestStandingsPage, meta: { pure: true } },
    { path: '/contests/:id/external-board', component: ContestExternalBoardPage, meta: { pure: true } },
    { path: '/contests/:id/live-board', component: ContestLiveBoardPage, meta: { pure: true } },
    { path: '/contests/:id/rolling-board', component: ContestRollingBoardPage, meta: { pure: true } },
    { path: '/contests/:id/clar', component: ContestClarificationPage, meta: { pure: true } },
    { path: '/judge/monitor/:id', component: ContestJudgePage, meta: { pure: true } },
    { path: '/judge/balloons/:id', component: ContestBalloonPage, meta: { pure: true } },
    { path: '/judge/clar/:id', component: JudgeClarificationPage, meta: { pure: true } },
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
