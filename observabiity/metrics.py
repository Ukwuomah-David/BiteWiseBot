from collections import defaultdict

METRICS = defaultdict(int)

def increment(metric):
    METRICS[metric] += 1