import Database from 'better-sqlite3';
import path from 'path';

// Connect to SQLite DB in the root of the project (or use DB_PATH for deployment)
const dbPath = process.env.DB_PATH || path.join(process.cwd(), 'earthre_sla.db');
const db = new Database(dbPath, { verbose: console.log });

// Initialize database schema
db.pragma('journal_mode = WAL');

db.exec(`
  CREATE TABLE IF NOT EXISTS monitoring_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service_id TEXT NOT NULL,
    service_name TEXT,
    timestamp TEXT NOT NULL,
    status_code INTEGER,
    latency_ms REAL,
    is_success BOOLEAN,
    agent TEXT,
    region TEXT,
    date TEXT,
    UNIQUE(service_id, timestamp, agent)
  );
`);

export interface MonitoringLog {
  service_id: string;
  service_name: string;
  timestamp: string;
  status_code: number;
  latency_ms: number | null;
  is_success: boolean;
  agent: string;
  region: string;
  date: string;
}

export function insertLogs(logs: MonitoringLog[]) {
  const insert = db.prepare(`
    INSERT OR IGNORE INTO monitoring_logs (
      service_id, service_name, timestamp, status_code, latency_ms, is_success, agent, region, date
    ) VALUES (
      @service_id, @service_name, @timestamp, @status_code, @latency_ms, @is_success, @agent, @region, @date
    )
  `);

  const insertMany = db.transaction((logsToInsert: MonitoringLog[]) => {
    let inserted = 0;
    for (const log of logsToInsert) {
      const res = insert.run({
        service_id: log.service_id,
        service_name: log.service_name,
        timestamp: log.timestamp,
        status_code: log.status_code,
        latency_ms: log.latency_ms,
        is_success: log.is_success ? 1 : 0,
        agent: log.agent,
        region: log.region,
        date: log.date
      });
      if (res.changes > 0) inserted++;
    }
    return inserted;
  });

  return insertMany(logs);
}

export function getStats() {
  const statsQuery = db.prepare(`
    SELECT 
      service_id,
      COUNT(*) as total_checks,
      SUM(CASE WHEN is_success = 1 THEN 1 ELSE 0 END) as successful_checks
    FROM monitoring_logs
    GROUP BY service_id
  `);
  
  const stats = statsQuery.all() as { service_id: string, total_checks: number, successful_checks: number }[];
  
  return stats.map(s => {
    const availability = (s.successful_checks / s.total_checks) * 100;
    return {
      ...s,
      availability_pct: parseFloat(availability.toFixed(4)),
      is_breached: availability < 99.9
    };
  });
}

export function getLogs(page = 1, limit = 100, startDate?: string, endDate?: string) {
  const offset = (page - 1) * limit;
  let query = 'SELECT * FROM monitoring_logs';
  const params: any[] = [];
  
  if (startDate && endDate) {
    query += ' WHERE date >= ? AND date <= ?';
    params.push(startDate, endDate);
  } else if (startDate) {
    query += ' WHERE date = ?';
    params.push(startDate);
  } else if (endDate) {
    query += ' WHERE date = ?';
    params.push(endDate);
  }
  
  query += ' ORDER BY timestamp DESC LIMIT ? OFFSET ?';
  params.push(limit, offset);
  
  let countQuery;
  if (startDate && endDate) {
    countQuery = db.prepare('SELECT COUNT(*) as count FROM monitoring_logs WHERE date >= ? AND date <= ?').get(startDate, endDate) as { count: number };
  } else if (startDate) {
    countQuery = db.prepare('SELECT COUNT(*) as count FROM monitoring_logs WHERE date = ?').get(startDate) as { count: number };
  } else if (endDate) {
    countQuery = db.prepare('SELECT COUNT(*) as count FROM monitoring_logs WHERE date = ?').get(endDate) as { count: number };
  } else {
    countQuery = db.prepare('SELECT COUNT(*) as count FROM monitoring_logs').get() as { count: number };
  }
    
  return {
    logs: db.prepare(query).all(...params),
    total: countQuery.count,
    page,
    totalPages: Math.ceil(countQuery.count / limit)
  };
}

export function clearDatabase() {
  db.exec('DELETE FROM monitoring_logs');
}
