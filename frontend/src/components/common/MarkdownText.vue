<script setup lang="ts">
import { computed } from 'vue'
import MarkdownIt from 'markdown-it'
import type Token from 'markdown-it/lib/token.mjs'
import type Renderer from 'markdown-it/lib/renderer.mjs'
import type { RenderRule } from 'markdown-it/lib/renderer.mjs'

const props = defineProps<{
  text: string
}>()

const md = new MarkdownIt({
  html: false,
  breaks: true,
  linkify: true,
  typographer: false,
})

md.disable('image')

// 禁用分隔线（---）渲染
md.renderer.rules.hr = () => ''

const defaultLinkOpen =
  md.renderer.rules.link_open ??
  ((tokens: Token[], idx: number, options, _env, self: Renderer) =>
    self.renderToken(tokens, idx, options))

md.renderer.rules.link_open = ((tokens, idx, options, env, self) => {
  const token = tokens[idx]
  if (token) {
    token.attrSet('target', '_blank')
    token.attrSet('rel', 'noopener noreferrer')
  }
  return defaultLinkOpen(tokens, idx, options, env, self)
}) satisfies RenderRule

const rendered = computed(() => md.render(props.text))
</script>

<template>
  <div class="markdown-text" v-html="rendered" />
</template>

<style scoped>
.markdown-text {
  overflow-wrap: anywhere;
  font-size: 14px;
  line-height: 1.6;
  color: #333;
}

.markdown-text :deep(*) {
  margin: 0;
}

/* 段落间距 - 微信风格紧凑 */
.markdown-text :deep(p) {
  margin: 0;
  padding: 0;
}

.markdown-text :deep(p + p),
.markdown-text :deep(p + ul),
.markdown-text :deep(p + ol),
.markdown-text :deep(ul + p),
.markdown-text :deep(ol + p),
.markdown-text :deep(pre + p),
.markdown-text :deep(p + pre) {
  margin-top: 0.5rem;
}

.markdown-text :deep(strong) {
  font-weight: 600;
  color: #1a1a1a;
}

.markdown-text :deep(em) {
  font-style: italic;
}

.markdown-text :deep(ul),
.markdown-text :deep(ol) {
  padding-left: 1.5rem;
  margin: 0.25rem 0;
}

.markdown-text :deep(ul) {
  list-style-type: disc;
}

.markdown-text :deep(ol) {
  list-style-type: decimal;
}

.markdown-text :deep(li) {
  margin: 0.15rem 0;
  line-height: 1.5;
}

.markdown-text :deep(a) {
  color: #576b95;
  text-decoration: none;
}

.markdown-text :deep(a:hover) {
  text-decoration: underline;
}

.markdown-text :deep(code) {
  border-radius: 4px;
  background: rgba(0, 0, 0, 0.06);
  padding: 0.15rem 0.35rem;
  color: #c41d7f;
  font-size: 0.9em;
  font-family: Monaco, Menlo, Consolas, monospace;
}

.markdown-text :deep(pre) {
  overflow-x: auto;
  border-radius: 8px;
  background: #f6f8fa;
  padding: 0.75rem 1rem;
  margin: 0.5rem 0;
  border: 1px solid #e8e8e8;
}

.markdown-text :deep(pre code) {
  background: transparent;
  padding: 0;
  color: #333;
  font-size: 0.85em;
}

.markdown-text :deep(blockquote) {
  border-left: 3px solid #ddd;
  padding-left: 0.75rem;
  color: #666;
  margin: 0.5rem 0;
}

/* 表格样式 - 微信风格 */
.markdown-text :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 0.5rem 0;
  font-size: 13px;
}

.markdown-text :deep(th),
.markdown-text :deep(td) {
  padding: 0.5rem 0.75rem;
  border: 1px solid #e8e8e8;
  text-align: left;
}

.markdown-text :deep(th) {
  background: #fafafa;
  font-weight: 600;
  color: #333;
}

.markdown-text :deep(tr:nth-child(even)) {
  background: #fafafa;
}

.markdown-text :deep(tr:hover) {
  background: #f0f0f0;
}

/* 标题样式 */
.markdown-text :deep(h1),
.markdown-text :deep(h2),
.markdown-text :deep(h3),
.markdown-text :deep(h4),
.markdown-text :deep(h5),
.markdown-text :deep(h6) {
  margin: 0.75rem 0 0.5rem 0;
  font-weight: 600;
  color: #1a1a1a;
}

.markdown-text :deep(h1) {
  font-size: 1.5em;
}

.markdown-text :deep(h2) {
  font-size: 1.3em;
}

.markdown-text :deep(h3) {
  font-size: 1.1em;
}

/* 水平线 - 隐藏 */
.markdown-text :deep(hr) {
  display: none;
}
</style>
