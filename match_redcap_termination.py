#!/usr/bin/env python3
import os
import csv
import requests
import argparse
import sys
from typing import Tuple, List, Dict

try:
    import pandas as pd
except Exception:
    pd = None

# Defaults (can be overridden via env or CLI)
REDCAP_API_TOKEN = os.environ.get('REDCAP_API_TOKEN', 'B40BBD579D769085375A5179F942F093')
REDCAP_API_URL = os.environ.get('REDCAP_API_URL', 'https://population.ahri.org/api/')
CSV_INPUT_PATH_DEFAULT = os.path.join('data', 'output1.csv')
CSV_OUTPUT_PATH_DEFAULT = os.path.join('data', 'matched_output.csv')
CSV_MATCH_COLUMN_DEFAULT = 'record'


def get_redcap_termination_data(token: str, url: str) -> Dict[str, Dict[str, str]]:
    payload = {
        'token': token,
        'content': 'record',
        'action': 'export',
        'format': 'json',
        'type': 'flat',
        'fields[0]': 'record_id',
        'fields[1]': 'termination_date',
        'fields[2]': 'dod',
        'events[0]': 'termination_arm_1',
        'rawOrLabel': 'raw',
        'rawOrLabelHeaders': 'raw',
        'exportCheckboxLabel': 'false',
        'exportSurveyFields': 'false',
        'exportDataAccessGroups': 'false',
        'returnFormat': 'json'
    }

    try:
        resp = requests.post(url, data=payload, timeout=30)
        resp.raise_for_status()
        records = resp.json()
    except Exception as e:
        print('Warning: could not fetch REDCap data:', e)
        return {}

    lookup = {}
    for rec in records:
        rid = rec.get('record_id', '').strip()
        if rid:
            lookup[rid] = {
                'termination_date': rec.get('termination_date', ''),
                'dod': rec.get('dod', '')
            }
    return lookup


def match_csv_with_redcap(redcap_lookup: Dict[str, Dict[str, str]],
                          input_path: str,
                          match_column: str) -> Tuple[List[Dict[str, str]], List[str], int]:
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"CSV not found: {input_path}")

    matched_rows = []
    unmatched_count = 0

    with open(input_path, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        original_fieldnames = reader.fieldnames or []

        for row in reader:
            record_id = row.get(match_column, '').strip()
            redcap_data = redcap_lookup.get(record_id)

            if redcap_data:
                row['termination_date'] = redcap_data.get('termination_date', '')
                row['dod'] = redcap_data.get('dod', '')
                row['matched'] = 'Y'
            else:
                row['termination_date'] = ''
                row['dod'] = ''
                row['matched'] = 'N'
                unmatched_count += 1

            matched_rows.append(row)

    output_fieldnames = original_fieldnames + ['termination_date', 'dod', 'matched']
    return matched_rows, output_fieldnames, unmatched_count


def main(argv=None):
    parser = argparse.ArgumentParser(description='Match local CSV rows with REDCap termination/dod fields')
    parser.add_argument('--input', '-i', default=CSV_INPUT_PATH_DEFAULT, help='Input CSV path')
    parser.add_argument('--output', '-o', default=CSV_OUTPUT_PATH_DEFAULT, help='Output CSV path')
    parser.add_argument('--token', '-t', default=REDCAP_API_TOKEN, help='REDCap API token')
    parser.add_argument('--url', '-u', default=REDCAP_API_URL, help='REDCap API URL')
    parser.add_argument('--column', '-c', default=CSV_MATCH_COLUMN_DEFAULT, help='CSV column to match on')
    parser.add_argument('--only-fetch', action='store_true', help='Fetch REDCap data only and save to CSV')

    args = parser.parse_args(argv)

    # If user wants only REDCap data, fetch and write minimal export
    if args.only_fetch:
        if not args.token:
            print("No REDCap token provided. Use --token to provide a valid token.")
            return 1

        redcap_lookup = get_redcap_termination_data(args.token, args.url)

        out_dir = os.path.dirname(args.output)
        if out_dir and not os.path.exists(out_dir):
            os.makedirs(out_dir, exist_ok=True)

        # write REDCap export rows to CSV with simple headers
        with open(args.output, 'w', newline='', encoding='utf-8') as out_f:
            fieldnames = ['record_id', 'termination_date', 'dod']
            writer = csv.DictWriter(out_f, fieldnames=fieldnames)
            writer.writeheader()
            for rid, vals in redcap_lookup.items():
                writer.writerow({
                    'record_id': rid,
                    'termination_date': vals.get('termination_date', ''),
                    'dod': vals.get('dod', '')
                })

        print(f"Wrote {len(redcap_lookup)} REDCap rows to {args.output}")
        return 0

    redcap_lookup = {}
    if args.token:
        redcap_lookup = get_redcap_termination_data(args.token, args.url)

    matched_rows, fieldnames, unmatched = match_csv_with_redcap(redcap_lookup, args.input, args.column)

    out_dir = os.path.dirname(args.output)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    with open(args.output, 'w', newline='', encoding='utf-8') as out_f:
        writer = csv.DictWriter(out_f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(matched_rows)

    total = len(matched_rows)
    matched = total - unmatched
    print(f"Wrote {total} rows ({matched} matched, {unmatched} unmatched) to {args.output}")

    if pd is not None:
        try:
            df = pd.DataFrame(matched_rows)
            print(df.head(10))
        except Exception:
            pass


if __name__ == '__main__':
    main()
