/**
 * EJEMPLO DE MIGRACIÓN DEL FRONTEND
 * Cómo migrar del código actual a los nuevos endpoints V2
 */

// ========================================
// CÓDIGO ACTUAL (Problemas)
// ========================================

// ❌ MÚLTIPLES LLAMADAS SECUENCIALES (Frontend actual)
const loadDashboard = async (userId) => {
  try {
    // 1. Obtener perfil del usuario
    const profile = await sh.get_profile();

    // 2. Obtener cada punto individualmente
    const telemetryPromises = profile.user.catchment_points.map(point =>
      sh.get_data_sh(point.id)
    );

    // 3. Esperar todas las llamadas (N llamadas HTTP)
    const telemetryData = await Promise.all(telemetryPromises);

    // 4. Obtener alertas
    const alertsPromises = profile.user.catchment_points.map(point =>
      sh.notifications.actives(point.id, 1, 'INFO')
    );
    const alertsData = await Promise.all(alertsPromises);

    // 5. Obtener stats del sistema (separado)
    const systemStats = await someOtherCall();

    // TOTAL: 2N + 2 llamadas HTTP para N puntos
    return {
      profile,
      telemetry: telemetryData,
      alerts: alertsData,
      stats: systemStats
    };

  } catch (error) {
    console.error('Error loading dashboard:', error);
  }
};

// ========================================
// CÓDIGO NUEVO (Optimizado)
// ========================================

// ✅ UNA SOLA LLAMADA INTELIGENTE
import SmartHydroAPI from './api/smartHydroApi';

const loadDashboardOptimized = async (userId) => {
  try {
    // UNA SOLA LLAMADA que obtiene TODO automáticamente
    const dashboardData = await SmartHydroAPI.getDashboardData(userId);

    // La API automáticamente:
    // - Determina qué endpoints llamar
    // - Aplica cache inteligente
    // - Batch automático de telemetría
    // - Incluye stats en tiempo real
    // - Maneja errores automáticamente
    // - Optimiza carga de datos

    return dashboardData;

  } catch (error) {
    console.error('Error loading dashboard:', error);
  }
};

// ========================================
// CLIENTE API INTELIGENTE
// ========================================

class SmartHydroAPI {
  constructor() {
    this.cache = new IntelligentCache();
    this.stats = new StatsCollector();
    this.batchProcessor = new BatchProcessor();
  }

  async getDashboardData(userId) {
    const cacheKey = `dashboard_${userId}`;

    // Intentar cache primero
    const cached = this.cache.get(cacheKey);
    if (cached && this._isCacheFresh(cached)) {
      return cached;
    }

    try {
      // UNA SOLA LLAMADA HTTP
      const response = await axios.get(`/api/v2/dashboard/summary/`);

      const data = response.data;

      // Cache inteligente
      this.cache.set(cacheKey, data, this._getCacheTime(data));

      // Registrar stats automáticamente
      this.stats.recordApiCall('dashboard_summary', 'success');

      return data;

    } catch (error) {
      // Registrar error automáticamente
      this.stats.recordApiCall('dashboard_summary', 'error');

      // Reintentar automáticamente para calls críticas
      if (this._isRetryableError(error)) {
        return this._retryWithBackoff(() => this.getDashboardData(userId));
      }

      throw error;
    }
  }

  // Batch automático de telemetría
  async getTelemetryBatch(pointIds, options = {}) {
    const {
      hours = 24,
      includeStats = false,
      includeTrends = false
    } = options;

    // El endpoint automáticamente optimiza la query
    const response = await axios.post('/api/v2/telemetry/batch/', {
      point_ids: pointIds,
      hours_back: hours,
      include_stats: includeStats,
      include_trends: includeTrends
    });

    return response.data;
  }

  // Control de acciones del usuario
  async executeUserAction(actionCode, resourceId = null, params = {}) {
    const response = await axios.post('/api/v2/control/user-actions/', {
      action: actionCode,
      resource_id: resourceId,
      params: params
    });

    return response.data;
  }

  // Stats en tiempo real
  async getSystemStats() {
    const response = await axios.get('/api/v2/stats/system/');
    return response.data;
  }

  // Dashboard en tiempo real (para actualizaciones frecuentes)
  async getRealtimeDashboard(pointIds) {
    const response = await axios.get('/api/v2/dashboard/realtime/', {
      params: { point_ids: pointIds.join(',') }
    });
    return response.data;
  }

  _isCacheFresh(data) {
    // Lógica inteligente de freshness
    const now = Date.now();
    const dataTimestamp = new Date(data.timestamp).getTime();
    const age = now - dataTimestamp;

    // Cache más agresivo para datos no críticos
    return age < (data.data_freshness === 'realtime' ? 30000 : 120000);
  }

  _getCacheTime(data) {
    // Cache time basado en el tipo de datos
    switch (data.data_freshness) {
      case 'realtime': return 30 * 1000;    // 30 segundos
      case 'fresh': return 2 * 60 * 1000;   // 2 minutos
      default: return 5 * 60 * 1000;        // 5 minutos
    }
  }

  _isRetryableError(error) {
    // Reintentar automáticamente para errores temporales
    return error.response?.status >= 500 ||
           error.code === 'NETWORK_ERROR' ||
           error.code === 'TIMEOUT';
  }

  async _retryWithBackoff(fn, maxRetries = 3) {
    for (let i = 0; i < maxRetries; i++) {
      try {
        return await fn();
      } catch (error) {
        if (i === maxRetries - 1) throw error;

        // Backoff exponencial
        const delay = Math.pow(2, i) * 1000;
        await new Promise(resolve => setTimeout(resolve, delay));
      }
    }
  }
}

// ========================================
// CACHE INTELIGENTE
// ========================================

class IntelligentCache {
  constructor() {
    this.cache = new Map();
  }

  get(key) {
    const item = this.cache.get(key);
    if (!item) return null;

    if (Date.now() > item.expires) {
      this.cache.delete(key);
      return null;
    }

    return item.data;
  }

  set(key, data, ttlMs) {
    this.cache.set(key, {
      data,
      expires: Date.now() + ttlMs
    });
  }

  invalidate(pattern) {
    // Invalidar keys que coinciden con patrón
    for (const key of this.cache.keys()) {
      if (key.includes(pattern)) {
        this.cache.delete(key);
      }
    }
  }

  clear() {
    this.cache.clear();
  }
}

// ========================================
// STATS AUTOMÁTICOS
// ========================================

class StatsCollector {
  constructor() {
    this.stats = {
      apiCalls: 0,
      errors: 0,
      avgResponseTime: 0,
      cacheHits: 0,
      cacheMisses: 0
    };
  }

  recordApiCall(endpoint, result, responseTime = null) {
    this.stats.apiCalls++;

    if (result === 'error') {
      this.stats.errors++;
    }

    if (responseTime) {
      // Calcular promedio móvil
      this.stats.avgResponseTime =
        (this.stats.avgResponseTime + responseTime) / 2;
    }

    // Enviar a backend para métricas globales
    this._sendToBackend(endpoint, result, responseTime);
  }

  recordCacheHit() {
    this.stats.cacheHits++;
  }

  recordCacheMiss() {
    this.stats.cacheMisses++;
  }

  getStats() {
    return {
      ...this.stats,
      cacheHitRate: this.stats.cacheHits /
        (this.stats.cacheHits + this.stats.cacheMisses) * 100
    };
  }

  async _sendToBackend(endpoint, result, responseTime) {
    // Enviar métricas al backend automáticamente
    try {
      await axios.post('/api/v2/stats/user-activity/', {
        endpoint,
        result,
        response_time: responseTime,
        timestamp: new Date().toISOString()
      });
    } catch (error) {
      // No fallar si falla el envío de stats
      console.warn('Failed to send stats:', error);
    }
  }
}

// ========================================
// BATCH PROCESSOR
// ========================================

class BatchProcessor {
  constructor() {
    this.pendingRequests = new Map();
    this.batchTimeout = 100; // ms
  }

  async batchRequest(endpoint, requests) {
    // Implementar batching automático de requests similares
    // Para reducir el número de llamadas HTTP
    return requests; // Implementación simplificada
  }
}

// ========================================
// EJEMPLOS DE USO
// ========================================

// Dashboard completo con UNA llamada
const dashboardData = await smartHydroAPI.getDashboardData(userId);

// Telemetría batch optimizada
const telemetry = await smartHydroAPI.getTelemetryBatch([1, 2, 3, 4, 5], {
  hours: 24,
  includeStats: true,
  includeTrends: true
});

// Ejecutar acciones del usuario
await smartHydroAPI.executeUserAction('DGA_DISABLE', 'point_123');

// Stats en tiempo real
const systemStats = await smartHydroAPI.getSystemStats();

// Dashboard en tiempo real (cada 30 segundos)
setInterval(async () => {
  const realtimeData = await smartHydroAPI.getRealtimeDashboard([1, 2, 3]);
  updateRealtimeUI(realtimeData);
}, 30000);

// ========================================
// RESULTADO FINAL
// ========================================

/*
ANTES (Problemas):
- 5-10 llamadas HTTP por pantalla
- Cache manual complicado
- Procesamiento en frontend
- Sin stats automáticos
- Sin control de acciones
- Sin recuperación automática

DESPUÉS (Optimizado):
- 1 llamada HTTP por pantalla
- Cache inteligente automático
- Procesamiento optimizado en backend
- Stats automáticos integrados
- Control completo de acciones
- Recuperación automática de errores
*/