<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <div class="card budget-card">
        <label class="budget-label" for="budget-slider">{{ t('restocking.budgetLabel') }}</label>
        <div class="budget-readout">{{ money(budget) }}</div>
        <input
          id="budget-slider"
          class="budget-slider"
          type="range"
          min="0"
          :max="sliderMax"
          :step="STEP"
          v-model.number="budget"
        />
        <div class="budget-help">{{ t('restocking.budgetHelp') }}</div>
      </div>

      <div class="stats-grid">
        <div class="stat-card info">
          <div class="stat-label">{{ t('restocking.itemsSelected') }}</div>
          <div class="stat-value">{{ recommendation.selected.length }}</div>
        </div>
        <div class="stat-card info">
          <div class="stat-label">{{ t('restocking.totalCost') }}</div>
          <div class="stat-value">{{ money(recommendation.totalCost) }}</div>
        </div>
        <div class="stat-card info">
          <div class="stat-label">{{ t('restocking.budgetRemaining') }}</div>
          <div class="stat-value">{{ money(recommendation.budgetRemaining) }}</div>
        </div>
        <div class="stat-card info">
          <div class="stat-label">{{ t('restocking.longestLeadTime') }}</div>
          <div class="stat-value">{{ t('restocking.leadTimeDays', { count: recommendation.maxLeadTime }) }}</div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.recommendedTitle') }}</h3>
        </div>
        <div v-if="recommendation.selected.length" class="table-container">
          <table>
            <thead>
              <tr>
                <th>{{ t('restocking.table.sku') }}</th>
                <th>{{ t('restocking.table.itemName') }}</th>
                <th>{{ t('restocking.table.trend') }}</th>
                <th>{{ t('restocking.table.shortfall') }}</th>
                <th>{{ t('restocking.table.orderQty') }}</th>
                <th>{{ t('restocking.table.unitCost') }}</th>
                <th>{{ t('restocking.table.lineCost') }}</th>
                <th>{{ t('restocking.table.leadTime') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in recommendation.selected" :key="row.id">
                <td><strong>{{ row.sku }}</strong></td>
                <td>{{ row.name }}</td>
                <td>
                  <span :class="['badge', row.trend]">{{ t('trends.' + row.trend) }}</span>
                </td>
                <td>{{ row.shortfall }}</td>
                <td>
                  {{ row.qty }}
                  <span v-if="row.partial" class="badge warning partial-pill">{{ t('restocking.partial') }}</span>
                </td>
                <td>{{ unitMoney(row.unitCost) }}</td>
                <td><strong>{{ money(row.cost) }}</strong></td>
                <td>{{ t('restocking.leadTimeDays', { count: row.leadTime }) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else class="no-data">
          {{ recommendation.hasCandidates ? t('restocking.emptyState') : t('restocking.noShortfall') }}
        </div>
      </div>

      <div class="card" v-if="recommendation.excluded.length">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.excludedTitle') }}</h3>
        </div>
        <div class="table-container">
          <table>
            <thead>
              <tr>
                <th>{{ t('restocking.table.sku') }}</th>
                <th>{{ t('restocking.table.itemName') }}</th>
                <th>{{ t('restocking.table.lineCost') }}</th>
                <th>{{ t('restocking.table.trend') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in recommendation.excluded" :key="item.id">
                <td><strong>{{ item.sku }}</strong></td>
                <td>{{ item.name }}</td>
                <td>{{ money(item.shortfall * item.unitCost) }}</td>
                <td class="excluded-reason">{{ t('restocking.excludedReason') }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="action-area">
        <template v-if="!placedOrder">
          <button
            v-if="!confirming"
            class="place-order-btn"
            :disabled="!recommendation.selected.length || submitting"
            @click="startConfirm"
          >
            {{ t('restocking.placeOrder') }}
          </button>

          <div v-else class="confirm-panel">
            <p class="confirm-text">
              {{ t('restocking.confirmPrompt', { count: recommendation.selected.length, total: money(recommendation.totalCost) }) }}
            </p>
            <div class="confirm-actions">
              <button class="place-order-btn" :disabled="submitting" @click="placeOrder">
                {{ submitting ? t('restocking.submitting') : t('restocking.confirmOrder') }}
              </button>
              <button class="secondary" :disabled="submitting" @click="cancelConfirm">
                {{ t('restocking.cancel') }}
              </button>
            </div>
          </div>

          <p v-if="submitError" class="submit-error">{{ submitError }}</p>
        </template>

        <div v-else class="success-banner">
          <span>{{ t('restocking.successMessage', { orderNumber: placedOrder.order_number }) }}</span>
          <router-link to="/orders" class="banner-link">{{ t('restocking.viewInOrders') }}</router-link>
          <button class="secondary" @click="resetOrder">{{ t('restocking.startAnother') }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, watch, onMounted } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'
import { formatCurrency, formatCurrencyWithDecimals } from '../utils/currency'

export default {
  name: 'Restocking',
  setup() {
    const { t, currentCurrency } = useI18n()
    const money = (v) => formatCurrency(v, currentCurrency.value)
    // Unit costs are small (single/double digits) - keep cents so $12.50 doesn't render as "$13"
    const unitMoney = (v) => formatCurrencyWithDecimals(v, currentCurrency.value, 2)

    const STEP = 500

    const loading = ref(true)
    const error = ref(null)
    const forecasts = ref([])
    const budget = ref(3000)
    const confirming = ref(false)
    const submitting = ref(false)
    const submitError = ref(null)
    const placedOrder = ref(null)

    const loadForecasts = async () => {
      try {
        loading.value = true
        error.value = null
        forecasts.value = await api.getDemandForecasts()
      } catch (err) {
        error.value = 'Failed to load demand forecast: ' + err.message
      } finally {
        loading.value = false
      }
    }
    onMounted(loadForecasts)

    const sliderMax = computed(() => {
      const total = forecasts.value.reduce(
        (s, f) => s + Math.max(0, f.forecasted_demand - f.current_demand) * (f.unit_cost || 0),
        0
      )
      return Math.max(STEP, Math.ceil(total / STEP) * STEP)
    })

    watch(sliderMax, (m) => {
      if (budget.value > m) budget.value = m
    })

    const recommendation = computed(() => {
      const candidates = forecasts.value
        .map(f => {
          const shortfall = Math.max(0, f.forecasted_demand - f.current_demand)
          return {
            id: f.id,
            sku: f.item_sku,
            name: f.item_name,
            trend: f.trend,
            unitCost: f.unit_cost,
            leadTime: f.lead_time_days,
            shortfall,
            fullCost: shortfall * f.unit_cost
          }
        })
        .filter(c => c.shortfall > 0)
        .sort((a, b) => {
          const at = a.trend === 'increasing' ? 0 : 1
          const bt = b.trend === 'increasing' ? 0 : 1
          return at !== bt ? at - bt : b.shortfall - a.shortfall
        })

      const selected = []
      const excluded = []
      let remaining = budget.value
      let stopped = false

      for (const c of candidates) {
        if (stopped) {
          excluded.push(c)
          continue
        }
        if (c.fullCost <= remaining) {
          selected.push({ ...c, qty: c.shortfall, cost: c.fullCost, partial: false })
          remaining -= c.fullCost
        } else {
          const qty = Math.floor(remaining / c.unitCost)
          if (qty > 0) {
            selected.push({ ...c, qty, cost: qty * c.unitCost, partial: true })
            remaining -= qty * c.unitCost
          } else {
            excluded.push(c)
          }
          stopped = true
        }
      }

      const totalCost = selected.reduce((s, x) => s + x.cost, 0)
      return {
        selected,
        excluded,
        totalCost,
        budgetRemaining: budget.value - totalCost,
        maxLeadTime: selected.length ? Math.max(...selected.map(x => x.leadTime)) : 0,
        hasCandidates: candidates.length > 0
      }
    })

    const startConfirm = () => {
      if (recommendation.value.selected.length) confirming.value = true
    }
    const cancelConfirm = () => {
      confirming.value = false
    }
    const resetOrder = () => {
      placedOrder.value = null
      confirming.value = false
      submitError.value = null
    }
    const placeOrder = async () => {
      const sel = recommendation.value.selected
      if (!sel.length) return
      submitting.value = true
      submitError.value = null
      try {
        placedOrder.value = await api.createRestockOrder({
          customer: 'Internal Restock',
          items: sel.map(s => ({
            sku: s.sku,
            name: s.name,
            quantity: s.qty,
            unit_price: s.unitCost,
            lead_time_days: s.leadTime
          }))
        })
        confirming.value = false
      } catch (err) {
        submitError.value = 'Failed to place order: ' + (err.response?.data?.detail || err.message)
      } finally {
        submitting.value = false
      }
    }

    return {
      t,
      loading,
      error,
      budget,
      STEP,
      sliderMax,
      recommendation,
      confirming,
      submitting,
      submitError,
      placedOrder,
      money,
      unitMoney,
      startConfirm,
      cancelConfirm,
      placeOrder,
      resetOrder
    }
  }
}
</script>

<style scoped>
.budget-card {
  display: flex;
  flex-direction: column;
}

.budget-label {
  font-size: 0.875rem;
  font-weight: 600;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.budget-readout {
  font-size: 2rem;
  font-weight: 700;
  color: #0f172a;
  margin: 0.5rem 0 1rem;
  letter-spacing: -0.025em;
}

.budget-slider {
  -webkit-appearance: none;
  appearance: none;
  width: 100%;
  background: transparent;
  cursor: pointer;
}

.budget-slider:focus {
  outline: none;
}

.budget-slider::-webkit-slider-runnable-track {
  height: 6px;
  background: #e2e8f0;
  border-radius: 3px;
}

.budget-slider::-moz-range-track {
  height: 6px;
  background: #e2e8f0;
  border-radius: 3px;
}

.budget-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  height: 18px;
  width: 18px;
  margin-top: -6px;
  border-radius: 50%;
  background: #3b82f6;
  border: 2px solid #ffffff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
}

.budget-slider::-moz-range-thumb {
  height: 18px;
  width: 18px;
  border-radius: 50%;
  background: #3b82f6;
  border: 2px solid #ffffff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
}

.budget-slider:focus::-webkit-slider-thumb {
  box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.15);
}

.budget-slider:focus::-moz-range-thumb {
  box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.15);
}

.budget-help {
  margin-top: 0.75rem;
  font-size: 0.875rem;
  color: #64748b;
}

.partial-pill {
  margin-left: 0.5rem;
}

.excluded-reason {
  color: #64748b;
}

.no-data {
  text-align: center;
  padding: 2rem;
  color: #64748b;
  font-size: 0.938rem;
}

.action-area {
  margin-top: 1.25rem;
}

.place-order-btn {
  background: #3b82f6;
  color: #ffffff;
  border: none;
  border-radius: 6px;
  padding: 0.6rem 1.25rem;
  font-weight: 600;
  font-size: 0.938rem;
  cursor: pointer;
  transition: all 0.2s ease;
}

.place-order-btn:hover:not(:disabled) {
  background: #2563eb;
  transform: translateY(-1px);
}

.place-order-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

button.secondary {
  background: #ffffff;
  color: #334155;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  padding: 0.6rem 1.25rem;
  font-weight: 600;
  font-size: 0.938rem;
  cursor: pointer;
  transition: all 0.2s ease;
}

button.secondary:hover:not(:disabled) {
  border-color: #94a3b8;
  background: #f8fafc;
}

button.secondary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.confirm-panel {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 1rem;
}

.confirm-text {
  color: #0f172a;
  font-size: 0.938rem;
  margin-bottom: 0.875rem;
}

.confirm-actions {
  display: flex;
  gap: 0.75rem;
}

.submit-error {
  color: #dc2626;
  font-size: 0.875rem;
  margin-top: 0.75rem;
}

.success-banner {
  display: flex;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
  background: #ecfdf5;
  border: 1px solid #a7f3d0;
  border-radius: 8px;
  padding: 1rem;
  color: #065f46;
  font-size: 0.938rem;
}

.banner-link {
  color: #065f46;
  font-weight: 600;
  text-decoration: underline;
}
</style>
