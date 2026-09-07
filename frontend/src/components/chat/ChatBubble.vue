<script setup lang="ts">
import { computed, ref } from 'vue'
import { Icon } from '@iconify/vue'
import type { ChatMessage, Persona } from '../../types'
import MarkdownText from '../common/MarkdownText.vue'
import RichText from '../common/RichText.vue'
import { personaAvatar } from '../../utils/avatar'

const props = defineProps<{
  message: ChatMessage
  activePersona?: Persona | null
}>()

const feedback = ref<'helpful' | 'improve' | null>(null)
const copied = ref(false)

const toolCatalog: Record<string, { label: string; action: string; icon: string }> = {
  search_insurance_knowledge: {
    label: '保险知识检索',
    action: '正在查询本轮相关保险条款与参考信息',
    icon: 'lucide:search',
  },
  query_premium_rate: {
    label: '保费测算',
    action: '正在根据客户信息与投保方案测算保费',
    icon: 'lucide:calculator',
  },
  query_cash_value: {
    label: '现金价值测算',
    action: '正在计算指定保单年度的现金价值',
    icon: 'lucide:chart-no-axes-combined',
  },
}

const isToolEvent = computed(() => (
  props.message.logType === 'tool_call' || props.message.logType === 'tool_result'
))

const toolName = computed(() => props.message.toolName || 'unknown_tool')
const toolInfo = computed(() => toolCatalog[toolName.value] || {
  label: toolName.value.split('_').filter(Boolean).join(' '),
  action: '正在准备本轮对话所需信息',
  icon: 'lucide:wrench',
})

const messageHasError = computed(() => /失败|错误|异常|不存在|未能完成/.test(props.message.content))
const stageIsFinished = computed(() => /训练完成|对话结束|最终状态/.test(props.message.content))

function buildToolResultSummary() {
  const content = props.message.content
  const label = toolInfo.value.label
  if (/失败|错误|不存在/.test(content)) return `${label}未能完成，请查看返回信息`

  const referenceCount = content.match(/找到最相关的\s*(\d+)\s*条/)
  if (referenceCount?.[1]) return `${label}已准备 ${referenceCount[1]} 条参考信息`

  const premium = content.match(/每年保费[:：]\s*([\d.]+)\s*元/)
  if (premium?.[1]) return `${label}已返回年缴保费 ${premium[1]} 元`

  const cashValue = content.match(/现金价值约[:：]\s*(\d+)\s*元/)
  if (cashValue?.[1]) return `${label}已返回预计现金价值 ${cashValue[1]} 元`

  return `${label}已返回本轮参考信息`
}

const toolSummary = computed(() => props.message.logType === 'tool_call'
  ? toolInfo.value.action
  : buildToolResultSummary())

const toolArguments = computed(() => {
  const args = props.message.toolArgs?.trim()
  if (!args) return ''
  return args
    .replace(/[{}]/g, '')
    .replace(/['"]/g, '')
    .replace(/,\s*/g, ' · ')
    .replace(/:/g, '：')
})

const systemMeta = computed(() => {
  switch (props.message.logType) {
    case 'tool_call':
      return {
        icon: toolInfo.value.icon,
        label: toolInfo.value.label,
        summary: toolSummary.value,
        foldLabel: '查看调用信息',
        tone: 'processing',
      }
    case 'tool_result':
      return {
        icon: messageHasError.value ? 'lucide:circle-alert' : 'lucide:circle-check',
        label: toolInfo.value.label,
        summary: toolSummary.value,
        foldLabel: '查看返回信息',
        tone: messageHasError.value ? 'error' : 'success',
      }
    case 'force_guard':
      return {
        icon: 'lucide:shield-alert',
        label: '训练提示',
        summary: props.message.content.includes('失败') || props.message.content.includes('错误')
          ? '本轮处理遇到问题，请稍后重试'
          : '先回应客户的真实顾虑，再自然推进下一步',
        foldLabel: '查看内部策略',
        tone: messageHasError.value ? 'error' : 'warning',
      }
    case 'stage_update':
      return {
        icon: stageIsFinished.value ? 'lucide:flag' : 'lucide:circle-dot-dashed',
        label: '对话进展',
        summary: props.message.content,
        foldLabel: '',
        tone: stageIsFinished.value ? 'finished' : 'progress',
      }
    default:
      return {
        icon: 'lucide:info',
        label: '系统动态',
        summary: props.message.content,
        foldLabel: '',
        tone: 'neutral',
      }
  }
})

const hasInternalDetail = computed(() => Boolean(
  !isToolEvent.value && systemMeta.value.foldLabel && props.message.content !== systemMeta.value.summary,
))

function setFeedback(value: 'helpful' | 'improve') {
  feedback.value = feedback.value === value ? null : value
}

async function copyMessage() {
  try {
    await navigator.clipboard.writeText(props.message.content)
  } catch {
    const textarea = document.createElement('textarea')
    textarea.value = props.message.content
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.select()
    document.execCommand('copy')
    textarea.remove()
  }
  copied.value = true
  window.setTimeout(() => { copied.value = false }, 1600)
}
</script>

<template>
  <div
    v-if="message.role === 'system'"
    class="system-event animate-fade-in"
    :class="`system-event--${systemMeta.tone}`"
  >
    <details v-if="isToolEvent" class="system-tool group/tool">
      <summary class="system-event__capsule system-event__capsule--interactive">
        <span class="system-event__icon" aria-hidden="true">
          <Icon :icon="systemMeta.icon" class="h-3.5 w-3.5" :class="message.logType === 'tool_call' ? 'animate-pulse' : ''" />
        </span>
        <span>{{ systemMeta.summary }}</span>
        <Icon icon="lucide:chevron-right" class="h-3 w-3 shrink-0 transition-transform group-open/tool:rotate-90" aria-hidden="true" />
      </summary>
      <div class="system-tool__detail">
        <div class="system-tool__heading">
          <Icon :icon="systemMeta.icon" class="h-3.5 w-3.5" aria-hidden="true" />
          {{ systemMeta.foldLabel }}
        </div>
        <dl class="system-tool__grid">
          <dt>工具</dt>
          <dd>{{ toolInfo.label }}</dd>
          <template v-if="message.logType === 'tool_call' && toolArguments">
            <dt>参数</dt>
            <dd>{{ toolArguments }}</dd>
          </template>
          <template v-if="message.logType === 'tool_result'">
            <dt>结果</dt>
            <dd class="whitespace-pre-wrap break-words">{{ message.content }}</dd>
          </template>
        </dl>
      </div>
    </details>

    <div v-else class="system-event__capsule">
      <span class="system-event__icon" aria-hidden="true">
        <Icon :icon="systemMeta.icon" class="h-3.5 w-3.5" />
      </span>
      <span>{{ systemMeta.label }}</span>
      <RichText :text="systemMeta.summary" />
    </div>
    <details v-if="hasInternalDetail" class="group/details mt-1 text-[11px] text-zinc-400">
        <summary class="inline-flex cursor-pointer list-none items-center gap-1 rounded px-1 py-0.5 hover:bg-zinc-100 hover:text-zinc-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/30">
          <Icon icon="lucide:chevron-right" class="h-3 w-3 transition-transform group-open/details:rotate-90" />
          {{ systemMeta.foldLabel }}
        </summary>
        <div class="mt-1 border-l border-zinc-200 pl-3 font-mono leading-5 text-zinc-500 break-words">
          <span v-if="message.toolName">工具：{{ message.toolName }}<br /></span>
          {{ message.content }}
        </div>
    </details>
  </div>

  <div v-else-if="message.role === 'sales'" class="group flex w-full flex-row-reverse gap-3 mb-5 animate-fade-in-up">
    <div class="shrink-0 mt-1">
      <div class="w-9 h-9 rounded-full overflow-hidden shadow-sm border border-white">
        <img src="/insurespar_logo.png" alt="InsureSpar" class="w-full h-full object-cover" />
      </div>
    </div>

    <div class="flex min-w-0 max-w-[78%] flex-col items-end pt-1 sm:max-w-[72%]">
      <div class="message-bubble message-bubble--sales">
        <MarkdownText v-if="message.content" :text="message.content" />
        <span v-if="message.isStreaming && !message.content" class="typing-indicator typing-indicator--sales" aria-label="销售正在回复">
          <span />
          <span />
          <span />
        </span>
      </div>
      <div v-if="message.content && !message.isStreaming" class="message-actions" role="toolbar" aria-label="消息操作">
        <button type="button" :class="{ 'is-active': feedback === 'helpful' }" title="这条回复有帮助" aria-label="这条回复有帮助" @click="setFeedback('helpful')">
          <Icon icon="lucide:thumbs-up" />
        </button>
        <button type="button" :class="{ 'is-active is-negative': feedback === 'improve' }" title="这条回复需要改进" aria-label="这条回复需要改进" @click="setFeedback('improve')">
          <Icon icon="lucide:thumbs-down" />
        </button>
        <button type="button" :title="copied ? '已复制' : '复制消息'" :aria-label="copied ? '已复制' : '复制消息'" @click="copyMessage">
          <Icon :icon="copied ? 'lucide:check' : 'lucide:copy'" />
        </button>
      </div>
    </div>
  </div>

  <div v-else-if="message.role === 'customer'" class="group flex w-full gap-3 mb-5 animate-fade-in-up">
    <div class="shrink-0 mt-1">
      <div class="w-9 h-9 rounded-full bg-gray-100 flex items-center justify-center shadow-sm border border-white overflow-hidden">
        <img v-if="personaAvatar(activePersona)" :src="personaAvatar(activePersona)" alt="客户头像" class="w-full h-full object-cover" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';" />
        <div :style="{ display: personaAvatar(activePersona) ? 'none' : 'flex' }" class="w-full h-full items-center justify-center text-gray-400">
          <Icon icon="lucide:user-round" class="h-4 w-4" />
        </div>
      </div>
    </div>

    <div class="flex min-w-0 max-w-[78%] flex-col items-start sm:max-w-[72%]">
      <div class="mb-1.5 ml-1 text-[12px] font-normal text-gray-400">{{ activePersona?.name || '客户' }}</div>
      <div class="message-bubble message-bubble--customer">
        <MarkdownText v-if="message.content" :text="message.content" />
        <span v-if="message.isStreaming && !message.content" class="typing-indicator typing-indicator--customer" aria-label="客户正在回复">
          <span />
          <span />
          <span />
        </span>
      </div>
      <div v-if="message.content && !message.isStreaming" class="message-actions" role="toolbar" aria-label="消息操作">
        <button type="button" :class="{ 'is-active': feedback === 'helpful' }" title="这条回复有帮助" aria-label="这条回复有帮助" @click="setFeedback('helpful')">
          <Icon icon="lucide:thumbs-up" />
        </button>
        <button type="button" :class="{ 'is-active is-negative': feedback === 'improve' }" title="这条回复需要改进" aria-label="这条回复需要改进" @click="setFeedback('improve')">
          <Icon icon="lucide:thumbs-down" />
        </button>
        <button type="button" :title="copied ? '已复制' : '复制消息'" :aria-label="copied ? '已复制' : '复制消息'" @click="copyMessage">
          <Icon :icon="copied ? 'lucide:check' : 'lucide:copy'" />
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.system-event {
  --event-bg: #f5f6f6;
  --event-hover-bg: #eef0ef;
  --event-fg: #737e78;
  --event-icon-bg: #e9ecea;
  --event-icon-fg: #69746e;
  --event-detail-bg: #f7f8f8;
  display: flex;
  width: min(100%, 720px);
  flex-direction: column;
  align-items: center;
  margin: 0.25rem auto 0.875rem;
}

.system-event__capsule {
  display: inline-flex;
  max-width: 100%;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 0.25rem 0.5rem;
  border-radius: 9999px;
  background: var(--event-bg);
  padding: 0.35rem 0.875rem;
  color: var(--event-fg);
  font-size: 12px;
  font-weight: 400;
  line-height: 1.25rem;
  text-align: center;
}

.system-event__capsule--interactive {
  cursor: pointer;
  list-style: none;
  transition: background-color 150ms ease, color 150ms ease;
}

.system-event__capsule--interactive::-webkit-details-marker {
  display: none;
}

.system-event__capsule--interactive:hover {
  background: var(--event-hover-bg);
}

.system-event__icon {
  display: inline-grid;
  width: 1.25rem;
  height: 1.25rem;
  flex: 0 0 1.25rem;
  place-items: center;
  border-radius: 9999px;
  background: var(--event-icon-bg);
  color: var(--event-icon-fg);
}

.system-tool {
  display: flex;
  max-width: min(100%, 680px);
  flex-direction: column;
  align-items: center;
}

.system-tool__detail {
  width: min(calc(100vw - 3rem), 620px);
  margin-top: 0.45rem;
  border-radius: 14px;
  background: var(--event-detail-bg);
  padding: 0.75rem 0.875rem;
  color: var(--event-fg);
  text-align: left;
}

.system-tool__heading {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  margin-bottom: 0.625rem;
  color: var(--event-fg);
  font-size: 12px;
}

.system-tool__grid {
  display: grid;
  grid-template-columns: 2.5rem minmax(0, 1fr);
  gap: 0.45rem 0.625rem;
  font-size: 12px;
  line-height: 1.65;
}

.system-tool__grid dt {
  color: var(--event-fg);
  opacity: 0.62;
}

.system-tool__grid dd {
  min-width: 0;
  color: var(--event-fg);
}

.system-event--progress {
  --event-bg: #f1f6fa;
  --event-hover-bg: #eaf2f7;
  --event-fg: #667f90;
  --event-icon-bg: #e4eef5;
  --event-icon-fg: #5f7f93;
  --event-detail-bg: #f5f8fa;
}

.system-event--processing {
  --event-bg: #fff7e8;
  --event-hover-bg: #fff1d4;
  --event-fg: #8c6a31;
  --event-icon-bg: #ffedc5;
  --event-icon-fg: #9b701f;
  --event-detail-bg: #fffbf3;
}

.system-event--success {
  --event-bg: #edf8f5;
  --event-hover-bg: #e3f3ee;
  --event-fg: #5c7f73;
  --event-icon-bg: #dff0ea;
  --event-icon-fg: #4f806f;
  --event-detail-bg: #f4faf8;
}

.system-event--warning {
  --event-bg: #fff4eb;
  --event-hover-bg: #ffeadb;
  --event-fg: #946d4d;
  --event-icon-bg: #ffe5d2;
  --event-icon-fg: #a26a3d;
  --event-detail-bg: #fff9f4;
}

.system-event--error {
  --event-bg: #fff0f0;
  --event-hover-bg: #ffe5e5;
  --event-fg: #9b6262;
  --event-icon-bg: #fbdede;
  --event-icon-fg: #a95353;
  --event-detail-bg: #fff7f7;
}

.system-event--finished {
  --event-bg: #eef3f6;
  --event-hover-bg: #e5edf1;
  --event-fg: #647a87;
  --event-icon-bg: #dfe9ee;
  --event-icon-fg: #587383;
  --event-detail-bg: #f5f8f9;
}

.message-bubble {
  position: relative;
  width: fit-content;
  max-width: 100%;
  padding: 0.625rem 0.875rem;
  color: #27332d;
  font-size: 14px;
  line-height: 1.65;
  overflow-wrap: anywhere;
  text-align: left;
}

.message-bubble--sales {
  border-radius: 17px;
  background: #eaf5ef;
  box-shadow: 0 1px 2px rgba(39, 79, 57, 0.05);
}

.message-bubble--customer {
  border-radius: 17px;
  background: #f5f6f6;
}

.typing-indicator {
  display: inline-flex;
  min-width: 2.75rem;
  align-items: center;
  justify-content: center;
  gap: 0.3rem;
  padding: 0.2rem 0;
  vertical-align: middle;
}

.typing-indicator > span {
  width: 0.4rem;
  height: 0.4rem;
  border-radius: 9999px;
  animation: typing-bounce 1.4s infinite;
}

.typing-indicator > span:nth-child(2) {
  animation-delay: 0.2s;
}

.typing-indicator > span:nth-child(3) {
  animation-delay: 0.4s;
}

.typing-indicator--sales > span {
  background: #a9cdb8;
}

.typing-indicator--customer > span {
  background: #c1c9c5;
}

.message-actions {
  display: flex;
  min-height: 1.75rem;
  align-items: center;
  gap: 0.125rem;
  padding-top: 0.25rem;
  color: #a1a1aa;
  opacity: 0;
  transform: translateY(-2px);
  transition: opacity 150ms ease, transform 150ms ease;
  pointer-events: none;
}

.group:hover .message-actions,
.group:focus-within .message-actions {
  opacity: 1;
  transform: translateY(0);
  pointer-events: auto;
}

.message-actions button {
  display: grid;
  width: 1.75rem;
  height: 1.75rem;
  place-items: center;
  border-radius: 0.375rem;
  transition: color 150ms ease, background 150ms ease;
}

.message-actions button:hover,
.message-actions button:focus-visible,
.message-actions button.is-active {
  background: #f4f4f5;
  color: #047857;
  outline: none;
}

.message-actions button.is-negative {
  color: #dc2626;
}

.message-actions :deep(svg) {
  width: 0.95rem;
  height: 0.95rem;
}

@media (hover: none) {
  .message-actions {
    opacity: 1;
    transform: none;
    pointer-events: auto;
  }
}
</style>
