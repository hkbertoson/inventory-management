<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <div v-if="successMessage" class="banner success-banner">{{ successMessage }}</div>
      <div v-if="submitError" class="banner error-banner">{{ submitError }}</div>

      <div class="card budget-card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.availableBudget') }}</h3>
        </div>
        <div class="budget-body">
          <div class="budget-amount">{{ formatCurrency(budget, currentCurrency) }}</div>
          <input
            type="range"
            class="budget-slider"
            v-model.number="budget"
            :min="0"
            :max="maxBudget"
            :step="sliderStep"
          />
          <p class="budget-help">{{ t('restocking.budgetHelp') }}</p>
          <p class="full-restock-cost">{{ t('restocking.fullRestockCost', { amount: formatCurrency(maxBudget, currentCurrency) }) }}</p>
        </div>
      </div>

      <div class="stats-grid">
        <div class="stat-card info">
          <div class="stat-label">{{ t('restocking.totalCost') }}</div>
          <div class="stat-value">{{ formatCurrency(totalCost, currentCurrency) }}</div>
        </div>
        <div class="stat-card success">
          <div class="stat-label">{{ t('restocking.remainingBudget') }}</div>
          <div class="stat-value">{{ formatCurrency(remainingBudget, currentCurrency) }}</div>
        </div>
        <div class="stat-card warning">
          <div class="stat-label">{{ t('restocking.itemsRecommended') }}</div>
          <div class="stat-value">{{ recommended.length }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('restocking.availableBudget') }}</div>
          <div class="stat-value">{{ formatCurrency(budget, currentCurrency) }}</div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.recommendedItems') }}</h3>
          <button
            class="btn-primary"
            :disabled="submitting || recommended.length === 0"
            @click="placeOrder"
          >
            {{ submitting ? t('restocking.placingOrder') : t('restocking.placeOrder') }}
          </button>
        </div>

        <div v-if="candidates.length === 0" class="empty-state">
          {{ t('restocking.noCandidates') }}
        </div>
        <div v-else-if="recommended.length === 0" class="empty-state">
          {{ t('restocking.budgetTooLow') }}
        </div>
        <template v-else>
          <p v-if="skippedCount > 0" class="skipped-note">
            {{ t('restocking.skippedItems', { count: skippedCount }) }}
          </p>
          <div class="table-container">
            <table>
              <thead>
                <tr>
                  <th>{{ t('restocking.table.sku') }}</th>
                  <th>{{ t('restocking.table.itemName') }}</th>
                  <th>{{ t('restocking.table.category') }}</th>
                  <th>{{ t('restocking.table.currentStock') }}</th>
                  <th>{{ t('restocking.table.forecastedDemand') }}</th>
                  <th>{{ t('restocking.table.recommendedQty') }}</th>
                  <th>{{ t('restocking.table.unitCost') }}</th>
                  <th>{{ t('restocking.table.lineTotal') }}</th>
                  <th>{{ t('restocking.table.leadTime') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="c in recommended" :key="c.sku">
                  <td><strong>{{ c.sku }}</strong></td>
                  <td>{{ translateProductName(c.name) }}</td>
                  <td>{{ translateCategory(c.category) }}</td>
                  <td>{{ c.quantity_on_hand }}</td>
                  <td>{{ c.forecasted_demand }}</td>
                  <td><strong>{{ c.recommendedQty }}</strong></td>
                  <td>{{ formatCurrencyWithDecimals(c.unit_cost, currentCurrency, 2) }}</td>
                  <td>{{ formatCurrency(c.lineTotal, currentCurrency) }}</td>
                  <td>{{ t('restocking.leadTimeDays', { days: c.leadTimeDays }) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted, watch } from 'vue'
import { api } from '../api'
import { useFilters } from '../composables/useFilters'
import { useI18n } from '../composables/useI18n'
import { formatCurrency, formatCurrencyWithDecimals } from '../utils/currency'

const LEAD_TIME_DAYS = {
  'Circuit Boards': 21,
  'Sensors': 14,
  'Actuators': 28,
  'Controllers': 18,
  'Power Supplies': 10
}
const DEFAULT_LEAD_TIME_DAYS = 14

export default {
  name: 'Restocking',
  setup() {
    const { t, currentCurrency, translateProductName } = useI18n()

    const { selectedLocation, selectedCategory, getCurrentFilters } = useFilters()

    const loading = ref(true)
    const error = ref(null)

    const forecasts = ref([])
    const inventoryItems = ref([])

    const budget = ref(0)
    const budgetInitialized = ref(false)
    const submitting = ref(false)
    const successMessage = ref(null)
    const submitError = ref(null)

    const candidates = computed(() => {
      const inventoryBySku = new Map(inventoryItems.value.map(item => [item.sku, item]))

      const joined = []
      for (const forecast of forecasts.value) {
        const inv = inventoryBySku.get(forecast.item_sku)
        if (!inv) continue

        const recommendedQty = Math.max(0, forecast.forecasted_demand - inv.quantity_on_hand)
        if (recommendedQty <= 0) continue

        const demandGap = forecast.forecasted_demand - forecast.current_demand
        const lineTotal = recommendedQty * inv.unit_cost

        joined.push({
          sku: inv.sku,
          name: inv.name,
          category: inv.category,
          quantity_on_hand: inv.quantity_on_hand,
          forecasted_demand: forecast.forecasted_demand,
          unit_cost: inv.unit_cost,
          leadTimeDays: LEAD_TIME_DAYS[inv.category] ?? DEFAULT_LEAD_TIME_DAYS,
          recommendedQty,
          demandGap,
          lineTotal
        })
      }

      joined.sort((a, b) => {
        if (b.demandGap !== a.demandGap) return b.demandGap - a.demandGap
        if (b.lineTotal !== a.lineTotal) return b.lineTotal - a.lineTotal
        return a.sku.localeCompare(b.sku)
      })

      return joined
    })

    const maxBudget = computed(() => candidates.value.reduce((sum, c) => sum + c.lineTotal, 0))

    const sliderStep = computed(() => Math.max(500, Math.round(maxBudget.value / 100)))

    const recommended = computed(() => {
      let remaining = budget.value
      const chosen = []
      for (const c of candidates.value) {
        if (c.lineTotal <= remaining + 1e-6) {
          remaining -= c.lineTotal
          chosen.push(c)
        }
      }
      return chosen
    })

    const totalCost = computed(() => recommended.value.reduce((sum, c) => sum + c.lineTotal, 0))
    const remainingBudget = computed(() => budget.value - totalCost.value)
    const skippedCount = computed(() => candidates.value.length - recommended.value.length)

    const translateCategory = (category) => {
      const categoryMap = {
        'Circuit Boards': t('categories.circuitBoards'),
        'Sensors': t('categories.sensors'),
        'Actuators': t('categories.actuators'),
        'Controllers': t('categories.controllers'),
        'Power Supplies': t('categories.powerSupplies')
      }
      return categoryMap[category] || category
    }

    const loadData = async () => {
      loading.value = true
      error.value = null
      try {
        const filters = getCurrentFilters()

        const [forecastsData, inventoryData] = await Promise.all([
          api.getDemandForecasts(),
          api.getInventory({
            warehouse: filters.warehouse,
            category: filters.category
          })
        ])

        forecasts.value = forecastsData
        inventoryItems.value = inventoryData

        // Initialize budget to 50% of max on first load, otherwise re-clamp
        // down if filters shrunk the candidate set below the current budget.
        const max = maxBudget.value
        if (!budgetInitialized.value) {
          budget.value = max / 2
          budgetInitialized.value = true
        } else if (budget.value > max) {
          budget.value = max
        }
      } catch (err) {
        error.value = 'Failed to load restocking data: ' + err.message
      } finally {
        loading.value = false
      }
    }

    watch([selectedLocation, selectedCategory], loadData)

    const placeOrder = async () => {
      submitting.value = true
      successMessage.value = null
      submitError.value = null
      try {
        const order = await api.createRestockingOrder({
          budget: budget.value,
          items: recommended.value.map(c => ({
            sku: c.sku,
            name: c.name,
            quantity: c.recommendedQty,
            unit_price: c.unit_cost
          }))
        })
        successMessage.value = t('restocking.orderPlaced', { orderNumber: order.order_number })
        await loadData()
      } catch (err) {
        submitError.value = t('restocking.orderFailed')
        console.error(err)
      } finally {
        submitting.value = false
      }
    }

    onMounted(loadData)

    return {
      t,
      loading,
      error,
      budget,
      maxBudget,
      sliderStep,
      candidates,
      recommended,
      totalCost,
      remainingBudget,
      skippedCount,
      submitting,
      successMessage,
      submitError,
      placeOrder,
      formatCurrency,
      formatCurrencyWithDecimals,
      currentCurrency,
      translateProductName,
      translateCategory
    }
  }
}
</script>

<style scoped>
.page-header {
  margin-bottom: 1.5rem;
}

.page-header h2 {
  margin-bottom: 0.25rem;
}

.page-header p {
  color: #64748b;
  font-size: 0.875rem;
}

.banner {
  padding: 0.75rem 1rem;
  border-radius: 8px;
  font-size: 0.875rem;
  font-weight: 500;
  margin-bottom: 1.5rem;
}

.success-banner {
  background: #d1fae5;
  color: #065f46;
  border: 1px solid #a7f3d0;
}

.error-banner {
  background: #fee2e2;
  color: #991b1b;
  border: 1px solid #fecaca;
}

.budget-card {
  margin-bottom: 1.5rem;
}

.budget-body {
  padding: 1.5rem;
}

.budget-amount {
  font-size: 2rem;
  font-weight: 700;
  color: #0f172a;
  margin-bottom: 1rem;
}

.budget-help {
  color: #64748b;
  font-size: 0.813rem;
  margin-top: 0.75rem;
}

.full-restock-cost {
  color: #64748b;
  font-size: 0.813rem;
  margin-top: 0.25rem;
}

.budget-slider {
  width: 100%;
  height: 6px;
  border-radius: 3px;
  background: #e2e8f0;
  appearance: none;
  -webkit-appearance: none;
  outline: none;
  cursor: pointer;
}

.budget-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #2563eb;
  border: 2px solid white;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
  cursor: pointer;
  transition: background 0.2s;
}

.budget-slider::-webkit-slider-thumb:hover {
  background: #1d4ed8;
}

.budget-slider::-moz-range-thumb {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #2563eb;
  border: 2px solid white;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
  cursor: pointer;
  transition: background 0.2s;
}

.budget-slider::-moz-range-thumb:hover {
  background: #1d4ed8;
}

.budget-slider::-moz-range-track {
  width: 100%;
  height: 6px;
  border-radius: 3px;
  background: #e2e8f0;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1.5rem;
  padding: 1.25rem 1.5rem;
  border-bottom: 1px solid #e2e8f0;
}

.card-title {
  font-size: 1rem;
  font-weight: 600;
  color: #0f172a;
  margin: 0;
}

.btn-primary {
  background: #2563eb;
  color: white;
  border: none;
  border-radius: 6px;
  padding: 0.5rem 1.25rem;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
}

.btn-primary:hover:not(:disabled) {
  background: #1d4ed8;
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.empty-state {
  padding: 2rem;
  text-align: center;
  color: #64748b;
  font-size: 0.875rem;
}

.skipped-note {
  padding: 0.75rem 1.5rem 0;
  color: #b45309;
  font-size: 0.813rem;
  font-weight: 500;
}

.loading,
.error {
  padding: 2rem;
  text-align: center;
  color: #64748b;
}

.error {
  color: #ef4444;
}
</style>
