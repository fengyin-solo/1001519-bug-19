<template>
  <section class="page" data-module="sensor-detail">
    <header class="page-head">
      <div>
        <h2>观测传感器详情</h2>
        <p class="page-desc">查看传感器档案、当前采集状态与状态变化记录，动作执行结果与列表页完全一致。</p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="goBack">返回列表</button>
      </div>
    </header>

    <div v-if="notFound" class="empty-state">未找到该观测传感器，可能已被归档。<button class="link" type="button" @click="goBack">返回列表</button></div>

    <template v-else-if="entry">
      <div class="stat-row">
        <article class="stat-card">
          <span class="stat-label">当前状态</span>
          <strong class="stat-value"><span class="tag" :class="statusTagClass(entry.status)">{{ entry.status }}</span></strong>
        </article>
        <article class="stat-card" :class="{ 'stat-card--warn': entry.expiry_state === 'missing' || entry.expiry_state === 'expired' }">
          <span class="stat-label">检定有效期</span>
          <strong class="stat-value">
            <span v-if="entry.expiry_state === 'missing'" class="tag tag-warn">缺失，请尽快补录</span>
            <span v-else-if="entry.expiry_state === 'expired'" class="tag tag-warn">{{ entry['检定有效期'] }}（已过期）</span>
            <span v-else>{{ entry['检定有效期'] }}</span>
          </strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">状态变化次数</span>
          <strong class="stat-value">{{ (entry.history ?? []).length }}</strong>
        </article>
      </div>

      <table class="data-table detail-table">
        <tbody>
          <tr v-for="field in detailFields" :key="field">
            <th>{{ field }}</th>
            <td>{{ entry[field] || '—' }}</td>
          </tr>
        </tbody>
      </table>

      <h3 class="section-title">状态变化记录</h3>
      <ul class="timeline">
        <li v-for="(item, index) in entry.history ?? []" :key="index" class="timeline-item">
          <span class="timeline-action">{{ item.action }}</span>
          <span class="timeline-flow">
            <template v-if="item.from">{{ item.from }} → {{ item.to }}</template>
            <template v-else>建档为 {{ item.to }}</template>
          </span>
        </li>
        <li v-if="!(entry.history ?? []).length" class="empty-state">暂无状态变化记录</li>
      </ul>

      <h3 class="section-title">执行动作</h3>
      <div class="detail-actions">
        <template v-if="(entry.available_actions ?? []).length">
          <button
            v-for="action in entry.available_actions"
            :key="action"
            class="btn"
            :class="{ primary: action === '检定通过' || action === '复检恢复' }"
            type="button"
            :disabled="pendingAction === action"
            @click="runAction(action)"
          >
            {{ pendingAction === action ? '处理中…' : action }}
          </button>
        </template>
        <span v-else class="muted-text">已拆除为终态，无可用动作。</span>
      </div>

      <footer class="page-foot">
        <span v-if="message" :class="messageError ? 'error-text' : 'ok-text'">{{ message }}</span>
      </footer>
    </template>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'

type HistoryItem = { action: string; from: string | null; to: string }
type DetailRow = {
  id: number
  status: string
  expiry_state: string
  available_actions: string[]
  history: HistoryItem[]
  [field: string]: string | number | boolean | string[] | HistoryItem[]
}

const ENDPOINT = '/api/sensor'
const detailFields = ['传感器编号', '所属站点', '观测要素', '设备型号', '出厂序列号', '安装高度', '检定有效期']

const route = useRoute()
const router = useRouter()

const entry = ref<DetailRow | null>(null)
const notFound = ref(false)
const message = ref('')
const messageError = ref(false)
const pendingAction = ref('')

function statusTagClass(status: unknown): string {
  if (status === '正常采集') return 'tag-ok'
  if (status === '疑误待查') return 'tag-warn'
  if (status === '待检定') return 'tag-pending'
  return 'tag-off'
}

function backQuery() {
  const query: Record<string, string> = {}
  for (const [key, value] of Object.entries(route.query)) {
    if (typeof value === 'string') query[key] = value
  }
  return query
}

function goBack() {
  void router.push({ name: 'sensor', query: backQuery() })
}

async function loadEntry() {
  const id = route.params.id
  try {
    const response = await request(`${ENDPOINT}/${id}`)
    if (response.status === 404) {
      notFound.value = true
      return
    }
    if (!response.ok) {
      throw new Error('明细读取失败')
    }
    entry.value = await response.json()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '明细读取失败'
    messageError.value = true
  }
}

async function runAction(action: string) {
  if (pendingAction.value || !entry.value) return
  pendingAction.value = action
  message.value = ''
  messageError.value = false
  try {
    const response = await request(`${ENDPOINT}/${entry.value.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload?.ok) {
      throw new Error(payload?.message ?? '动作未生效，请稍后重试')
    }
    message.value = payload.changed === false
      ? `未重复记录：${payload.message}`
      : payload.message
    await loadEntry()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '操作失败'
    messageError.value = true
  } finally {
    pendingAction.value = ''
  }
}

onMounted(loadEntry)
</script>

<style scoped>
.detail-table th { width: 140px; background: #f8fafc; }
.section-title { font-size: 14px; margin: 16px 0 8px; }
.timeline { list-style: none; margin: 0; padding: 0; background: #fff; border: 1px solid var(--border); border-radius: 8px; }
.timeline-item { display: flex; justify-content: space-between; padding: 8px 12px; font-size: 13px; border-bottom: 1px solid var(--border); }
.timeline-item:last-child { border-bottom: none; }
.timeline-action { font-weight: 600; }
.timeline-flow { color: var(--muted); }
.detail-actions { display: flex; gap: 8px; }
.stat-card--warn .stat-value { color: #b42318; }
.tag { display: inline-block; padding: 1px 8px; border-radius: 10px; font-size: 12px; background: #eef2f7; color: #475569; }
.tag-ok { background: #e7f6ec; color: #157347; }
.tag-warn { background: #fee4e2; color: #b42318; font-weight: 600; }
.tag-pending { background: #fff4e5; color: #b54708; }
.tag-off { background: #e2e8f0; color: #64748b; }
.muted-text { color: var(--muted); font-size: 13px; }
.ok-text { color: #157347; }
.btn:disabled { color: var(--muted); cursor: not-allowed; }
</style>
