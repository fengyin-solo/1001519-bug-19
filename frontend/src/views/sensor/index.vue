<template>
  <section class="page" data-module="sensor">
    <header class="page-head">
      <div>
        <h2>观测传感器管理</h2>
        <p class="page-desc">维护观测传感器，围绕传感器编号、所属站点、观测要素、设备型号做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记观测传感器</button>
        <button class="btn" type="button" @click="exportRows">导出观测传感器清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article
        v-for="item in stats"
        :key="item.key"
        class="stat-card"
        :class="{ 'stat-clickable': item.key === 'missing_validity' }"
        @click="item.key === 'missing_validity' && toggleMissingFilter()"
      >
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value" :class="{ 'stat-alert': item.key === 'missing_validity' && item.value > 0 }">
          {{ item.value }}
        </strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="() => reload()">
      <label class="filter-item">
        <span>传感器编号</span>
        <input v-model="keyword" placeholder="按传感器编号检索" />
      </label>
      <label class="filter-item">
        <span>传感器状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <label class="filter-check">
        <input v-model="missingOnly" type="checkbox" @change="() => reload()" />
        <span>只看检定有效期缺失</span>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <template v-if="column === '传感器编号'">
              <RouterLink class="link" :to="{ name: 'sensor-detail', params: { id: row.id } }">
                {{ row[column] }}
              </RouterLink>
            </template>
            <template v-else-if="column === '检定有效期'">
              <span v-if="isValidityMissing(row[column])" class="missing-badge">缺失</span>
              <template v-else>{{ row[column] }}</template>
            </template>
            <template v-else-if="column === '传感器状态'">
              <span :class="['status-tag', statusClass(String(row[column] ?? ''))]">
                {{ row[column] ?? '—' }}
              </span>
            </template>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              :disabled="!canRun(action, String(row.status ?? '')) || busyId === row.id"
              :title="canRun(action, String(row.status ?? '')) ? action : `当前状态不允许${action}`"
              @click="runAction(action, row)"
            >
              {{ busyId === row.id && busyAction === action ? `正在${action}…` : action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无符合条件的观测传感器数据</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条观测传感器记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
      <span v-else-if="noticeMessage" class="info-text">{{ noticeMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onActivated, onMounted, ref } from 'vue'

import { request } from '@/api/client'
import {
  ACTIONS,
  actionEnabled,
  COLUMNS,
  ENDPOINT,
  validityMissing,
  type SensorAction,
} from './shared'

type Row = Record<string, string | number | null>
type StatItem = { key: string; label: string; value: number }

const columns = COLUMNS
const actions = ACTIONS
const statuses = ['待检定', '正常采集', '疑误待查', '已拆除']

const rows = ref<Row[]>([])
const total = ref(0)
const stats = ref<StatItem[]>([])
const errorMessage = ref('')
const noticeMessage = ref('')

const keyword = ref('')
const statusFilter = ref('')
const missingOnly = ref(false)

// 行级动作锁：一次请求没回来之前，同一行所有动作不可再点，防止连点产生重复状态变化。
const busyId = ref<number | null>(null)
const busyAction = ref<SensorAction | null>(null)

function isValidityMissing(value: unknown): boolean {
  return validityMissing(value)
}

function statusClass(status: string): string {
  return {
    待检定: 'status-pending',
    正常采集: 'status-ok',
    疑误待查: 'status-suspect',
    已拆除: 'status-removed',
  }[status] ?? ''
}

function canRun(action: SensorAction, status: string): boolean {
  return actionEnabled(action, status)
}

function buildQuery(withPaging = true): string {
  const params = new URLSearchParams()
  if (keyword.value.trim()) {
    params.set('keyword', keyword.value.trim())
  }
  if (statusFilter.value) {
    params.set('status', statusFilter.value)
  }
  if (missingOnly.value) {
    params.set('missing_validity', 'true')
  }
  if (withPaging) {
    params.set('size', '200')
  }
  return params.toString()
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  missingOnly.value = false
  void reload()
}

function toggleMissingFilter() {
  missingOnly.value = !missingOnly.value
  void reload()
}

function exportRows() {
  // 导出沿用当前筛选条件，保证和列表、统计卡是同一批数据。
  window.open(`${ENDPOINT}/export?${buildQuery(false)}`, '_blank')
}

function openCreate() {
  errorMessage.value = '观测传感器登记入口尚未接入审批流'
}

async function runAction(action: SensorAction, row: Row) {
  if (busyId.value !== null || !canRun(action, String(row.status ?? ''))) {
    return
  }
  busyId.value = Number(row.id)
  busyAction.value = action
  errorMessage.value = ''
  noticeMessage.value = ''
  let rejected = false
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    if (!response.ok) {
      throw new Error('观测传感器动作未生效，请稍后重试')
    }
    const payload = (await response.json()) as { ok: boolean; message: string; changed?: boolean }
    if (!payload.ok) {
      // 后端业务校验失败（如非法流转）时 HTTP 仍是 200，必须读 ok 字段；
      // 状态在服务端没有变化，直接展示原因，不刷新列表。
      errorMessage.value = payload.message
      rejected = true
    } else {
      noticeMessage.value = payload.message
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '观测传感器操作失败'
  } finally {
    busyId.value = null
    busyAction.value = null
  }
  // 被服务端明确拒绝时无需刷新；成功或网络异常都重拉列表与统计卡，保证三处一致。
  if (!rejected) {
    await reload(false)
  }
}

async function reload(clearMessage = true) {
  if (clearMessage) {
    errorMessage.value = ''
    noticeMessage.value = ''
  }
  const query = buildQuery()
  try {
    const [listResponse, statsResponse] = await Promise.all([
      request(`${ENDPOINT}?${query}`),
      request(`${ENDPOINT}/stats`),
    ])
    if (!listResponse.ok) {
      throw new Error('观测传感器列表读取失败')
    }
    if (!statsResponse.ok) {
      throw new Error('观测传感器统计读取失败')
    }
    const payload = (await listResponse.json()) as { items?: Row[]; total?: number }
    const statsPayload = (await statsResponse.json()) as { items?: StatItem[] }
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    stats.value = statsPayload.items ?? []
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '观测传感器列表读取失败'
  }
}

onMounted(() => reload())
// 从详情页返回时（组件被 keep-alive 缓存的场景）同样刷新，保证列表/统计/导出三处不错位。
onActivated(() => reload())
</script>
