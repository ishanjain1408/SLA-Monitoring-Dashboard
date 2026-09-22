# EarthRe SLA Monitoring — Case Study Report

## 1. Executive Summary

This analysis examines health-check monitoring data across **5 simulated datasets** for 5 cloud services. The datasets span 9 to 30 days with different random seeds, each containing ~4,600 to ~15,600 records of 15-minute health checks.

**Key findings:**
- **All 5 services breach the 99.9% SLA threshold** across all datasets
- **`svc-reports` is the least reliable service** at 97.28% mean availability (≈2.6% SLA gap)
- **8 documented incidents** were identified and correlated with monitoring data, all showing 57–84% failure rates during incident windows
- **6 categories of data quality issues** were found consistently across all datasets: missing latency values, mixed timestamp formats (ISO UTC, non-UTC offsets, Unix epochs), negative latency, exact duplicates, and duplicate (service_id, timestamp) keys
- All datasets show ~7–9% **more records than expected**, caused by duplicate monitoring agent reports

---

## 2. Problem Understanding

The case study requires building an **SLA Monitoring Dashboard** for a cloud provider's health-check pipeline. The provided data simulates multi-agent, multi-day monitoring logs that are intentionally messy. The core objective is to:

1. **Discover and handle data quality issues** in the raw CSV monitoring logs
2. **Compute reliability metrics** (availability, latency, failure rates) per service
3. **Correlate incidents** defined in the incident log JSON with monitoring data
4. **Assess SLA compliance** against the industry-standard 99.9% threshold
5. **Build a full-stack dashboard** (Upload UI → Serverless Function → Database → Dashboard)

---

## 3. Dataset Overview

### 3.1 Monitoring CSV Files

| Dataset | Days | Start Date | Rows | Expected Rows | Excess |
|---------|------|------------|------|---------------|--------|
| 9d_seed101 | 9 | 2025-05-08 | 4,672 | 4,320 | +352 (8.1%) |
| 12d_seed505 | 12 | 2025-04-10 | 6,230 | 5,760 | +470 (8.2%) |
| 14d_seed202 | 14 | 2025-05-19 | 7,269 | 6,720 | +549 (8.2%) |
| 21d_seed303 | 21 | 2025-04-03 | 10,904 | 10,080 | +824 (8.2%) |
| 30d_seed404 | 30 | 2025-04-06 | 15,577 | 14,400 | +1,177 (8.2%) |

**Schema** (8 columns):
- `service_id`: Service identifier (svc-auth, svc-search, svc-payments, svc-reports, svc-notify)
- `service_name`: Human-readable name (auth-api, search-api, payments-api, reports-api, notify-worker)
- `timestamp`: Check timestamp (mixed formats: ISO UTC, ISO+offset, Unix epoch)
- `status_code`: HTTP response code (200, 500, 502, 503)
- `latency`: Response latency value (numeric, some missing)
- `latency_unit`: Unit of latency (`ms` or `s`)
- `agent`: Monitoring agent (agent-1, agent-2)
- `region`: Cloud region (ap-south-1)

### 3.2 Incident Log (JSON)

Each CSV file has associated incident entries specifying:
- Which service was affected
- Which day (0-indexed from dataset start)
- Which checkpoints (15-min intervals within the day)
- Approximate time range

**Total documented incidents across all datasets: 8**

---

## 4. Data Quality Assessment

All 5 datasets exhibit the **same 6 categories** of data quality issues, consistently proportional to dataset size:

### 4.1 Missing Latency Values
| Dataset | Missing Latency Count | % of Total |
|---------|----------------------|------------|
| 9d_seed101 | 56 | 1.2% |
| 12d_seed505 | 74 | 1.2% |
| 14d_seed202 | 87 | 1.2% |
| 21d_seed303 | 130 | 1.2% |
| 30d_seed404 | 186 | 1.2% |

**Handling:** Latency values are treated as NULL. These rows are still counted for availability (status_code is present), but excluded from latency statistics.

### 4.2 Mixed Timestamp Formats
| Dataset | Non-UTC Offset | Unix Epoch | Standard ISO UTC |
|---------|---------------|------------|-----------------|
| 9d_seed101 | 32 | 70 | ~4,570 |
| 12d_seed505 | 43 | 93 | ~6,094 |
| 14d_seed202 | 50 | 109 | ~7,110 |
| 21d_seed303 | 76 | 163 | ~10,665 |
| 30d_seed404 | 109 | 233 | ~15,235 |

**Handling:** All timestamps are normalized to UTC. Non-UTC offsets (e.g., `+05:30`) are converted. Unix epochs are converted to ISO datetime.

### 4.3 Negative Latency Values
- **Exactly 1 negative latency per dataset** — a synthetic data artifact
- **Handling:** Retained in the dataset but flagged. Not removed to avoid silently modifying data.

### 4.4 Exact Duplicate Rows
| Dataset | Duplicate Rows |
|---------|---------------|
| 9d_seed101 | 6 |
| 12d_seed505 | 8 |
| 14d_seed202 | 10 |
| 21d_seed303 | 18 |
| 30d_seed404 | 24 |

**Handling:** Documented but not removed for the analysis (they represent a real data issue the dashboard should surface).

### 4.5 Duplicate (service_id, timestamp) Keys
| Dataset | Duplicate Key Rows |
|---------|-------------------|
| 9d_seed101 | 678 |
| 12d_seed505 | 902 |
| 14d_seed202 | 1,055 |
| 21d_seed303 | 1,579 |
| 30d_seed404 | 2,260 |

This is the **primary cause of the ~8% excess rows** — two monitoring agents (agent-1, agent-2) occasionally report the same check for the same service at the same timestamp.

**Handling:** All records are retained. For a production dashboard, deduplication by keeping the latest or agent-1 record would be appropriate.

### 4.6 Data Quality Consistency
The proportional consistency of all issues across datasets (each ~1.2% missing latency, ~0.7% non-UTC offsets, ~1.5% epoch timestamps, exactly 1 negative latency) strongly suggests these datasets are **synthetically generated from the same data generation model** with different seeds and durations.

---

## 5. Methodology

### Availability Calculation
```
Availability % = (Successful Checks / Total Checks) × 100
Successful Check = HTTP status code 2xx (200-299)
```

### SLA Breach Assessment
```
SLA Threshold = 99.9%
SLA Breached = Availability % < 99.9%
SLA Gap = max(0, 99.9% - Availability %)
```

### Incident Correlation
For each documented incident:
1. Map the incident to its specific service, day, and checkpoint range
2. Filter monitoring records to the incident window
3. Compute failure rate, status code distribution, and latency impact within the window
4. Compare incident-window latency to normal baseline latency (with the baseline correctly excluding *all* incidents for that service to avoid contamination).

### Latency Normalization
- `latency_unit = "ms"` → value in milliseconds (no conversion)
- `latency_unit = "s"` → value × 1000 to get milliseconds

---

## 6. Key Metrics

### 6.1 Service Availability (Cross-Dataset)

| Service | Min Availability | Max Availability | Mean Availability | Std Dev | SLA Status |
|---------|-----------------|-----------------|-------------------|---------|------------|
| svc-auth | 98.97% | 99.82% | 99.45% | 0.29% | BREACHED |
| svc-notify | 97.80% | 99.86% | 99.34% | 0.78% | BREACHED |
| svc-payments | 97.72% | 99.47% | 98.78% | 0.58% | BREACHED |
| svc-reports | 96.45% | 97.72% | 97.28% | 0.45% | BREACHED |
| svc-search | 97.67% | 99.45% | 98.85% | 0.62% | BREACHED |

**Key Observation:** `svc-reports` consistently has the lowest availability, never reaching above 97.72% in any dataset. This is the most problematic service.

### 6.2 Latency Statistics (Representative: 30d_seed404)

| Service | Mean (ms) | Median (ms) | P95 (ms) | P99 (ms) | Max (ms) |
|---------|-----------|-------------|----------|----------|----------|
| svc-auth | 146.4 | 143.0 | 188.0 | 196.3 | 660.0 |
| svc-notify | 113.3 | 113.0 | 148.0 | 151.0 | 158.0 |
| svc-payments | 372.3 | 371.0 | 484.0 | 494.0 | 514.0 |
| svc-reports | 656.0 | 655.0 | 846.0 | 862.0 | 2865.0 |
| svc-search | 539.3 | 537.0 | 700.3 | 716.0 | 727.0 |

**`svc-reports` has the highest baseline latency** (~650ms median) and shows extreme outliers during incidents (up to 3,022ms in 9d dataset).

### 6.3 Failure Distribution
All failed checks return HTTP 500, 502, or 503 status codes:
- **500 (Internal Server Error)**: Application-level failures
- **502 (Bad Gateway)**: Upstream/proxy failures
- **503 (Service Unavailable)**: Service overload or maintenance

---

## 7. Incident Analysis

### 7.1 Summary of All Incidents

| Dataset | Service | Date | Duration (min) | Checks | Failed | Fail Rate | Top Error |
|---------|---------|------|----------------|--------|--------|-----------|-----------|
| 9d_seed101 | svc-reports | 2025-05-13 | 90 | 6 | 4 | 66.7% | 502, 503 |
| 12d_seed505 | svc-search | 2025-04-14 | 300 | 21 | 16 | 76.2% | 502 (8) |
| 12d_seed505 | svc-search | 2025-04-18 | 90 | 7 | 4 | 57.1% | 503 (4) |
| 14d_seed202 | svc-notify | 2025-05-19 | 285 | 19 | 16 | 84.2% | 503 (8) |
| 14d_seed202 | svc-notify | 2025-05-25 | 165 | 13 | 8 | 61.5% | 502 (4) |
| 21d_seed303 | svc-payments | 2025-04-05 | 345 | 23 | 16 | 69.6% | 500, 502 |
| 30d_seed404 | svc-auth | 2025-04-22 | 390 | 28 | 20 | 71.4% | 502 (9) |
| 30d_seed404 | svc-reports | 2025-04-09 | 135 | 9 | 7 | 77.8% | 502 (5) |

### 7.2 Latency Impact During Incidents

| Incident | Normal Latency (mean) | Incident Latency (mean) | Latency Spike |
|----------|----------------------|------------------------|---------------|
| svc-reports (9d) | 643 ms | 2,658 ms | **4.1×** |
| svc-search (12d, day 4) | 536 ms | 1,827 ms | **3.4×** |
| svc-search (12d, day 8) | 536 ms | 1,857 ms | **3.5×** |
| svc-notify (14d, day 0) | 116 ms | 368 ms | **3.2×** |
| svc-notify (14d, day 6) | 117 ms | 402 ms | **3.4×** |
| svc-payments (21d) | 371 ms | 1,304 ms | **3.5×** |
| svc-auth (30d) | 143 ms | 469 ms | **3.3×** |
| svc-reports (30d) | 651 ms | 2,406 ms | **3.7×** |

**FACT:** All incidents show a **3–4× latency increase** over baseline, indicating the service didn't just fail — it degraded severely before/during outage. Note: The normal baseline latency excludes *all* incident windows for that service to avoid baseline contamination.

---

## 8. Root Cause Analysis

### 8.1 svc-reports — Persistent Reliability Issues

**Evidence Chain:**
1. **Monitoring data:** Consistently lowest availability across ALL 5 datasets (96.4%–97.7%)
2. **Observed anomaly:** High baseline latency (650ms median) compared to other services
3. **Incidents:** Two documented incidents (9d and 30d datasets) with 67–78% failure rates
4. **Impact:** Latency spikes to 2,400–2,600ms during incidents (3.7–4.1× normal)
5. **Error profile:** Predominantly 502 (Bad Gateway) errors, suggesting upstream/backend issues

**INFERENCE:** `svc-reports` has systemic reliability problems, likely related to backend resource constraints or dependency on an unstable upstream service. The 502 error dominance suggests the reports-api's backend or upstream dependency is frequently unreachable.

**Confidence:** HIGH — Pattern is consistent across all 5 independent datasets.

### 8.2 svc-search — Intermittent Failures

**Evidence Chain:**
1. **Monitoring data:** Availability varies from 97.7% to 99.4% across datasets
2. **Incidents:** Two incidents in 12d dataset with 57–76% failure rates
3. **Error profile:** Mix of 500, 502, 503 — suggesting multiple failure modes
4. **Latency impact:** 3.4–3.5× spike during incidents

**INFERENCE:** `svc-search` experiences intermittent failures that may be related to query load spikes or search index issues.

### 8.3 Other Services

- **svc-payments:** One major incident (21d dataset) with 70% failure rate and 3.5× latency spike. Otherwise moderate availability (98.8% mean).
- **svc-auth:** One major incident (30d dataset) with 71% failure rate. Otherwise relatively stable (99.5% mean).
- **svc-notify:** Two incidents in 14d dataset with 62–84% failure rates. Lowest baseline latency (113ms), but incidents cause proportionally large latency spikes (3.2–3.4×).

---

## 9. Dataset Comparison

### 9.1 What Each Dataset Represents

Each dataset is a **synthetic simulation** of the same monitoring system with different:
- **Duration** (9, 12, 14, 21, 30 days)
- **Random seed** (101, 505, 202, 303, 404)
- **Start date** (varying dates in April–May 2025)

They are NOT different production environments — they are different simulation runs of the same system model.

### 9.2 Consistency of Results

| Metric | Consistent Across Datasets? | Evidence |
|--------|---------------------------|----------|
| svc-reports worst service | ✅ Yes | Lowest availability in ALL 5 |
| Data quality issue types | ✅ Yes | Same 6 categories in all |
| Issue proportions | ✅ Yes | ~1.2% missing latency, ~8% excess rows in all |
| Latency baselines | ✅ Yes | Mean latencies within ±5% across datasets |
| SLA breach (all services) | ✅ Yes | All services breach 99.9% in all datasets |
| Incident failure rates | ✅ Yes | All incidents show 57–84% failure rates |

### 9.3 Statistical Note

With only 5 datasets from a synthetic generator, formal statistical significance testing (e.g., hypothesis testing for service reliability differences) is not meaningful. However, the **directional consistency** of results across all 5 datasets provides strong practical confidence in the findings.

---

## 10. Important Findings

1. **No service meets the 99.9% SLA** — all 5 services breach the threshold in every dataset
2. **`svc-reports` is the most problematic** — consistently 2.3–3.5% below SLA, the worst performing service by a significant margin
3. **Data is messy in predictable ways** — the monitoring pipeline produces mixed timestamp formats, missing latencies, and duplicate records from multi-agent collection
4. **Incidents cause 3–4× latency degradation** — services don't fail cleanly; they degrade first
5. **502 (Bad Gateway) is the dominant error** — suggesting upstream/backend connectivity is the primary failure mode across services
6. **~8% of records are duplicates** from multi-agent monitoring — the dashboard must handle deduplication

---

## 11. Recommendations

1. **Prioritize svc-reports reliability** — It's consistently the worst performer and would benefit most from infrastructure investment
2. **Implement deduplication in the data pipeline** — Handle multi-agent duplicate reports before computing metrics
3. **Add latency-based alerting** — A 3× latency spike reliably predicts or accompanies failures
4. **Investigate 502 error sources** — The dominance of Bad Gateway errors across all services suggests a common infrastructure issue (load balancer, reverse proxy, or shared backend)
5. **Normalize timestamps at ingestion** — Enforce UTC-only timestamps to avoid timezone-related computation errors
6. **Add latency validation** — Reject or flag negative latency values at ingestion

---

## 12. Limitations

1. **Synthetic data:** Results are from simulated datasets, not production logs. Real-world patterns may differ.
2. **No root cause attribution:** The data only shows symptoms (HTTP errors, latency spikes), not actual infrastructure causes.
3. **Single region:** All data is from `ap-south-1`; multi-region behavior is not captured.
4. **No correlation with external events:** Without deployment logs, config changes, or traffic data, root causes remain inferences.
5. **Duplicate handling:** The current analysis includes duplicates in all metrics. A production system would need a deduplication strategy.

---

## 13. Reproduction Instructions

```bash
# 1. Install dependencies
pip install pandas numpy matplotlib

# 2. Run the full analysis
python analysis/data_analysis.py

# 3. Run tests
python -m unittest tests.test_analysis -v

# 4. Run audit
python tests/audit_analysis.py

# 5. View outputs
# - output/data_quality_reports.json
# - output/incident_analysis.json
# - output/sla_analysis.json
# - output/cross_dataset_comparison.json
# - output/dataset_summary.csv
# - output/charts/*.png (14 visualization charts)
```

---

## 14. Conclusion

The analysis of 44,652 total monitoring records across 5 datasets reveals a monitoring system with significant, consistent reliability issues. `svc-reports` is the most problematic service at 97.28% mean availability, 2.62 percentage points below the 99.9% SLA. All 8 documented incidents correlate with monitoring data showing 57–84% failure rates and 3–4× latency spikes. The data pipeline produces predictable quality issues (mixed timestamps, missing latencies, duplicates) that a production dashboard must handle. These findings are robust across all 5 datasets, providing high confidence in the conclusions despite the synthetic nature of the data.
