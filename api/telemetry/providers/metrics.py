from prometheus_client import Counter, Histogram

TELEMETRY_FETCH_TOTAL = Counter(
    'telemetry_fetch_total',
    'Total number of telemetry fetch attempts',
    ['provider', 'status']
)

TELEMETRY_FETCH_DURATION = Histogram(
    'telemetry_fetch_duration_seconds',
    'Time spent fetching telemetry data from provider',
    ['provider']
)
