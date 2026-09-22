import { NextResponse } from 'next/server';
import { processCsvData } from '@/lib/process-csv';

export async function POST(request: Request) {
  try {
    const formData = await request.formData();
    const file = formData.get('file') as File;
    
    if (!file) {
      return NextResponse.json({ error: 'No file uploaded' }, { status: 400 });
    }

    const text = await file.text();
    const result = await processCsvData(text);
    
    return NextResponse.json({
      message: 'Upload successful',
      totalParsed: result.totalParsed,
      insertedCount: result.insertedCount
    });
  } catch (error: any) {
    console.error('Upload error:', error);
    return NextResponse.json({ error: error.message || 'Error processing upload' }, { status: 500 });
  }
}
