<script setup lang="ts">
import { Braces, CheckSquare, CircleDot, Keyboard } from 'lucide-vue-next';
import { computed } from 'vue';
import type { ProblemType } from '@/services/types';

const props = defineProps<{ type: ProblemType }>();

const icon = computed(() => {
  if (props.type === 'code') return Braces;
  if (props.type === 'blank') return Keyboard;
  if (props.type === 'single_choice') return CircleDot;
  return CheckSquare;
});
</script>

<template>
  <span class="type-icon" :class="`type-${type}`">
    <component :is="icon" :size="17" />
  </span>
</template>
