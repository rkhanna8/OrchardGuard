"""Optional receiver context; never changes the estimator's GPS validity."""
import csv
from bisect import bisect_right
from pathlib import Path

FIELDS = ('num_sat', 'rtk_mode_fix', 'fix_mode', 'system_error', 'io_error',
          'swift_nap_error', 'external_antenna_present')


def load_diagnostics(path):
    if not path or not Path(path).is_file():
        return [], []
    with open(path, newline='') as stream:
        rows = list(csv.DictReader(stream))
    return parse_diagnostics(rows)


def parse_diagnostics(rows):
    samples = []
    for row in rows:
        sample = {k: (row[k] if k == 'fix_mode' else int(row[k])) for k in FIELDS}
        sample['time'] = int(row['bag_time_ns']) * 1e-9
        samples.append(sample)
    samples.sort(key=lambda s: s['time'])
    return [s['time'] for s in samples], samples


def latest_diagnostics(data, timestamp, max_age=2.0):
    times, samples = data
    index = bisect_right(times, timestamp) - 1
    if index < 0:
        return {'available': False, 'reason': 'missing', 'age_s': None}
    age = timestamp - times[index]
    if age > max_age:
        return {'available': False, 'reason': 'stale', 'age_s': age}
    return {**samples[index], 'available': True, 'age_s': age}


def extract(bag, output):
    # Optional dependency, not needed to run a sensor ZIP.
    from rosbags.rosbag1 import Reader
    from rosbags.typesys import Stores, get_typestore, get_types_from_msg
    store = get_typestore(Stores.ROS1_NOETIC)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with Reader(Path(bag)) as reader:
        connections = [c for c in reader.connections if c.topic == '/piksi/debug/receiver_state']
        if not connections:
            raise ValueError('Receiver state topic is absent')
        for c in connections:
            store.register(get_types_from_msg(c.msgdef.data, c.msgtype))
        count = 0
        with output.open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=('bag_time_ns', *FIELDS))
            writer.writeheader()
            for connection, timestamp, raw in reader.messages(connections=connections):
                msg = store.deserialize_ros1(raw, connection.msgtype)
                writer.writerow({'bag_time_ns': timestamp, **{
                    k: str(getattr(msg, k)) if k == 'fix_mode' else int(getattr(msg, k)) for k in FIELDS}})
                count += 1
    return count


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bag')
    parser.add_argument('--output', default='data/receiver_state.csv')
    args = parser.parse_args()
    print(f'Extracted {extract(args.bag, args.output)} samples to {args.output}')
