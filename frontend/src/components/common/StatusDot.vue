<script setup lang="ts">
defineProps<{
  status: 'idle' | 'ready' | 'processing' | 'error' | 'finished'
}>()
</script>

<template>
  <span class="relative flex h-2.5 w-2.5 shrink-0 items-center justify-center">
    <span
      v-if="status === 'ready' || status === 'processing'"
      class="animate-ping absolute inline-flex h-full w-full rounded-full opacity-60"
      :class="{
        'bg-emerald-400': status === 'ready',
        'bg-amber-400': status === 'processing'
      }"
    />

    <span
      class="relative inline-flex rounded-full h-2 w-2"
      :class="{
        'bg-zinc-300': status === 'idle',
        'bg-emerald-500': status === 'ready',
        'bg-amber-500': status === 'processing',
        'bg-rose-500': status === 'error',
        'bg-zinc-800': status === 'finished',
      }"
    />
  </span>
</template>
