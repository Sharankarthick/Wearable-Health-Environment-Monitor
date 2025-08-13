# save as run_model.py
import os
import sys
import signal
import time
from edge_impulse_linux.runner import ImpulseRunner

runner = None

def signal_handler(sig, frame):
    print('Interrupted')
    if (runner):
        runner.stop()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

def main(model_path, features_file=None):
    global runner
    
    # If features file is provided, use it
    if features_file:
        with open(features_file, 'r') as f:
            features = f.read().strip().split(",")
            if '0x' in features[0]:
                features = [float(int(f, 16)) for f in features]
            else:
                features = [float(f) for f in features]
    
    print('MODEL: ' + model_path)
    
    runner = ImpulseRunner(model_path)
    try:
        model_info = runner.init()
        print('Loaded runner for "' + model_info['project']['owner'] + ' / ' + model_info['project']['name'] + '"')
        
        if features_file:
            # Classify with provided features
            res = runner.classify(features)
            print("classification:")
            print(res["result"])
            print("timing:")
            print(res["timing"])
        else:
            # Just print model info
            print("Model information:")
            print(f"Project: {model_info['project']['name']}")
            print(f"Description: {model_info['project'].get('description', 'No description')}")
            print(f"Model type: {model_info.get('model_parameters', {}).get('model_type', 'Unknown')}")
            
    finally:
        if (runner):
            runner.stop()

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python run_model.py <model_path> [features_file]")
        sys.exit(1)
    
    model_path = sys.argv[1]
    features_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    main(model_path, features_file)