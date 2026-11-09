    # --- PART E: FOCUSED DISCOVERY COMBINATIONS ---
    {
        "code": "EXP23_London0809_FVG",
        "description": "Best Window + Best Confirmation: London 08-09 Impulse + FVG Imbalance",
        "overrides": {"Reference": 1, "EuropeWindow": 2, "Confirmation": 4},
    },
    {
        "code": "EXP24_London0809_Candle_FVG",
        "description": "London 08-09 Impulse + Candle Quality (Body>=0.45) + FVG",
        "overrides": {"Reference": 1, "EuropeWindow": 2, "Confirmation": 4, "MinBreakoutBodyRatio": 0.45},
    },
    {
        "code": "EXP25_LondonFull_FVG",
        "description": "Full London 08-11 + FVG Imbalance",
        "overrides": {"Reference": 1, "EuropeWindow": 5, "Confirmation": 4},
    },
    {
        "code": "EXP26_London0809_Fast",
        "description": "London 08-09 Impulse Fast Baseline (No confirmation)",
        "overrides": {"Reference": 1, "EuropeWindow": 2, "Confirmation": 0},
    },
