# Frontend Performance Architecture for <75ms Backend Response

## Overview
This document outlines the frontend optimization strategies to complement the backend performance improvements and achieve the overall <75ms user experience target.

## Client-Side Caching Strategy

### 1. Multi-Level Frontend Caching

```javascript
// Frontend Cache Architecture
class VelroFrontendCache {
  constructor() {
    this.l1Cache = new Map(); // Memory cache for hot data
    this.l2Cache = new LocalStorageCache(); // Persistent cache
    this.l3Cache = new IndexedDBCache(); // Large data cache
  }

  async get(key, fallbackFn) {
    // L1: Memory cache (instant)
    if (this.l1Cache.has(key)) {
      return this.l1Cache.get(key);
    }

    // L2: LocalStorage (1-2ms)
    const l2Data = await this.l2Cache.get(key);
    if (l2Data) {
      this.l1Cache.set(key, l2Data);
      return l2Data;
    }

    // L3: IndexedDB (5-10ms)
    const l3Data = await this.l3Cache.get(key);
    if (l3Data) {
      this.l1Cache.set(key, l3Data);
      this.l2Cache.set(key, l3Data);
      return l3Data;
    }

    // Fallback to network
    if (fallbackFn) {
      const networkData = await fallbackFn();
      this.setAll(key, networkData);
      return networkData;
    }

    return null;
  }

  setAll(key, data) {
    this.l1Cache.set(key, data);
    this.l2Cache.set(key, data);
    this.l3Cache.set(key, data);
  }
}
```

### 2. Optimistic UI Updates

```javascript
// Optimistic UI for Generation Actions
class OptimisticGenerationService {
  async createGeneration(prompt, model) {
    // Immediately show optimistic state
    const optimisticId = generateTempId();
    const optimisticGeneration = {
      id: optimisticId,
      prompt,
      model,
      status: 'generating',
      created_at: new Date(),
      optimistic: true
    };

    // Update UI immediately
    this.store.addGeneration(optimisticGeneration);

    try {
      // Make actual API call
      const response = await this.api.createGeneration(prompt, model);
      
      // Replace optimistic with real data
      this.store.replaceGeneration(optimisticId, response.data);
      
      return response.data;
    } catch (error) {
      // Remove optimistic entry on error
      this.store.removeGeneration(optimisticId);
      throw error;
    }
  }
}
```

### 3. Progressive Loading Patterns

```javascript
// Progressive Loading for Generation Lists
class ProgressiveGenerationLoader {
  constructor() {
    this.loadingStates = new Map();
    this.intersectionObserver = new IntersectionObserver(
      this.handleIntersection.bind(this),
      { threshold: 0.1 }
    );
  }

  async loadGenerationsProgressive(userId) {
    // Load essential data first (fastest)
    const essentialData = await this.loadEssentialGenerations(userId);
    this.renderEssentialGenerations(essentialData);

    // Load detailed data progressively
    const detailedPromises = essentialData.map(gen => 
      this.loadGenerationDetails(gen.id)
    );

    // Render as details become available
    for (const promise of detailedPromises) {
      promise.then(details => this.updateGenerationDetails(details));
    }
  }

  async loadEssentialGenerations(userId) {
    // Load only critical fields for fast initial render
    return this.api.getGenerations(userId, {
      fields: ['id', 'prompt', 'status', 'created_at'],
      limit: 20
    });
  }

  async loadGenerationDetails(generationId) {
    // Load complete generation data
    return this.api.getGeneration(generationId, {
      include_media: true,
      include_metadata: true
    });
  }
}
```

## 4. API Call Batching

```javascript
// Intelligent API Call Batching
class VelroBatchingService {
  constructor() {
    this.pendingRequests = new Map();
    this.batchTimeout = 50; // 50ms batching window
    this.maxBatchSize = 10;
  }

  async batchedRequest(endpoint, params) {
    const batchKey = this.getBatchKey(endpoint, params);
    
    if (!this.pendingRequests.has(batchKey)) {
      this.pendingRequests.set(batchKey, {
        requests: [],
        timer: null
      });
    }

    const batch = this.pendingRequests.get(batchKey);

    return new Promise((resolve, reject) => {
      batch.requests.push({ params, resolve, reject });

      // Clear existing timer
      if (batch.timer) {
        clearTimeout(batch.timer);
      }

      // Set new timer or execute immediately if batch is full
      if (batch.requests.length >= this.maxBatchSize) {
        this.executeBatch(batchKey);
      } else {
        batch.timer = setTimeout(() => {
          this.executeBatch(batchKey);
        }, this.batchTimeout);
      }
    });
  }

  async executeBatch(batchKey) {
    const batch = this.pendingRequests.get(batchKey);
    if (!batch || batch.requests.length === 0) return;

    this.pendingRequests.delete(batchKey);

    try {
      const batchedParams = batch.requests.map(req => req.params);
      const results = await this.api.batchRequest(batchKey, batchedParams);

      // Resolve individual promises
      batch.requests.forEach((request, index) => {
        request.resolve(results[index]);
      });
    } catch (error) {
      // Reject all promises in batch
      batch.requests.forEach(request => {
        request.reject(error);
      });
    }
  }
}
```

## 5. Smart Prefetching

```javascript
// Predictive Prefetching Based on User Behavior
class VelroPrefetchingService {
  constructor() {
    this.userPatterns = new Map();
    this.prefetchQueue = [];
    this.prefetchInProgress = new Set();
  }

  trackUserAction(action, context) {
    const userId = context.userId;
    const pattern = this.userPatterns.get(userId) || {
      sequences: [],
      frequency: new Map()
    };

    // Record action sequence
    pattern.sequences.push({
      action,
      timestamp: Date.now(),
      context
    });

    // Keep only recent sequences (last 100 actions)
    if (pattern.sequences.length > 100) {
      pattern.sequences = pattern.sequences.slice(-100);
    }

    // Update frequency map
    const actionKey = `${action}:${context.resourceType || 'unknown'}`;
    pattern.frequency.set(
      actionKey,
      (pattern.frequency.get(actionKey) || 0) + 1
    );

    this.userPatterns.set(userId, pattern);

    // Trigger predictive prefetching
    this.predictAndPrefetch(userId, action, context);
  }

  predictAndPrefetch(userId, currentAction, context) {
    const pattern = this.userPatterns.get(userId);
    if (!pattern) return;

    // Analyze recent sequences to predict next actions
    const recentSequences = pattern.sequences.slice(-10);
    const predictions = this.analyzePredictions(recentSequences, currentAction);

    // Prefetch predicted resources
    predictions.forEach(prediction => {
      if (prediction.confidence > 0.7) { // High confidence threshold
        this.queuePrefetch(prediction);
      }
    });
  }

  analyzePredictions(sequences, currentAction) {
    const predictions = [];
    
    // Look for patterns: if user did A, they often do B next
    const patterns = this.extractPatterns(sequences);
    
    for (const [triggerAction, nextActions] of patterns) {
      if (triggerAction === currentAction) {
        nextActions.forEach(({ action, frequency }) => {
          predictions.push({
            action,
            confidence: frequency,
            priority: this.calculatePriority(action, frequency)
          });
        });
      }
    }

    return predictions.sort((a, b) => b.confidence - a.confidence);
  }

  async queuePrefetch(prediction) {
    const prefetchKey = this.getPrefetchKey(prediction);
    
    if (this.prefetchInProgress.has(prefetchKey)) {
      return; // Already prefetching
    }

    this.prefetchInProgress.add(prefetchKey);

    try {
      const data = await this.executePrefe
.    ction);
      
      // Cache prefetched data
      this.cache.setAll(prefetchKey, data);
      
    } catch (error) {
      console.debug('Prefetch failed:', error);
    } finally {
      this.prefetchInProgress.delete(prefetchKey);
    }
  }
}
```

## 6. Response Compression and Serialization

```javascript
// Optimized Response Handling
class VelroResponseOptimizer {
  constructor() {
    this.compressionThreshold = 1024; // 1KB
    this.serializationFormats = new Map([
      ['generation_list', this.optimizeGenerationList.bind(this)],
      ['generation_detail', this.optimizeGenerationDetail.bind(this)],
      ['user_profile', this.optimizeUserProfile.bind(this)]
    ]);
  }

  async processResponse(response, responseType) {
    const optimizer = this.serializationFormats.get(responseType);
    
    if (optimizer) {
      return optimizer(response);
    }

    return response;
  }

  optimizeGenerationList(generations) {
    // Remove unnecessary fields for list view
    return generations.map(gen => ({
      id: gen.id,
      prompt: gen.prompt.substring(0, 100) + (gen.prompt.length > 100 ? '...' : ''),
      status: gen.status,
      thumbnail_url: gen.media_urls?.[0]?.replace('/full/', '/thumb/'),
      created_at: gen.created_at,
      model: gen.model.name // Only name, not full model object
    }));
  }

  optimizeGenerationDetail(generation) {
    return {
      ...generation,
      // Lazy load heavy fields
      full_metadata: null, // Load on demand
      related_generations: generation.related_generations?.slice(0, 5) // Limit related
    };
  }

  optimizeUserProfile(profile) {
    return {
      id: profile.id,
      email: profile.email,
      display_name: profile.display_name,
      avatar_url: profile.avatar_url,
      credits_balance: profile.credits_balance,
      role: profile.role,
      // Lazy load settings and preferences
      settings: null,
      recent_activity: null
    };
  }
}
```

## 7. Connection Optimization

```javascript
// HTTP/2 Connection Multiplexing and Keep-Alive
class VelroHttpClient {
  constructor() {
    this.baseURL = process.env.REACT_APP_API_URL;
    this.connections = new Map();
    this.keepAliveAgents = new Map();
  }

  async request(endpoint, options = {}) {
    const url = `${this.baseURL}${endpoint}`;
    const connectionKey = new URL(url).origin;

    // Reuse existing connection
    let connection = this.connections.get(connectionKey);
    if (!connection) {
      connection = this.createOptimizedConnection(connectionKey);
      this.connections.set(connectionKey, connection);
    }

    // Apply performance optimizations
    const optimizedOptions = {
      ...options,
      keepalive: true,
      signal: AbortSignal.timeout(options.timeout || 10000),
      headers: {
        'Connection': 'keep-alive',
        'Accept-Encoding': 'gzip, br',
        'Accept': 'application/json',
        ...options.headers
      }
    };

    return fetch(url, optimizedOptions);
  }

  createOptimizedConnection(origin) {
    // Configure HTTP/2 multiplexing and keep-alive
    const agent = new https.Agent({
      keepAlive: true,
      keepAliveMsecs: 30000,
      maxSockets: 20,
      maxFreeSockets: 10,
      timeout: 60000
    });

    this.keepAliveAgents.set(origin, agent);
    return agent;
  }
}
```

## 8. State Management Optimization

```javascript
// Optimized Redux Store with Normalized Data
const optimizedGenerationsSlice = createSlice({
  name: 'generations',
  initialState: {
    byId: {},
    allIds: [],
    loading: {},
    lastFetch: {},
    pagination: {
      hasMore: true,
      nextCursor: null
    }
  },
  reducers: {
    addGenerations: (state, action) => {
      const { generations, replace = false } = action.payload;
      
      if (replace) {
        state.byId = {};
        state.allIds = [];
      }

      generations.forEach(generation => {
        state.byId[generation.id] = generation;
        if (!state.allIds.includes(generation.id)) {
          state.allIds.push(generation.id);
        }
      });

      // Keep sorted by creation date
      state.allIds.sort((a, b) => 
        new Date(state.byId[b].created_at) - new Date(state.byId[a].created_at)
      );
    },
    
    updateGenerationOptimistic: (state, action) => {
      const { id, updates } = action.payload;
      if (state.byId[id]) {
        state.byId[id] = { ...state.byId[id], ...updates };
      }
    },

    setLoading: (state, action) => {
      const { resource, loading } = action.payload;
      state.loading[resource] = loading;
    }
  }
});

// Memoized selectors for performance
export const selectGenerationById = createSelector(
  [state => state.generations.byId, (state, id) => id],
  (byId, id) => byId[id]
);

export const selectGenerationsList = createSelector(
  [state => state.generations.byId, state => state.generations.allIds],
  (byId, allIds) => allIds.map(id => byId[id])
);
```

## 9. Real-Time Optimization

```javascript
// Optimized WebSocket Connection with Intelligent Batching
class VelroRealtimeService {
  constructor() {
    this.ws = null;
    this.messageQueue = [];
    this.batchTimer = null;
    this.batchDelay = 16; // ~60fps
    this.reconnectDelay = 1000;
    this.maxReconnectDelay = 30000;
  }

  connect() {
    this.ws = new WebSocket(process.env.REACT_APP_WS_URL);
    
    this.ws.onmessage = (event) => {
      const message = JSON.parse(event.data);
      this.queueMessage(message);
    };

    this.ws.onclose = () => {
      this.scheduleReconnect();
    };
  }

  queueMessage(message) {
    this.messageQueue.push(message);

    if (!this.batchTimer) {
      this.batchTimer = setTimeout(() => {
        this.processBatch();
      }, this.batchDelay);
    }
  }

  processBatch() {
    const batch = [...this.messageQueue];
    this.messageQueue = [];
    this.batchTimer = null;

    // Group messages by type for efficient processing
    const groupedMessages = batch.reduce((groups, message) => {
      const type = message.type;
      if (!groups[type]) groups[type] = [];
      groups[type].push(message);
      return groups;
    }, {});

    // Process each group optimally
    Object.entries(groupedMessages).forEach(([type, messages]) => {
      this.processMessageGroup(type, messages);
    });
  }

  processMessageGroup(type, messages) {
    switch (type) {
      case 'generation_update':
        this.batchUpdateGenerations(messages);
        break;
      case 'user_credit_update':
        this.batchUpdateCredits(messages);
        break;
      default:
        messages.forEach(msg => this.processMessage(msg));
    }
  }
}
```

## Performance Monitoring and Alerting

```javascript
// Frontend Performance Monitoring
class VelroPerformanceMonitor {
  constructor() {
    this.metrics = {
      apiCalls: new Map(),
      renderTimes: new Map(),
      cacheHitRates: new Map(),
      errors: []
    };
    
    this.observer = new PerformanceObserver(this.handlePerformanceEntry.bind(this));
    this.observer.observe({ entryTypes: ['measure', 'navigation', 'resource'] });
  }

  trackApiCall(endpoint, startTime, endTime, success) {
    const duration = endTime - startTime;
    const key = endpoint;
    
    if (!this.metrics.apiCalls.has(key)) {
      this.metrics.apiCalls.set(key, {
        count: 0,
        totalTime: 0,
        errors: 0,
        avgTime: 0
      });
    }

    const stats = this.metrics.apiCalls.get(key);
    stats.count++;
    stats.totalTime += duration;
    stats.avgTime = stats.totalTime / stats.count;
    
    if (!success) {
      stats.errors++;
    }

    // Alert if average exceeds target
    if (stats.avgTime > 75) { // 75ms target
      console.warn(`API performance degraded: ${key} avg=${stats.avgTime}ms`);
    }
  }

  trackCacheHit(cacheLevel, hit) {
    if (!this.metrics.cacheHitRates.has(cacheLevel)) {
      this.metrics.cacheHitRates.set(cacheLevel, {
        hits: 0,
        misses: 0,
        rate: 0
      });
    }

    const stats = this.metrics.cacheHitRates.get(cacheLevel);
    if (hit) {
      stats.hits++;
    } else {
      stats.misses++;
    }

    stats.rate = stats.hits / (stats.hits + stats.misses) * 100;

    // Alert if hit rate drops below target
    if (stats.rate < 80) { // 80% minimum target
      console.warn(`Cache hit rate low: ${cacheLevel} rate=${stats.rate}%`);
    }
  }

  getMetrics() {
    return {
      apiCalls: Array.from(this.metrics.apiCalls.entries()),
      cacheHitRates: Array.from(this.metrics.cacheHitRates.entries()),
      errors: this.metrics.errors.slice(-50), // Last 50 errors
      timestamp: Date.now()
    };
  }
}
```

## Implementation Timeline

1. **Week 1**: Implement multi-level caching and optimistic UI
2. **Week 2**: Add API batching and progressive loading
3. **Week 3**: Implement smart prefetching and response optimization
4. **Week 4**: Optimize state management and real-time features
5. **Week 5**: Performance monitoring and fine-tuning

## Expected Performance Gains

- **Initial Load**: 2-3s → 800ms (70% reduction)
- **Navigation**: 500ms → 150ms (70% reduction) 
- **API Interactions**: 300ms → <75ms (75% reduction)
- **Cache Hit Rate**: 60% → 95% (35% improvement)
- **Perceived Performance**: Immediate UI updates with optimistic rendering