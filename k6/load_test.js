/**
 * K6 Load Test untuk Pub-Sub Log Aggregator
 * 
 * Test scenarios:
 * - High throughput event publishing
 * - Duplicate detection
 * - Response time monitoring
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

// Custom metrics
const errorRate = new Rate('errors');
const publishDuration = new Trend('publish_duration');

// Test configuration
export const options = {
    stages: [
        { duration: '30s', target: 50 },   // Ramp up to 50 users
        { duration: '1m', target: 100 },   // Stay at 100 users
        { duration: '30s', target: 200 },  // Ramp up to 200 users
        { duration: '1m', target: 200 },   // Stay at 200 users
        { duration: '30s', target: 0 },    // Ramp down
    ],
    thresholds: {
        'http_req_duration': ['p(95)<500'], // 95% of requests should be below 500ms
        'errors': ['rate<0.01'],             // Error rate should be below 1%
    },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8080';
const TOPICS = ['logs', 'metrics', 'events', 'alerts', 'traces'];

// Generate unique event ID
function generateEventId() {
    return `k6-${Date.now()}-${Math.random().toString(36).substring(7)}`;
}

// Generate random topic
function randomTopic() {
    return TOPICS[Math.floor(Math.random() * TOPICS.length)];
}

// Generate event payload
function generateEvent(forceDuplicate = false) {
    // 30% chance of duplicate (reuse event_id from shared data)
    let eventId;
    if (forceDuplicate && Math.random() < 0.3 && __VU > 1) {
        // Simulate duplicate by using predictable ID
        eventId = `duplicate-${__VU % 100}`;
    } else {
        eventId = generateEventId();
    }
    
    return {
        topic: randomTopic(),
        event_id: eventId,
        timestamp: new Date().toISOString(),
        source: `k6-vu-${__VU}`,
        payload: {
            message: `Load test event from VU ${__VU}`,
            level: ['INFO', 'WARNING', 'ERROR'][Math.floor(Math.random() * 3)],
            metadata: {
                iteration: __ITER,
                vu: __VU,
                timestamp: Date.now(),
            },
        },
    };
}

export default function () {
    // Test 1: Publish single event
    const singleEvent = generateEvent(true);
    
    const singlePayload = JSON.stringify({
        events: singleEvent,
    });
    
    const singleParams = {
        headers: {
            'Content-Type': 'application/json',
        },
    };
    
    let singleResponse = http.post(`${BASE_URL}/publish`, singlePayload, singleParams);
    
    check(singleResponse, {
        'single publish status is 200': (r) => r.status === 200,
        'single publish response has status': (r) => JSON.parse(r.body).status === 'accepted',
    }) || errorRate.add(1);
    
    publishDuration.add(singleResponse.timings.duration);
    
    sleep(0.1);
    
    // Test 2: Publish batch events
    const batchSize = 10;
    const batchEvents = [];
    
    for (let i = 0; i < batchSize; i++) {
        batchEvents.push(generateEvent(true));
    }
    
    const batchPayload = JSON.stringify({
        events: batchEvents,
    });
    
    let batchResponse = http.post(`${BASE_URL}/publish`, batchPayload, singleParams);
    
    check(batchResponse, {
        'batch publish status is 200': (r) => r.status === 200,
        'batch publish response has status': (r) => JSON.parse(r.body).status === 'accepted',
        'batch publish received count matches': (r) => JSON.parse(r.body).received === batchSize,
    }) || errorRate.add(1);
    
    sleep(0.2);
    
    // Test 3: Get stats every 10 iterations
    if (__ITER % 10 === 0) {
        const statsResponse = http.get(`${BASE_URL}/stats`);
        
        check(statsResponse, {
            'stats status is 200': (r) => r.status === 200,
            'stats has required fields': (r) => {
                const stats = JSON.parse(r.body);
                return stats.received !== undefined && 
                       stats.unique_processed !== undefined &&
                       stats.duplicate_dropped !== undefined;
            },
        }) || errorRate.add(1);
        
        if (statsResponse.status === 200) {
            const stats = JSON.parse(statsResponse.body);
            console.log(`[VU ${__VU}] Stats - Received: ${stats.received}, Processed: ${stats.unique_processed}, Dropped: ${stats.duplicate_dropped}`);
        }
    }
    
    // Test 4: Get events every 20 iterations
    if (__ITER % 20 === 0) {
        const eventsResponse = http.get(`${BASE_URL}/events?limit=10`);
        
        check(eventsResponse, {
            'events status is 200': (r) => r.status === 200,
            'events response has events array': (r) => {
                const data = JSON.parse(r.body);
                return Array.isArray(data.events);
            },
        }) || errorRate.add(1);
    }
    
    sleep(0.5);
}

// Teardown function - run after test
export function handleSummary(data) {
    return {
        'summary.json': JSON.stringify(data),
        'stdout': textSummary(data, { indent: ' ', enableColors: true }),
    };
}

function textSummary(data, options) {
    const summary = [];
    summary.push('\n=== K6 Load Test Summary ===\n');
    summary.push(`Test Duration: ${data.state.testRunDurationMs / 1000}s`);
    summary.push(`VUs: ${data.metrics.vus.values.max}`);
    summary.push(`Iterations: ${data.metrics.iterations.values.count}`);
    summary.push(`\nHTTP Requests:`);
    summary.push(`  Total: ${data.metrics.http_reqs.values.count}`);
    summary.push(`  Rate: ${data.metrics.http_reqs.values.rate.toFixed(2)} req/s`);
    summary.push(`\nResponse Time:`);
    summary.push(`  Avg: ${data.metrics.http_req_duration.values.avg.toFixed(2)}ms`);
    summary.push(`  p95: ${data.metrics.http_req_duration.values['p(95)'].toFixed(2)}ms`);
    summary.push(`  p99: ${data.metrics.http_req_duration.values['p(99)'].toFixed(2)}ms`);
    summary.push(`\nError Rate: ${(data.metrics.errors.values.rate * 100).toFixed(2)}%`);
    summary.push('\n========================\n');
    return summary.join('\n');
}
