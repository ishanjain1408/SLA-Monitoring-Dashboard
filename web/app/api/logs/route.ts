import { NextResponse } from 'next/server';
import { getLogs } from '@/lib/db';

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const page = parseInt(searchParams.get('page') || '1', 10);
    const startDate = searchParams.get('startDate') || undefined;
    const endDate = searchParams.get('endDate') || undefined;
    
    // Also support legacy 'date' param as both start and end for backwards compatibility
    const legacyDate = searchParams.get('date') || undefined;
    const start = startDate || legacyDate;
    const end = endDate || legacyDate;
    
    const logs = await getLogs(page, 100, start, end);
    return NextResponse.json(logs);
  } catch (error: any) {
    console.error('Logs error:', error);
    return NextResponse.json({ error: error.message || 'Error fetching logs' }, { status: 500 });
  }
}
