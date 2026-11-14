import joblib
import os
import sys
from pathlib import Path

# The business clock is Asia/Manila (backend/app/core/time.py), whatever zone this machine uses.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend"))
from app.core.time import now_manila  # noqa: E402
from app.services.spoilage import SpoilagePredictor  # noqa: E402

MODEL_PATH = Path(__file__).resolve().parent / "backend/app/ml/spoilage_rfr.joblib"

def run_matrix_test():
    output_lines = []
    
    def log(msg):
        print(msg)
        output_lines.append(msg)

    log(f"Loading RFR model from {MODEL_PATH}...")
    if not os.path.exists(MODEL_PATH):
        log(f"Error: Model not found at {MODEL_PATH}")
        return

    # Use exactly the app's feature order, category maps, VPD and model mean.
    # A separate hand-built vector or tree-quantile range can hide integration bugs.
    predictor = SpoilagePredictor()
    predictor._configure_artifact(joblib.load(MODEL_PATH))
    log(f"Model expects {predictor._n_features} features; results are model means")

    conditions = [
        {"label": "Matrix ref", "temp": 31.0, "hum": 60.8},
        {"label": "Station", "temp": 36.4, "hum": 52.6},
        {"label": "Cool/Humid", "temp": 26.5, "hum": 92.0},
        {"label": "Typical PH", "temp": 31.0, "hum": 77.0},
        {"label": "Hot/Dry", "temp": 33.0, "hum": 72.0},
    ]
    
    cultivars = {0: 'Lakatan', 1: 'Latundan', 2: 'Cardaba'}
    ripeness = {0: 'Unripe', 1: 'Semi-Ripe', 2: 'Ripe', 3: 'Overripe'}
    treatments = {0: 'Natural', 1: 'Ethephon'}

    results = []
    
    log("\n" + "="*95)
    log(f"{'Cultivar':10s} | {'Ripeness':10s} | {'Treatment':10s} | {'Condition':12s} | {'Temp / RH':12s} => {'Shelf Life'}")
    log("-" * 95)

    for c in [0, 1, 2]:
        for r in [0, 1, 2, 3]:
            for t in [0, 1]:
                for cond in conditions:
                    try:
                        mean = predictor.predict(
                            cultivars[c], ripeness[r].replace("-", " "),
                            cond["temp"], cond["hum"], treatment=treatments[t],
                        )
                        days = f"{mean} days"
                            
                    except Exception as e:
                        days = f"Error: {e}"
                        
                    results.append({
                        "cultivar": c,
                        "ripeness": r,
                        "treatment": t,
                        "condition": cond["label"],
                        "predicted_days": days
                    })
                    
                    env_str = f"{cond['temp']}°C / {cond['hum']}%"
                    log(f"{cultivars[c]:10s} | {ripeness[r]:10s} | {treatments[t]:10s} | {cond['label']:12s} | {env_str:12s} => {days}")
            
            log("-" * 95)  # Separator for each Ripeness stage

    log("="*95)
    log(f"Total Tests: {len(results)}")

    # Save to text file
    timestamp = now_manila().strftime("%Y%m%d_%H%M%S")
    out_file = f"matrix_results_{timestamp}.txt"
    with open(out_file, "w") as f:
        f.write("\n".join(output_lines))
        
    print(f"\n✅ Detailed matrix test saved to {out_file}")

if __name__ == "__main__":
    run_matrix_test()
