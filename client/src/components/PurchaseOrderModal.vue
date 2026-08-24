<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="isOpen && backlogItem" class="modal-overlay" @click="close">
        <div class="modal-container" @click.stop>
          <div class="modal-header">
            <h3 class="modal-title">
              {{ mode === 'view' ? 'Purchase Order Details' : 'Create Purchase Order' }}
            </h3>
            <button class="close-button" @click="close">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <path d="M15 5L5 15M5 5L15 15" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
              </svg>
            </button>
          </div>

          <div class="modal-body">
            <div class="po-header">
              <div class="po-title-section">
                <h4 class="item-name">{{ translateProductName(backlogItem.item_name) }}</h4>
                <div class="item-sku">SKU: {{ backlogItem.item_sku }}</div>
              </div>
              <span class="priority-badge" :class="backlogItem.priority">
                {{ backlogItem.priority }} Priority
              </span>
            </div>

            <!-- View mode -->
            <template v-if="mode === 'view'">
              <div v-if="loading" class="state-message">Loading purchase order...</div>
              <div v-else-if="error" class="state-message error">{{ error }}</div>
              <div v-else-if="purchaseOrder" class="info-grid">
                <div class="info-item">
                  <div class="info-label">PO Number</div>
                  <div class="info-value po-id">{{ purchaseOrder.id }}</div>
                </div>

                <div class="info-item">
                  <div class="info-label">Supplier</div>
                  <div class="info-value">{{ purchaseOrder.supplier_name }}</div>
                </div>

                <div class="info-item">
                  <div class="info-label">Quantity</div>
                  <div class="info-value">{{ purchaseOrder.quantity }} units</div>
                </div>

                <div class="info-item">
                  <div class="info-label">Unit Cost</div>
                  <div class="info-value">{{ formatCurrency(purchaseOrder.unit_cost) }}</div>
                </div>

                <div class="info-item">
                  <div class="info-label">Total Cost</div>
                  <div class="info-value">
                    <strong>{{ formatCurrency(purchaseOrder.quantity * purchaseOrder.unit_cost) }}</strong>
                  </div>
                </div>

                <div class="info-item">
                  <div class="info-label">Status</div>
                  <div class="info-value">
                    <span class="badge">{{ purchaseOrder.status }}</span>
                  </div>
                </div>

                <div class="info-item">
                  <div class="info-label">Created</div>
                  <div class="info-value">{{ formatDate(purchaseOrder.created_date) }}</div>
                </div>

                <div class="info-item">
                  <div class="info-label">Expected Delivery</div>
                  <div class="info-value">{{ formatDate(purchaseOrder.expected_delivery_date) }}</div>
                </div>

                <div v-if="purchaseOrder.notes" class="info-item info-item-full">
                  <div class="info-label">Notes</div>
                  <div class="info-value">{{ purchaseOrder.notes }}</div>
                </div>
              </div>
            </template>

            <!-- Create mode -->
            <template v-else>
              <div class="shortage-summary">
                <div class="summary-card danger">
                  <div class="summary-label">Shortage Amount</div>
                  <div class="summary-value">{{ shortage }} units</div>
                </div>
                <div class="summary-card warning">
                  <div class="summary-label">Days Delayed</div>
                  <div class="summary-value">{{ backlogItem.days_delayed }} days</div>
                </div>
              </div>

              <div class="form-grid">
                <div class="form-group">
                  <label for="po-supplier">Supplier Name</label>
                  <input
                    id="po-supplier"
                    v-model="form.supplierName"
                    type="text"
                    placeholder="e.g. Precision Parts Co."
                    class="form-input"
                  />
                </div>

                <div class="form-group">
                  <label for="po-quantity">Quantity</label>
                  <input
                    id="po-quantity"
                    v-model.number="form.quantity"
                    type="number"
                    min="1"
                    class="form-input"
                  />
                </div>

                <div class="form-group">
                  <label for="po-unit-cost">Unit Cost</label>
                  <input
                    id="po-unit-cost"
                    v-model.number="form.unitCost"
                    type="number"
                    min="0"
                    step="0.01"
                    class="form-input"
                  />
                </div>

                <div class="form-group">
                  <label for="po-delivery">Expected Delivery Date</label>
                  <input
                    id="po-delivery"
                    v-model="form.expectedDeliveryDate"
                    type="date"
                    class="form-input"
                  />
                </div>

                <div class="form-group form-group-full">
                  <label for="po-notes">Notes</label>
                  <textarea
                    id="po-notes"
                    v-model="form.notes"
                    rows="3"
                    placeholder="Optional"
                    class="form-input"
                  ></textarea>
                </div>
              </div>

              <div class="total-line">
                <span class="total-label">Order Total</span>
                <span class="total-value">{{ formatCurrency(orderTotal) }}</span>
              </div>

              <div v-if="error" class="state-message error">{{ error }}</div>
            </template>
          </div>

          <div class="modal-footer">
            <button class="btn-secondary" @click="close">Close</button>
            <button
              v-if="mode !== 'view'"
              class="btn-primary"
              :disabled="!canSubmit"
              @click="submit"
            >
              {{ submitting ? 'Creating...' : 'Create Purchase Order' }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'

const { translateProductName } = useI18n()

const props = defineProps({
  isOpen: {
    type: Boolean,
    default: false
  },
  backlogItem: {
    type: Object,
    default: null
  },
  mode: {
    type: String,
    default: 'create'
  }
})

const emit = defineEmits(['close', 'po-created'])

const loading = ref(false)
const submitting = ref(false)
const error = ref(null)
const purchaseOrder = ref(null)

const form = ref({
  supplierName: '',
  quantity: 0,
  unitCost: 0,
  expectedDeliveryDate: '',
  notes: ''
})

const shortage = computed(() => {
  if (!props.backlogItem) return 0
  return props.backlogItem.quantity_needed - props.backlogItem.quantity_available
})

const orderTotal = computed(() => {
  return (form.value.quantity || 0) * (form.value.unitCost || 0)
})

const canSubmit = computed(() => {
  return !submitting.value &&
    form.value.supplierName.trim() !== '' &&
    form.value.quantity > 0 &&
    form.value.unitCost >= 0 &&
    form.value.expectedDeliveryDate !== ''
})

const resetForm = () => {
  form.value = {
    supplierName: '',
    // Default to covering exactly the shortage - the most common case
    quantity: shortage.value,
    unitCost: 0,
    expectedDeliveryDate: '',
    notes: ''
  }
}

const loadPurchaseOrder = async () => {
  try {
    loading.value = true
    error.value = null
    purchaseOrder.value = await api.getPurchaseOrderByBacklogItem(props.backlogItem.id)
  } catch (err) {
    error.value = 'Failed to load purchase order'
    console.error('Load purchase order error:', err)
  } finally {
    loading.value = false
  }
}

// Re-seed on every open so a reopened modal never shows the previous item's values
watch(
  () => [props.isOpen, props.backlogItem, props.mode],
  () => {
    if (!props.isOpen || !props.backlogItem) return

    error.value = null
    purchaseOrder.value = null

    if (props.mode === 'view') {
      loadPurchaseOrder()
    } else {
      resetForm()
    }
  },
  { immediate: true }
)

const submit = async () => {
  if (!canSubmit.value) return

  try {
    submitting.value = true
    error.value = null
    const created = await api.createPurchaseOrder({
      backlog_item_id: props.backlogItem.id,
      supplier_name: form.value.supplierName.trim(),
      quantity: form.value.quantity,
      unit_cost: form.value.unitCost,
      expected_delivery_date: form.value.expectedDeliveryDate,
      notes: form.value.notes.trim() || null
    })
    emit('po-created', created)
  } catch (err) {
    error.value = err.response?.data?.detail || 'Failed to create purchase order'
    console.error('Create purchase order error:', err)
  } finally {
    submitting.value = false
  }
}

const close = () => {
  emit('close')
}

const formatCurrency = (value) => {
  return (value || 0).toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD'
  })
}

const formatDate = (dateString) => {
  if (!dateString) return 'N/A'
  // A bare YYYY-MM-DD parses as UTC midnight, which renders as the previous day in
  // any negative-offset timezone. Pin it to local midnight so the picked date shows.
  const isDateOnly = /^\d{4}-\d{2}-\d{2}$/.test(dateString)
  const date = new Date(isDateOnly ? `${dateString}T00:00:00` : dateString)
  if (isNaN(date.getTime())) return 'N/A'
  return date.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  })
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
  padding: 1rem;
}

.modal-container {
  background: white;
  border-radius: 12px;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.15);
  max-width: 700px;
  width: 100%;
  max-height: 90vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1.5rem;
  border-bottom: 1px solid #e2e8f0;
}

.modal-title {
  font-size: 1.25rem;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.025em;
}

.close-button {
  background: none;
  border: none;
  color: #64748b;
  cursor: pointer;
  padding: 0.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  transition: all 0.15s ease;
}

.close-button:hover {
  background: #f1f5f9;
  color: #0f172a;
}

.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 2rem;
}

.po-header {
  display: flex;
  align-items: center;
  gap: 1.25rem;
  padding-bottom: 1.5rem;
  border-bottom: 1px solid #e2e8f0;
  margin-bottom: 1.5rem;
}

.po-title-section {
  flex: 1;
  min-width: 0;
}

.item-name {
  font-size: 1.5rem;
  font-weight: 700;
  color: #0f172a;
  margin: 0 0 0.5rem 0;
}

.item-sku {
  font-size: 0.875rem;
  color: #64748b;
  font-family: 'Monaco', 'Courier New', monospace;
}

.priority-badge {
  padding: 0.5rem 1rem;
  border-radius: 6px;
  font-size: 0.875rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.025em;
  flex-shrink: 0;
}

.priority-badge.high {
  background: #fecaca;
  color: #991b1b;
}

.priority-badge.medium {
  background: #fed7aa;
  color: #92400e;
}

.priority-badge.low {
  background: #dbeafe;
  color: #1e40af;
}

.shortage-summary {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1rem;
  margin-bottom: 2rem;
}

.summary-card {
  padding: 1.25rem;
  border-radius: 10px;
  border: 2px solid;
}

.summary-card.danger {
  border-color: #fecaca;
  background: #fef2f2;
}

.summary-card.warning {
  border-color: #fed7aa;
  background: #fffbeb;
}

.summary-label {
  font-size: 0.813rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #64748b;
  margin-bottom: 0.5rem;
}

.summary-value {
  font-size: 1.875rem;
  font-weight: 700;
  color: #0f172a;
}

.summary-card.danger .summary-value {
  color: #dc2626;
}

.summary-card.warning .summary-value {
  color: #f59e0b;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 1.25rem;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.form-group-full {
  grid-column: 1 / -1;
}

.form-group label {
  font-size: 0.813rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #64748b;
}

.form-input {
  padding: 0.625rem 0.75rem;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-size: 0.938rem;
  color: #0f172a;
  font-family: inherit;
  background: white;
  transition: all 0.15s ease;
}

.form-input:focus {
  outline: none;
  border-color: #2563eb;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
}

textarea.form-input {
  resize: vertical;
}

.total-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 1.5rem;
  padding-top: 1.5rem;
  border-top: 1px solid #e2e8f0;
}

.total-label {
  font-size: 0.813rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #64748b;
}

.total-value {
  font-size: 1.5rem;
  font-weight: 700;
  color: #0f172a;
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1.5rem;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.info-item-full {
  grid-column: 1 / -1;
}

.info-label {
  font-size: 0.813rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #64748b;
}

.info-value {
  font-size: 0.938rem;
  color: #0f172a;
  font-weight: 500;
}

.info-value.po-id {
  font-family: 'Monaco', 'Courier New', monospace;
  color: #2563eb;
}

.badge {
  display: inline-block;
  padding: 0.25rem 0.625rem;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 600;
  background: #dbeafe;
  color: #1e40af;
}

.state-message {
  padding: 1rem 0;
  font-size: 0.938rem;
  color: #64748b;
}

.state-message.error {
  color: #dc2626;
}

.modal-footer {
  padding: 1.5rem;
  border-top: 1px solid #e2e8f0;
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
}

.btn-secondary {
  padding: 0.625rem 1.25rem;
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-weight: 500;
  font-size: 0.875rem;
  color: #334155;
  cursor: pointer;
  transition: all 0.15s ease;
  font-family: inherit;
}

.btn-secondary:hover {
  background: #e2e8f0;
  border-color: #cbd5e1;
}

.btn-primary {
  padding: 0.625rem 1.25rem;
  background: #2563eb;
  border: 1px solid #2563eb;
  border-radius: 8px;
  font-weight: 500;
  font-size: 0.875rem;
  color: white;
  cursor: pointer;
  transition: all 0.15s ease;
  font-family: inherit;
}

.btn-primary:hover:not(:disabled) {
  background: #1d4ed8;
  border-color: #1d4ed8;
}

.btn-primary:disabled {
  background: #cbd5e1;
  border-color: #cbd5e1;
  cursor: not-allowed;
}

/* Modal transition animations */
.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.2s ease;
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}

.modal-enter-active .modal-container,
.modal-leave-active .modal-container {
  transition: transform 0.2s ease;
}

.modal-enter-from .modal-container,
.modal-leave-to .modal-container {
  transform: scale(0.95);
}
</style>
