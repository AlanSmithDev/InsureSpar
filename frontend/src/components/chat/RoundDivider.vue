<script setup lang="ts">
import { computed } from 'vue'
import { Icon } from '@iconify/vue'

type RoundState = 'idle' | 'ready' | 'processing' | 'error' | 'finished' | 'completed'

const props = defineProps<{
  turn: number
  state: RoundState
}>()

const stateMeta = computed(() => ({
  idle: { icon: 'lucide:circle-dashed', label: '等待中' },
  ready: { icon: 'lucide:circle-check', label: '已完成' },
  processing: { icon: 'lucide:loader-circle', label: '进行中' },
  error: { icon: 'lucide:circle-alert', label: '异常' },
  finished: { icon: 'lucide:flag', label: '对话结束' },
  completed: { icon: 'lucide:circle-check', label: '已完成' },
}[props.state]))
</script>

<template>
  <div class="round-progress" :class="`round-progress--${state}`">
    <span class="round-progress__line" aria-hidden="true" />
    <div class="round-progress__marker">
      <Icon
        :icon="stateMeta.icon"
        class="h-3.5 w-3.5"
        :class="state === 'processing' ? 'animate-spin' : ''"
        aria-hidden="true"
      />
      <span class="round-progress__round">Round {{ turn }}</span>
      <span class="round-progress__label">{{ stateMeta.label }}</span>
    </div>
    <span class="round-progress__line" aria-hidden="true" />
  </div>
</template>

<style scoped>
.round-progress {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  padding: 1.5rem 1rem;
  transition: color 180ms ease;
}

.round-progress__line {
  width: min(12vw, 5rem);
  height: 1px;
  background: currentColor;
  opacity: 0.22;
}

.round-progress__marker {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  border-radius: 9999px;
  padding: 0.35rem 0.75rem;
  background: var(--round-bg);
  color: var(--round-fg);
  font-size: 10px;
  line-height: 1rem;
  white-space: nowrap;
}

.round-progress__round {
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.round-progress__label {
  font-weight: 500;
  opacity: 0.82;
}

.round-progress--idle {
  --round-bg: #f4f5f5;
  --round-fg: #87918c;
  color: #87918c;
}

.round-progress--ready,
.round-progress--completed {
  --round-bg: #eef8f2;
  --round-fg: #5f806d;
  color: #82a28f;
}

.round-progress--processing {
  --round-bg: #fff6e6;
  --round-fg: #956d2e;
  color: #d1aa67;
}

.round-progress--error {
  --round-bg: #fff0f0;
  --round-fg: #a65e5e;
  color: #d59a9a;
}

.round-progress--finished {
  --round-bg: #eef3f6;
  --round-fg: #607786;
  color: #94a9b5;
}
</style>
