# Power Consumption Skill (kW Monitoring System)

This skill defines how to interpret electrical power (kW) time-series data from industrial SCADA systems.

The system is used for:
- Factory energy monitoring
- Load analysis
- Anomaly detection
- Demand forecasting
- Efficiency evaluation

---

# 1. Data Structure

The system works with time-series data:

- timestamp (ISO datetime)
- kw (real power consumption in kilowatts)

Optional derived features:
- rolling_15min_avg
- rolling_1h_avg
- daily_avg
- weekly_avg
- peak_kw

---

# 2. Core Energy Behavior Principles

## 2.1 Normal Behavior
Power consumption is considered normal when:
- current kW is within ±15% of rolling 1-hour average
- changes are gradual, not sudden spikes

---

## 2.2 High Load Condition
If:
current_kw > 1.3 × rolling_1h_avg

Then:
→ HIGH_CONSUMPTION

Meaning:
- additional machines may be active
- production load increased
- or inefficiency occurred

---

## 2.3 Sudden Spike Condition
If:
(current_kw - previous_kw) / previous_kw > 0.25

Then:
→ POWER_SPIKE

Meaning:
- sudden equipment startup
- abnormal load switching
- possible fault or heavy motor start

---

## 2.4 Sustained High Load
If:
current_kw remains > 1.2 × daily_avg for > 30 minutes

Then:
→ SUSTAINED_HIGH_LOAD

Meaning:
- extended production overload
- possible inefficient scheduling

---

## 2.5 Idle Waste Detection
If:
production_status = IDLE (or inferred low activity)
AND current_kw > idle_threshold

Then:
→ IDLE_POWER_WASTE

Meaning:
- machines consuming power while not producing
- standby losses
- compressor or auxiliary systems running

---

## 2.6 Night Baseline Anomaly
If:
night_kw > 0.6 × daytime_avg

Then:
→ NIGHT_BASELOAD_HIGH

Meaning:
- equipment not shutting down properly
- leakage or continuous auxiliary load

---

## 2.7 Efficiency Degradation Trend
If:
weekly_avg is increasing continuously (>5% trend rise)

Then:
→ EFFICIENCY_DEGRADATION

Meaning:
- aging equipment
- process inefficiency
- increasing baseline consumption

---

# 3. Forecast Interpretation (Prophet)

Forecast outputs are used to compare expected vs actual behavior.

## Rules:

If actual_kw > forecast_kw × 1.2:
→ POSITIVE_DEVIATION (over-consumption)

If actual_kw < forecast_kw × 0.8:
→ NEGATIVE_DEVIATION (under-utilization or shutdown)

If forecast trend is increasing:
→ LONG_TERM_LOAD_INCREASE

If forecast is flat:
→ STABLE_CONSUMPTION_PATTERN

---

# 4. Anomaly Interpretation Priority

When multiple anomalies exist:

Priority order:
1. POWER_SPIKE
2. HIGH_CONSUMPTION
3. SUSTAINED_HIGH_LOAD
4. IDLE_POWER_WASTE
5. NIGHT_BASELOAD_HIGH
6. EFFICIENCY_DEGRADATION

Always report highest priority first.

---

# 5. Insight Generation Rules

All outputs must be interpreted into structured insights:

Format:

1. Observation
2. Comparison with baseline
3. Detected anomaly (if any)
4. Possible operational cause (based on rules)
5. Suggested action (simple and practical)

Never output raw kW data alone.

---

# 6. Reasoning Constraints

- Do NOT guess missing data
- Always use comparisons (baseline, rolling averages, or forecast)
- Prefer time-based reasoning (hour/day/week)
- Avoid generic explanations without data reference
- Focus on industrial meaning, not statistical description only

---

# 7. Output Style

- Short and technical
- Industrial engineering tone
- No conversational chatbot language
- No unnecessary explanations