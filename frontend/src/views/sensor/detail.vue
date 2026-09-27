<template>
  <section class="page" data-module="sensor-detail">
    <header class="page-head">
      <div>
        <h2>观测传感器明细</h2>
        <p class="page-desc">查看传感器档案与当前状态，可在此执行安排检定、标记疑误、拆除传感器。</p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="goBack">返回列表</button>
      </div>
    </header>

    <div v-if="errorMessage" class="detail-error">{{ errorMessage }}</div>

    <template v-else-if="entry">
      <div class="stat-row">
        <article class="stat-card">
          <span class="stat-label">当前状态</span>
          <strong class="stat-value">
            <span :class="['status-tag', statusClass(String(entry.status ?? ''))]">{{ entry.status }}</span>
          </strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">检定有效期</span>
          <strong v-if="isValidityMissing" class="stat-value missing">缺失</strong>
          <strong v-else class="stat-value">{{ entry['检定有效期'] }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">传感器编号</span>
          <strong class="stat-value">{{ entry['传感器编号'] }}</strong>
        </article>
      </div>

      <table class="data-table detail-table">
        <tbody>
          <tr v-for="field in detailFields" :key="field">
            <th>{{ field }}</th>
            <td>
              <template v-if="field === '检定有效期' && isValidityMissing">
                <span class="missing-badge">未填写 / 无法识别</span>
              </template>
              <template v-else>{{ entry[field] ?? '—' }}</template>
            </td>
          </tr>
        </tbody>
      </table>

      <div class="detail-actions">
        <button
          v-for="action in actions"
          :key="action"
          class="btn"
          :class="{ primary: action === '安排检定', danger: action === '拆除传感器' }"
          type="button"
          :disabled="!canRun(action) || busy !== null"
          :title="canRun(action) ? action : `当前「${entry.status}」状态不允许${action}`"
          @click="runAction(action)"
        >
          {{ busy === action ? `正在${action}…` : action }}
        </button>
      </div>

      <footer class="page-foot">
        <span v-if="actionMessage" :class="lastOk ? 'info-text' : 'error-text'">{{ actionMessage }}</span>
      </footer>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'
import {
  ACTIONS,
  actionEnabled,
  DETAIL_FIELDS,
  ENDPOINT,
  validityMissing,
  type SensorAction,
} from './shared'

type Entry = Record<string, string | number | null>

const route = useRoute()
const router = useRouter()

const actions = ACTIONS
const detailFields = DETAIL_FIELDS

const entry = ref<Entry | null>(null)
const errorMessage = ref('')
const actionMessage = ref('')
const lastOk = ref(true)
const busy = ref<SensorAction | null>(null)

const entryId = computed(() => Number(route.params.id))
const isValidityMissing = computed(() => entry.value !== null && validityMissing(entry.value['检定有效期']))

function statusClass(status: string | null | undefined): string {
  return {
    待检定: 'status-pending',
    正常采集: 'status-ok',
    疑误待查: 'status-suspect',
    已拆除: 'status-removed',
  }[String(status ?? '')] ?? ''
}

function canRun(action: SensorAction): boolean {
  return entry.value !== null && actionEnabled(action, String(entry.value.status ?? ''))
}

async function load() {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${entryId.value}`)
    if (response.status === 404) {
      errorMessage.value = `观测传感器 ${entryId.value} 不存在或已拆除归档`
      return
    }
    if (!response.ok) {
      throw new Error('传感器明细读取失败')
    }
    entry.value = await response.json()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '传感器明细读取失败'
  }
}

async function runAction(action: SensorAction) {
  if (busy.value || !canRun(action)) {
    return
  }
  busy.value = action
  actionMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${entryId.value}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    if (!response.ok) {
      throw new Error('传感器动作未生效，请稍后重试')
    }
    const payload = (await response.json()) as { ok: boolean; message: string; entry?: Entry }
    lastOk.value = payload.ok
    actionMessage.value = payload.message
    if (payload.entry) {
      entry.value = payload.entry
    } else {
      await load()
    }
  } catch (error) {
    lastOk.value = false
    actionMessage.value = error instanceof Error ? error.message : '传感器操作失败'
  } finally {
    busy.value = null
  }
}

function goBack() {
  router.push({ name: 'sensor' })
}

onMounted(load)
</script>
