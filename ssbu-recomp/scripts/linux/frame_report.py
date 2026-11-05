"""Summarize SSBU_VK_FRAMECSV, including the entrance frames omitted by the old report."""
import argparse
import csv
import json
import math
import statistics


def summarize(rows):
    result = {'frames': len(rows), 'over_20_ms': sum(float(r['wall_ms']) > 20 for r in rows)}
    for field in ('wall_ms', 'gpu_ms', 'replay_ms', 'gpu_wait_ms', 'pipeline_ms'):
        values = sorted(float(r[field]) for r in rows if r.get(field, '') != '')
        result[field] = None if not values else {
            'samples': len(values), 'median': statistics.median(values),
            'p99': values[max(0, math.ceil(len(values) * .99) - 1)], 'max': values[-1],
        }
    return result


def report(rows, intro_frames=420):
    if intro_frames < 1:
        raise ValueError('intro_frames must be positive')
    battle = [r for r in rows if r['fighters'] == '1']
    return {'all': summarize(rows), 'entrance': summarize(battle[:intro_frames]),
            'after_entrance': summarize(battle[intro_frames:]),
            'entrance_definition': 'first %d frames with compute dispatches and more than 120 draws' % intro_frames}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('csv')
    ap.add_argument('--intro-frames', type=int, default=420)
    args = ap.parse_args()
    if args.intro_frames < 1:
        ap.error('--intro-frames must be positive')
    with open(args.csv, newline='') as stream:
        result = report(list(csv.DictReader(stream)), args.intro_frames)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
