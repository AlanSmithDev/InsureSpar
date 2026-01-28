<script setup lang="ts">
import type { AppStatus, Persona } from '../../types'
import StatusDot from '../common/StatusDot.vue'
import RichText from '../common/RichText.vue'
import { Icon } from '@iconify/vue'
import { DEFAULT_AVATAR, personaAvatar } from '../../utils/avatar'

defineProps<{
  status: AppStatus
  statusText: string
  activePersona?: Persona | null
  showBackButton?: boolean
  evalOpen?: boolean
}>()

defineEmits<{
  (e: 'new-session'): void
  (e: 'show-history'): void
  (e: 'show-dashboard'): void
  (e: 'show-settings'): void
  (e: 'back'): void
  (e: 'toggle-evaluation'): void
}>()
</script>

<template>
  <div class="flex min-h-11 w-full items-center justify-between gap-3">
    <div class="group/persona relative min-w-0">
      <button
        type="button"
        class="flex min-w-0 items-center gap-2 rounded-xl p-1 text-left transition-colors hover:bg-[var(--color-surface)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]/30"
        :aria-label="activePersona ? `对练对象：${activePersona.name}` : '对练对象：未选择'"
        title="查看对练对象资料"
      >
        <span class="grid h-10 w-10 shrink-0 place-items-center overflow-hidden rounded-xl bg-[var(--color-accent-soft)] text-[var(--color-accent-dark)]">
          <img v-if="personaAvatar(activePersona)" :src="personaAvatar(activePersona)" :alt="`${activePersona?.name || '对练对象'}头像`" class="h-full w-full object-cover" />
          <img v-else :src="DEFAULT_AVATAR" alt="默认对练对象头像" class="h-full w-full object-cover" />
        </span>
        <span class="min-w-0">
          <span class="block max-w-[180px] truncate text-sm font-semibold text-[var(--color-text-primary)]">{{ activePersona?.name || '对练对象' }}</span>
          <span class="mt-0.5 flex items-center gap-1.5 text-[11px] text-[var(--color-text-muted)]">
            <StatusDot :status="status" />
            <RichText :text="activePersona?.description || statusText" class="max-w-[180px] truncate sm:max-w-[300px]" />
          </span>
        </span>
      </button>

      <div
        v-if="activePersona"
        class="pointer-events-none absolute left-0 top-full z-50 mt-0 w-[300px] rounded-2xl bg-white p-4 opacity-0 shadow-[var(--shadow-modal)] transition-opacity duration-150 group-hover/persona:pointer-events-auto group-hover/persona:opacity-100 group-focus-within/persona:pointer-events-auto group-focus-within/persona:opacity-100"
      >
        <div class="flex items-center gap-3">
          <img :src="personaAvatar(activePersona)" :alt="`${activePersona.name}头像`" class="h-12 w-12 rounded-xl object-cover" />
          <div class="min-w-0">
            <p class="truncate text-sm font-semibold text-[var(--color-text-primary)]">{{ activePersona.name }}</p>
            <p class="mt-1 text-[11px] text-[var(--color-text-muted)]">{{ activePersona.difficulty || '常规' }} · 对练对象</p>
          </div>
        </div>
        <p class="mt-3 text-xs leading-5 text-[var(--color-text-secondary)]">{{ activePersona.description }}</p>
        <div v-if="activePersona.tags?.length" class="mt-3 flex flex-wrap gap-1.5">
          <span v-for="tag in activePersona.tags" :key="tag" class="rounded-md bg-[var(--color-accent-soft)] px-2 py-1 text-[10px] text-[var(--color-accent-dark)]">{{ tag }}</span>
        </div>
      </div>
    </div>

    <div class="flex shrink-0 items-center gap-2">
      <button
        type="button"
        aria-label="历史记录"
        title="历史记录"
        class="grid h-9 w-9 place-items-center rounded-full text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface)] hover:text-[var(--color-text-primary)]"
        @click="$emit('show-history')"
      >
        <Icon icon="lucide:history" class="h-4 w-4" />
      </button>

      <button
        type="button"
        aria-label="实时反馈"
        title="实时反馈"
        :aria-expanded="evalOpen"
        class="grid h-9 w-9 place-items-center rounded-full text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface)] hover:text-[var(--color-text-primary)]"
        :class="evalOpen ? 'bg-[var(--color-accent-soft)] text-[var(--color-accent-dark)]' : ''"
        @click="$emit('toggle-evaluation')"
      >
        <Icon icon="lucide:list-checks" class="h-4 w-4" />
      </button>

      <button
        type="button"
        aria-label="设置"
        title="设置"
        class="grid h-9 w-9 place-items-center rounded-full text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface)] hover:text-[var(--color-text-primary)]"
        @click="$emit('show-settings')"
      >
        <Icon icon="lucide:settings" class="h-4 w-4" />
      </button>

      <button
        type="button"
        class="flex h-9 items-center gap-2 rounded-lg bg-[var(--color-accent)] px-3 text-xs font-semibold text-white transition-colors hover:bg-[var(--color-accent-hover)] sm:px-4"
        @click="$emit('new-session')"
      >
        <Icon icon="lucide:message-square-plus" class="h-4 w-4" />
        <span class="hidden sm:inline">新建对练</span>
      </button>
    </div>
  </div>
</template>
