<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { Icon } from '@iconify/vue'

// API 配置类型
interface ApiConfig {
  provider: 'mimo' | 'deepseek'
  apiKey: string
  baseUrl: string
  model: string
}

// 厂商配置
const providers = [
  {
    id: 'mimo' as const,
    name: 'Mimo',
    description: '小米 MiMo AI 大语言模型',
    baseUrl: 'https://api.mimo.ai/v1',
    models: [
      { id: 'mimo-v2.5-pro', name: 'Mimo V2.5 Pro', description: '专业版，高性能推理' },
      { id: 'mimo-v2.5', name: 'Mimo V2.5', description: '标准版，均衡性能' },
    ]
  },
  {
    id: 'deepseek' as const,
    name: 'DeepSeek',
    description: 'DeepSeek AI 官方 API',
    baseUrl: 'https://api.deepseek.com',
    models: [
      { id: 'deepseek-v4-flash', name: 'DeepSeek V4 Flash', description: '轻量级，1M上下文，高性价比' },
      { id: 'deepseek-v4-pro', name: 'DeepSeek V4 Pro', description: '专业版，1M上下文，高性能' },
    ]
  }
]

// 当前配置
const selectedProvider = ref<'mimo' | 'deepseek'>('mimo')
const apiKey = ref('')
const selectedModel = ref('mimo-v2.5')
const baseUrl = ref('https://api.mimo.ai/v1')

// UI 状态
const isSaving = ref(false)
const saveSuccess = ref(false)
const showApiKey = ref(false)

// 获取当前厂商的模型列表
const currentModels = ref(providers[0].models)

watch(selectedProvider, (newProvider) => {
  const provider = providers.find(p => p.id === newProvider)
  if (provider) {
    currentModels.value = provider.models
    baseUrl.value = provider.baseUrl
    // 如果当前选择的模型不在新厂商的模型列表中，选择第一个
    if (!provider.models.find(m => m.id === selectedModel.value)) {
      selectedModel.value = provider.models[0].id
    }
  }
})

// 加载保存的配置
onMounted(() => {
  const savedConfig = localStorage.getItem('insurespar_api_config')
  if (savedConfig) {
    try {
      const config: ApiConfig = JSON.parse(savedConfig)
      selectedProvider.value = config.provider
      apiKey.value = config.apiKey
      selectedModel.value = config.model
      baseUrl.value = config.baseUrl
    } catch (e) {
      console.error('加载配置失败', e)
    }
  }
})

// 保存配置
async function saveConfig() {
  isSaving.value = true
  saveSuccess.value = false

  try {
    const config: ApiConfig = {
      provider: selectedProvider.value,
      apiKey: apiKey.value,
      baseUrl: baseUrl.value,
      model: selectedModel.value
    }

    localStorage.setItem('insurespar_api_config', JSON.stringify(config))

    // 模拟保存延迟
    await new Promise(resolve => setTimeout(resolve, 500))

    saveSuccess.value = true
    setTimeout(() => {
      saveSuccess.value = false
    }, 2000)
  } catch (e) {
    console.error('保存配置失败', e)
    alert('保存失败，请重试')
  } finally {
    isSaving.value = false
  }
}

// 重置配置
function resetConfig() {
  selectedProvider.value = 'mimo'
  apiKey.value = ''
  selectedModel.value = 'mimo-v2.5'
  baseUrl.value = 'https://api.mimo.ai/v1'
  localStorage.removeItem('insurespar_api_config')
}
</script>

<template>
  <div class="settings-view min-h-0 flex-1 overflow-y-auto bg-white px-4 pb-4 pt-3 sm:px-6 lg:overflow-hidden xl:px-8">
    <section class="settings-surface h-full min-h-0 overflow-hidden" aria-label="API 设置">
      <div class="settings-grid grid h-full min-h-0 grid-cols-1 overflow-y-auto lg:grid-cols-[1fr_320px] lg:gap-6 lg:overflow-hidden">
        <!-- 左侧：配置表单 -->
        <div class="settings-form min-h-0 overflow-y-auto">
          <!-- 标题区域 -->
          <div class="flex items-center justify-between mb-6">
            <div class="flex items-center gap-3">
              <div class="w-10 h-10 rounded-xl bg-[var(--color-accent-soft)] flex items-center justify-center">
                <Icon icon="lucide:settings" class="w-5 h-5 text-[var(--color-accent-dark)]" />
              </div>
              <div>
                <h1 class="text-xl font-bold text-[var(--color-text-primary)]">API 设置</h1>
                <p class="text-sm text-[var(--color-text-secondary)]">配置 AI 模型和 API 参数</p>
              </div>
            </div>
            <div class="flex items-center gap-3">
              <Transition name="fade">
                <span v-if="saveSuccess" class="text-sm text-green-600 flex items-center gap-1">
                  <Icon icon="lucide:check-circle" class="w-4 h-4" />
                  保存成功
                </span>
              </Transition>
              <button
                type="button"
                class="px-4 py-2 text-sm font-medium rounded-lg text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface)] transition-colors"
                @click="resetConfig"
              >
                重置默认
              </button>
              <button
                type="button"
                class="px-5 py-2 text-sm font-medium rounded-lg bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                :disabled="isSaving || !apiKey"
                @click="saveConfig"
              >
                <Icon v-if="isSaving" icon="lucide:loader-2" class="w-4 h-4 animate-spin" />
                {{ isSaving ? '保存中...' : '保存配置' }}
              </button>
            </div>
          </div>

          <!-- 厂商选择 -->
          <div class="mb-5">
            <label class="block text-sm font-medium text-[var(--color-text-primary)] mb-3">选择服务商</label>
            <div class="grid grid-cols-2 gap-3">
              <button
                v-for="provider in providers"
                :key="provider.id"
                type="button"
                class="p-4 rounded-xl border-2 text-left transition-all"
                :class="selectedProvider === provider.id
                  ? 'border-[var(--color-accent)] bg-[var(--color-accent-soft)]'
                  : 'border-[var(--color-border)] hover:border-[var(--color-accent)]/50'"
                @click="selectedProvider = provider.id"
              >
                <div class="font-medium text-[var(--color-text-primary)]">{{ provider.name }}</div>
                <div class="text-xs text-[var(--color-text-secondary)] mt-1">{{ provider.description }}</div>
              </button>
            </div>
          </div>

          <!-- API Key 和 Base URL 并排 -->
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-5">
            <div>
              <label class="block text-sm font-medium text-[var(--color-text-primary)] mb-2">API Key</label>
              <div class="relative">
                <input
                  v-model="apiKey"
                  :type="showApiKey ? 'text' : 'password'"
                  placeholder="请输入 API Key"
                  class="w-full rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-2.5 text-sm text-[var(--color-text-primary)] placeholder-[var(--color-text-muted)] focus:border-[var(--color-accent)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]/20"
                />
                <button
                  type="button"
                  class="absolute right-3 top-1/2 -translate-y-1/2 p-1 rounded-lg hover:bg-[var(--color-border)] transition-colors"
                  @click="showApiKey = !showApiKey"
                >
                  <Icon :icon="showApiKey ? 'lucide:eye-off' : 'lucide:eye'" class="w-4 h-4 text-[var(--color-text-muted)]" />
                </button>
              </div>
              <p class="mt-1.5 text-[11px] text-[var(--color-text-muted)]">
                <Icon icon="lucide:shield-check" class="w-3 h-3 inline mr-1" />
                仅存储在本地浏览器
              </p>
            </div>

            <div>
              <label class="block text-sm font-medium text-[var(--color-text-primary)] mb-2">API 地址</label>
              <input
                v-model="baseUrl"
                type="text"
                placeholder="https://api.example.com"
                class="w-full rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-2.5 text-sm text-[var(--color-text-primary)] placeholder-[var(--color-text-muted)] focus:border-[var(--color-accent)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]/20"
              />
              <p class="mt-1.5 text-[11px] text-[var(--color-text-muted)]">
                选择服务商后自动填充
              </p>
            </div>
          </div>

          <!-- 模型选择 -->
          <div>
            <label class="block text-sm font-medium text-[var(--color-text-primary)] mb-3">选择模型</label>
            <div class="grid grid-cols-2 gap-3">
              <label
                v-for="model in currentModels"
                :key="model.id"
                class="flex items-center p-3 rounded-xl border-2 cursor-pointer transition-all"
                :class="selectedModel === model.id
                  ? 'border-[var(--color-accent)] bg-[var(--color-accent-soft)]'
                  : 'border-[var(--color-border)] hover:border-[var(--color-accent)]/50'"
              >
                <input
                  v-model="selectedModel"
                  type="radio"
                  :value="model.id"
                  class="sr-only"
                />
                <div class="flex-1 min-w-0">
                  <div class="font-medium text-[var(--color-text-primary)] text-sm">{{ model.name }}</div>
                  <div class="text-[11px] text-[var(--color-text-secondary)] mt-0.5">{{ model.description }}</div>
                  <div class="text-[10px] text-[var(--color-text-muted)] mt-1 font-mono truncate">{{ model.id }}</div>
                </div>
                <div
                  v-if="selectedModel === model.id"
                  class="w-5 h-5 rounded-full bg-[var(--color-accent)] flex items-center justify-center shrink-0 ml-2"
                >
                  <Icon icon="lucide:check" class="w-3 h-3 text-white" />
                </div>
              </label>
            </div>
          </div>
        </div>

        <!-- 右侧：配置预览和说明 -->
        <div class="settings-sidebar min-h-0 overflow-y-auto space-y-4">
          <!-- 当前配置预览 -->
          <div class="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
            <h3 class="text-sm font-semibold text-[var(--color-text-primary)] mb-3 flex items-center gap-2">
              <Icon icon="lucide:eye" class="w-4 h-4 text-[var(--color-accent)]" />
              当前配置
            </h3>
            <div class="space-y-2.5 text-sm">
              <div class="flex justify-between items-center">
                <span class="text-[var(--color-text-secondary)]">服务商</span>
                <span class="font-medium text-[var(--color-text-primary)]">
                  {{ providers.find(p => p.id === selectedProvider)?.name || '未选择' }}
                </span>
              </div>
              <div class="flex justify-between items-start">
                <span class="text-[var(--color-text-secondary)]">模型</span>
                <div class="text-right">
                  <div class="font-medium text-[var(--color-text-primary)]">
                    {{ currentModels.find(m => m.id === selectedModel)?.name || '未选择' }}
                  </div>
                  <div class="text-[10px] text-[var(--color-text-muted)] font-mono">
                    {{ selectedModel }}
                  </div>
                </div>
              </div>
              <div class="flex justify-between items-center">
                <span class="text-[var(--color-text-secondary)]">API 地址</span>
                <span class="font-medium text-[var(--color-text-primary)] font-mono text-[11px]">
                  {{ baseUrl || '未配置' }}
                </span>
              </div>
              <div class="flex justify-between items-center">
                <span class="text-[var(--color-text-secondary)]">API Key</span>
                <span class="font-medium text-[var(--color-text-primary)]">
                  {{ apiKey ? '••••••••' + apiKey.slice(-4) : '未配置' }}
                </span>
              </div>
            </div>
          </div>

          <!-- 使用说明 -->
          <div class="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
            <h3 class="text-sm font-semibold text-[var(--color-text-primary)] mb-3 flex items-center gap-2">
              <Icon icon="lucide:help-circle" class="w-4 h-4 text-amber-500" />
              使用说明
            </h3>
            <ul class="space-y-2 text-xs text-[var(--color-text-secondary)]">
              <li class="flex items-start gap-2">
                <Icon icon="lucide:check" class="w-3.5 h-3.5 text-green-500 mt-0.5 shrink-0" />
                <span>API Key 仅存储在本地浏览器</span>
              </li>
              <li class="flex items-start gap-2">
                <Icon icon="lucide:check" class="w-3.5 h-3.5 text-green-500 mt-0.5 shrink-0" />
                <span>配置后 AI 对练将使用所选模型</span>
              </li>
              <li class="flex items-start gap-2">
                <Icon icon="lucide:check" class="w-3.5 h-3.5 text-green-500 mt-0.5 shrink-0" />
                <span>可随时返回修改配置</span>
              </li>
            </ul>
          </div>

          <!-- 服务商说明 -->
          <div class="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
            <h3 class="text-sm font-semibold text-[var(--color-text-primary)] mb-3 flex items-center gap-2">
              <Icon icon="lucide:building-2" class="w-4 h-4 text-blue-500" />
              服务商
            </h3>
            <div class="space-y-2 text-xs text-[var(--color-text-secondary)]">
              <div class="flex items-start gap-2">
                <span class="font-medium text-[var(--color-text-primary)]">Mimo:</span>
                <span>小米 MiMo AI 大语言模型</span>
              </div>
              <div class="flex items-start gap-2">
                <span class="font-medium text-[var(--color-text-primary)]">DeepSeek:</span>
                <span>官方 API，V4 系列模型</span>
              </div>
            </div>
            <div class="mt-3 pt-3 border-t border-[var(--color-border)] text-[10px] text-[var(--color-text-muted)]">
              获取 API Key: Mimo → api.mimo.ai | DeepSeek → platform.deepseek.com
            </div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.settings-view {
  background: transparent;
}

.settings-surface {
  background: transparent;
}

.settings-form {
  min-width: 0;
  background: transparent;
  border: 0;
  box-shadow: none;
}

.settings-sidebar {
  min-width: 0;
  width: 100%;
  background: transparent;
  border: 0;
  box-shadow: none;
  scrollbar-width: none;
}

.settings-sidebar::-webkit-scrollbar {
  display: none;
}

@media (max-width: 1023px) {
  .settings-grid {
    grid-template-columns: 1fr;
  }
}
</style>
