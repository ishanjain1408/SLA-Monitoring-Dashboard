"""
Test suite for EarthRe SLA Monitoring Data Analysis.
Tests data loading, validation, cleaning, metric calculations, and incident analysis.
"""

import sys
import os
import json
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.data_analysis import (
    parse_timestamp,
    normalize_latency,
    load_csv,
    load_incident_log,
    validate_csv,
    clean_dataframe,
    compute_service_availability,
    compute_latency_stats,
    compute_sla_breach_analysis,
    compute_failure_distribution,
    compute_daily_availability,
    parse_incident_log_entry,
    analyze_incidents_in_csv,
    DataQualityReport,
    EXPECTED_SERVICES,
    CHECK_INTERVAL_MINUTES,
    CHECKS_PER_DAY,
    CSV_FILES,
)

import pandas as pd
import numpy as np


class TestParseTimestamp(unittest.TestCase):
    """Tests for the parse_timestamp function."""
    
    def test_iso_utc_format(self):
        """Standard ISO 8601 UTC format."""
        result = parse_timestamp("2025-05-13T12:45:00Z")
        self.assertIsNotNone(result)
        self.assertEqual(result.year, 2025)
        self.assertEqual(result.month, 5)
        self.assertEqual(result.day, 13)
        self.assertEqual(result.hour, 12)
        self.assertEqual(result.minute, 45)
        self.assertEqual(result.tzinfo, timezone.utc)
    
    def test_iso_with_offset(self):
        """ISO 8601 with +05:30 offset, should convert to UTC."""
        result = parse_timestamp("2025-04-12T14:15:00+05:30")
        self.assertIsNotNone(result)
        # 14:15 +05:30 = 08:45 UTC
        self.assertEqual(result.hour, 8)
        self.assertEqual(result.minute, 45)
        self.assertEqual(result.tzinfo, timezone.utc)
    
    def test_unix_epoch(self):
        """Unix epoch timestamp."""
        result = parse_timestamp("1746938700")
        self.assertIsNotNone(result)
        self.assertEqual(result.tzinfo, timezone.utc)
        # Verify it's a reasonable 2025 date
        self.assertEqual(result.year, 2025)
    
    def test_none_input(self):
        """None input should return None."""
        self.assertIsNone(parse_timestamp(None))
    
    def test_empty_string(self):
        """Empty string should return None."""
        self.assertIsNone(parse_timestamp(""))
        self.assertIsNone(parse_timestamp("   "))
    
    def test_nan_input(self):
        """NaN should return None."""
        self.assertIsNone(parse_timestamp(float('nan')))
    
    def test_invalid_format(self):
        """Invalid format should return None."""
        self.assertIsNone(parse_timestamp("not-a-date"))
        self.assertIsNone(parse_timestamp("2025-13-01T00:00:00Z"))  # Invalid month


class TestNormalizeLatency(unittest.TestCase):
    """Tests for the normalize_latency function."""
    
    def test_milliseconds(self):
        """Value already in milliseconds."""
        self.assertEqual(normalize_latency("707", "ms"), 707.0)
    
    def test_seconds(self):
        """Value in seconds, should convert to ms."""
        self.assertAlmostEqual(normalize_latency("0.717", "s"), 717.0, places=1)
    
    def test_none_value(self):
        """None latency returns None."""
        self.assertIsNone(normalize_latency(None, "ms"))
    
    def test_empty_value(self):
        """Empty string latency returns None."""
        self.assertIsNone(normalize_latency("", "ms"))
    
    def test_none_unit(self):
        """None unit returns None."""
        self.assertIsNone(normalize_latency("100", None))
    
    def test_empty_unit(self):
        """Empty unit returns None."""
        self.assertIsNone(normalize_latency("100", ""))
    
    def test_invalid_unit(self):
        """Unknown unit returns None."""
        self.assertIsNone(normalize_latency("100", "us"))
    
    def test_non_numeric(self):
        """Non-numeric latency returns None."""
        self.assertIsNone(normalize_latency("abc", "ms"))
    
    def test_negative_value(self):
        """Negative value should still be returned (flagged elsewhere)."""
        result = normalize_latency("-5", "ms")
        self.assertEqual(result, -5.0)
    
    def test_zero_value(self):
        """Zero latency should be returned."""
        self.assertEqual(normalize_latency("0", "ms"), 0.0)


class TestDataQualityReport(unittest.TestCase):
    """Tests for DataQualityReport class."""
    
    def test_add_issue(self):
        report = DataQualityReport("test.csv")
        report.add_issue("TEST", "test issue", count=5, examples=["ex1"])
        self.assertEqual(len(report.issues), 1)
        self.assertEqual(report.issues[0]['category'], "TEST")
        self.assertEqual(report.issues[0]['count'], 5)
    
    def test_to_dict(self):
        report = DataQualityReport("test.csv")
        report.stats["total_rows"] = 100
        report.add_issue("TEST", "desc")
        d = report.to_dict()
        self.assertEqual(d['filename'], "test.csv")
        self.assertEqual(d['stats']['total_rows'], 100)
        self.assertEqual(len(d['issues']), 1)


class TestValidateCSV(unittest.TestCase):
    """Tests for CSV validation on synthetic data."""
    
    def _make_df(self, rows):
        """Helper to create a DataFrame from list of dicts."""
        return pd.DataFrame(rows)
    
    def test_missing_columns(self):
        df = self._make_df([{"service_id": "svc-auth", "timestamp": "2025-05-13T00:00:00Z"}])
        report = validate_csv("test.csv", df)
        schema_issues = [i for i in report.issues if i['category'] == 'SCHEMA']
        self.assertTrue(len(schema_issues) > 0)
    
    def test_detects_duplicates(self):
        row = {
            "service_id": "svc-auth", "service_name": "auth-api",
            "timestamp": "2025-05-13T00:00:00Z", "status_code": "200",
            "latency": "100", "latency_unit": "ms", "agent": "agent-1", "region": "us-east-1"
        }
        df = self._make_df([row, row])  # exact duplicate
        report = validate_csv("test.csv", df)
        dup_issues = [i for i in report.issues if i['category'] == 'DUPLICATES']
        self.assertTrue(len(dup_issues) > 0)
    
    def test_missing_latency(self):
        rows = [
            {"service_id": "svc-auth", "service_name": "auth-api",
             "timestamp": "2025-05-13T00:00:00Z", "status_code": "200",
             "latency": None, "latency_unit": "ms", "agent": "agent-1", "region": "us-east-1"}
        ]
        df = self._make_df(rows)
        report = validate_csv("test.csv", df)
        missing = [i for i in report.issues if 'latency' in i['description'].lower() and i['category'] == 'MISSING_VALUES']
        self.assertTrue(len(missing) > 0)
    
    def test_unexpected_service(self):
        rows = [
            {"service_id": "svc-unknown", "service_name": "unknown-api",
             "timestamp": "2025-05-13T00:00:00Z", "status_code": "200",
             "latency": "100", "latency_unit": "ms", "agent": "agent-1", "region": "us-east-1"}
        ]
        df = self._make_df(rows)
        report = validate_csv("test.csv", df)
        svc_issues = [i for i in report.issues if i['category'] == 'SERVICE_ID']
        self.assertTrue(len(svc_issues) > 0)


class TestComputeAvailability(unittest.TestCase):
    """Tests for availability computation."""
    
    def _make_clean_df(self, statuses):
        """Create a minimal cleaned DataFrame with given status codes."""
        rows = []
        for i, sc in enumerate(statuses):
            rows.append({
                'service_id': 'svc-auth',
                'status_code_int': sc,
                'is_success': 200 <= sc < 300,
                'latency_ms': 100.0,
                'timestamp_parsed': datetime(2025, 5, 13, 0, i*15, 0, tzinfo=timezone.utc),
                'date': datetime(2025, 5, 13).date(),
            })
        return pd.DataFrame(rows)
    
    def test_all_successful(self):
        df = self._make_clean_df([200, 200, 200, 200])
        result = compute_service_availability(df, 'svc-auth')
        self.assertEqual(result['availability_pct'], 100.0)
        self.assertEqual(result['failed_checks'], 0)
    
    def test_some_failures(self):
        df = self._make_clean_df([200, 500, 200, 503])
        result = compute_service_availability(df, 'svc-auth')
        self.assertEqual(result['availability_pct'], 50.0)
        self.assertEqual(result['failed_checks'], 2)
    
    def test_all_failures(self):
        df = self._make_clean_df([500, 502, 503, 504])
        result = compute_service_availability(df, 'svc-auth')
        self.assertEqual(result['availability_pct'], 0.0)
        self.assertEqual(result['failed_checks'], 4)
    
    def test_empty_dataset(self):
        df = pd.DataFrame(columns=['service_id', 'status_code_int', 'is_success'])
        result = compute_service_availability(df, 'svc-auth')
        self.assertIsNone(result)


class TestSLABreach(unittest.TestCase):
    """Tests for SLA breach analysis."""
    
    def _make_df(self, svc_id, n_success, n_fail):
        rows = []
        for i in range(n_success):
            rows.append({
                'service_id': svc_id, 'status_code_int': 200,
                'is_success': True, 'latency_ms': 100.0,
                'timestamp_parsed': datetime(2025, 5, 13, tzinfo=timezone.utc),
                'date': datetime(2025, 5, 13).date(),
            })
        for i in range(n_fail):
            rows.append({
                'service_id': svc_id, 'status_code_int': 500,
                'is_success': False, 'latency_ms': 100.0,
                'timestamp_parsed': datetime(2025, 5, 13, tzinfo=timezone.utc),
                'date': datetime(2025, 5, 13).date(),
            })
        return pd.DataFrame(rows)
    
    def test_sla_met(self):
        # 1000 checks, 0 failures = 100% availability
        df = self._make_df('svc-auth', 1000, 0)
        result = compute_sla_breach_analysis(df, sla_threshold=99.9)
        self.assertTrue(result['svc-auth']['sla_met'])
    
    def test_sla_breached(self):
        # 990 success, 10 failure = 99.0%
        df = self._make_df('svc-auth', 990, 10)
        result = compute_sla_breach_analysis(df, sla_threshold=99.9)
        self.assertFalse(result['svc-auth']['sla_met'])
    
    def test_sla_exactly_at_threshold(self):
        # 999 success, 1 failure = 99.9%
        df = self._make_df('svc-auth', 999, 1)
        result = compute_sla_breach_analysis(df, sla_threshold=99.9)
        self.assertTrue(result['svc-auth']['sla_met'])


class TestLatencyStats(unittest.TestCase):
    """Tests for latency statistics."""
    
    def test_basic_stats(self):
        df = pd.DataFrame({
            'service_id': ['svc-auth'] * 5,
            'latency_ms': [100, 200, 300, 400, 500],
        })
        result = compute_latency_stats(df, 'svc-auth')
        self.assertEqual(result['count'], 5)
        self.assertEqual(result['mean_ms'], 300.0)
        self.assertEqual(result['median_ms'], 300.0)
        self.assertEqual(result['min_ms'], 100.0)
        self.assertEqual(result['max_ms'], 500.0)
    
    def test_empty_data(self):
        df = pd.DataFrame({'service_id': [], 'latency_ms': []})
        result = compute_latency_stats(df, 'svc-auth')
        self.assertIsNone(result)
    
    def test_with_nans(self):
        df = pd.DataFrame({
            'service_id': ['svc-auth'] * 4,
            'latency_ms': [100, None, 300, None],
        })
        result = compute_latency_stats(df, 'svc-auth')
        self.assertEqual(result['count'], 2)
        self.assertEqual(result['mean_ms'], 200.0)


class TestFailureDistribution(unittest.TestCase):
    """Tests for failure distribution."""
    
    def test_multiple_codes(self):
        df = pd.DataFrame({
            'is_success': [False, False, False, True],
            'status_code_int': [500, 502, 500, 200],
        })
        result = compute_failure_distribution(df)
        self.assertEqual(result['500'], 2)
        self.assertEqual(result['502'], 1)
        self.assertNotIn('200', result)
    
    def test_no_failures(self):
        df = pd.DataFrame({
            'is_success': [True, True],
            'status_code_int': [200, 200],
        })
        result = compute_failure_distribution(df)
        self.assertEqual(result, {})


class TestDataLoading(unittest.TestCase):
    """Tests for actual data loading from the repository files."""
    
    def test_incident_log_loads(self):
        data = load_incident_log()
        self.assertIsInstance(data, dict)
        self.assertEqual(len(data), 5)
        for csv_file in CSV_FILES:
            self.assertIn(csv_file, data)
    
    def test_incident_log_structure(self):
        data = load_incident_log()
        for filename, info in data.items():
            self.assertIn('days', info)
            self.assertIn('start', info)
            self.assertIn('incidents', info)
            self.assertIsInstance(info['days'], int)
            self.assertIsInstance(info['start'], str)
            self.assertIsInstance(info['incidents'], dict)
    
    def test_csv_loads(self):
        for csv_file in CSV_FILES:
            df = load_csv(csv_file)
            self.assertGreater(len(df), 0, f"{csv_file} should have data")
            expected_cols = ["service_id", "service_name", "timestamp", 
                           "status_code", "latency", "latency_unit", "agent", "region"]
            for col in expected_cols:
                self.assertIn(col, df.columns, f"{csv_file} missing column {col}")
    
    def test_csv_row_counts(self):
        """Verify we load all rows from each CSV."""
        expected_approx = {
            "monitoring_checks_9d_seed101.csv": 4672,
            "monitoring_checks_12d_seed505.csv": 6230,
            "monitoring_checks_14d_seed202.csv": 7269,
            "monitoring_checks_21d_seed303.csv": 10904,
            "monitoring_checks_30d_seed404.csv": 15577,
        }
        for csv_file, expected in expected_approx.items():
            df = load_csv(csv_file)
            self.assertEqual(len(df), expected, 
                           f"{csv_file}: expected {expected} rows, got {len(df)}")


class TestIncidentParsing(unittest.TestCase):
    """Tests for incident log entry parsing."""
    
    def test_parse_entry(self):
        csv_info = {"days": 9, "start": "2025-05-08"}
        result = parse_incident_log_entry(
            "svc-reports day 5", 
            "check-points 64-69 (~16:00-17:15 UTC)",
            csv_info
        )
        self.assertEqual(result['service_id'], 'svc-reports')
        self.assertEqual(result['day_number'], 5)
        self.assertEqual(result['checkpoint_start'], 64)
        self.assertEqual(result['checkpoint_end'], 69)
        self.assertEqual(result['expected_duration_checks'], 6)
        self.assertEqual(result['expected_duration_minutes'], 90)
        self.assertEqual(result['date'].day, 13)  # May 8 + 5 = May 13


class TestConstants(unittest.TestCase):
    """Test important constants."""
    
    def test_checks_per_day(self):
        self.assertEqual(CHECKS_PER_DAY, 96)
    
    def test_check_interval(self):
        self.assertEqual(CHECK_INTERVAL_MINUTES, 15)
    
    def test_expected_services(self):
        self.assertEqual(len(EXPECTED_SERVICES), 5)
        self.assertIn('svc-auth', EXPECTED_SERVICES)
        self.assertIn('svc-search', EXPECTED_SERVICES)
        self.assertIn('svc-payments', EXPECTED_SERVICES)
        self.assertIn('svc-reports', EXPECTED_SERVICES)
        self.assertIn('svc-notify', EXPECTED_SERVICES)


class TestEdgeCases(unittest.TestCase):
    """Test edge cases."""
    
    def test_availability_single_check(self):
        df = pd.DataFrame({
            'service_id': ['svc-auth'],
            'status_code_int': [200],
            'is_success': [True],
        })
        result = compute_service_availability(df, 'svc-auth')
        self.assertEqual(result['availability_pct'], 100.0)
    
    def test_availability_wrong_service_filter(self):
        df = pd.DataFrame({
            'service_id': ['svc-auth'],
            'status_code_int': [200],
            'is_success': [True],
        })
        result = compute_service_availability(df, 'svc-nonexistent')
        self.assertIsNone(result)


class TestIncidentBaselineFix(unittest.TestCase):
    """
    Verify that when a service has multiple incidents in the same dataset,
    the 'normal' latency baseline excludes ALL incident windows — not just 
    the current one.
    """
    
    def test_multi_incident_baseline_exclusion(self):
        """
        In the 12d dataset, svc-search has incidents on day 4 and day 8.
        The normal baseline for BOTH incidents should be the same value,
        because both exclude the same set of incident-window rows.
        """
        incident_log = load_incident_log()
        df_raw = load_csv("monitoring_checks_12d_seed505.csv")
        df_clean, _ = clean_dataframe(df_raw, "monitoring_checks_12d_seed505.csv")
        
        incidents = analyze_incidents_in_csv(df_clean, "monitoring_checks_12d_seed505.csv", incident_log)
        
        search_incidents = [i for i in incidents if i['service_id'] == 'svc-search']
        self.assertEqual(len(search_incidents), 2, "Expected 2 svc-search incidents in 12d dataset")
        
        # Both incidents should have the SAME normal baseline since they 
        # both exclude the same set of incident windows
        baseline_0 = search_incidents[0]['normal_latency_mean_ms']
        baseline_1 = search_incidents[1]['normal_latency_mean_ms']
        self.assertAlmostEqual(baseline_0, baseline_1, places=1,
            msg=f"Normal baselines should be equal when excluding all incidents: "
                f"day {search_incidents[0]['day_number']}={baseline_0:.1f}ms vs "
                f"day {search_incidents[1]['day_number']}={baseline_1:.1f}ms")
    
    def test_all_incidents_have_failures(self):
        """Every documented incident should have at least 1 failed check."""
        incident_log = load_incident_log()
        for csv_file in CSV_FILES:
            df_raw = load_csv(csv_file)
            df_clean, _ = clean_dataframe(df_raw, csv_file)
            incidents = analyze_incidents_in_csv(df_clean, csv_file, incident_log)
            for inc in incidents:
                self.assertGreater(inc['failed_checks'], 0,
                    f"{csv_file} {inc['service_id']} day {inc['day_number']} has 0 failures")
                self.assertGreater(inc['total_checks_in_window'], 0,
                    f"{csv_file} {inc['service_id']} day {inc['day_number']} has 0 checks")


class TestTimestampOffsetDayAssignment(unittest.TestCase):
    """Verify that non-UTC offset timestamps get assigned the correct UTC date."""
    
    def test_offset_rolls_back_day(self):
        """
        2025-05-13T02:00:00+05:30 = 2025-05-12T20:30:00Z.
        If start is May 8, day_number should be 4 (May 12 - May 8).
        """
        ts = parse_timestamp("2025-05-13T02:00:00+05:30")
        self.assertIsNotNone(ts)
        self.assertEqual(ts.day, 12, "UTC day should be 12, not 13")
        self.assertEqual(ts.hour, 20)
        self.assertEqual(ts.minute, 30)
    
    def test_offset_stays_same_day(self):
        """
        2025-05-13T14:00:00+05:30 = 2025-05-13T08:30:00Z.
        Same day in UTC.
        """
        ts = parse_timestamp("2025-05-13T14:00:00+05:30")
        self.assertIsNotNone(ts)
        self.assertEqual(ts.day, 13, "UTC day should still be 13")
        self.assertEqual(ts.hour, 8)
        self.assertEqual(ts.minute, 30)


if __name__ == '__main__':
    unittest.main(verbosity=2)
