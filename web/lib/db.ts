import { createClient } from '@vercel/postgres';

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

// Helper to handle the direct connection client instead of the pooled sql tag
async function withClient<T>(queryFn: (client: any) => Promise<T>): Promise<T> {
  const client = createClient();
  await client.connect();
  try {
    return await queryFn(client);
  } finally {
    await client.end();
  }
}

export async function initDb() {
  await withClient(async (client) => {
    await client.sql`
      CREATE TABLE IF NOT EXISTS monitoring_logs (
        id SERIAL PRIMARY KEY,
        service_id VARCHAR(255) NOT NULL,
        service_name VARCHAR(255),
        timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
        status_code INTEGER,
        latency_ms REAL,
        is_success BOOLEAN,
        agent VARCHAR(255),
        region VARCHAR(255),
        date DATE,
        UNIQUE(service_id, timestamp, agent)
      );
    `;
  });
}

export async function insertLogs(logs: MonitoringLog[]) {
  await initDb();
  let inserted = 0;
  
  await withClient(async (client) => {
    for (const log of logs) {
      try {
        const res = await client.sql`
          INSERT INTO monitoring_logs (
            service_id, service_name, timestamp, status_code, latency_ms, is_success, agent, region, date
          ) VALUES (
            ${log.service_id}, ${log.service_name}, ${log.timestamp}, ${log.status_code}, ${log.latency_ms}, ${log.is_success}, ${log.agent}, ${log.region}, ${log.date}
          )
          ON CONFLICT (service_id, timestamp, agent) DO NOTHING
        `;
        if (res.rowCount && res.rowCount > 0) inserted++;
      } catch (e) {
        console.error('Failed to insert log', log, e);
      }
    }
  });
  
  return inserted;
}

export async function getStats() {
  await initDb();
  
  const result = await withClient(async (client) => {
    return await client.sql`
      SELECT 
        service_id,
        COUNT(*)::INTEGER as total_checks,
        SUM(CASE WHEN is_success = TRUE THEN 1 ELSE 0 END)::INTEGER as successful_checks
      FROM monitoring_logs
      GROUP BY service_id
    `;
  });
  
  const stats = result.rows;
  
  return stats.map((s: any) => {
    const availability = (s.successful_checks / s.total_checks) * 100;
    return {
      ...s,
      availability_pct: parseFloat(availability.toFixed(4)),
      is_breached: availability < 99.9
    };
  });
}

export async function getLogs(page = 1, limit = 100, startDate?: string, endDate?: string) {
  await initDb();
  const offset = (page - 1) * limit;
  
  return await withClient(async (client) => {
    let logsResult;
    let countResult;

    if (startDate && endDate) {
      logsResult = await client.sql`
        SELECT * FROM monitoring_logs 
        WHERE date >= ${startDate} AND date <= ${endDate} 
        ORDER BY timestamp DESC LIMIT ${limit} OFFSET ${offset}
      `;
      countResult = await client.sql`
        SELECT COUNT(*)::INTEGER as count FROM monitoring_logs 
        WHERE date >= ${startDate} AND date <= ${endDate}
      `;
    } else if (startDate) {
      logsResult = await client.sql`
        SELECT * FROM monitoring_logs 
        WHERE date = ${startDate} 
        ORDER BY timestamp DESC LIMIT ${limit} OFFSET ${offset}
      `;
      countResult = await client.sql`
        SELECT COUNT(*)::INTEGER as count FROM monitoring_logs 
        WHERE date = ${startDate}
      `;
    } else if (endDate) {
      logsResult = await client.sql`
        SELECT * FROM monitoring_logs 
        WHERE date = ${endDate} 
        ORDER BY timestamp DESC LIMIT ${limit} OFFSET ${offset}
      `;
      countResult = await client.sql`
        SELECT COUNT(*)::INTEGER as count FROM monitoring_logs 
        WHERE date = ${endDate}
      `;
    } else {
      logsResult = await client.sql`
        SELECT * FROM monitoring_logs 
        ORDER BY timestamp DESC LIMIT ${limit} OFFSET ${offset}
      `;
      countResult = await client.sql`
        SELECT COUNT(*)::INTEGER as count FROM monitoring_logs
      `;
    }

    return {
      logs: logsResult.rows,
      total: countResult.rows[0].count,
      page,
      totalPages: Math.ceil(countResult.rows[0].count / limit)
    };
  });
}

export async function clearDatabase() {
  await initDb();
  await withClient(async (client) => {
    await client.sql`DELETE FROM monitoring_logs`;
  });
}
