"""
Comprehensive Data Analysis for EarthRe SLA Monitoring Case Study
================================================================

This script analyzes all 5 CSV monitoring datasets and the incident log JSON.
It performs:
  - Schema discovery
  - Data quality validation
  - Incident analysis & correlation
  - Metrics computation (availability, latency, failure rates)
  - Cross-dataset comparison
  - Visualization generation
  - Report generation
"""

import pandas as pd
import numpy as np
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from pathlib import Path

# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = Path(r"e:\New - Projects\Full Stack Case Study - EarthRe")
OUTPUT_DIR = BASE_DIR / "output"
CHARTS_DIR = OUTPUT_DIR / "charts"

CSV_FILES = [
    "monitoring_checks_9d_seed101.csv",
    "monitoring_checks_12d_seed505.csv",
    "monitoring_checks_14d_seed202.csv",
    "monitoring_checks_21d_seed303.csv",
    "monitoring_checks_30d_seed404.csv",
]

INCIDENT_LOG_FILE = "dataset_incident_log.json"

# Expected services from problem statement
EXPECTED_SERVICES = {"svc-auth", "svc-search", "svc-payments", "svc-reports", "svc-notify"}

# Expected check interval (15 minutes)
CHECK_INTERVAL_MINUTES = 15
CHECKS_PER_DAY = 24 * 60 // CHECK_INTERVAL_MINUTES  # 96


# ============================================================
# DATA LOADING
# ============================================================

def load_incident_log():
    """Load and parse the incident log JSON."""
    filepath = BASE_DIR / INCIDENT_LOG_FILE
    with open(filepath, 'r') as f:
        data = json.load(f)
    return data


def load_csv(filename):
    """Load a CSV file and return raw DataFrame (no cleaning yet)."""
    filepath = BASE_DIR / filename
    df = pd.read_csv(filepath, dtype=str)  # Load all as string initially
    return df


def parse_timestamp(ts_str):
    """
    Parse a timestamp string. Handles:
    - ISO 8601 format (2025-05-13T12:45:00Z)
    - ISO 8601 with timezone offset (2025-04-12T14:15:00+05:30)
    - Unix epoch seconds (1746938700)
    Returns a timezone-aware datetime in UTC, or None if unparsable.
    """
    if pd.isna(ts_str) or str(ts_str).strip() == '':
        return None
    
    ts_str = str(ts_str).strip()
    
    # Try unix epoch (all digits)
    try:
        if ts_str.isdigit() or (ts_str.replace('.', '').isdigit() and ts_str.count('.') <= 1):
            epoch = float(ts_str)
            # Reasonable epoch range: 2020-2030
            if 1577836800 < epoch < 1893456000:
                return datetime.fromtimestamp(epoch, tz=timezone.utc)
    except (ValueError, OSError):
        pass
    
    # Try ISO 8601 formats
    formats = [
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%S.%f%z",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(ts_str, fmt)
            # Convert to UTC if has timezone info
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc)
            else:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    
    return None


def normalize_latency(latency_val, unit):
    """
    Normalize latency to milliseconds.
    Handles:
    - 'ms' unit: value is already in ms
    - 's' unit: value is in seconds, convert to ms
    Returns float ms value or None if invalid.
    """
    if pd.isna(latency_val) or str(latency_val).strip() == '':
        return None
    
    try:
        val = float(latency_val)
    except (ValueError, TypeError):
        return None
    
    if pd.isna(unit) or str(unit).strip() == '':
        return None
    
    unit = str(unit).strip().lower()
    if unit == 'ms':
        return val
    elif unit == 's':
        return val * 1000.0
    else:
        return None


# ============================================================
# DATA QUALITY VALIDATION
# ============================================================

class DataQualityReport:
    def __init__(self, filename):
        self.filename = filename
        self.issues = []
        self.stats = {}
    
    def add_issue(self, category, description, count=None, examples=None):
        issue = {"category": category, "description": description}
        if count is not None:
            issue["count"] = count
        if examples is not None:
            issue["examples"] = examples
        self.issues.append(issue)
    
    def to_dict(self):
        return {
            "filename": self.filename,
            "stats": self.stats,
            "issues": self.issues
        }


def validate_csv(filename, df_raw):
    """Perform comprehensive data quality validation on a raw CSV DataFrame."""
    report = DataQualityReport(filename)
    
    # Basic stats
    report.stats["total_rows"] = len(df_raw)
    report.stats["columns"] = list(df_raw.columns)
    report.stats["expected_columns"] = ["service_id", "service_name", "timestamp", 
                                         "status_code", "latency", "latency_unit", 
                                         "agent", "region"]
    
    # Check columns
    expected_cols = set(report.stats["expected_columns"])
    actual_cols = set(df_raw.columns)
    missing_cols = expected_cols - actual_cols
    extra_cols = actual_cols - expected_cols
    if missing_cols:
        report.add_issue("SCHEMA", f"Missing columns: {missing_cols}")
    if extra_cols:
        report.add_issue("SCHEMA", f"Extra columns: {extra_cols}")
    
    # Check for completely empty rows
    empty_rows = df_raw.isna().all(axis=1).sum()
    if empty_rows > 0:
        report.add_issue("EMPTY_ROWS", f"Completely empty rows found", count=empty_rows)
    
    # Check null/missing values per column
    for col in df_raw.columns:
        null_count = df_raw[col].isna().sum()
        empty_count = (df_raw[col].astype(str).str.strip() == '').sum()
        total_missing = null_count + empty_count
        if total_missing > 0:
            report.add_issue("MISSING_VALUES", 
                           f"Column '{col}': {total_missing} missing/empty values "
                           f"({null_count} null, {empty_count} empty string)",
                           count=total_missing)
    
    # Check service_id values
    if 'service_id' in df_raw.columns:
        unique_services = set(df_raw['service_id'].dropna().unique())
        unexpected = unique_services - EXPECTED_SERVICES
        missing = EXPECTED_SERVICES - unique_services
        report.stats["unique_services"] = sorted(list(unique_services))
        if unexpected:
            report.add_issue("SERVICE_ID", f"Unexpected service IDs: {unexpected}")
        if missing:
            report.add_issue("SERVICE_ID", f"Missing expected services: {missing}")
    
    # Check timestamp formats
    if 'timestamp' in df_raw.columns:
        ts_col = df_raw['timestamp'].astype(str)
        
        # Identify different formats
        iso_utc = ts_col.str.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$')
        iso_tz = ts_col.str.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$')
        epoch = ts_col.str.match(r'^\d{10,}$')
        other = ~(iso_utc | iso_tz | epoch | ts_col.isin(['', 'nan', 'None']))
        
        format_counts = {
            "ISO_UTC (Z)": int(iso_utc.sum()),
            "ISO_with_offset": int(iso_tz.sum()),
            "Unix_epoch": int(epoch.sum()),
            "Other/Invalid": int(other.sum())
        }
        report.stats["timestamp_formats"] = format_counts
        
        if format_counts["ISO_with_offset"] > 0:
            examples = ts_col[iso_tz].head(5).tolist()
            report.add_issue("TIMESTAMP_FORMAT", 
                           f"Non-UTC timezone offsets found in timestamps",
                           count=format_counts["ISO_with_offset"],
                           examples=examples)
        
        if format_counts["Unix_epoch"] > 0:
            examples = ts_col[epoch].head(5).tolist()
            report.add_issue("TIMESTAMP_FORMAT",
                           f"Unix epoch timestamps found (should be ISO 8601)",
                           count=format_counts["Unix_epoch"],
                           examples=examples)
        
        if format_counts["Other/Invalid"] > 0:
            examples = ts_col[other].head(5).tolist()
            report.add_issue("TIMESTAMP_FORMAT",
                           f"Invalid/unrecognized timestamp formats",
                           count=format_counts["Other/Invalid"],
                           examples=examples)
    
    # Check status codes
    if 'status_code' in df_raw.columns:
        status_codes = df_raw['status_code'].dropna().astype(str).str.strip()
        unique_codes = sorted(status_codes.unique().tolist())
        report.stats["unique_status_codes"] = unique_codes
        
        # Check for non-numeric status codes
        non_numeric = status_codes[~status_codes.str.match(r'^\d+$')]
        if len(non_numeric) > 0:
            report.add_issue("STATUS_CODE", 
                           f"Non-numeric status codes found",
                           count=len(non_numeric),
                           examples=non_numeric.head(5).tolist())
    
    # Check latency values
    if 'latency' in df_raw.columns:
        latency_vals = df_raw['latency'].dropna().astype(str).str.strip()
        latency_vals = latency_vals[latency_vals != '']
        
        # Try to convert to numeric
        numeric_lat = pd.to_numeric(latency_vals, errors='coerce')
        non_numeric_count = numeric_lat.isna().sum()
        if non_numeric_count > 0:
            bad = latency_vals[numeric_lat.isna()]
            report.add_issue("LATENCY", 
                           f"Non-numeric latency values",
                           count=non_numeric_count,
                           examples=bad.head(5).tolist())
        
        # Check for negative latency
        neg_count = (numeric_lat < 0).sum()
        if neg_count > 0:
            report.add_issue("LATENCY", f"Negative latency values found", count=neg_count)
        
        # Check for zero latency
        zero_count = (numeric_lat == 0).sum()
        if zero_count > 0:
            report.add_issue("LATENCY", f"Zero latency values found", count=zero_count)
    
    # Check latency_unit values
    if 'latency_unit' in df_raw.columns:
        units = df_raw['latency_unit'].dropna().astype(str).str.strip()
        unique_units = sorted(units.unique().tolist())
        report.stats["unique_latency_units"] = unique_units
        unexpected_units = set(unique_units) - {'ms', 's', ''}
        if unexpected_units:
            report.add_issue("LATENCY_UNIT", f"Unexpected latency units: {unexpected_units}")
    
    # Check agent values
    if 'agent' in df_raw.columns:
        agents = df_raw['agent'].dropna().astype(str).str.strip()
        report.stats["unique_agents"] = sorted(agents.unique().tolist())
    
    # Check region values
    if 'region' in df_raw.columns:
        regions = df_raw['region'].dropna().astype(str).str.strip()
        report.stats["unique_regions"] = sorted(regions.unique().tolist())
    
    # Check for exact duplicate rows
    dup_count = df_raw.duplicated().sum()
    if dup_count > 0:
        report.add_issue("DUPLICATES", f"Exact duplicate rows found", count=dup_count)
    
    # Check for duplicate (service_id, timestamp) combinations
    if 'service_id' in df_raw.columns and 'timestamp' in df_raw.columns:
        dup_key = df_raw.duplicated(subset=['service_id', 'timestamp'], keep=False)
        dup_key_count = dup_key.sum()
        if dup_key_count > 0:
            dup_examples = df_raw[dup_key].head(10)[['service_id', 'timestamp']].to_dict('records')
            report.add_issue("DUPLICATE_KEYS", 
                           f"Duplicate (service_id, timestamp) combinations found",
                           count=dup_key_count,
                           examples=dup_examples)
    
    return report


# ============================================================
# DATA CLEANING
# ============================================================

def clean_dataframe(df_raw, filename):
    """
    Clean a raw DataFrame:
    1. Parse timestamps to UTC datetime
    2. Normalize latency to milliseconds
    3. Parse status codes to integers
    4. Track all transformations
    
    Returns (cleaned_df, cleaning_log)
    """
    cleaning_log = []
    df = df_raw.copy()
    
    # Parse timestamps
    df['timestamp_parsed'] = df['timestamp'].apply(parse_timestamp)
    
    # Log timestamp conversions
    non_utc = df['timestamp'].astype(str).str.contains(r'[+-]\d{2}:\d{2}$', regex=True, na=False)
    non_utc_not_z = non_utc & ~df['timestamp'].astype(str).str.endswith('Z')
    if non_utc_not_z.sum() > 0:
        cleaning_log.append(f"Converted {non_utc_not_z.sum()} non-UTC timestamps to UTC")
    
    epoch_ts = df['timestamp'].astype(str).str.match(r'^\d{10,}$')
    if epoch_ts.sum() > 0:
        cleaning_log.append(f"Converted {epoch_ts.sum()} Unix epoch timestamps to UTC datetime")
    
    unparsable = df['timestamp_parsed'].isna() & df['timestamp'].notna()
    if unparsable.sum() > 0:
        cleaning_log.append(f"WARNING: {unparsable.sum()} timestamps could not be parsed")
    
    # Normalize latency to ms
    df['latency_ms'] = df.apply(
        lambda row: normalize_latency(row.get('latency'), row.get('latency_unit')), axis=1
    )
    
    # Parse status codes
    df['status_code_int'] = pd.to_numeric(df['status_code'], errors='coerce').astype('Int64')
    
    # Determine if check is "successful"
    # HTTP 2xx = success, anything else = failure
    df['is_success'] = df['status_code_int'].apply(
        lambda x: True if pd.notna(x) and 200 <= x < 300 else False
    )
    
    # Add date column for daily grouping
    df['date'] = df['timestamp_parsed'].apply(
        lambda x: x.date() if x is not None else None
    )
    
    # Determine day number (0-indexed from start date per incident log)
    incident_log = load_incident_log()
    if filename in incident_log:
        start_str = incident_log[filename]['start']
        start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
        df['day_number'] = df['date'].apply(
            lambda d: (d - start_date).days if d is not None else None
        )
    
    # Check-point within day (0-indexed, each check is 15 min apart)
    df['checkpoint'] = df['timestamp_parsed'].apply(
        lambda x: (x.hour * 60 + x.minute) // CHECK_INTERVAL_MINUTES if x is not None else None
    )
    
    return df, cleaning_log


# ============================================================
# INCIDENT ANALYSIS
# ============================================================

def parse_incident_log_entry(service_day_key, checkpoints_str, csv_info):
    """Parse an incident log entry into structured data."""
    parts = service_day_key.split(' day ')
    service_id = parts[0]
    day_num = int(parts[1])
    
    # Parse checkpoint range
    cp_parts = checkpoints_str.split('(')[0].strip()
    cp_range = cp_parts.replace('check-points ', '').strip()
    cp_start, cp_end = [int(x) for x in cp_range.split('-')]
    
    # Parse time range
    time_str = checkpoints_str.split('(')[1].replace(')', '').strip()
    time_start, time_end = time_str.split('-')
    
    start_date = datetime.strptime(csv_info['start'], "%Y-%m-%d").date()
    incident_date = start_date + timedelta(days=day_num)
    
    return {
        'service_id': service_id,
        'day_number': day_num,
        'date': incident_date,
        'checkpoint_start': cp_start,
        'checkpoint_end': cp_end,
        'time_range': f"{time_start.strip()}-{time_end.strip()}",
        'expected_duration_checks': cp_end - cp_start + 1,
        'expected_duration_minutes': (cp_end - cp_start + 1) * CHECK_INTERVAL_MINUTES,
    }


def analyze_incidents_in_csv(df_clean, filename, incident_log):
    """
    Analyze incidents defined in the incident log against the actual monitoring data.
    """
    if filename not in incident_log:
        return []
    
    csv_info = incident_log[filename]
    results = []
    
    # Pre-parse all incidents to build per-service combined incident masks.
    # This ensures the "normal" baseline excludes ALL incident windows for a service,
    # not just the current one (matters when a service has multiple incidents).
    all_parsed = []
    for incident_key, checkpoints_str in csv_info.get('incidents', {}).items():
        info = parse_incident_log_entry(incident_key, checkpoints_str, csv_info)
        all_parsed.append((incident_key, checkpoints_str, info))
    
    # Build combined incident mask per service
    any_incident_mask_per_service = {}
    for _, _, info in all_parsed:
        svc = info['service_id']
        mask_i = (
            (df_clean['service_id'] == svc) &
            (df_clean['day_number'] == info['day_number']) &
            (df_clean['checkpoint'] >= info['checkpoint_start']) &
            (df_clean['checkpoint'] <= info['checkpoint_end'])
        )
        if svc in any_incident_mask_per_service:
            any_incident_mask_per_service[svc] = any_incident_mask_per_service[svc] | mask_i
        else:
            any_incident_mask_per_service[svc] = mask_i
    
    for incident_key, checkpoints_str, incident_info in all_parsed:
        service_id = incident_info['service_id']
        day_num = incident_info['day_number']
        cp_start = incident_info['checkpoint_start']
        cp_end = incident_info['checkpoint_end']
        
        # Filter data for this service on this day
        mask = (
            (df_clean['service_id'] == service_id) & 
            (df_clean['day_number'] == day_num)
        )
        day_data = df_clean[mask].sort_values('timestamp_parsed')
        
        # Filter to the incident checkpoint range
        incident_mask = mask & (
            (df_clean['checkpoint'] >= cp_start) & 
            (df_clean['checkpoint'] <= cp_end)
        )
        incident_data = df_clean[incident_mask].sort_values('timestamp_parsed')
        
        # Analyze the incident window
        total_checks_in_window = len(incident_data)
        failed_checks = incident_data[~incident_data['is_success']]
        successful_checks = incident_data[incident_data['is_success']]
        
        result = {
            **incident_info,
            'filename': filename,
            'total_checks_in_window': total_checks_in_window,
            'failed_checks': len(failed_checks),
            'successful_checks': len(successful_checks),
            'failure_rate_in_window': len(failed_checks) / total_checks_in_window if total_checks_in_window > 0 else None,
            'status_codes_seen': {str(k): v for k, v in failed_checks['status_code_int'].value_counts().to_dict().items()} if len(failed_checks) > 0 else {},
            'all_status_codes_in_window': {str(k): v for k, v in incident_data['status_code_int'].value_counts().to_dict().items()},
            'total_day_checks': len(day_data),
        }
        
        # Latency analysis during incident
        if len(incident_data) > 0 and incident_data['latency_ms'].notna().any():
            lat = incident_data['latency_ms'].dropna()
            result['incident_latency_mean_ms'] = float(lat.mean())
            result['incident_latency_p50_ms'] = float(lat.median())
            result['incident_latency_p95_ms'] = float(lat.quantile(0.95))
            result['incident_latency_p99_ms'] = float(lat.quantile(0.99))
            result['incident_latency_max_ms'] = float(lat.max())
        
        # Compare with non-incident data for the same service
        # Use the combined mask to exclude ALL incident windows, not just the current one
        combined_incident_mask = any_incident_mask_per_service.get(service_id, incident_mask)
        non_incident_mask = (df_clean['service_id'] == service_id) & ~combined_incident_mask
        non_incident_data = df_clean[non_incident_mask]
        if len(non_incident_data) > 0 and non_incident_data['latency_ms'].notna().any():
            lat_ni = non_incident_data['latency_ms'].dropna()
            result['normal_latency_mean_ms'] = float(lat_ni.mean())
            result['normal_latency_p50_ms'] = float(lat_ni.median())
        
        results.append(result)
    
    return results


# ============================================================
# METRICS COMPUTATION
# ============================================================

def compute_service_availability(df_clean, service_id=None):
    """
    Compute availability = (successful checks / total checks) * 100
    Optionally filtered by service_id.
    """
    if service_id:
        data = df_clean[df_clean['service_id'] == service_id]
    else:
        data = df_clean
    
    total = len(data)
    if total == 0:
        return None
    
    successful = data['is_success'].sum()
    return {
        'total_checks': int(total),
        'successful_checks': int(successful),
        'failed_checks': int(total - successful),
        'availability_pct': float((successful / total) * 100),
        'failure_rate_pct': float(((total - successful) / total) * 100),
    }


def compute_daily_availability(df_clean, service_id=None):
    """Compute daily availability per service."""
    if service_id:
        data = df_clean[df_clean['service_id'] == service_id]
    else:
        data = df_clean
    
    daily = data.groupby(['service_id', 'date']).agg(
        total_checks=('is_success', 'count'),
        successful_checks=('is_success', 'sum'),
    ).reset_index()
    
    daily['availability_pct'] = (daily['successful_checks'] / daily['total_checks']) * 100
    daily['failed_checks'] = daily['total_checks'] - daily['successful_checks']
    
    return daily


def compute_latency_stats(df_clean, service_id=None):
    """Compute latency statistics (in ms)."""
    if service_id:
        data = df_clean[df_clean['service_id'] == service_id]
    else:
        data = df_clean
    
    lat = data['latency_ms'].dropna()
    
    if len(lat) == 0:
        return None
    
    return {
        'count': int(len(lat)),
        'mean_ms': float(lat.mean()),
        'median_ms': float(lat.median()),
        'p95_ms': float(lat.quantile(0.95)),
        'p99_ms': float(lat.quantile(0.99)),
        'min_ms': float(lat.min()),
        'max_ms': float(lat.max()),
        'std_ms': float(lat.std()),
    }


def compute_failure_distribution(df_clean):
    """Compute failure distribution by status code."""
    failed = df_clean[~df_clean['is_success']]
    if len(failed) == 0:
        return {}
    return {str(k): int(v) for k, v in failed['status_code_int'].value_counts().to_dict().items()}


def compute_sla_breach_analysis(df_clean, sla_threshold=99.9):
    """
    Determine if SLA (availability threshold) is breached.
    Returns per-service SLA status.
    """
    results = {}
    for svc in df_clean['service_id'].unique():
        avail = compute_service_availability(df_clean, svc)
        if avail:
            results[svc] = {
                **avail,
                'sla_threshold': sla_threshold,
                'sla_met': avail['availability_pct'] >= sla_threshold,
                'sla_gap_pct': float(max(0, sla_threshold - avail['availability_pct'])),
            }
    return results


def compute_expected_vs_actual_checks(df_clean, filename, incident_log):
    """Compare expected number of checks vs actual."""
    if filename not in incident_log:
        return None
    
    csv_info = incident_log[filename]
    expected_days = csv_info['days']
    expected_total_per_service = expected_days * CHECKS_PER_DAY
    expected_total = expected_total_per_service * len(EXPECTED_SERVICES)
    
    actual_total = len(df_clean)
    
    per_service = {}
    for svc in EXPECTED_SERVICES:
        svc_data = df_clean[df_clean['service_id'] == svc]
        per_service[svc] = {
            'expected': int(expected_total_per_service),
            'actual': int(len(svc_data)),
            'difference': int(len(svc_data) - expected_total_per_service),
            'coverage_pct': float(len(svc_data) / expected_total_per_service * 100) if expected_total_per_service > 0 else None,
        }
    
    return {
        'expected_days': expected_days,
        'expected_total_checks': int(expected_total),
        'actual_total_checks': int(actual_total),
        'difference': int(actual_total - expected_total),
        'per_service': per_service,
    }


# ============================================================
# CROSS-DATASET COMPARISON
# ============================================================

def compare_datasets(all_results):
    """Compare metrics across all datasets."""
    comparison = {
        'datasets': [],
        'per_service_availability': defaultdict(list),
        'per_service_latency': defaultdict(list),
    }
    
    for filename, result in all_results.items():
        ds_summary = {
            'filename': filename,
            'total_rows': result['quality_report'].stats['total_rows'],
            'data_quality_issues': len(result['quality_report'].issues),
            'incidents_defined': len(result.get('incidents', [])),
        }
        
        # Add SLA info
        if 'sla_analysis' in result:
            for svc, sla in result['sla_analysis'].items():
                ds_summary[f'{svc}_availability'] = sla['availability_pct']
                comparison['per_service_availability'][svc].append({
                    'filename': filename,
                    'availability_pct': sla['availability_pct'],
                })
        
        # Add latency info
        if 'latency_stats' in result:
            for svc, lat in result['latency_stats'].items():
                if lat:
                    comparison['per_service_latency'][svc].append({
                        'filename': filename,
                        'mean_ms': lat['mean_ms'],
                        'p95_ms': lat['p95_ms'],
                    })
        
        comparison['datasets'].append(ds_summary)
    
    return comparison


# ============================================================
# VISUALIZATION
# ============================================================

def create_visualizations(all_results, output_dir):
    """Generate all visualization charts."""
    os.makedirs(output_dir, exist_ok=True)
    chart_files = []
    
    # 1. Per-service availability across datasets
    fig, ax = plt.subplots(figsize=(14, 7))
    services = sorted(EXPECTED_SERVICES)
    x = np.arange(len(services))
    width = 0.15
    
    for i, (filename, result) in enumerate(sorted(all_results.items())):
        avails = []
        for svc in services:
            if 'sla_analysis' in result and svc in result['sla_analysis']:
                avails.append(result['sla_analysis'][svc]['availability_pct'])
            else:
                avails.append(0)
        label = filename.replace('monitoring_checks_', '').replace('.csv', '')
        ax.bar(x + i * width, avails, width, label=label)
    
    ax.set_ylabel('Availability (%)')
    ax.set_title('Service Availability Across Datasets')
    ax.set_xticks(x + width * 2)
    ax.set_xticklabels(services, rotation=15)
    ax.legend(fontsize=8)
    ax.set_ylim(95, 100.5)
    ax.axhline(y=99.9, color='r', linestyle='--', alpha=0.7, label='SLA 99.9%')
    ax.legend(fontsize=8)
    plt.tight_layout()
    chart_path = output_dir / "availability_comparison.png"
    plt.savefig(str(chart_path), dpi=150)
    plt.close()
    chart_files.append(str(chart_path))
    
    # 2. Failure distribution by status code (all datasets combined)
    fig, axes = plt.subplots(1, len(all_results), figsize=(20, 5))
    if len(all_results) == 1:
        axes = [axes]
    
    for idx, (filename, result) in enumerate(sorted(all_results.items())):
        ax = axes[idx]
        dist = result.get('failure_distribution', {})
        if dist:
            codes = [str(k) for k in dist.keys()]
            counts = list(dist.values())
            ax.bar(codes, counts, color='coral')
        ax.set_title(filename.replace('monitoring_checks_', '').replace('.csv', ''), fontsize=9)
        ax.set_xlabel('Status Code')
        ax.set_ylabel('Count')
    
    plt.suptitle('Failure Distribution by HTTP Status Code', fontsize=14)
    plt.tight_layout()
    chart_path = output_dir / "failure_distribution.png"
    plt.savefig(str(chart_path), dpi=150)
    plt.close()
    chart_files.append(str(chart_path))
    
    # 3. Daily availability timeline for each dataset
    for filename, result in sorted(all_results.items()):
        if 'daily_availability' not in result:
            continue
        
        daily = result['daily_availability']
        fig, ax = plt.subplots(figsize=(16, 6))
        
        for svc in sorted(daily['service_id'].unique()):
            svc_data = daily[daily['service_id'] == svc].sort_values('date')
            ax.plot(svc_data['date'], svc_data['availability_pct'], 
                   marker='o', markersize=3, label=svc, alpha=0.8)
        
        ax.axhline(y=99.9, color='r', linestyle='--', alpha=0.7, label='SLA 99.9%')
        ax.set_ylabel('Availability (%)')
        ax.set_xlabel('Date')
        label = filename.replace('monitoring_checks_', '').replace('.csv', '')
        ax.set_title(f'Daily Service Availability - {label}')
        ax.legend(fontsize=8)
        ax.set_ylim(85, 101)
        plt.xticks(rotation=45)
        plt.tight_layout()
        
        chart_path = output_dir / f"daily_availability_{label}.png"
        plt.savefig(str(chart_path), dpi=150)
        plt.close()
        chart_files.append(str(chart_path))
    
    # 4. Latency distribution per service (box plot for one representative dataset)
    for filename, result in sorted(all_results.items()):
        if 'cleaned_df' not in result:
            continue
        
        df = result['cleaned_df']
        fig, ax = plt.subplots(figsize=(12, 6))
        
        data_to_plot = []
        labels = []
        for svc in sorted(df['service_id'].unique()):
            svc_data = df[df['service_id'] == svc]['latency_ms'].dropna()
            if len(svc_data) > 0:
                data_to_plot.append(svc_data.values)
                labels.append(svc)
        
        if data_to_plot:
            bp = ax.boxplot(data_to_plot, tick_labels=labels, patch_artist=True)
            colors = ['#FF9999', '#66B2FF', '#99FF99', '#FFCC99', '#FF99CC']
            for patch, color in zip(bp['boxes'], colors):
                patch.set_facecolor(color)
        
        ax.set_ylabel('Latency (ms)')
        label = filename.replace('monitoring_checks_', '').replace('.csv', '')
        ax.set_title(f'Latency Distribution by Service - {label}')
        plt.tight_layout()
        
        chart_path = output_dir / f"latency_boxplot_{label}.png"
        plt.savefig(str(chart_path), dpi=150)
        plt.close()
        chart_files.append(str(chart_path))
    
    # 5. Incident timeline
    fig, ax = plt.subplots(figsize=(16, 8))
    y_pos = 0
    y_labels = []
    colors_map = {
        'svc-auth': '#FF6B6B',
        'svc-search': '#4ECDC4',
        'svc-payments': '#45B7D1',
        'svc-reports': '#96CEB4',
        'svc-notify': '#FFEAA7',
    }
    
    for filename, result in sorted(all_results.items()):
        for inc in result.get('incidents', []):
            label_str = f"{filename.replace('monitoring_checks_', '').replace('.csv', '')}\n{inc['service_id']} day {inc['day_number']}"
            y_labels.append(label_str)
            
            color = colors_map.get(inc['service_id'], 'gray')
            ax.barh(y_pos, inc['expected_duration_minutes'], 
                   left=0, height=0.6, color=color, alpha=0.7)
            
            # Annotate with failure rate
            fr = inc.get('failure_rate_in_window')
            if fr is not None:
                ax.text(inc['expected_duration_minutes'] + 5, y_pos, 
                       f"{fr*100:.1f}% fail", va='center', fontsize=8)
            
            y_pos += 1
    
    ax.set_yticks(range(len(y_labels)))
    ax.set_yticklabels(y_labels, fontsize=8)
    ax.set_xlabel('Incident Duration (minutes)')
    ax.set_title('Incident Timeline - All Datasets')
    
    # Create custom legend
    handles = [plt.Rectangle((0,0),1,1, color=c, alpha=0.7) for c in colors_map.values()]
    ax.legend(handles, colors_map.keys(), loc='upper right', fontsize=8)
    
    plt.tight_layout()
    chart_path = output_dir / "incident_timeline.png"
    plt.savefig(str(chart_path), dpi=150)
    plt.close()
    chart_files.append(str(chart_path))
    
    # 6. Checks coverage heatmap (expected vs actual per service per dataset)
    fig, ax = plt.subplots(figsize=(12, 6))
    datasets_labels = []
    coverage_data = []
    
    for filename, result in sorted(all_results.items()):
        if 'check_coverage' in result and result['check_coverage']:
            label = filename.replace('monitoring_checks_', '').replace('.csv', '')
            datasets_labels.append(label)
            row = []
            for svc in sorted(EXPECTED_SERVICES):
                cov = result['check_coverage']['per_service'].get(svc, {})
                row.append(cov.get('coverage_pct', 0))
            coverage_data.append(row)
    
    if coverage_data:
        coverage_arr = np.array(coverage_data)
        im = ax.imshow(coverage_arr, cmap='RdYlGn', aspect='auto', vmin=90, vmax=110)
        ax.set_xticks(range(len(sorted(EXPECTED_SERVICES))))
        ax.set_xticklabels(sorted(EXPECTED_SERVICES), rotation=30)
        ax.set_yticks(range(len(datasets_labels)))
        ax.set_yticklabels(datasets_labels)
        
        # Add text annotations
        for i in range(len(datasets_labels)):
            for j in range(len(sorted(EXPECTED_SERVICES))):
                ax.text(j, i, f"{coverage_arr[i, j]:.1f}%", 
                       ha='center', va='center', fontsize=9,
                       color='black' if coverage_arr[i, j] > 95 else 'white')
        
        plt.colorbar(im, label='Coverage %')
        ax.set_title('Check Coverage: Actual vs Expected (per service per dataset)')
    
    plt.tight_layout()
    chart_path = output_dir / "check_coverage_heatmap.png"
    plt.savefig(str(chart_path), dpi=150)
    plt.close()
    chart_files.append(str(chart_path))
    
    return chart_files


# ============================================================
# MAIN ANALYSIS PIPELINE
# ============================================================

def run_full_analysis():
    """Run the complete analysis pipeline."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(CHARTS_DIR, exist_ok=True)
    
    incident_log = load_incident_log()
    all_results = {}
    all_quality_reports = []
    
    print("=" * 80)
    print("EARTHRE SLA MONITORING - COMPREHENSIVE DATA ANALYSIS")
    print("=" * 80)
    
    # --------------------------------------------------------
    # PHASE 1-3: Load, validate, and clean each dataset
    # --------------------------------------------------------
    for csv_file in CSV_FILES:
        print(f"\n{'='*60}")
        print(f"Processing: {csv_file}")
        print(f"{'='*60}")
        
        # Load raw data
        df_raw = load_csv(csv_file)
        print(f"  Raw rows: {len(df_raw)}")
        
        # Validate
        quality_report = validate_csv(csv_file, df_raw)
        all_quality_reports.append(quality_report)
        
        print(f"  Quality issues found: {len(quality_report.issues)}")
        for issue in quality_report.issues:
            cnt_str = f" (count: {issue['count']})" if 'count' in issue else ""
            print(f"    [{issue['category']}] {issue['description']}{cnt_str}")
            if 'examples' in issue and issue['examples']:
                for ex in issue['examples'][:3]:
                    print(f"      Example: {ex}")
        
        # Clean
        df_clean, cleaning_log = clean_dataframe(df_raw, csv_file)
        print(f"  Cleaning log:")
        for log_entry in cleaning_log:
            print(f"    - {log_entry}")
        
        # Store results
        result = {
            'raw_df': df_raw,
            'cleaned_df': df_clean,
            'quality_report': quality_report,
            'cleaning_log': cleaning_log,
        }
        
        # --------------------------------------------------------
        # PHASE 4: Compute metrics
        # --------------------------------------------------------
        
        # SLA / Availability
        sla_analysis = compute_sla_breach_analysis(df_clean)
        result['sla_analysis'] = sla_analysis
        
        print(f"\n  SLA Analysis (threshold: 99.9%):")
        for svc in sorted(sla_analysis.keys()):
            sla = sla_analysis[svc]
            status = "MET" if sla['sla_met'] else "BREACHED"
            print(f"    {svc}: {sla['availability_pct']:.4f}% ({sla['successful_checks']}/{sla['total_checks']}) {status}")
        
        # Daily availability
        daily_avail = compute_daily_availability(df_clean)
        result['daily_availability'] = daily_avail
        
        # Latency stats per service
        latency_stats = {}
        for svc in df_clean['service_id'].unique():
            latency_stats[svc] = compute_latency_stats(df_clean, svc)
        result['latency_stats'] = latency_stats
        
        print(f"\n  Latency Stats (ms):")
        for svc in sorted(latency_stats.keys()):
            ls = latency_stats[svc]
            if ls:
                print(f"    {svc}: mean={ls['mean_ms']:.1f}, median={ls['median_ms']:.1f}, "
                      f"p95={ls['p95_ms']:.1f}, p99={ls['p99_ms']:.1f}, max={ls['max_ms']:.1f}")
        
        # Failure distribution
        result['failure_distribution'] = compute_failure_distribution(df_clean)
        
        # Expected vs actual checks
        check_coverage = compute_expected_vs_actual_checks(df_clean, csv_file, incident_log)
        result['check_coverage'] = check_coverage
        
        if check_coverage:
            print(f"\n  Check Coverage (expected {check_coverage['expected_days']} days):")
            print(f"    Expected total: {check_coverage['expected_total_checks']}")
            print(f"    Actual total:   {check_coverage['actual_total_checks']}")
            print(f"    Difference:     {check_coverage['difference']}")
            for svc in sorted(check_coverage['per_service'].keys()):
                sc = check_coverage['per_service'][svc]
                print(f"    {svc}: {sc['actual']}/{sc['expected']} ({sc['coverage_pct']:.1f}%)")
        
        # --------------------------------------------------------
        # PHASE 5: Incident analysis
        # --------------------------------------------------------
        incidents = analyze_incidents_in_csv(df_clean, csv_file, incident_log)
        result['incidents'] = incidents
        
        if incidents:
            print(f"\n  Incident Analysis:")
            for inc in incidents:
                print(f"    {inc['service_id']} day {inc['day_number']} (date: {inc['date']}):")
                print(f"      Time range: {inc['time_range']}")
                print(f"      Checkpoints: {inc['checkpoint_start']}-{inc['checkpoint_end']}")
                print(f"      Checks in window: {inc['total_checks_in_window']}")
                print(f"      Failed checks: {inc['failed_checks']}")
                fr = inc.get('failure_rate_in_window')
                if fr is not None:
                    print(f"      Failure rate: {fr*100:.1f}%")
                else:
                    print(f"      Failure rate: N/A")
                print(f"      Status codes: {inc['status_codes_seen']}")
                if 'incident_latency_mean_ms' in inc:
                    print(f"      Incident latency (mean): {inc['incident_latency_mean_ms']:.1f} ms")
                if 'normal_latency_mean_ms' in inc:
                    print(f"      Normal latency (mean): {inc['normal_latency_mean_ms']:.1f} ms")
        
        all_results[csv_file] = result
    
    # --------------------------------------------------------
    # PHASE 6: Cross-dataset comparison
    # --------------------------------------------------------
    print(f"\n{'='*80}")
    print("CROSS-DATASET COMPARISON")
    print(f"{'='*80}")
    
    comparison = compare_datasets(all_results)
    
    print("\nPer-service availability across datasets:")
    for svc in sorted(comparison['per_service_availability'].keys()):
        entries = comparison['per_service_availability'][svc]
        avails = [e['availability_pct'] for e in entries]
        print(f"  {svc}: min={min(avails):.4f}%, max={max(avails):.4f}%, "
              f"mean={np.mean(avails):.4f}%, std={np.std(avails):.4f}%")
    
    # --------------------------------------------------------
    # PHASE 9: Visualizations
    # --------------------------------------------------------
    print(f"\n{'='*80}")
    print("GENERATING VISUALIZATIONS")
    print(f"{'='*80}")
    
    chart_files = create_visualizations(all_results, CHARTS_DIR)
    for cf in chart_files:
        print(f"  Generated: {cf}")
    
    # --------------------------------------------------------
    # Save processed data
    # --------------------------------------------------------
    print(f"\n{'='*80}")
    print("SAVING PROCESSED DATA")
    print(f"{'='*80}")
    
    # Save quality reports as JSON
    qr_data = [qr.to_dict() for qr in all_quality_reports]
    qr_path = OUTPUT_DIR / "data_quality_reports.json"
    with open(qr_path, 'w') as f:
        json.dump(qr_data, f, indent=2, default=str)
    print(f"  Saved: {qr_path}")
    
    # Save incident analysis as JSON
    all_incidents = []
    for filename, result in all_results.items():
        for inc in result.get('incidents', []):
            all_incidents.append(inc)
    
    inc_path = OUTPUT_DIR / "incident_analysis.json"
    with open(inc_path, 'w') as f:
        json.dump(all_incidents, f, indent=2, default=str)
    print(f"  Saved: {inc_path}")
    
    # Save SLA analysis as JSON
    sla_data = {}
    for filename, result in all_results.items():
        sla_data[filename] = result.get('sla_analysis', {})
    
    sla_path = OUTPUT_DIR / "sla_analysis.json"
    with open(sla_path, 'w') as f:
        json.dump(sla_data, f, indent=2, default=str)
    print(f"  Saved: {sla_path}")
    
    # Save comparison data
    comp_data = {
        'datasets': comparison['datasets'],
        'per_service_availability': dict(comparison['per_service_availability']),
        'per_service_latency': dict(comparison['per_service_latency']),
    }
    comp_path = OUTPUT_DIR / "cross_dataset_comparison.json"
    with open(comp_path, 'w') as f:
        json.dump(comp_data, f, indent=2, default=str)
    print(f"  Saved: {comp_path}")
    
    # Save per-dataset summary CSV
    summary_rows = []
    for filename, result in sorted(all_results.items()):
        row = {
            'filename': filename,
            'total_rows': result['quality_report'].stats['total_rows'],
            'quality_issues': len(result['quality_report'].issues),
            'incidents': len(result.get('incidents', [])),
        }
        if 'check_coverage' in result and result['check_coverage']:
            row['expected_days'] = result['check_coverage']['expected_days']
            row['expected_checks'] = result['check_coverage']['expected_total_checks']
            row['actual_checks'] = result['check_coverage']['actual_total_checks']
        
        for svc in sorted(EXPECTED_SERVICES):
            if 'sla_analysis' in result and svc in result['sla_analysis']:
                row[f'{svc}_availability'] = result['sla_analysis'][svc]['availability_pct']
                row[f'{svc}_sla_met'] = result['sla_analysis'][svc]['sla_met']
        
        summary_rows.append(row)
    
    summary_df = pd.DataFrame(summary_rows)
    summary_path = OUTPUT_DIR / "dataset_summary.csv"
    summary_df.to_csv(str(summary_path), index=False)
    print(f"  Saved: {summary_path}")
    
    print(f"\n{'='*80}")
    print("ANALYSIS COMPLETE")
    print(f"{'='*80}")
    
    return all_results, comparison


if __name__ == "__main__":
    all_results, comparison = run_full_analysis()
