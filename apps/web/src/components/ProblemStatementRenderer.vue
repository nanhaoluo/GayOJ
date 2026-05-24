<script setup lang="ts">
import 'highlight.js/styles/github.css';
import 'katex/dist/katex.min.css';
import { computed } from 'vue';
import { renderMarkdown } from '@/services/markdown';

const props = withDefaults(
  defineProps<{
    source: string;
    compact?: boolean;
    ariaLabel?: string;
  }>(),
  {
    compact: false,
    ariaLabel: '题面内容',
  },
);

const rendered = computed(() => renderMarkdown(props.source));
</script>

<template>
  <div
    class="markdown-body"
    :class="{ 'markdown-body-compact': compact }"
    :aria-label="ariaLabel"
    v-html="rendered"
  />
</template>
