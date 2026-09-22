import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

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

export async function insertLogs(logs: MonitoringLog[]) {
  const res = await prisma.monitoringLog.createMany({
    data: logs,
    skipDuplicates: true,
  });
  return res.count;
}

export async function getStats() {
  const rawStats = await prisma.$queryRaw`
    SELECT 
      service_id,
      COUNT(*) as total_checks,
      SUM(CASE WHEN is_success = 1 THEN 1 ELSE 0 END) as successful_checks
    FROM MonitoringLog
    GROUP BY service_id
  ` as { service_id: string, total_checks: number | bigint, successful_checks: number | bigint }[];
  
  return rawStats.map(s => {
    const total = Number(s.total_checks);
    const successful = Number(s.successful_checks);
    const availability = total > 0 ? (successful / total) * 100 : 0;
    return {
      service_id: s.service_id,
      total_checks: total,
      successful_checks: successful,
      availability_pct: parseFloat(availability.toFixed(4)),
      is_breached: availability < 99.9
    };
  });
}

export async function getLogs(page = 1, limit = 100, startDate?: string, endDate?: string) {
  const skip = (page - 1) * limit;
  const where: any = {};
  
  if (startDate && endDate) {
    where.date = { gte: startDate, lte: endDate };
  } else if (startDate) {
    where.date = startDate;
  } else if (endDate) {
    where.date = endDate;
  }
  
  const [logs, total] = await Promise.all([
    prisma.monitoringLog.findMany({
      where,
      orderBy: { timestamp: 'desc' },
      take: limit,
      skip,
    }),
    prisma.monitoringLog.count({ where })
  ]);
  
  return {
    logs,
    total,
    page,
    totalPages: Math.ceil(total / limit)
  };
}

export async function clearDatabase() {
  await prisma.monitoringLog.deleteMany({});
}
