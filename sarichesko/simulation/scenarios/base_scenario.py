SCENARIOS = {
    "bulk_transfer": {
        "name": "Bulk Transfer",
        "description": "Sustained high-throughput file transfer — steady load slightly above link capacity",
        "load_factor": 1.2,
    },
    "bursty_traffic": {
        "name": "Bursty Traffic",
        "description": "Periodic traffic bursts with quiet intervals — models web browsing, API calls, gaming",
        "load_factor": 1.5,
    },
    "mixed_traffic": {
        "name": "Mixed Traffic",
        "description": "Combination of steady background load with random burst spikes — realistic multi-user scenario",
        "load_factor": 1.0,
    },
}