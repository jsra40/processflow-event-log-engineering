import argparse, json
from pipeline.runner import run_project

if __name__=='__main__':
    ap=argparse.ArgumentParser(description='Run ProcessFlow Event Log Pipeline')
    ap.add_argument('config',help='Path to project YAML')
    args=ap.parse_args()
    result=run_project(args.config)
    print(json.dumps(result,indent=2,default=str))
