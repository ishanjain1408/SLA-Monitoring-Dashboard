import { parse } from 'csv-parse/sync';
import { insertLogs, MonitoringLog } from './db';

// Helper to normalize timestamp to ISO UTC
function parseTimestamp(ts: string): string | null {
  if (!ts || ts.trim() === '') return null;
  ts = ts.trim();
  
  // Check Unix epoch (all digits)
  if (/^\d{10,}$/.test(ts)) {
    const epoch = parseInt(ts, 10);
    // reasonable epoch range 2020 - 2030
    if (epoch > 1577836800 && epoch < 1893456000) {
      return new Date(epoch * 1000).toISOString();
    }
  }
  
  // Try parsing ISO strings (built-in Date handles ISO with offsets and Z)
  const d = new Date(ts);
  if (!isNaN(d.getTime())) {
    return d.toISOString();
  }
  
  return null;
}

// Helper to normalize latency to ms
function normalizeLatency(latencyVal: string, unit: string): number | null {
  if (!latencyVal || latencyVal.trim() === '') return null;
  const val = parseFloat(latencyVal);
  if (isNaN(val)) return null;
  
  const u = unit ? unit.trim().toLowerCase() : '';
  if (u === 'ms') {
    return val;
  } else if (u === 's') {
    return val * 1000.0;
  }
  return null;
}

export function processCsvData(csvText: string) {
  // Use csv-parse to parse the text
  const records = parse(csvText, {
    columns: true,
    skip_empty_lines: true,
  });

  const logsToInsert: MonitoringLog[] = [];

  for (const row of records) {
    // Expected columns: service_id, service_name, timestamp, status_code, latency, latency_unit, agent, region
    const tsParsed = parseTimestamp(row.timestamp);
    if (!tsParsed) continue; // Skip invalid timestamps

    const dateOnly = tsParsed.split('T')[0];
    const statusCode = parseInt(row.status_code, 10);
    const latency = normalizeLatency(row.latency, row.latency_unit);
    
    // HTTP 2xx = success
    const isSuccess = !isNaN(statusCode) && statusCode >= 200 && statusCode < 300;

    logsToInsert.push({
      service_id: row.service_id,
      service_name: row.service_name,
      timestamp: tsParsed,
      status_code: isNaN(statusCode) ? 0 : statusCode,
      latency_ms: latency,
      is_success: isSuccess,
      agent: row.agent,
      region: row.region,
      date: dateOnly
    });
  }

  // Insert into DB
  const insertedCount = insertLogs(logsToInsert);
  
  return {
    totalParsed: records.length,
    insertedCount
  };
}
