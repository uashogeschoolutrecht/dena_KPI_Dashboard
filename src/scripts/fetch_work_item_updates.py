"""
Azure DevOps Work Item Updates Fetcher

Given one or more Work Item IDs, fetches the full update/revision history
(field changes over time, including state transitions) for each work item
from the Azure DevOps REST API:

    GET https://dev.azure.com/{organization}/{project}/_apis/wit/workItems/{id}/updates?api-version=7.1

Requirements:
- Azure DevOps PAT with 'Work Items: Read' permission
- Environment variable AZURE_API set in .env file
- Dependencies: requests, python-dotenv

Output:
- JSON file in azure_devops_data/ directory containing the raw updates
  for each requested work item, keyed by work item ID.

Usage:
    python fetch_work_item_updates.py 1234 1235 1236
"""

import argparse
import base64
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

# Load environment variables from .env file
env_path = Path(__file__).parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

# Get API key from environment
AZURE_API_KEY = os.getenv('AZURE_API')

# Azure DevOps configuration
ORGANIZATION = 'HogeschoolUtrecht'
PROJECT = 'DevOps DenA'
API_VERSION = '7.1'

# Base URL for Azure DevOps REST API (organization level)
BASE_URL = f'https://dev.azure.com/{ORGANIZATION}'


def get_auth_header():
    """Create authentication header using Personal Access Token.

    Returns:
        dict: HTTP headers for authentication.

    Raises:
        ValueError: If AZURE_API_KEY is not found in environment variables.
    """
    if not AZURE_API_KEY:
        raise ValueError("AZURE_API key not found in .env file")

    credentials = f':{AZURE_API_KEY}'
    encoded_credentials = base64.b64encode(credentials.encode()).decode()

    return {
        'Authorization': f'Basic {encoded_credentials}',
        'Content-Type': 'application/json',
        'User-Agent': 'Python-Azure-DevOps-Client/1.0'
    }


def get_work_item_updates(work_item_id, max_retries=3):
    """Fetch the update/revision history for a single work item.

    Args:
        work_item_id (int): The Work Item ID to fetch updates for.
        max_retries (int): Maximum number of retry attempts (default: 3).

    Returns:
        list: List of update dictionaries as returned by the Azure DevOps API,
            or an empty list if the request ultimately fails.
    """
    url = (
        f'{BASE_URL}/{PROJECT}/_apis/wit/workItems/{work_item_id}/updates'
        f'?api-version={API_VERSION}'
    )

    print(f"Fetching updates for work item {work_item_id}...")
    print(f"  URL: {url}")

    for attempt in range(max_retries):
        try:
            print(f"  Attempt {attempt + 1}/{max_retries}...")

            session = requests.Session()
            session.headers.update(get_auth_header())

            response = session.get(url, timeout=30)
            response.raise_for_status()

            data = response.json()
            updates = data.get('value', [])
            print(f"  ✓ Retrieved {len(updates)} update(s) for work item {work_item_id}")
            return updates

        except requests.exceptions.HTTPError as e:
            print(f"  ✗ HTTP error: {e}")
            if response.status_code == 404:
                print(f"    Work item {work_item_id} not found in project '{PROJECT}'")
                break
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                print(f"    Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
        except requests.exceptions.RequestException as e:
            print(f"  ✗ Request error: {type(e).__name__}: {e}")
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                print(f"    Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
        finally:
            session.close()

    print(f"  ✗ Failed to fetch updates for work item {work_item_id} after {max_retries} attempts")
    return []


def get_updates_for_work_items(work_item_ids):
    """Fetch updates for multiple work items.

    Args:
        work_item_ids (list[int]): List of Work Item IDs.

    Returns:
        dict: Mapping of work item ID (str) to its list of updates.
    """
    results = {}
    for idx, work_item_id in enumerate(work_item_ids):
        results[str(work_item_id)] = get_work_item_updates(work_item_id)

        # Avoid hammering the API
        if idx < len(work_item_ids) - 1:
            time.sleep(0.5)

    return results


def save_updates_to_json(updates_by_id):
    """Save fetched work item updates to a timestamped JSON file.

    Args:
        updates_by_id (dict): Mapping of work item ID to list of updates.

    Returns:
        Path: Path to the saved JSON file.
    """
    output_dir = Path(__file__).parent.parent.parent / 'azure_devops_data'
    output_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d')
    output_file = output_dir / f'work_item_updates_{timestamp}.json'

    output_data = {
        'metadata': {
            'fetch_date': datetime.now().isoformat(),
            'organization': ORGANIZATION,
            'project': PROJECT,
            'work_item_ids': list(updates_by_id.keys()),
        },
        'updates': updates_by_id,
    }

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print(f"\n✓ Saved updates to {output_file}")
    return output_file


def main():
    parser = argparse.ArgumentParser(
        description="Fetch Azure DevOps work item state update history for one or more Work Item IDs."
    )
    parser.add_argument(
        'work_item_ids',
        nargs='+',
        type=int,
        help="One or more Work Item IDs to fetch updates for."
    )
    args = parser.parse_args()

    print("=" * 60)
    print("AZURE DEVOPS WORK ITEM UPDATES FETCHER")
    print("=" * 60)
    print(f"Organization: {ORGANIZATION}")
    print(f"Project: {PROJECT}")
    print(f"Work Item IDs: {args.work_item_ids}")
    print("=" * 60)

    try:
        get_auth_header()
    except ValueError as e:
        print(f"\n✗ {e}")
        sys.exit(1)

    updates_by_id = get_updates_for_work_items(args.work_item_ids)
    save_updates_to_json(updates_by_id)


if __name__ == '__main__':
    main()
