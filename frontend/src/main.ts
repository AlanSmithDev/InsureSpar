import { createApp } from 'vue'
import '@fontsource-variable/noto-sans-sc/index.css'
import { addIcon } from '@iconify/vue'
import brainCircuit from '@iconify-icons/lucide/brain-circuit'
import arrowRight from '@iconify-icons/lucide/arrow-right'
import ban from '@iconify-icons/lucide/ban'
import bell from '@iconify-icons/lucide/bell'
import bot from '@iconify-icons/lucide/bot'
import calculator from '@iconify-icons/lucide/calculator'
import chartNoAxesCombined from '@iconify-icons/lucide/line-chart'
import check from '@iconify-icons/lucide/check'
import chevronDown from '@iconify-icons/lucide/chevron-down'
import chevronRight from '@iconify-icons/lucide/chevron-right'
import circleCheck from '@iconify-icons/lucide/check-circle'
import circleAlert from '@iconify-icons/lucide/alert-circle'
import circleDashed from '@iconify-icons/lucide/circle-dashed'
import circleDotDashed from '@iconify-icons/lucide/circle-dot-dashed'
import circleX from '@iconify-icons/lucide/x-circle'
import clipboardCheck from '@iconify-icons/lucide/clipboard-check'
import clock3 from '@iconify-icons/lucide/clock-3'
import cloudOff from '@iconify-icons/lucide/cloud-off'
import copy from '@iconify-icons/lucide/copy'
import fileSearch from '@iconify-icons/lucide/file-search'
import flag from '@iconify-icons/lucide/flag'
import graduationCap from '@iconify-icons/lucide/graduation-cap'
import history from '@iconify-icons/lucide/history'
import house from '@iconify-icons/lucide/home'
import inbox from '@iconify-icons/lucide/inbox'
import info from '@iconify-icons/lucide/info'
import listChecks from '@iconify-icons/lucide/list-checks'
import loaderCircle from '@iconify-icons/lucide/loader-2'
import mapPin from '@iconify-icons/lucide/map-pin'
import messageCircle from '@iconify-icons/lucide/message-circle'
import messageSquarePlus from '@iconify-icons/lucide/message-square-plus'
import messagesSquare from '@iconify-icons/lucide/messages-square'
import panelLeftClose from '@iconify-icons/lucide/panel-left-close'
import panelLeftOpen from '@iconify-icons/lucide/panel-left-open'
import pause from '@iconify-icons/lucide/pause'
import phone from '@iconify-icons/lucide/phone'
import play from '@iconify-icons/lucide/play'
import plus from '@iconify-icons/lucide/plus'
import radar from '@iconify-icons/lucide/radar'
import repeat2 from '@iconify-icons/lucide/repeat-2'
import route from '@iconify-icons/lucide/route'
import search from '@iconify-icons/lucide/search'
import shieldCheck from '@iconify-icons/lucide/shield-check'
import shieldAlert from '@iconify-icons/lucide/shield-alert'
import sparkles from '@iconify-icons/lucide/sparkles'
import star from '@iconify-icons/lucide/star'
import thumbsDown from '@iconify-icons/lucide/thumbs-down'
import thumbsUp from '@iconify-icons/lucide/thumbs-up'
import toolCase from '@iconify-icons/lucide/wrench'
import trophy from '@iconify-icons/lucide/trophy'
import trendingUp from '@iconify-icons/lucide/trending-up'
import triangleAlert from '@iconify-icons/lucide/alert-triangle'
import userRound from '@iconify-icons/lucide/user'
import x from '@iconify-icons/lucide/x'
import zap from '@iconify-icons/lucide/zap'
import './style.css'
import App from './App.vue'

const localIcons = {
  'brain-circuit': brainCircuit,
  'arrow-right': arrowRight,
  ban,
  bell,
  bot,
  calculator,
  'chart-no-axes-combined': chartNoAxesCombined,
  check,
  'chevron-down': chevronDown,
  'chevron-right': chevronRight,
  'circle-check': circleCheck,
  'circle-alert': circleAlert,
  'circle-dashed': circleDashed,
  'circle-dot-dashed': circleDotDashed,
  'circle-x': circleX,
  'clipboard-check': clipboardCheck,
  'clock-3': clock3,
  'cloud-off': cloudOff,
  copy,
  'file-search': fileSearch,
  flag,
  'graduation-cap': graduationCap,
  history,
  house,
  inbox,
  info,
  'list-checks': listChecks,
  'loader-circle': loaderCircle,
  'map-pin': mapPin,
  'message-circle': messageCircle,
  'message-square-plus': messageSquarePlus,
  'messages-square': messagesSquare,
  'panel-left-close': panelLeftClose,
  'panel-left-open': panelLeftOpen,
  pause,
  phone,
  play,
  plus,
  radar,
  'repeat-2': repeat2,
  route,
  search,
  'shield-check': shieldCheck,
  'shield-alert': shieldAlert,
  sparkles,
  star,
  'thumbs-down': thumbsDown,
  'thumbs-up': thumbsUp,
  wrench: toolCase,
  trophy,
  'trending-up': trendingUp,
  'triangle-alert': triangleAlert,
  'user-round': userRound,
  x,
  zap,
}

Object.entries(localIcons).forEach(([name, data]) => addIcon(`lucide:${name}`, data))

createApp(App).mount('#app')
