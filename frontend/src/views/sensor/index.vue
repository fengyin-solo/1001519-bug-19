<template>
  <section class="page" data-module="sensor">
    <header class="page-head">
      <div>
        <h2>观测传感器管理</h2>
        <p class="page-desc">维护观测传感器，围绕传感器编号、所属站点、观测要素、设备型号做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记观测传感器</button>
        <button class="btn" type="button" :disabled="exporting" @click="exportRows">导出观测传感器清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article
        v-for="item in statCards"
        :key="item.label"
        class="stat-card"
        :class="{ 'stat-card--warn': item.warn, 'stat-card--active': activeStatus === item.status }"
        @click="item.status && toggleStatus(item.status)"
      >
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <label class="filter-item">
        <span>传感器状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
      <label class="filter-item">
        <input v-model="missingOnly" type="checkbox" @change="reload" />
        <span class="missing-toggle">只看检定有效期缺失</span>
      </label>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th>传感器编号</th>
          <th>所属站点</th>
          <th>观测要素</th>
          <th>设备型号</th>
          <th>出厂序列号</th>
          <th>安装高度</th>
          <th>检定有效期</th>
          <th>传感器状态</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in pagedRows" :key="String(row.id)" :class="{ 'row-warn': row.expiry_state === 'missing' }">
          <td><button class="link" type="button" @click="openDetail(row)">{{ row['传感器编号'] ?? '—' }}</button></td>
          <td>{{ row['所属站点'] ?? '—' }}</td>
          <td>{{ row['观测要素'] ?? '—' }}</td>
          <td>{{ row['设备型号'] ?? '—' }}</td>
          <td>{{ row['出厂序列号'] ?? '—' }}</td>
          <td>{{ row['安装高度'] ?? '—' }}</td>
          <td>
            <span v-if="row.expiry_state === 'missing'" class="tag tag-warn">缺失</span>
            <span v-else-if="row.expiry_state === 'expired'" class="tag tag-warn">{{ row['检定有效期'] }}（已过期）</span>
            <span v-else>{{ row['检定有效期'] }}</span>
          </td>
          <td><span class="tag" :class="statusTagClass(row.status)">{{ row.status }}</span></td>
          <td class="row-actions">
            <template v-if="(row.available_actions ?? []).length">
              <button
                v-for="action in row.available_actions"
                :key="action"
                class="link"
                type="button"
                :disabled="pendingKey === `${row.id}:${action}`"
                @click="runAction(action, row)"
              >
                {{ pendingKey === `${row.id}:${action}` ? '处理中…' : action }}
              </button>
            </template>
            <span v-else class="muted-text">—</span>
          </td>
        </tr>
        <tr v-if="!pagedRows.length">
          <td colspan="9" class="empty-state">暂无符合条件的观测传感器数据，可先登记观测传感器</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>
        共 {{ total }} 条观测传感器记录
        <button v-if="statusFilter || missingOnly" class="link" type="button" @click="resetFilters">清除筛选</button>
      </span>
      <span v-if="message" :class="messageError ? 'error-text' : 'ok-text'">{{ message }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onActivated, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'

type Row = {
  id: number
  status: string
  expiry_state: string
  available_actions: string[]
  [field: string]: string | number | boolean | string[]
}

const ENDPOINT = '/api/sensor'
const statuses = ['待检定', '正常采集', '疑误待查', '已拆除']
const filterFields = ['传感器编号', '所属站点', '观测要素']

const router = useRouter()
const route = useRoute()

const rows = ref<Row[]>([])
const total = ref(0)
const pageSize = 20
const message = ref('')
const messageError = ref(false)
const exporting = ref(false)
const pendingKey = ref('')

const filters = ref<Record<string, string>>({})
const statusFilter = ref('')
const missingOnly = ref(false)
const activeStatus = computed(() => statusFilter.value)

const stats = ref<Record<string, number>>({
  installed: 0,
  collecting: 0,
  pending: 0,
  suspect: 0,
  removed: 0,
  expiry_missing: 0,
})

const statCards = computed(() => [
  { label: '在装传感器', value: stats.value.installed, status: '', warn: false },
  { label: '正常采集', value: stats.value.collecting, status: '正常采集', warn: false },
  { label: '待检定传感器', value: stats.value.pending, status: '待检定', warn: false },
  { label: '疑误待查', value: stats.value.suspect, status: '疑误待查', warn: false },
  { label: '已拆除（不参与采集统计）', value: stats.value.removed, status: '已拆除', warn: false },
  { label: '检定有效期缺失', value: stats.value.expiry_missing, status: '', warn: stats.value.expiry_missing > 0 },
])

const pagedRows = computed(() => rows.value.slice(0, pageSize))

function toggleStatus(status: string) {
  statusFilter.value = statusFilter.value === status ? '' : status
  void reload()
}

function statusTagClass(status: unknown): string {
  if (status === '正常采集') return 'tag-ok'
  if (status === '疑误待查') return 'tag-warn'
  if (status === '待检定') return 'tag-pending'
  return 'tag-off'
}

function resetFilters() {
  filters.value = {}
  statusFilter.value = ''
  missingOnly.value = false
  void reload()
}

async function loadStats() {
  try {
    const response = await request(`${ENDPOINT}/stats`)
    if (response.ok) {
      stats.value = await response.json()
    }
  } catch {
    // 统计失败不阻塞列表，沿用上次数字
  }
}

async function exportRows() {
  exporting.value = true
  message.value = ''
  try {
    const params = new URLSearchParams()
    if (statusFilter.value) params.set('status', statusFilter.value)
    if (missingOnly.value) params.set('expiry_missing', 'true')
    const url = `${ENDPOINT}/export?${params.toString()}`
    const response = await request(url)
    if (!response.ok) {
      throw new Error('导出清单生成失败')
    }
    const blob = await response.blob()
    const href = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = href
    link.download = `观测传感器清单_${new Date().toISOString().slice(0, 10)}.json`
    link.click()
    URL.revokeObjectURL(href)
    message.value = '导出清单已生成，口径与当前列表、统计一致'
    messageError.value = false
  } catch (error) {
    message.value = error instanceof Error ? error.message : '导出失败'
    messageError.value = true
  } finally {
    exporting.value = false
  }
}

function openCreate() {
  message.value = '观测传感器登记入口尚未接入审批流'
  messageError.value = true
}

function openDetail(row: Row) {
  // 把当前筛选条件带去详情页，返回时原样恢复，避免刷新后错位
  const query: Record<string, string> = {}
  const terms = Object.values(filters.value).map((v) => v.trim()).filter(Boolean)
  if (terms.length) query.keyword = terms.join(' ')
  if (statusFilter.value) query.status = statusFilter.value
  if (missingOnly.value) query.missing = '1'
  void router.push({ name: 'sensor-detail', params: { id: String(row.id) }, query })
}

async function runAction(action: string, row: Row) {
  const key = `${row.id}:${action}`
  if (pendingKey.value) return // 同一时间只放行一个动作，连点不会发出两条请求
  pendingKey.value = key
  message.value = ''
  messageError.value = false
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload?.ok) {
      throw new Error(payload?.message ?? '观测传感器动作未生效，请稍后重试')
    }
    message.value = payload.changed === false
      ? `未重复记录：${payload.message}`
      : payload.message
    await reload()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '观测传感器操作失败'
    messageError.value = true
  } finally {
    pendingKey.value = ''
  }
}

async function reload() {
  message.value = ''
  const params = new URLSearchParams()
  const terms = Object.values(filters.value).map((v) => v.trim()).filter(Boolean)
  if (terms.length) params.set('keyword', terms.join(' '))
  if (statusFilter.value) params.set('status', statusFilter.value)
  if (missingOnly.value) params.set('expiry_missing', 'true')
  try {
    const response = await request(`${ENDPOINT}?${params.toString()}`)
    if (!response.ok) {
      throw new Error('观测传感器列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    await loadStats()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '观测传感器列表读取失败'
    messageError.value = true
  }
}

function restoreQuery() {
  filters.value = {}
  // 往返详情页只携带一个合并后的 keyword，恢复时放回主检索框（传感器编号）
  const keyword = typeof route.query.keyword === 'string' ? route.query.keyword : ''
  if (keyword) filters.value[filterFields[0]] = keyword
  statusFilter.value = typeof route.query.status === 'string' ? route.query.status : ''
  missingOnly.value = route.query.missing === '1'
}

onMounted(() => {
  restoreQuery()
  void reload()
})

// keep-alive 缓存下从详情页返回也会触发，普通返回时 onMounted 同样会重新拉取
onActivated(() => {
  restoreQuery()
  void reload()
})
</script>

<style scoped>
.stat-card { cursor: pointer; }
.stat-card--active { border-color: var(--brand); box-shadow: 0 0 0 1px var(--brand); }
.stat-card--warn .stat-value { color: #b42318; }
.row-warn { background: #fef3f2; }
.tag { display: inline-block; padding: 1px 8px; border-radius: 10px; font-size: 12px; background: #eef2f7; color: #475569; }
.tag-ok { background: #e7f6ec; color: #157347; }
.tag-warn { background: #fee4e2; color: #b42318; font-weight: 600; }
.tag-pending { background: #fff4e5; color: #b54708; }
.tag-off { background: #e2e8f0; color: #64748b; }
.muted-text, .missing-toggle { color: var(--muted); font-size: 12px; }
.ok-text { color: #157347; }
.link:disabled { color: var(--muted); cursor: not-allowed; }
</style>
