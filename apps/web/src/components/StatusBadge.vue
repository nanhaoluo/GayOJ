<script setup lang="ts">
defineProps<{ status: string }>();

function label(status: string): string {
  const labels: Record<string, string> = {
    accepted: 'AC',
    wrong_answer: 'WA',
    time_limit_exceeded: 'TLE',
    memory_limit_exceeded: 'MLE',
    output_limit_exceeded: 'OLE',
    compile_error: 'CE',
    runtime_error: 'RE',
    system_error: 'SE',
    queued: 'Queued',
    judging: 'Judging',
    manual_override: 'Override',
    running: '进行中',
    scheduled: '未开始',
    ended: '已结束',
    online: '在线',
    offline: '离线',
    draining: '下线中',
    pending: '待调度',
    leased: '已分配',
    completed: '已完成',
    failed: '失败',
  };
  return labels[status] ?? status;
}
</script>

<template>
  <span class="status-badge" :class="`status-${status}`">{{ label(status) }}</span>
</template>
